"""Smoke tests: every dashboard page renders (before and after a scan) and a scan can be run from the Scan Folder page."""
import os
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from conftest import edit_text, make_text, photo_like, write_docx
from scanner import run_scan

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")
PAGES = ["Overview", "Scan Folder", "Storage Comparison", "Documents", "Images", "Videos", "Duplicate Groups",
         "Similarity Explorer", "Analytics", "Optimization", "Accuracy", "Performance", "Scan History", "Settings"]


@pytest.fixture
def sample(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(tmp_path)                       # scan_history.json is written to the working directory
    base = make_text(300)
    write_docx(work / "Report_v1.docx", base)
    write_docx(work / "Report_v2.docx", edit_text(base, 0.05))
    shutil.copy(work / "Report_v1.docx", work / "Report_copy.docx")
    write_docx(work / "Other.docx", make_text(300, seed=9))
    photo_like(1).save(work / "pic.png")
    photo_like(1).resize((100, 100)).save(work / "pic_small.png")
    (work / "empty.txt").write_bytes(b"")
    (work / "broken.docx").write_bytes(b"junk")
    return str(work)


def state_from(result):
    return dict(scanned=True, scan_folder=result.folder, all_files=result.files, exact_groups=result.exact_groups,
                text_pairs=result.text_pairs, image_pairs=result.image_pairs, video_pairs=result.video_pairs,
                scan_warnings=result.warnings, empty_files=result.empty_files, last_scan_time="2026-11-02 12:00")


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_scan(page, sample):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [e.value[:300] for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_after_scan(page, sample):
    result = run_scan(sample)
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in state_from(result).items():
        at.session_state[k] = v
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [e.value[:300] for e in at.exception]


def test_scan_from_the_scan_folder_page(sample):
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["page"] = "Scan Folder"
    at.run()
    at.text_input(key="scan_path_local").set_value(sample)
    at.run()
    start = [b for b in at.button if "START ANALYSIS" in b.label][0]
    start.click()
    at.run()
    assert not at.exception, [e.value[:300] for e in at.exception]
    assert at.session_state["scanned"] is True
    assert len(at.session_state["exact_groups"]) == 1
    assert len(at.session_state["scan_warnings"]) == 1
    assert at.session_state["page"] == "Overview"

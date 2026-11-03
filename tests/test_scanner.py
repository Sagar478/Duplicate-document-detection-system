import os
import shutil

from conftest import edit_text, make_text, photo_like, write_docx
from file_utils import REVIEW_FOLDER_NAME
from scanner import run_scan, without_exact_copies


def build_folder(root):
    base = make_text(300)
    write_docx(root / "Report_v1.docx", base)
    write_docx(root / "Report_v2.docx", edit_text(base, 0.05))
    shutil.copy(root / "Report_v1.docx", root / "Report_copy.docx")                 # exact copy
    write_docx(root / "Other.docx", make_text(300, seed=9))
    photo_like(1).save(root / "pic.png")
    photo_like(1).resize((120, 120)).save(root / "pic_small.png")
    shutil.copy(root / "pic.png", root / "pic_copy.png")                            # exact copy of an image
    (root / "empty.txt").write_bytes(b"")
    (root / "broken.docx").write_bytes(b"junk")
    (root / "~$Report_v1.docx").write_bytes(b"lock")


def test_full_scan_counts(tmp_path):
    build_folder(tmp_path)
    r = run_scan(str(tmp_path), run_videos=False)
    assert len(r.files) == 9                                   # lock file ignored
    assert len(r.exact_groups) == 2                            # Report_v1/copy and pic/pic_copy
    # near pairs never repeat an exact copy: v1~v2 and copy~v2 are real near pairs, v1~copy is not one
    text_names = {frozenset(os.path.basename(x) for x in p[:2]) for p in r.text_pairs}
    assert frozenset(("Report_v1.docx", "Report_copy.docx")) not in text_names
    assert frozenset(("Report_v1.docx", "Report_v2.docx")) in text_names
    assert len(r.groups()) == 2                                # the three reports, the three pictures
    assert [os.path.basename(p) for p in r.empty_files] == ["empty.txt"]
    assert [os.path.basename(p) for p, _ in r.warnings] == ["broken.docx"]


def test_scan_is_repeatable(tmp_path):
    build_folder(tmp_path)
    a, b = run_scan(str(tmp_path), run_videos=False), run_scan(str(tmp_path), run_videos=False)
    assert a.exact_groups == b.exact_groups and a.text_pairs == b.text_pairs and a.image_pairs == b.image_pairs


def test_review_folder_is_not_scanned_again(tmp_path):
    build_folder(tmp_path)
    review = tmp_path / REVIEW_FOLDER_NAME
    review.mkdir()
    shutil.copy(tmp_path / "Report_v1.docx", review / "Report_v1.docx")
    r = run_scan(str(tmp_path), run_videos=False)
    assert not any(REVIEW_FOLDER_NAME in f for f in r.files)
    assert len(r.exact_groups) == 2


def test_progress_callback_and_options(tmp_path):
    build_folder(tmp_path)
    stages = []
    r = run_scan(str(tmp_path), run_text=False, run_images=False, run_videos=False,
                 progress=lambda stage, frac, msg: stages.append(stage))
    assert r.text_pairs == [] and r.image_pairs == [] and len(r.exact_groups) == 2
    assert "exact" in stages and stages[-1] == "done"


def test_empty_folder(tmp_path):
    r = run_scan(str(tmp_path))
    assert r.files == [] and r.exact_groups == [] and r.near_pairs == [] and r.groups() == []


def test_without_exact_copies():
    pairs = [("a", "b", 1.0), ("a", "c", .8)]
    assert without_exact_copies(pairs, [["a", "b"]]) == [("a", "c", .8)]

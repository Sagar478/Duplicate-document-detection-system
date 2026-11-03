import os

import pytest

from conftest import edit_text, make_text, write_docx, write_pdf
from near_duplicate_text import (SIMILARITY_THRESHOLD, _could_reach_threshold, _shingles, calculate_similarity,
                                 find_near_duplicate_texts, load_texts)
from text_extractor import extract_text, is_text_file


def test_extracts_docx_paragraphs_and_table_text(tmp_path):
    p = tmp_path / "a.docx"
    write_docx(p, "First paragraph\nSecond paragraph", table=[["Item", "Cost"], ["Pens", "10"]])
    text = extract_text(str(p))
    assert "First paragraph" in text and "Second paragraph" in text
    assert "Pens | 10" in text


def test_extracts_pdf_and_txt(tmp_path):
    write_pdf(tmp_path / "a.pdf", "quarterly report about the budget")
    (tmp_path / "b.txt").write_text("plain text file", encoding="utf-8")
    assert "quarterly report" in extract_text(str(tmp_path / "a.pdf"))
    assert extract_text(str(tmp_path / "b.txt")) == "plain text file"
    assert extract_text(str(tmp_path / "c.xyz")) is None
    assert is_text_file("X.DOCX") and not is_text_file("x.png")


def test_corrupt_documents_are_reported_and_do_not_stop_the_scan(tmp_path):
    base = make_text(120)
    write_docx(tmp_path / "good1.docx", base)
    write_docx(tmp_path / "good2.docx", base + " one more sentence")
    (tmp_path / "broken.docx").write_bytes(b"this is not a zip file")
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    errors = []
    pairs = find_near_duplicate_texts(str(tmp_path), errors=errors)
    assert len(pairs) == 1
    assert {os.path.basename(p) for p, _ in errors} == {"broken.docx", "broken.pdf"}


def test_word_lock_files_are_ignored_by_the_scanner(tmp_path):
    from file_utils import list_files
    write_docx(tmp_path / "a.docx", "hello")
    (tmp_path / "~$a.docx").write_bytes(b"lock")
    assert [os.path.basename(p) for p in list_files(str(tmp_path))] == ["a.docx"]


def test_document_without_text_is_reported(tmp_path):
    write_docx(tmp_path / "blank.docx", "")
    errors = []
    assert load_texts(str(tmp_path), errors=errors) == {}
    assert "no extractable text" in errors[0][1]


def test_heavily_edited_copy_is_still_found():
    """Regression: with SequenceMatcher's default autojunk a 1/3-rewritten 11,000-character text scored 5%."""
    base = make_text(1500)
    edited = edit_text(base, 0.25)
    assert calculate_similarity(base, edited) > 0.6


def test_status_report_style_pair_scores_above_threshold(tmp_path):
    v1 = ("Status report. Project is on schedule. The team completed the login module and started testing. "
          "Budget is within limits. Risks: two developers are on leave next month. Next steps: finish testing, "
          "prepare the demo, and update the user guide for release.")
    v2 = ("Status update. The project remains on schedule. The login module is complete and testing has begun. "
          "Spending is within budget. Risk: two developers will be on leave next month. Next: finish testing, "
          "prepare the demo and update the user guide before release.")
    write_docx(tmp_path / "Status_v1.docx", v1)
    write_docx(tmp_path / "Status_v2.docx", v2)
    pairs = find_near_duplicate_texts(str(tmp_path))
    assert len(pairs) == 1 and pairs[0][2] >= SIMILARITY_THRESHOLD


def test_unrelated_documents_are_not_reported(tmp_path):
    write_docx(tmp_path / "a.docx", make_text(300, seed=1))
    write_docx(tmp_path / "b.docx", make_text(300, seed=2))
    assert find_near_duplicate_texts(str(tmp_path)) == []


def test_identical_text_scores_one_and_empty_is_safe():
    assert calculate_similarity("same", "same") == 1.0
    assert calculate_similarity("", "text") == 0.0


@pytest.mark.parametrize("fraction", [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3])
@pytest.mark.parametrize("seed", range(4))
def test_prefilter_never_discards_a_pair_the_full_algorithm_would_report(fraction, seed):
    """The quick pre-filter is only allowed to remove pairs that would not reach the threshold anyway."""
    base = make_text(250, seed=seed)
    edited = edit_text(base, fraction, seed=seed + 100)
    sim = calculate_similarity(base, edited)
    kept = _could_reach_threshold(base, edited, _shingles(base), _shingles(edited), SIMILARITY_THRESHOLD)
    if sim >= SIMILARITY_THRESHOLD:
        assert kept, f"pre-filter dropped a pair with similarity {sim:.2f}"


def test_threshold_can_be_overridden(tmp_path):
    base = make_text(200)
    write_docx(tmp_path / "a.docx", base)
    write_docx(tmp_path / "b.docx", edit_text(base, 0.4))
    assert find_near_duplicate_texts(str(tmp_path), threshold=0.99) == []
    assert len(find_near_duplicate_texts(str(tmp_path), threshold=0.3)) == 1

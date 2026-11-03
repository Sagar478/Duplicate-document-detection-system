import os
import time

from conftest import write_docx
from version_recommender import group_related_files, recommend_latest_version


def test_pair_that_links_two_groups_merges_them():
    groups = group_related_files([("a", "b", .9), ("c", "d", .9), ("b", "c", .9)])
    assert groups == [{"a", "b", "c", "d"}]


def test_separate_groups_stay_separate_and_input_order_does_not_matter():
    pairs = [("a", "b", 1), ("c", "d", 1), ("e", "f", 1)]
    assert sorted(map(sorted, group_related_files(pairs))) == [["a", "b"], ["c", "d"], ["e", "f"]]
    assert sorted(map(sorted, group_related_files(pairs[::-1]))) == [["a", "b"], ["c", "d"], ["e", "f"]]


def test_newest_file_is_recommended(tmp_path):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text("report"); new.write_text("report")
    os.utime(old, (1_600_000_000, 1_600_000_000)); os.utime(new, (1_700_000_000, 1_700_000_000))
    assert recommend_latest_version([str(old), str(new)]) == str(new)


def test_longer_text_wins_when_saved_at_the_same_time(tmp_path):
    short, long_ = tmp_path / "a.txt", tmp_path / "b.txt"
    short.write_text("short"); long_.write_text("short " * 5000)
    os.utime(short, (1_700_000_000, 1_700_000_000)); os.utime(long_, (1_700_000_000, 1_700_000_000))
    assert recommend_latest_version([str(short), str(long_)]) == str(long_)


def test_deleted_file_is_ignored_and_result_is_deterministic(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"x"); b.write_bytes(b"x")
    os.utime(a, (1_700_000_000, 1_700_000_000)); os.utime(b, (1_700_000_000, 1_700_000_000))
    assert recommend_latest_version([str(a), str(b), str(tmp_path / "gone.png")]) == recommend_latest_version([str(b), str(a)])
    assert recommend_latest_version([str(tmp_path / "gone.png")]) is None


def test_unreadable_document_does_not_stop_recommendation(tmp_path):
    bad = tmp_path / "bad.docx"; bad.write_bytes(b"junk")
    good = tmp_path / "good.docx"; write_docx(good, "text")
    os.utime(good, (1_800_000_000, 1_800_000_000))
    assert recommend_latest_version([str(bad), str(good)]) == str(good)

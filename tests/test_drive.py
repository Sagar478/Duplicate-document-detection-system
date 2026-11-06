import os
from datetime import datetime, timezone

import pytest

import google_drive_connector as gdc


def test_extract_folder_id():
    assert gdc.extract_folder_id("1AbC_dEf-123") == "1AbC_dEf-123"
    assert gdc.extract_folder_id("https://drive.google.com/drive/folders/1AbC_dEf-123?usp=sharing") == "1AbC_dEf-123"
    assert gdc.extract_folder_id("https://drive.google.com/open?id=1AbC_dEf-123") == "1AbC_dEf-123"
    assert gdc.extract_folder_id("  ") == ""


def test_safe_names_and_unique_paths(tmp_path):
    assert gdc.safe_local_name('Plan: 2026/v2?.docx') == "Plan_ 2026_v2_.docx"
    assert gdc.safe_local_name("CON.txt") == "_CON.txt"
    assert gdc.safe_local_name("name. ") == "name"
    used = set()
    p1 = gdc.unique_local_path(str(tmp_path), "Report.docx", used)
    p2 = gdc.unique_local_path(str(tmp_path), "report.docx", used)      # Windows ignores case
    p3 = gdc.unique_local_path(str(tmp_path), "Report.docx", used)
    assert len({p1.lower(), p2.lower(), p3.lower()}) == 3


class FakeRequest:
    def __init__(self, data): self.data = data


class FakeFiles:
    def __init__(self, items, contents): self.items, self.contents = items, contents
    def list(self, **kw): return type("R", (), {"execute": lambda s, items=self.items: {"files": items}})()
    def get_media(self, fileId): return FakeRequest(self.contents[fileId])


class FakeService:
    def __init__(self, items, contents): self._f = FakeFiles(items, contents)
    def files(self): return self._f


@pytest.fixture
def fake_download(monkeypatch):
    def fake(service, file_id, local_path, on_progress=None):
        with open(local_path, "wb") as fh:
            fh.write(service.files().contents[file_id])
        if on_progress:
            on_progress(1.0)
        return local_path
    monkeypatch.setattr(gdc, "download_file", fake)


def make_items():
    mod = "2026-03-01T10:00:00.000Z"
    return ([
        {"id": "1", "name": "Report.docx", "mimeType": "application/x", "size": "5", "modifiedTime": mod, "owners": [{"emailAddress": "a@x.com"}]},
        {"id": "2", "name": "Report.docx", "mimeType": "application/x", "size": "5", "modifiedTime": "2026-04-01T10:00:00.000Z", "owners": [{"emailAddress": "b@x.com"}]},
        {"id": "3", "name": "Huge.mp4", "mimeType": "video/mp4", "size": str(2000 * 1024 * 1024), "modifiedTime": mod, "owners": []},
        {"id": "4", "name": "Sheet", "mimeType": "application/vnd.google-apps.spreadsheet", "modifiedTime": mod, "owners": []},
        {"id": "5", "name": "Sub", "mimeType": "application/vnd.google-apps.folder", "modifiedTime": mod, "owners": []},
        {"id": "6", "name": "bad:name?.txt", "mimeType": "text/plain", "size": "3", "modifiedTime": mod, "owners": []},
    ], {"1": b"AAAAA", "2": b"BBBBB", "3": b"", "6": b"abc"})


def test_sync_keeps_same_named_files_sets_dates_and_reports_skips(tmp_path, fake_download):
    items, contents = make_items()
    target = tmp_path / "drive_downloads"
    paths = gdc.sync_drive_folder_to_local("folder", str(target), max_size_mb=500, service=FakeService(items, contents))
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ["Report (2).docx", "Report.docx", "bad_name_.txt"]
    assert open(target / "Report.docx", "rb").read() == b"AAAAA" and open(target / "Report (2).docx", "rb").read() == b"BBBBB"
    first = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    assert abs(os.path.getmtime(target / "Report.docx") - first) < 1
    assert gdc.LAST_SKIPPED == [("Huge.mp4", 2000 * 1024 * 1024)]
    assert {n for n, _ in gdc.LAST_NOT_DOWNLOADED} == {"Sheet", "Sub"}


def test_sync_report_gives_each_call_its_own_lists(tmp_path, fake_download):
    """Hosted mode: two visitors syncing at the same time must not see each other's skipped files."""
    items, contents = make_items()
    first, second = {}, {}
    gdc.sync_drive_folder_to_local("f", str(tmp_path / "a" / "drive_downloads"), max_size_mb=500,
                                   service=FakeService(items, contents), report=first)
    gdc.sync_drive_folder_to_local("f", str(tmp_path / "b" / "drive_downloads"), max_size_mb=None,
                                   service=FakeService(items, contents), report=second)
    assert first["skipped"] == [("Huge.mp4", 2000 * 1024 * 1024)]
    assert second["skipped"] == []
    assert {n for n, _ in first["not_downloaded"]} == {"Sheet", "Sub"}


def test_online_download_limit_defaults_to_100_mb(monkeypatch):
    monkeypatch.delenv("DOCDETECT_MAX_DOWNLOAD_MB", raising=False)
    assert gdc.max_online_download_mb() == 100
    monkeypatch.setenv("DOCDETECT_MAX_DOWNLOAD_MB", "250")
    assert gdc.max_online_download_mb() == 250


def test_owner_filter(tmp_path, fake_download):
    items, contents = make_items()
    paths = gdc.sync_drive_folder_to_local("f", str(tmp_path / "drive_downloads"), owner_email_filter="b@x.com",
                                           service=FakeService(items, contents))
    assert [os.path.basename(p) for p in paths] == ["Report.docx"]
    with pytest.raises(ValueError):
        gdc.sync_drive_folder_to_local("f", str(tmp_path / "d2"), owner_email_filter="nobody@x.com", service=FakeService(items, contents))


def test_refuses_to_empty_a_folder_it_did_not_create(tmp_path, fake_download):
    items, contents = make_items()
    mine = tmp_path / "My Documents"
    mine.mkdir(); (mine / "important.docx").write_bytes(b"precious")
    with pytest.raises(ValueError, match="will not empty it"):
        gdc.sync_drive_folder_to_local("f", str(mine), service=FakeService(items, contents))
    assert (mine / "important.docx").exists()


def test_default_and_own_download_folders_are_emptied_and_reused(tmp_path, fake_download):
    items, contents = make_items()
    legacy = tmp_path / "drive_downloads"                 # created by an older version, has no marker file
    legacy.mkdir(); (legacy / "old.txt").write_bytes(b"old")
    gdc.sync_drive_folder_to_local("f", str(legacy), service=FakeService(items, contents))
    assert not (legacy / "old.txt").exists()
    own = tmp_path / "cache"
    gdc.sync_drive_folder_to_local("f", str(own), service=FakeService(items, contents))
    gdc.sync_drive_folder_to_local("f", str(own), service=FakeService(items, contents))      # marker present, allowed again


def test_empty_folder_message(tmp_path, fake_download):
    with pytest.raises(ValueError, match="No files found"):
        gdc.sync_drive_folder_to_local("f", str(tmp_path / "drive_downloads"), service=FakeService([], {}))

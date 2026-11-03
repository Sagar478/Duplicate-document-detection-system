"""Online (deployed) mode: per-visitor Google sign-in, private temporary folders, nothing saved to disk."""
import os
import time

import pytest
from streamlit.testing.v1 import AppTest

import google_drive_connector as gdc

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")
PAGES = ["Overview", "Scan Folder", "Storage Comparison", "Documents", "Images", "Videos", "Duplicate Groups",
         "Similarity Explorer", "Analytics", "Optimization", "Accuracy", "Performance", "Scan History", "Settings"]


@pytest.fixture
def online_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCDETECT_ONLINE", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("DOCDETECT_REDIRECT_URI", "https://docdetect.example.com")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class FakeFlow:
    def __init__(self):
        self.credentials = object()
        self.code = None

    def authorization_url(self, **kwargs):
        assert kwargs.get("access_type") == "online"          # no long-lived refresh token is requested
        return "https://accounts.google.com/o/oauth2/auth?state=abc", "abc"

    def fetch_token(self, code):
        self.code = code


def test_online_flag(monkeypatch):
    monkeypatch.delenv("DOCDETECT_ONLINE", raising=False)
    assert not gdc.is_online()
    monkeypatch.setenv("DOCDETECT_ONLINE", "1")
    assert gdc.is_online()


def test_login_needs_configuration(monkeypatch):
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "DOCDETECT_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
    assert not gdc.web_login_configured()
    with pytest.raises(RuntimeError, match="not configured"):
        gdc.start_web_login()


def test_start_and_finish_login(monkeypatch, online_env):
    flow = FakeFlow()
    monkeypatch.setattr(gdc, "_web_flow", lambda: flow)
    gdc._PENDING.clear()
    url = gdc.start_web_login()
    assert url.startswith("https://accounts.google.com/")
    creds = gdc.finish_web_login("the-code", "abc")
    assert creds is flow.credentials and flow.code == "the-code"
    with pytest.raises(ValueError, match="expired or was already used"):   # a state value works once only
        gdc.finish_web_login("the-code", "abc")


def test_unknown_or_old_state_is_refused(monkeypatch, online_env):
    gdc._PENDING.clear()
    with pytest.raises(ValueError):
        gdc.finish_web_login("code", "never-issued")
    gdc._PENDING["old"] = (FakeFlow(), time.time() - gdc._PENDING_TTL_SECONDS - 5)
    with pytest.raises(ValueError):
        gdc.finish_web_login("code", "old")


def test_pending_sign_ins_are_limited(monkeypatch, online_env):
    gdc._PENDING.clear()
    monkeypatch.setattr(gdc, "_PENDING_MAX", 3)
    states = iter(f"s{i}" for i in range(10))

    class Flow(FakeFlow):
        def authorization_url(self, **kwargs):
            return "https://accounts.google.com/x", next(states)

    monkeypatch.setattr(gdc, "_web_flow", lambda: Flow())
    for _ in range(6):
        gdc.start_web_login()
    assert len(gdc._PENDING) <= 3


def test_session_folders_are_private_and_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(gdc.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(gdc.tempfile, "mkdtemp", lambda prefix: str(tmp_path / (prefix + "x")) if os.makedirs(str(tmp_path / (prefix + "x")), exist_ok=True) is None else "")
    mine = gdc.new_session_dir()
    assert os.path.isdir(mine) and os.path.basename(mine).startswith(gdc.SESSION_PREFIX)
    other = tmp_path / "someone_elses_documents"
    other.mkdir()
    (other / "keep.txt").write_text("keep")
    gdc.delete_session_dir(str(other))                      # not a DocDetect session folder: must not be touched
    assert (other / "keep.txt").exists()
    old = time.time() - 3 * 3600
    os.utime(mine, (old, old))
    gdc.cleanup_old_session_dirs()
    assert not os.path.exists(mine) and (other / "keep.txt").exists()
    gdc.delete_session_dir(mine)                            # already gone: no error


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_online(page, online_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [e.value[:300] for e in at.exception]
    assert not os.path.exists("scan_history.json")           # nothing is written to disk


def test_scan_page_has_sign_in_and_no_local_folder(online_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = "Scan Folder"
    at.run()
    assert not at.exception
    assert not [r for r in at.radio if r.label == "Source"]
    assert not [t for t in at.text_input if t.label == "Selected folder path"]
    assert any("Sign in with your own Google account" in i.value for i in at.info)
    assert at.session_state["drive_dir"] and os.path.basename(at.session_state["drive_dir"]).startswith(gdc.SESSION_PREFIX)
    assert at.session_state["scan_folder"] == at.session_state["drive_dir"]


def test_failed_callback_shows_an_error_and_returns_to_scan_page(online_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["code"] = "abc"
    at.query_params["state"] = "unknown"
    at.run()
    assert not at.exception
    assert at.session_state["page"] == "Scan Folder"
    assert any("Sign-in failed" in e.value for e in at.error)
    assert "drive_creds" not in at.session_state


def test_not_configured_server_says_so(monkeypatch, online_env):
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = "Scan Folder"
    at.run()
    assert any("not configured" in e.value for e in at.error)


def test_local_mode_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.delenv("DOCDETECT_ONLINE", raising=False)
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = "Scan Folder"
    at.run()
    assert not at.exception
    assert [r for r in at.radio if r.label == "Source"]

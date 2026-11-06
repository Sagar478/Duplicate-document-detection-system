"""Google Drive access (read-only) for DocDetect. Files are downloaded to a local folder and analysed there."""
import io
import os
import re
import shutil
import stat
import tempfile
import threading
import time
from datetime import datetime

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
CACHE_MARKER = ".docdetect_drive_cache"   # written into the download folder so DocDetect only ever empties its own folder

# Filled in by the last sync: files skipped because of the size limit, and items that cannot be downloaded.
LAST_SKIPPED = []            # [(name, size_bytes)] larger than the size limit
LAST_NOT_DOWNLOADED = []     # [(name, reason)] subfolders and native Google Docs/Sheets/Slides (need an export)

_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def extract_folder_id(text):
    """Accept either a bare folder ID or a full Drive URL and return the folder ID."""
    text = (text or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", text) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", text)
    return m.group(1) if m else text


def safe_local_name(name):
    """Make a Drive file name usable on Windows (Drive allows characters such as : ? * that Windows does not)."""
    cleaned = _INVALID_NAME_CHARS.sub("_", name).rstrip(" .") or "unnamed"
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned = "_" + cleaned
    return cleaned


def unique_local_path(download_dir, name, used):
    """Drive lets one folder hold several files with the same name. Save each under its own name instead of
    overwriting, because same-named files are often exactly the duplicates DocDetect is looking for."""
    name = safe_local_name(name)
    base, ext = os.path.splitext(name)
    candidate, n = name, 1
    while candidate.lower() in used:
        n += 1
        candidate = f"{base} ({n}){ext}"
    used.add(candidate.lower())
    return os.path.join(download_dir, candidate)


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # The saved login has expired or was revoked: remove it and ask the user to sign in again.
                os.remove(TOKEN_FILE)
        if not refreshed:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"{CREDENTIALS_FILE} was not found. Create an OAuth client in Google Cloud Console "
                    "(Desktop app) and save its JSON file next to app.py as credentials.json.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id):
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, owners(emailAddress, displayName))",
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def list_owners_in_folder(folder_id, service=None):
    service = service or get_drive_service()
    files = list_files_in_folder(service, extract_folder_id(folder_id))
    owners = {}
    for f in files:
        for owner in f.get("owners", []):
            owners[owner.get("emailAddress", "unknown")] = owner.get("displayName", "Unknown")
    return owners


def download_file(service, file_id, local_path, on_progress=None):
    """Download one file in 8 MB chunks. on_progress(fraction 0..1) is called after every chunk."""
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if on_progress and status is not None:
                on_progress(status.progress())
    return local_path


def _set_modified_time(local_path, modified_time):
    """Give the downloaded file Drive's own 'modified' time. Without this every file would carry the time of the
    download, and the version recommender (which prefers the newest file) would be guessing."""
    try:
        ts = datetime.fromisoformat(modified_time.replace("Z", "+00:00")).timestamp()
        os.utime(local_path, (ts, ts))
    except (ValueError, OSError, AttributeError):
        pass


def _force_remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _prepare_download_dir(local_download_dir):
    """Empty the download folder, but only if it is empty or was created by DocDetect (never someone's documents)."""
    if os.path.exists(local_download_dir):
        marker = os.path.join(local_download_dir, CACHE_MARKER)
        is_default = os.path.basename(os.path.normpath(local_download_dir)).lower() == "drive_downloads"
        if os.listdir(local_download_dir) and not os.path.exists(marker) and not is_default:
            raise ValueError(
                f"'{local_download_dir}' already contains files that DocDetect did not download, so it will not "
                "empty it. Choose an empty folder or a new folder name for the Google Drive download.")
        shutil.rmtree(local_download_dir, onerror=_force_remove_readonly)
    os.makedirs(local_download_dir, exist_ok=True)
    open(os.path.join(local_download_dir, CACHE_MARKER), "w").close()


def sync_drive_folder_to_local(folder_id, local_download_dir, owner_email_filter=None,
                               max_size_mb=None, progress_callback=None, service=None, report=None):
    """Download the files of a Drive folder to a local folder and return their local paths.

    max_size_mb: files larger than this are skipped (None = no limit); they are listed in LAST_SKIPPED and in report["skipped"].
    progress_callback(index, total, file_name, fraction): called while downloading, so the app can show progress.
    Subfolders and native Google Docs/Sheets/Slides are not downloaded; they are listed in LAST_NOT_DOWNLOADED and in report["not_downloaded"].
    """
    global LAST_SKIPPED, LAST_NOT_DOWNLOADED
    skipped, not_downloaded = [], []    # this call's own lists, so two visitors never share them
    LAST_SKIPPED, LAST_NOT_DOWNLOADED = skipped, not_downloaded
    if report is not None:
        report["skipped"], report["not_downloaded"] = skipped, not_downloaded
    folder_id = extract_folder_id(folder_id)

    _prepare_download_dir(local_download_dir)

    service = service or get_drive_service()
    files = list_files_in_folder(service, folder_id)

    if not files:
        raise ValueError("No files found in this Drive folder. This usually means the folder "
                         "hasn't been shared with your authenticated Google account, or the "
                         "folder ID is incorrect.")

    if owner_email_filter:
        files = [f for f in files if any(o.get("emailAddress") == owner_email_filter for o in f.get("owners", []))]
        if not files:
            raise ValueError(f"No files owned by {owner_email_filter} were found in this folder.")

    downloadable = []
    for f in files:
        mime = f.get("mimeType", "")
        if mime == "application/vnd.google-apps.folder":
            not_downloaded.append((f["name"], "subfolder (only the top level of the folder is downloaded)"))
        elif mime.startswith("application/vnd.google-apps"):
            not_downloaded.append((f["name"], "Google Docs/Sheets/Slides file (needs an export)"))
        else:
            downloadable.append(f)

    to_download = []
    for f in downloadable:
        size_bytes = int(f.get("size", 0) or 0)
        if max_size_mb and size_bytes > max_size_mb * 1024 * 1024:
            skipped.append((f["name"], size_bytes))
        else:
            to_download.append(f)

    downloaded_paths, used_names = [], set()
    total = len(to_download)
    for i, f in enumerate(to_download):
        if progress_callback:
            progress_callback(i, total, f["name"], 0.0)
        cb = (lambda frac, i=i, name=f["name"]: progress_callback(i, total, name, frac)) if progress_callback else None
        local_path = unique_local_path(local_download_dir, f["name"], used_names)
        download_file(service, f["id"], local_path, on_progress=cb)
        _set_modified_time(local_path, f.get("modifiedTime"))
        downloaded_paths.append(local_path)
    return downloaded_paths


# ---------------------------------------------------------------------------
# Online (deployed) mode: every visitor signs in with their own Google account through the web OAuth flow.
# Nothing is written to disk: the access token lives only in the visitor's Streamlit session, and downloads go to a
# private temporary folder that is deleted on request or after SESSION_MAX_AGE_HOURS.
# ---------------------------------------------------------------------------
SESSION_PREFIX = "docdetect_session_"
SESSION_MAX_AGE_HOURS = 2
_PENDING = {}                 # state -> (flow, created) for sign-ins that have started but not finished
_PENDING_LOCK = threading.Lock()
_PENDING_TTL_SECONDS = 15 * 60
_PENDING_MAX = 200


def is_online():
    """True when DocDetect runs as a hosted app (DOCDETECT_ONLINE=1) and not on the user's own computer."""
    return os.environ.get("DOCDETECT_ONLINE", "").strip().lower() in ("1", "true", "yes")


def max_online_download_mb():
    try:
        return max(1, int(os.environ.get("DOCDETECT_MAX_DOWNLOAD_MB", "100")))
    except ValueError:
        return 100


def web_login_configured():
    return all(os.environ.get(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "DOCDETECT_REDIRECT_URI"))


def _web_flow():
    redirect = os.environ["DOCDETECT_REDIRECT_URI"].strip()
    config = {"web": {
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [redirect],
    }}
    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect)


def start_web_login():
    """Return the Google sign-in address for one visitor. The flow is kept until Google redirects back."""
    if not web_login_configured():
        raise RuntimeError("Google sign-in is not configured on this server "
                           "(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and DOCDETECT_REDIRECT_URI must be set).")
    flow = _web_flow()
    url, state = flow.authorization_url(access_type="online", prompt="select_account")
    now = time.time()
    with _PENDING_LOCK:
        for key in [k for k, (_, created) in _PENDING.items() if now - created > _PENDING_TTL_SECONDS]:
            del _PENDING[key]
        while len(_PENDING) >= _PENDING_MAX:
            del _PENDING[min(_PENDING, key=lambda k: _PENDING[k][1])]
        _PENDING[state] = (flow, now)
    return url


def finish_web_login(code, state):
    """Exchange the code that Google sent back for credentials. A state value can be used only once."""
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    with _PENDING_LOCK:
        item = _PENDING.pop(state, None)
    if item is None or time.time() - item[1] > _PENDING_TTL_SECONDS:
        raise ValueError("The sign-in link expired or was already used. Please sign in again.")
    flow = item[0]
    flow.fetch_token(code=code)
    return flow.credentials


def service_from_credentials(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def cleanup_old_session_dirs(max_age_hours=SESSION_MAX_AGE_HOURS):
    """Remove temporary download folders left behind by sessions that ended without deleting them."""
    root = tempfile.gettempdir()
    cutoff = time.time() - max_age_hours * 3600
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if name.startswith(SESSION_PREFIX) and os.path.isdir(path) and os.path.getmtime(path) < cutoff:
            shutil.rmtree(path, onerror=_force_remove_readonly)


def new_session_dir():
    cleanup_old_session_dirs()
    return tempfile.mkdtemp(prefix=SESSION_PREFIX)


def delete_session_dir(path):
    """Delete a session folder created by new_session_dir (and nothing else)."""
    if path and os.path.basename(os.path.normpath(path)).startswith(SESSION_PREFIX) and os.path.isdir(path):
        shutil.rmtree(path, onerror=_force_remove_readonly)

"""Google Drive access (read-only) for DocDetect. Files are downloaded to a local folder and analysed there."""
import io
import os
import re
import shutil
import stat
from datetime import datetime

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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


def list_owners_in_folder(folder_id):
    service = get_drive_service()
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
                               max_size_mb=None, progress_callback=None, service=None):
    """Download the files of a Drive folder to a local folder and return their local paths.

    max_size_mb: files larger than this are skipped (None = no limit); they are listed in LAST_SKIPPED.
    progress_callback(index, total, file_name, fraction): called while downloading, so the app can show progress.
    Subfolders and native Google Docs/Sheets/Slides are not downloaded; they are listed in LAST_NOT_DOWNLOADED.
    """
    global LAST_SKIPPED, LAST_NOT_DOWNLOADED
    LAST_SKIPPED, LAST_NOT_DOWNLOADED = [], []
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
            LAST_NOT_DOWNLOADED.append((f["name"], "subfolder (only the top level of the folder is downloaded)"))
        elif mime.startswith("application/vnd.google-apps"):
            LAST_NOT_DOWNLOADED.append((f["name"], "Google Docs/Sheets/Slides file (needs an export)"))
        else:
            downloadable.append(f)

    to_download = []
    for f in downloadable:
        size_bytes = int(f.get("size", 0) or 0)
        if max_size_mb and size_bytes > max_size_mb * 1024 * 1024:
            LAST_SKIPPED.append((f["name"], size_bytes))
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

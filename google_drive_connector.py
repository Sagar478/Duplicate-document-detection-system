import os, shutil, stat, io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

# Names (and sizes) of files skipped by the last sync because they were larger than the size limit.
LAST_SKIPPED = []


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
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
            fields="nextPageToken, files(id, name, mimeType, size, owners(emailAddress, displayName))",
            pageToken=page_token,
        ).execute()
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def list_owners_in_folder(folder_id):
    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)
    owners = {}
    for f in files:
        for owner in f.get("owners", []):
            owners[owner.get("emailAddress", "unknown")] = owner.get("displayName", "Unknown")
    return owners


def download_file(service, file_id, file_name, download_dir, on_progress=None):
    """Download one file in 8 MB chunks. on_progress(fraction 0..1) is called after every chunk."""
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, file_name)
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if on_progress and status is not None:
            on_progress(status.progress())
    fh.close()
    return local_path


def _force_remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def sync_drive_folder_to_local(folder_id, local_download_dir, owner_email_filter=None,
                               max_size_mb=None, progress_callback=None):
    """Download a Drive folder to a local folder.

    max_size_mb: files larger than this are skipped (None = no limit). Skipped files are listed in LAST_SKIPPED.
    progress_callback(index, total, file_name, fraction): called while downloading, so the app can show progress.
    """
    global LAST_SKIPPED
    LAST_SKIPPED = []

    if os.path.exists(local_download_dir):
        shutil.rmtree(local_download_dir, onerror=_force_remove_readonly)
    os.makedirs(local_download_dir, exist_ok=True)

    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)

    if not files:
        raise ValueError("No files found in this Drive folder. This usually means the folder "
                         "hasn't been shared with your authenticated Google account, or the "
                         "folder ID is incorrect.")

    if owner_email_filter:
        files = [f for f in files if any(o.get("emailAddress") == owner_email_filter for o in f.get("owners", []))]
        if not files:
            raise ValueError(f"No files owned by {owner_email_filter} were found in this folder.")

    # native Google Docs/Sheets/Slides need export and are skipped
    files = [f for f in files if not f["mimeType"].startswith("application/vnd.google-apps")]

    to_download = []
    for f in files:
        size_bytes = int(f.get("size", 0) or 0)
        if max_size_mb and size_bytes > max_size_mb * 1024 * 1024:
            LAST_SKIPPED.append((f["name"], size_bytes))
        else:
            to_download.append(f)

    downloaded_paths = []
    total = len(to_download)
    for i, f in enumerate(to_download):
        if progress_callback:
            progress_callback(i, total, f["name"], 0.0)
        cb = (lambda frac, i=i, name=f["name"]: progress_callback(i, total, name, frac)) if progress_callback else None
        downloaded_paths.append(download_file(service, f["id"], f["name"], local_download_dir, on_progress=cb))
    return downloaded_paths
import os
import shutil
import stat
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"


def get_drive_service():
    """Authenticate with Google Drive and return a usable connection.
    On first run, this opens a browser window asking you to log in and
    approve access. After that, it remembers you via token.json."""
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
    """List all files inside a specific Google Drive folder, including
    who uploaded each one (owner email), so files from different
    contributors in a shared folder can be told apart."""
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None

    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, owners(emailAddress, displayName))",
            pageToken=page_token,
        ).execute()

        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def list_owners_in_folder(folder_id):
    """Return the distinct list of {email: display_name} who own files
    in this folder, so the UI can offer an owner filter."""
    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)
    owners = {}
    for f in files:
        for owner in f.get("owners", []):
            owners[owner.get("emailAddress", "unknown")] = owner.get("displayName", "Unknown")
    return owners


def download_file(service, file_id, file_name, download_dir):
    """Download a single file from Drive to a local folder."""
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, file_name)

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.close()
    return local_path


def _force_remove_readonly(func, path, exc_info):
    """Handler for shutil.rmtree: clears the read-only flag and retries.
    Needed because OneDrive/Windows sometimes marks synced files
    read-only, which blocks normal deletion."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass  # last resort: skip this one file/folder rather than crash the whole sync


def sync_drive_folder_to_local(folder_id, local_download_dir, owner_email_filter=None):
    """Main entry point: downloads files from a Drive folder into a local
    folder, so the existing detection code can scan it exactly like any
    other local folder. Clears any previously downloaded files first, so
    results always reflect the CURRENT sync, not a leftover mix from a
    previous one. If owner_email_filter is set, only files uploaded by
    that specific person are downloaded - useful when a shared folder
    contains files from multiple contributors."""
    if os.path.exists(local_download_dir):
        shutil.rmtree(local_download_dir, onerror=_force_remove_readonly)
    os.makedirs(local_download_dir, exist_ok=True)

    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)

    if not files:
        raise ValueError(
            "No files found in this Drive folder. This usually means the folder "
            "hasn't been shared with your authenticated Google account, or the "
            "folder ID is incorrect."
        )

    if owner_email_filter:
        files = [
            f for f in files
            if any(o.get("emailAddress") == owner_email_filter for o in f.get("owners", []))
        ]
        if not files:
            raise ValueError(f"No files owned by {owner_email_filter} were found in this folder.")

    downloaded_paths = []
    for f in files:
        # Skip native Google Docs/Sheets/Slides for now - they need
        # export handling, not direct download.
        if f["mimeType"].startswith("application/vnd.google-apps"):
            continue
        path = download_file(service, f["id"], f["name"], local_download_dir)
        downloaded_paths.append(path)

    return downloaded_paths
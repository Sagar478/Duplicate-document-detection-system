import os
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
    """List all files inside a specific Google Drive folder."""
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None

    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
        ).execute()

        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


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


def sync_drive_folder_to_local(folder_id, local_download_dir):
    """Main entry point: downloads every file from a Drive folder into
    a local folder, so the existing detection code can scan it exactly
    like any other local folder."""
    service = get_drive_service()
    files = list_files_in_folder(service, folder_id)

    downloaded_paths = []
    for f in files:
        # Skip native Google Docs/Sheets/Slides for now - they need
        # export handling, not direct download (see note below)
        if f["mimeType"].startswith("application/vnd.google-apps"):
            continue
        path = download_file(service, f["id"], f["name"], local_download_dir)
        downloaded_paths.append(path)

    return downloaded_paths


if __name__ == "__main__":
    # Quick manual test: replace with a real folder ID from your Drive
    # (the long string in the folder's URL after /folders/)
    TEST_FOLDER_ID = "16JkomdWxvT3WPGIWXYtwNn2AcjdSE6b_"
    TEST_DOWNLOAD_DIR = "drive_downloads"

    print("Connecting to Google Drive...")
    paths = sync_drive_folder_to_local(TEST_FOLDER_ID, TEST_DOWNLOAD_DIR)
    print(f"Downloaded {len(paths)} file(s):")
    for p in paths:
        print(f"  - {p}")
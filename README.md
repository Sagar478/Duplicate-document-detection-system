# DocDetect – duplicate document detection for cloud storage folders

DocDetect finds **exact** and **near-duplicate** files (documents, images, video) in a local, OneDrive-synchronised or
Google Drive folder, recommends which file is the most likely current version, and shows the results in a Streamlit
dashboard. All analysis runs on your own computer.

## How it works

| Step | Method |
|---|---|
| Exact duplicates | SHA-256 of the file bytes (`hashlib`, read in 1 MiB chunks). Files are only hashed when another file has the same size. Empty files are ignored. |
| Near-duplicate documents (.docx, .pdf, .txt) | Text is extracted, then compared with the Ratcliff/Obershelp ratio (`difflib.SequenceMatcher`, `autojunk=False`). Pairs scoring ≥ 0.75 are related. A quick word-overlap and length test skips pairs that cannot reach the threshold. |
| Near-duplicate images | Perceptual hash (pHash); related when the Hamming distance is ≤ 4 of 64 bits. EXIF rotation is applied first. |
| Near-duplicate videos | 5 evenly spaced frames per video, each pHashed; related when ≥ 60 % of each video's frames match a frame of the other (frame distance ≤ 4). |
| Version recommendation | Newest modification time; for text files the length (0.001 s per character) breaks near-ties. |
| Google Drive | Read-only OAuth; files are downloaded (with their Drive modified time) and analysed locally. |

Nothing is ever deleted automatically: the Optimization page only *moves* outdated copies to a `_docdetect_review` folder.

## Install and run

```
pip install -r requirements.txt
python -m streamlit run app.py
```

Command line (no dashboard): `python scanner.py "C:\path\to\folder"`

### Google Drive (optional)
1. In Google Cloud Console create an OAuth client of type *Desktop app* and enable the Drive API.
2. Save the downloaded JSON next to `app.py` as `credentials.json` (never commit it).
3. In the app choose *Google Drive folder*, paste the folder link or ID, and click *Connect and download*.
   Subfolders and native Google Docs/Sheets/Slides are not downloaded (the app lists them).

## Tests
```
python -m pytest tests
```
The tests cover SHA-256 (NIST vectors, chunk boundaries), text extraction, similarity, images, video, grouping,
version recommendation, the scanner, the Drive connector (with a fake Drive service) and every dashboard page.

## Files
`app.py` dashboard · `scanner.py` shared scan pipeline · `hasher.py` · `text_extractor.py` · `near_duplicate_text.py` ·
`image_similarity.py` · `video_similarity.py` · `version_recommender.py` · `google_drive_connector.py` · `file_utils.py` ·
`benchmark.py` (timing by file size)


## Online demo (Render) - each visitor signs in with their own Google account

The same code can run as a hosted app. Set `DOCDETECT_ONLINE=1` and the dashboard shows only the Google Drive route: a visitor
clicks **Sign in with Google**, chooses their own account, pastes a folder link, and DocDetect downloads that folder to a private
temporary folder on the server, analyses it, and deletes it when the visitor clicks **Delete my files and sign out** (or after
2 hours). Access is read-only. No token, `credentials.json`, scan history or download is kept on disk, and Local folder and
Storage Comparison are hidden because they only make sense on the user's own computer.

1. Google Cloud Console -> APIs & Services -> enable the **Google Drive API**.
2. OAuth consent screen: user type *External*, publishing status **Testing**, and add each tester's Google address under
   **Test users** (up to 100). Google shows an "unverified app" warning because `drive.readonly` is a restricted scope.
3. Credentials -> **Create OAuth client ID -> Web application**. Under *Authorised redirect URIs* add the exact address of
   the Render app (for example `https://docdetect.onrender.com`, no trailing slash).
4. On Render: New -> Blueprint (or Web Service) from this repository (`render.yaml`). Set the environment variables
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `DOCDETECT_REDIRECT_URI` in the dashboard. Never commit them.
5. Open the app, sign in with a test-user account and scan a small test folder. Files larger than
   `DOCDETECT_MAX_DOWNLOAD_MB` (100 by default) are skipped because the free plan has little memory.

Run it locally in online mode to try it: set the three variables and `DOCDETECT_ONLINE=1`, then `streamlit run app.py`
(use `http://localhost:8501` as the redirect URI and add it to the OAuth client).

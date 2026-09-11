import hashlib
import os
from collections import defaultdict


def get_file_hash(filepath):
    """Compute a SHA-256 hash of a file's raw content.
    Works on ANY file type - text, image, video, etc."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_exact_duplicates(folder):
    """Scan a folder and subfolders, group files by identical content hash."""
    hash_to_files = defaultdict(list)

    for root, dirs, files in os.walk(folder):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                file_hash = get_file_hash(filepath)
                hash_to_files[file_hash].append(filepath)
            except Exception:
                continue  # skip unreadable files

    return [files for files in hash_to_files.values() if len(files) > 1]


if __name__ == "__main__":
    FOLDER_TO_SCAN = r"C:\Users\sagar\OneDrive\Documents\messy"
    groups = find_exact_duplicates(FOLDER_TO_SCAN)
    print(f"Found {len(groups)} exact duplicate group(s):\n")
    for i, group in enumerate(groups, 1):
        print(f"Group {i}:")
        for f in group:
            print(f"  - {f}")
        print()
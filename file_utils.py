"""Shared helpers: one definition of 'which files does DocDetect look at'.

Every detector walks the folder through iter_files(), so all of them see the same list of files and none of
them ever picks up DocDetect's own review folder or temporary files created by other programs.
"""
import os

REVIEW_FOLDER_NAME = "_docdetect_review"      # outdated copies are moved here by the Optimization page
SKIP_DIRS = {REVIEW_FOLDER_NAME, "__pycache__", ".git", "$RECYCLE.BIN", ".Trash"}
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store", ".docdetect_drive_cache"}
SKIP_PREFIXES = ("~$", ".~lock.")             # Word / LibreOffice lock files (not real documents)
SKIP_SUFFIXES = (".tmp", ".part", ".crdownload")


def is_ignored_file(filename):
    lower = filename.lower()
    return (lower in SKIP_FILES or filename.startswith(SKIP_PREFIXES) or lower.endswith(SKIP_SUFFIXES))


def iter_files(folder):
    """Yield the full path of every real file below `folder`, in a stable (sorted) order."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for filename in sorted(files):
            if not is_ignored_file(filename):
                yield os.path.join(root, filename)


def list_files(folder):
    return list(iter_files(folder))

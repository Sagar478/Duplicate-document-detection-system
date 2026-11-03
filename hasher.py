"""Exact duplicate detection with SHA-256 (FIPS 180-4), computed with Python's hashlib."""
import hashlib
import os
import sys
from collections import defaultdict

from file_utils import iter_files

CHUNK_SIZE = 1024 * 1024  # read 1 MiB at a time, so a multi-GB file never has to fit in memory


def get_file_hash(filepath):
    """SHA-256 of a file's raw bytes (64 hex characters). Works on ANY file type."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_exact_duplicates(folder, files=None, errors=None, progress=None, size_prefilter=True):
    """Group files with identical content. Returns a list of groups (lists of paths, 2 or more files each).

    files           optional list of paths (defaults to every file below `folder`)
    errors          optional list; unreadable files are appended as (path, message) instead of being ignored silently
    progress        optional callback(done, total, path)
    size_prefilter  two files can only be identical if they have the same size, so a file whose size is
                    unique is never read. The result is the same as hashing every file, only faster.
    Empty (0-byte) files are ignored: they all share one hash but contain nothing worth merging.
    """
    paths = list(files) if files is not None else list(iter_files(folder))

    by_size = defaultdict(list)
    for p in paths:
        try:
            size = os.path.getsize(p)
        except OSError as e:
            if errors is not None:
                errors.append((p, f"cannot read file size: {e}"))
            continue
        if size > 0:
            by_size[size].append(p)

    if size_prefilter:
        candidates = [p for group in by_size.values() if len(group) > 1 for p in group]
    else:
        candidates = [p for group in by_size.values() for p in group]

    hash_to_files = defaultdict(list)
    for i, p in enumerate(candidates):
        if progress:
            progress(i, len(candidates), p)
        try:
            hash_to_files[get_file_hash(p)].append(p)
        except OSError as e:
            if errors is not None:
                errors.append((p, f"cannot read file: {e}"))
    return [group for group in hash_to_files.values() if len(group) > 1]


def find_empty_files(folder, files=None):
    paths = list(files) if files is not None else list(iter_files(folder))
    out = []
    for p in paths:
        try:
            if os.path.getsize(p) == 0:
                out.append(p)
        except OSError:
            pass
    return out


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    groups = find_exact_duplicates(folder)
    print(f"Found {len(groups)} exact duplicate group(s):\n")
    for i, group in enumerate(groups, 1):
        print(f"Group {i}:")
        for f in group:
            print(f"  - {f}")
        print()

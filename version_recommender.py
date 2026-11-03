"""Groups related files and recommends which file in a group is the current version."""
import os

from text_extractor import extract_text_cached, is_text_file

# Rule used to pick the current version: score = modification time (seconds since 1970) plus
# LENGTH_WEIGHT_SECONDS for every character of text. The newest file wins; the length term only matters when two
# files were saved within a few minutes of each other, where the longer (more complete) document is preferred.
LENGTH_WEIGHT_SECONDS = 0.001


def group_related_files(pairs):
    """Combine pairwise matches (from any detector) into groups of related files.

    Uses union-find, so a pair that links two existing groups merges them (A~B and C~D, then B~C gives one group
    A, B, C, D). Returns a list of sets, in the order the groups were first seen.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    order = []
    for file_a, file_b, *_ in pairs:
        for f in (file_a, file_b):
            if f not in parent:
                order.append(f)
        ra, rb = find(file_a), find(file_b)
        if ra != rb:
            parent[rb] = ra

    groups = {}
    for f in order:
        groups.setdefault(find(f), set()).add(f)
    return list(groups.values())


def version_score(filepath):
    mod_time = os.path.getmtime(filepath)
    content_length = 0
    if is_text_file(filepath):
        try:
            content_length = len(extract_text_cached(filepath) or "")
        except Exception:
            content_length = 0   # unreadable text does not stop a recommendation being made
    return mod_time + content_length * LENGTH_WEIGHT_SECONDS


def recommend_latest_version(group):
    """Pick the most likely 'current' file in a group (see LENGTH_WEIGHT_SECONDS). Ties are broken by path so
    the answer is always the same for the same files. Files that no longer exist are ignored."""
    best_file, best_key = None, None
    for filepath in sorted(group):
        try:
            key = version_score(filepath)
        except OSError:
            continue
        if best_key is None or key > best_key:
            best_file, best_key = filepath, key
    return best_file

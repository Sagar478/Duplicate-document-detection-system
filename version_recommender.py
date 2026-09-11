import os
from text_extractor import extract_text, is_text_file


def group_related_files(pairs):
    """Combine pairwise matches (from any source) into groups."""
    groups = []
    for file_a, file_b, similarity in pairs:
        placed = False
        for group in groups:
            if file_a in group or file_b in group:
                group.add(file_a)
                group.add(file_b)
                placed = True
                break
        if not placed:
            groups.append({file_a, file_b})
    return groups


def recommend_latest_version(group):
    """Pick the most likely 'current' file in a group.
    Works for any file type - uses modification date, and content
    length only when the file is text-based."""
    best_file = None
    best_score = -1

    for filepath in group:
        mod_time = os.path.getmtime(filepath)
        content_length = 0
        if is_text_file(filepath):
            content_length = len(extract_text(filepath) or "")
        score = mod_time + (content_length * 0.001)

        if score > best_score:
            best_score = score
            best_file = filepath

    return best_file
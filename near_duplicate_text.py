"""Near-duplicate detection for text documents (.docx, .pdf, .txt).

Two documents are related when the Ratcliff/Obershelp similarity ratio (difflib.SequenceMatcher, ratio = 2*M/T)
of their extracted text is at least SIMILARITY_THRESHOLD.

Two points that matter for correctness:
* SequenceMatcher is created with autojunk=False. By default Python treats any character that makes up more
  than 1% of a text longer than 200 characters as "junk" and ignores it when it looks for matching blocks.
  In ordinary text almost every letter is that frequent, so a heavily edited copy of a document scored far too
  low (a rewritten version of a 240-character report scored 51% instead of 91%).
* Comparing every pair of long documents character by character is slow, so each pair first goes through two
  cheap tests that can only discard pairs that are certain (or, for the word test, almost certain) not to reach the
  threshold. Pairs that pass are scored with the full algorithm, so the reported scores are exact.
"""
import os
import sys
from difflib import SequenceMatcher

from file_utils import iter_files
from text_extractor import extract_text_cached, is_text_file

SIMILARITY_THRESHOLD = 0.75
SHINGLE_WORDS = 3          # word shingles used by the quick pre-filter (Broder, 1997)
SHINGLE_MIN_OVERLAP = 0.10  # pairs sharing less than 10% of their shingles are far below 75% similarity


def calculate_similarity(text1, text2):
    """Similarity ratio between 0 and 1 (1.0 = identical text)."""
    if text1 == text2:
        return 1.0
    return SequenceMatcher(None, text1, text2, autojunk=False).ratio()


def _shingles(text, k=SHINGLE_WORDS):
    words = text.lower().split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _could_reach_threshold(a, b, sa, sb, threshold):
    """False only when the pair is certain (length) or very unlikely (word overlap) to reach the threshold."""
    la, lb = len(a), len(b)
    if 2.0 * min(la, lb) / (la + lb) < threshold:     # upper bound of the ratio: even a perfect match is too short
        return False
    if not sa or not sb:
        return True
    overlap = len(sa & sb) / min(len(sa), len(sb))
    return overlap >= SHINGLE_MIN_OVERLAP


def load_texts(folder, files=None, errors=None):
    """Return {path: text} for every readable document with text. Problem files are listed in `errors`."""
    paths = files if files is not None else iter_files(folder)
    texts = {}
    for filepath in paths:
        if not is_text_file(filepath):
            continue
        try:
            if os.path.getsize(filepath) == 0:
                continue                      # empty files are reported separately by the scanner
            text = extract_text_cached(filepath)
        except Exception as e:  # corrupt, password protected, locked ...
            if errors is not None:
                errors.append((filepath, f"could not read text: {type(e).__name__}: {e}"))
            continue
        if text is None or not text.strip():
            if errors is not None:
                errors.append((filepath, "no extractable text (for example a scanned PDF); not compared"))
            continue
        texts[filepath] = text
    return texts


def find_near_duplicate_texts(folder, files=None, errors=None, progress=None, threshold=None):
    """Find near-duplicate text documents. Returns [(file_a, file_b, similarity 0-1), ...]."""
    threshold = SIMILARITY_THRESHOLD if threshold is None else threshold
    file_texts = load_texts(folder, files, errors)
    filepaths = list(file_texts)
    shingles = {p: _shingles(t) for p, t in file_texts.items()}

    pairs = []
    total = len(filepaths) * (len(filepaths) - 1) // 2
    done = 0
    for i in range(len(filepaths)):
        for j in range(i + 1, len(filepaths)):
            a, b = filepaths[i], filepaths[j]
            done += 1
            if progress and done % 20 == 0:
                progress(done, total, a)
            if not _could_reach_threshold(file_texts[a], file_texts[b], shingles[a], shingles[b], threshold):
                continue
            sim = calculate_similarity(file_texts[a], file_texts[b])
            if sim >= threshold:
                pairs.append((a, b, sim))
    return pairs


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    results = find_near_duplicate_texts(folder)
    if not results:
        print("No near-duplicate text documents found.")
    else:
        print(f"Found {len(results)} near-duplicate pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}\n  <--> {b}\n  Similarity: {sim * 100:.1f}%\n")

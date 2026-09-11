import os
from difflib import SequenceMatcher
from text_extractor import extract_text, is_text_file

SIMILARITY_THRESHOLD = 0.75


def calculate_similarity(text1, text2):
    return SequenceMatcher(None, text1, text2).ratio()


def find_near_duplicate_texts(folder):
    """Find near-duplicate TEXT documents (.docx, .pdf, .txt) only."""
    file_texts = {}
    for root, dirs, files in os.walk(folder):
        for filename in files:
            filepath = os.path.join(root, filename)
            if is_text_file(filepath):
                text = extract_text(filepath)
                if text:
                    file_texts[filepath] = text

    filepaths = list(file_texts.keys())
    pairs = []
    for i in range(len(filepaths)):
        for j in range(i + 1, len(filepaths)):
            a, b = filepaths[i], filepaths[j]
            sim = calculate_similarity(file_texts[a], file_texts[b])
            if sim >= SIMILARITY_THRESHOLD:
                pairs.append((a, b, sim))
    return pairs


if __name__ == "__main__":
    FOLDER_TO_SCAN = r"C:\Users\sagar\OneDrive\Documents\messy"
    results = find_near_duplicate_texts(FOLDER_TO_SCAN)

    if not results:
        print("No near-duplicate text documents found.")
    else:
        print(f"Found {len(results)} near-duplicate pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}")
            print(f"  <--> {b}")
            print(f"  Similarity: {sim * 100:.1f}%\n")
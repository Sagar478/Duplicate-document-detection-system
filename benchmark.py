import time
import os
from hasher import get_file_hash
from text_extractor import extract_text, is_text_file

FOLDER_TO_SCAN = r"C:\Users\sagar\OneDrive\Documents\messy"


def classify_size(size_kb):
    if size_kb < 100:
        return "Small (<100 KB)"
    elif size_kb < 5000:
        return "Medium (100 KB-5 MB)"
    else:
        return "Large (>5 MB)"


if __name__ == "__main__":
    print(f"{'File':<45} {'Size Category':<22} {'Hash (s)':<12} {'Extract (s)'}")
    print("-" * 100)

    for root, dirs, files in os.walk(FOLDER_TO_SCAN):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                size_kb = os.path.getsize(filepath) / 1024
                category = classify_size(size_kb)

                t0 = time.time()
                get_file_hash(filepath)
                hash_time = time.time() - t0

                extract_time_str = "N/A"
                if is_text_file(filepath):
                    t0 = time.time()
                    extract_text(filepath)
                    extract_time_str = f"{time.time() - t0:.4f}"

                print(f"{filename:<45} {category:<22} {hash_time:<12.4f} {extract_time_str}")
            except Exception as e:
                print(f"{filename:<45} ERROR: {e}")
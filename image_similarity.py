import os
import imagehash
from PIL import Image

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
HASH_DIFFERENCE_THRESHOLD = 4  # lower = stricter match; 0 = identical


def is_image_file(filepath):
    return filepath.lower().endswith(IMAGE_EXTENSIONS)


def get_image_hash(filepath):
    """Perceptual hash: similar-LOOKING images get similar hashes,
    even if resized, recompressed, or slightly edited."""
    with Image.open(filepath) as img:
        return imagehash.phash(img)


def find_near_duplicate_images(folder):
    """Find visually similar images using perceptual hashing."""
    image_hashes = {}
    for root, dirs, files in os.walk(folder):
        for filename in files:
            filepath = os.path.join(root, filename)
            if is_image_file(filepath):
                try:
                    image_hashes[filepath] = get_image_hash(filepath)
                except Exception:
                    continue

    filepaths = list(image_hashes.keys())
    pairs = []
    for i in range(len(filepaths)):
        for j in range(i + 1, len(filepaths)):
            a, b = filepaths[i], filepaths[j]
            difference = image_hashes[a] - image_hashes[b]
            if difference <= HASH_DIFFERENCE_THRESHOLD:
                similarity = 1 - (difference / 64)
                pairs.append((a, b, similarity))
    return pairs


if __name__ == "__main__":
    print(f"Using threshold: {HASH_DIFFERENCE_THRESHOLD}")
    FOLDER_TO_SCAN = r"C:\Users\sagar\OneDrive\Documents\messy"
    results = find_near_duplicate_images(FOLDER_TO_SCAN)

    if not results:
        print("No near-duplicate images found.")
    else:
        print(f"Found {len(results)} near-duplicate image pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}")
            print(f"  <--> {b}")
            print(f"  Similarity: {sim * 100:.1f}%\n")
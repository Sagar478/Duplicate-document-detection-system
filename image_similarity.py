"""Near-duplicate image detection with perceptual hashing (pHash, a DCT-based hash; Zauner, 2010)."""
import sys

import imagehash
import numpy as np
from PIL import Image, ImageOps

from file_utils import iter_files

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
HASH_DIFFERENCE_THRESHOLD = 4  # maximum Hamming distance (of 64 bits) to call two images related; 0 = identical hash

_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def is_image_file(filepath):
    return filepath.lower().endswith(IMAGE_EXTENSIONS)


def get_image_hash(filepath):
    """Perceptual hash: similar-LOOKING images get similar hashes, even if resized, recompressed or edited.
    The photo's EXIF rotation is applied first, so a phone photo stored 'sideways' is hashed as it looks."""
    with Image.open(filepath) as img:
        img = ImageOps.exif_transpose(img)
        return imagehash.phash(img)


def _hash_to_int(h):
    value = 0
    for bit in h.hash.flatten():
        value = (value << 1) | int(bit)
    return value


def find_near_duplicate_images(folder, files=None, errors=None, progress=None, threshold=None):
    """Find visually similar images. Returns [(file_a, file_b, similarity 0-1), ...]."""
    threshold = HASH_DIFFERENCE_THRESHOLD if threshold is None else threshold
    paths = files if files is not None else iter_files(folder)
    filepaths, hash_ints = [], []
    for filepath in paths:
        if not is_image_file(filepath):
            continue
        try:
            hash_ints.append(_hash_to_int(get_image_hash(filepath)))
            filepaths.append(filepath)
        except Exception as e:
            if errors is not None:
                errors.append((filepath, f"could not read image: {type(e).__name__}: {e}"))

    pairs = []
    arr = np.array(hash_ints, dtype=np.uint64)
    for i in range(len(filepaths)):
        if progress and i % 25 == 0:
            progress(i, len(filepaths), filepaths[i])
        if i + 1 >= len(filepaths):
            break
        xor = arr[i + 1:] ^ arr[i]
        dist = _POPCOUNT[xor.view(np.uint8).reshape(-1, 8)].sum(axis=1)
        for offset in np.nonzero(dist <= threshold)[0]:
            j = i + 1 + int(offset)
            pairs.append((filepaths[i], filepaths[j], 1 - (int(dist[offset]) / 64)))
    return pairs


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"Using threshold: {HASH_DIFFERENCE_THRESHOLD}")
    results = find_near_duplicate_images(folder)
    if not results:
        print("No near-duplicate images found.")
    else:
        print(f"Found {len(results)} near-duplicate image pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}\n  <--> {b}\n  Similarity: {sim * 100:.1f}%\n")

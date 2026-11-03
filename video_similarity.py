"""Near-duplicate video detection: perceptual hashes of a few sampled frames."""
import sys

import cv2
import imagehash
from PIL import Image

from file_utils import iter_files

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
FRAMES_PER_VIDEO = 5           # how many evenly spaced sample frames are taken from each video
FRAME_HASH_THRESHOLD = 4       # maximum perceptual-hash (Hamming) distance for two frames to match
MATCH_FRACTION_REQUIRED = 0.6  # fraction of EACH video's frames that must match the other video to call them related


def is_video_file(filepath):
    return filepath.lower().endswith(VIDEO_EXTENSIONS)


def extract_sample_frame_hashes(filepath, num_frames=FRAMES_PER_VIDEO):
    """Perceptual hashes of evenly spaced frames, so videos are compared by what they show, not by their bytes."""
    hashes = []
    cap = cv2.VideoCapture(filepath)
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return hashes
        positions = [int(total_frames * i / num_frames) for i in range(num_frames)]
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            success, frame = cap.read()
            if success:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hashes.append(imagehash.phash(Image.fromarray(rgb_frame)))
    finally:
        cap.release()
    return hashes


def _directional_match(hashes_a, hashes_b):
    """Fraction of A's frames that closely match at least one frame of B."""
    if not hashes_a or not hashes_b:
        return 0.0
    matched = sum(1 for ha in hashes_a if min(ha - hb for hb in hashes_b) <= FRAME_HASH_THRESHOLD)
    return matched / len(hashes_a)


def compare_videos(hashes_a, hashes_b):
    """Similarity (0-1) of two videos: the SMALLER of the two directional match fractions. Both videos must
    match the other, so the result does not depend on which file is listed first, and a short run of similar
    frames (for example a shared dark intro) in an unrelated video does not make it a match."""
    return min(_directional_match(hashes_a, hashes_b), _directional_match(hashes_b, hashes_a))


def find_near_duplicate_videos(folder, files=None, errors=None, progress=None):
    """Find visually similar videos. Returns [(file_a, file_b, similarity 0-1), ...]."""
    paths = files if files is not None else iter_files(folder)
    video_hashes = {}
    for filepath in paths:
        if not is_video_file(filepath):
            continue
        try:
            hashes = extract_sample_frame_hashes(filepath)
        except Exception as e:
            if errors is not None:
                errors.append((filepath, f"could not read video: {type(e).__name__}: {e}"))
            continue
        if hashes:
            video_hashes[filepath] = hashes
        elif errors is not None:
            errors.append((filepath, "no readable frames (unsupported codec or corrupt file); not compared"))

    filepaths = list(video_hashes)
    pairs = []
    for i in range(len(filepaths)):
        for j in range(i + 1, len(filepaths)):
            a, b = filepaths[i], filepaths[j]
            sim = compare_videos(video_hashes[a], video_hashes[b])
            if sim >= MATCH_FRACTION_REQUIRED:
                pairs.append((a, b, sim))
    return pairs


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    results = find_near_duplicate_videos(folder)
    if not results:
        print("No near-duplicate videos found.")
    else:
        print(f"Found {len(results)} near-duplicate video pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}\n  <--> {b}\n  Matching frames: {sim * 100:.1f}%\n")

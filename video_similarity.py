import os
import cv2
import imagehash
from PIL import Image

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".wmv")
FRAMES_PER_VIDEO = 5          # how many sample frames to extract per video
FRAME_HASH_THRESHOLD = 4      # perceptual hash difference threshold, per frame
MATCH_FRACTION_REQUIRED = 0.6  # fraction of frames that must match to call videos related


def is_video_file(filepath):
    return filepath.lower().endswith(VIDEO_EXTENSIONS)


def extract_sample_frame_hashes(filepath, num_frames=FRAMES_PER_VIDEO):
    """Extract evenly-spaced frames from a video and return their
    perceptual hashes. This lets us compare videos by their visual
    content, not just their raw bytes."""
    hashes = []
    cap = cv2.VideoCapture(filepath)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        return hashes

    positions = [int(total_frames * i / num_frames) for i in range(num_frames)]

    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        success, frame = cap.read()
        if success:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            hashes.append(imagehash.phash(pil_image))

    cap.release()
    return hashes


def compare_videos(hashes_a, hashes_b):
    """Compare two videos' sampled frame hashes. Returns a similarity
    ratio (0-1) based on the fraction of frames that closely match."""
    if not hashes_a or not hashes_b:
        return 0.0

    matched = 0
    for ha in hashes_a:
        best_diff = min(ha - hb for hb in hashes_b)
        if best_diff <= FRAME_HASH_THRESHOLD:
            matched += 1

    return matched / len(hashes_a)


def find_near_duplicate_videos(folder):
    """Find visually similar videos using sampled-frame perceptual hashing."""
    video_hashes = {}
    for root, dirs, files in os.walk(folder):
        for filename in files:
            filepath = os.path.join(root, filename)
            if is_video_file(filepath):
                try:
                    hashes = extract_sample_frame_hashes(filepath)
                    if hashes:
                        video_hashes[filepath] = hashes
                except Exception:
                    continue

    filepaths = list(video_hashes.keys())
    pairs = []
    for i in range(len(filepaths)):
        for j in range(i + 1, len(filepaths)):
            a, b = filepaths[i], filepaths[j]
            sim = compare_videos(video_hashes[a], video_hashes[b])
            if sim >= MATCH_FRACTION_REQUIRED:
                pairs.append((a, b, sim))
    return pairs


if __name__ == "__main__":
    FOLDER_TO_SCAN = r"C:\Users\sagar\OneDrive\Documents\messy"
    results = find_near_duplicate_videos(FOLDER_TO_SCAN)

    if not results:
        print("No near-duplicate videos found.")
    else:
        print(f"Found {len(results)} near-duplicate video pair(s):\n")
        for a, b, sim in results:
            print(f"  {a}")
            print(f"  <--> {b}")
            print(f"  Matching frames: {sim * 100:.1f}%\n")
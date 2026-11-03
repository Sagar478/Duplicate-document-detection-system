import os

import cv2
import imagehash
import numpy as np
import pytest
from PIL import Image

from conftest import photo_like
from image_similarity import (HASH_DIFFERENCE_THRESHOLD, _hash_to_int, find_near_duplicate_images, get_image_hash)
from video_similarity import compare_videos, extract_sample_frame_hashes, find_near_duplicate_videos


def names(pairs):
    return {frozenset((os.path.basename(a), os.path.basename(b))) for a, b, _ in pairs}


def test_resized_and_recompressed_copies_match_and_different_pictures_do_not(tmp_path):
    img = photo_like(1)
    img.save(tmp_path / "orig.png")
    img.resize((128, 128)).save(tmp_path / "small.png")
    img.save(tmp_path / "recompressed.jpg", quality=40)
    photo_like(2).save(tmp_path / "other.png")
    found = names(find_near_duplicate_images(str(tmp_path)))
    assert frozenset(("orig.png", "small.png")) in found
    assert frozenset(("orig.png", "recompressed.jpg")) in found
    assert not any("other.png" in p for p in found)


def test_exif_rotation_is_applied(tmp_path):
    img = photo_like(3)
    img.save(tmp_path / "upright.jpg")
    rotated = img.rotate(90, expand=True)
    exif = Image.Exif(); exif[0x0112] = 6          # "rotate 90 degrees clockwise to display"
    rotated.save(tmp_path / "sideways.jpg", exif=exif)
    pairs = find_near_duplicate_images(str(tmp_path))
    assert len(pairs) == 1


def test_vectorised_distance_equals_imagehash_distance(tmp_path):
    for i in range(6):
        photo_like(i).save(tmp_path / f"p{i}.png")
    paths = sorted(str(p) for p in tmp_path.iterdir())
    hashes = [get_image_hash(p) for p in paths]
    got = {frozenset((os.path.basename(a), os.path.basename(b))): round((1 - s) * 64)
           for a, b, s in find_near_duplicate_images(str(tmp_path), threshold=64)}
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            key = frozenset((os.path.basename(paths[i]), os.path.basename(paths[j])))
            assert got[key] == hashes[i] - hashes[j]


def test_corrupt_image_is_reported_not_fatal(tmp_path):
    photo_like(1).save(tmp_path / "a.png")
    (tmp_path / "bad.png").write_bytes(b"not an image")
    errors = []
    find_near_duplicate_images(str(tmp_path), errors=errors)
    assert len(errors) == 1 and "bad.png" in errors[0][0]


def write_video(path, seed, size=(160, 120), frames=40, fps=10):
    """A short synthetic clip whose picture changes smoothly with time."""
    rnd = np.random.RandomState(seed)
    a = rnd.randint(0, 255, (8, 8, 3), dtype=np.uint8)
    b = rnd.randint(0, 255, (8, 8, 3), dtype=np.uint8)
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(frames):
        t = i / (frames - 1)
        small = (a * (1 - t) + b * t).astype(np.uint8)
        frame = cv2.GaussianBlur(cv2.resize(small, size, interpolation=cv2.INTER_CUBIC), (9, 9), 3)
        out.write(frame)
    out.release()


def test_reencoded_video_matches_and_unrelated_video_does_not(tmp_path):
    write_video(tmp_path / "clip.mp4", seed=1)
    write_video(tmp_path / "clip_small.mp4", seed=1, size=(96, 72))          # same content, other resolution
    write_video(tmp_path / "unrelated.mp4", seed=7)
    found = names(find_near_duplicate_videos(str(tmp_path)))
    assert frozenset(("clip.mp4", "clip_small.mp4")) in found
    assert not any("unrelated.mp4" in p for p in found)


def test_video_comparison_is_symmetric(tmp_path):
    write_video(tmp_path / "a.mp4", seed=1)
    write_video(tmp_path / "b.mp4", seed=2)
    ha, hb = (extract_sample_frame_hashes(str(tmp_path / n)) for n in ("a.mp4", "b.mp4"))
    assert compare_videos(ha, hb) == compare_videos(hb, ha)
    assert compare_videos([], hb) == 0.0


def test_unreadable_video_is_reported_not_fatal(tmp_path):
    write_video(tmp_path / "ok.mp4", seed=1)
    (tmp_path / "bad.mp4").write_bytes(b"not a video")
    errors = []
    find_near_duplicate_videos(str(tmp_path), errors=errors)
    assert any("bad.mp4" in p for p, _ in errors)


def test_a_video_matching_only_in_one_direction_is_not_related():
    """Regression: 3 of 5 frames of one clip matched an unrelated clip, which made the pair 'related'."""
    zeros = imagehash.ImageHash(np.zeros((8, 8), dtype=bool))
    ones = imagehash.ImageHash(np.ones((8, 8), dtype=bool))
    half = np.zeros((8, 8), dtype=bool); half[:4, :] = True
    middle = imagehash.ImageHash(half)               # 32 bits away from both zeros and ones
    a = [zeros, zeros, zeros, ones, ones]            # 3 of A's 5 frames match a frame of B  (A -> B = 0.6)
    b = [zeros, middle, middle, middle, middle]      # only 1 of B's 5 frames matches a frame of A (B -> A = 0.2)
    assert compare_videos(a, b) == compare_videos(b, a) == 0.2

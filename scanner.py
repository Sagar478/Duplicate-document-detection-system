"""One scanning pipeline shared by the dashboard (Scan Folder and Storage Comparison pages), the command line
and the tests, so every part of DocDetect reports exactly the same results for the same folder."""
import argparse
import os
import time
from dataclasses import dataclass, field

from file_utils import list_files
from hasher import find_exact_duplicates, find_empty_files
from image_similarity import find_near_duplicate_images
from near_duplicate_text import find_near_duplicate_texts
from version_recommender import group_related_files, recommend_latest_version
from video_similarity import find_near_duplicate_videos


@dataclass
class ScanResult:
    folder: str
    files: list = field(default_factory=list)
    exact_groups: list = field(default_factory=list)
    text_pairs: list = field(default_factory=list)
    image_pairs: list = field(default_factory=list)
    video_pairs: list = field(default_factory=list)
    empty_files: list = field(default_factory=list)
    warnings: list = field(default_factory=list)    # [(path, message)] files that could not be analysed
    timings: dict = field(default_factory=dict)     # seconds per stage
    scan_time: float = 0.0

    @property
    def near_pairs(self):
        return self.text_pairs + self.image_pairs + self.video_pairs

    def all_pairs(self):
        """Every pair of related files, including the pairs implied by exact-duplicate groups."""
        pairs = list(self.near_pairs)
        for group in self.exact_groups:
            for i in range(len(group) - 1):
                pairs.append((group[i], group[i + 1], 1.0))
        return pairs

    def groups(self):
        return group_related_files(self.all_pairs())

    def wasted_kb(self):
        wasted = 0
        for group in self.groups():
            existing = [f for f in group if os.path.exists(f)]
            if len(existing) < 2:
                continue
            latest = recommend_latest_version(existing)
            wasted += sum(os.path.getsize(f) for f in existing if f != latest) / 1024
        return wasted


def without_exact_copies(pairs, exact_groups):
    """Drop pairs whose two files are byte-identical copies. They are already reported as exact duplicates, so
    counting them again as 'near' duplicates would count the same two files twice."""
    group_id = {f: i for i, g in enumerate(exact_groups) for f in g}
    return [p for p in pairs if not (p[0] in group_id and group_id[p[0]] == group_id.get(p[1]))]


def run_scan(folder, run_exact=True, run_text=True, run_images=True, run_videos=True, progress=None):
    """Run the whole detection pipeline on `folder`.

    progress(stage, fraction, message) is called as the scan advances (stage: 'files', 'exact', 'text', 'images', 'videos').
    A file that cannot be read never stops the scan: it is listed in result.warnings instead.
    """
    def report(stage, fraction, message=""):
        if progress:
            progress(stage, fraction, message)

    t_start = time.perf_counter()
    result = ScanResult(folder=folder)
    report("files", 0.0, "Listing files")
    result.files = list_files(folder)
    errors = result.warnings

    def timed(name, fn):
        t0 = time.perf_counter()
        out = fn()
        result.timings[name] = round(time.perf_counter() - t0, 3)
        return out

    if run_exact:
        report("exact", 0.0, "Hashing files (SHA-256)")
        result.exact_groups = timed("exact", lambda: find_exact_duplicates(
            folder, files=result.files, errors=errors,
            progress=lambda i, n, p: report("exact", i / max(n, 1), os.path.basename(p))))
        result.empty_files = find_empty_files(folder, files=result.files)
    if run_text:
        report("text", 0.0, "Comparing documents")
        text_pairs = timed("text", lambda: find_near_duplicate_texts(
            folder, files=result.files, errors=errors,
            progress=lambda i, n, p: report("text", i / max(n, 1), os.path.basename(p))))
        result.text_pairs = without_exact_copies(text_pairs, result.exact_groups)
    if run_images:
        report("images", 0.0, "Comparing images")
        image_pairs = timed("images", lambda: find_near_duplicate_images(
            folder, files=result.files, errors=errors,
            progress=lambda i, n, p: report("images", i / max(n, 1), os.path.basename(p))))
        result.image_pairs = without_exact_copies(image_pairs, result.exact_groups)
    if run_videos:
        report("videos", 0.0, "Comparing videos")
        video_pairs = timed("videos", lambda: find_near_duplicate_videos(
            folder, files=result.files, errors=errors))
        result.video_pairs = without_exact_copies(video_pairs, result.exact_groups)

    result.scan_time = round(time.perf_counter() - t_start, 3)
    report("done", 1.0, "Analysis complete")
    return result


def main():
    parser = argparse.ArgumentParser(description="DocDetect: find exact and near-duplicate files in a folder.")
    parser.add_argument("folder")
    parser.add_argument("--no-video", action="store_true", help="skip video comparison")
    args = parser.parse_args()
    r = run_scan(args.folder, run_videos=not args.no_video)
    print(f"Files: {len(r.files)}  Exact groups: {len(r.exact_groups)}  Near pairs: {len(r.near_pairs)}  "
          f"Related groups: {len(r.groups())}  Potential savings: {r.wasted_kb():.1f} KB  Time: {r.scan_time}s")
    for g in r.exact_groups:
        print("EXACT :", " == ".join(os.path.basename(f) for f in g))
    for a, b, s in r.near_pairs:
        print(f"NEAR  : {os.path.basename(a)} ~ {os.path.basename(b)}  {s * 100:.1f}%")
    for p, msg in r.warnings:
        print("WARN  :", os.path.basename(p), "-", msg)


if __name__ == "__main__":
    main()

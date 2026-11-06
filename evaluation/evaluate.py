"""Reproduce the text-similarity evaluation in the thesis (Tables 5.2 and 5.6).

Run from the repository root:
    python evaluation/evaluate.py

It compares all 45 pairs of the ten documents in evaluation/docs_test, using the same
text extraction and similarity measure as DocDetect, and scores the reported pairs
against the pairs listed by hand in evaluation/ground_truth.csv.
"""
import csv
import itertools
import os
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # so the DocDetect modules can be imported

from text_extractor import extract_text                    # noqa: E402
from near_duplicate_text import SIMILARITY_THRESHOLD       # noqa: E402

DOCS = os.path.join(HERE, "docs_test")
THRESHOLDS = [0.30, 0.40, 0.50, 0.75, 0.80, 0.90]


def similarity(a, b, autojunk):
    # autojunk=False is DocDetect's setting; autojunk=True is Python's default, used in the first evaluation
    return SequenceMatcher(None, a, b, autojunk=autojunk).ratio()


def load_truth():
    with open(os.path.join(HERE, "ground_truth.csv"), newline="", encoding="utf-8") as f:
        return {frozenset((row["file_a"], row["file_b"])) for row in csv.DictReader(f)}


def metrics(reported, truth):
    correct = len(reported & truth)
    precision = correct / len(reported) if reported else 0.0
    recall = correct / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return correct, precision, recall, f1


def main():
    files = sorted(os.listdir(DOCS))
    texts = {f: extract_text(os.path.join(DOCS, f)) or "" for f in files}
    truth = load_truth()
    pairs = list(itertools.combinations(files, 2))
    print(f"{len(files)} documents, {len(pairs)} pairs, {len(truth)} true pairs\n")

    for label, autojunk in (("First evaluation (autojunk on, Python's default)", True),
                            ("Final version (autojunk off, as in DocDetect)", False)):
        scores = {frozenset(p): similarity(texts[p[0]], texts[p[1]], autojunk) for p in pairs}
        reported = {p for p, s in scores.items() if s >= SIMILARITY_THRESHOLD}
        correct, p, r, f1 = metrics(reported, truth)
        print(f"{label}, threshold {SIMILARITY_THRESHOLD:.0%}:")
        print(f"  reported {len(reported)}, correct {correct}: precision {p:.1%}, recall {r:.1%}, F1 {f1:.1%}")
        for pair in sorted(truth, key=lambda x: sorted(x)):
            a, b = sorted(pair)
            print(f"    {a} / {b}: {scores[pair]:.1%}{'' if pair in reported else '  (missed)'}")
        print()

    scores = {frozenset(p): similarity(texts[p[0]], texts[p[1]], False) for p in pairs}
    print("Threshold sweep (Table 5.6, autojunk off):")
    print(f"  {'threshold':>9} {'reported':>8} {'correct':>7} {'precision':>9} {'recall':>7} {'F1':>6}")
    for t in THRESHOLDS:
        reported = {p for p, s in scores.items() if s >= t}
        correct, p, r, f1 = metrics(reported, truth)
        print(f"  {t:>9.0%} {len(reported):>8} {correct:>7} {p:>9.1%} {r:>7.1%} {f1:>6.1%}")
    false = [s for pr, s in scores.items() if pr not in truth]
    print(f"\nLowest true-pair score {min(scores[p] for p in truth):.1%}; highest unrelated score {max(false):.1%}")


if __name__ == "__main__":
    main()

# Evaluation data

Reproduces the text-similarity results in the thesis (Tables 5.2 and 5.6).

- `docs_test/`: the ten test documents (synthetic, created for this project)
- `ground_truth.csv`: the five related pairs, listed by hand before running the system
- `evaluate.py`: scores all 45 pairs and prints precision, recall and F1

Run from the repository root:

```
python evaluation/evaluate.py
```

The 52-file real folder used in Section 5.1 is not included, because it contains the author's own coursework.

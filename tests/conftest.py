import os
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

WORDS = ("the system file cloud storage document version duplicate hash image video detect user folder data report "
         "meeting plan budget project team review update final draft quarterly revenue marketing customer analysis "
         "strategy risk compliance policy security network performance quality delivery milestone schedule stakeholder").split()


def make_text(n_words, seed=0):
    rnd = random.Random(seed)
    return " ".join(rnd.choice(WORDS) for _ in range(n_words))


def edit_text(text, fraction, seed=1):
    """Replace roughly `fraction` of the words with other words."""
    rnd = random.Random(seed)
    words = text.split()
    for i in range(len(words)):
        if rnd.random() < fraction:
            words[i] = rnd.choice(WORDS)
    return " ".join(words)


def write_docx(path, text, table=None):
    import docx
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    d.save(str(path))


def write_pdf(path, text):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    line = ""
    for w in text.split():
        if len(line) + len(w) > 90:
            c.drawString(40, y, line); y -= 14; line = ""
            if y < 40:
                c.showPage(); y = 800
        line += w + " "
    c.drawString(40, y, line)
    c.save()


def photo_like(seed=0, size=(256, 256)):
    """A smooth, photo-like picture (blurred random blobs). Flat shapes would hash almost identically."""
    from PIL import Image, ImageFilter
    rnd = np.random.RandomState(seed)
    small = rnd.randint(0, 255, (16, 16, 3), dtype=np.uint8)
    return Image.fromarray(small).resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))


@pytest.fixture
def folder(tmp_path):
    return tmp_path

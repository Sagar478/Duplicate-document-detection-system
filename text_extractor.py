"""Text extraction for .docx, .pdf and .txt files."""
import os
from functools import lru_cache

import docx
import pdfplumber

TEXT_EXTENSIONS = (".docx", ".pdf", ".txt")


def extract_text_from_docx(filepath):
    """Paragraph text, plus the text inside tables (in document order)."""
    document = docx.Document(filepath)
    lines = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(docx.text.paragraph.Paragraph(child, document).text)
        elif tag == "tbl":
            for row in docx.table.Table(child, document).rows:
                cells = [c.text.strip() for c in row.cells]
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def extract_text_from_pdf(filepath):
    full_text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text)


def extract_text(filepath):
    """Return the text of a file, or None if the file type is not a text document.

    A scanned PDF (pictures of pages) has no text layer and returns '' (see is_empty_text in near_duplicate_text).
    Raises an exception if the file is corrupt or password protected; callers decide how to report that.
    """
    lower = filepath.lower()
    if lower.endswith(".docx"):
        return extract_text_from_docx(filepath)
    elif lower.endswith(".pdf"):
        return extract_text_from_pdf(filepath)
    elif lower.endswith(".txt"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return None


@lru_cache(maxsize=512)
def _cached_extract(filepath, mtime, size):
    return extract_text(filepath)


def extract_text_cached(filepath):
    """Same as extract_text, but remembers the result until the file changes. The dashboard asks for the
    same text many times (version recommendation, comparison view), and parsing a PDF each time is slow."""
    st = os.stat(filepath)
    return _cached_extract(filepath, st.st_mtime_ns, st.st_size)


def is_text_file(filepath):
    return filepath.lower().endswith(TEXT_EXTENSIONS)

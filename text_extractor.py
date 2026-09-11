import docx
import pdfplumber

TEXT_EXTENSIONS = (".docx", ".pdf", ".txt")


def extract_text_from_docx(filepath):
    document = docx.Document(filepath)
    return "\n".join(p.text for p in document.paragraphs)


def extract_text_from_pdf(filepath):
    full_text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text)


def extract_text(filepath):
    """Returns text content, or None if the file type isn't text-based."""
    lower = filepath.lower()
    if lower.endswith(".docx"):
        return extract_text_from_docx(filepath)
    elif lower.endswith(".pdf"):
        return extract_text_from_pdf(filepath)
    elif lower.endswith(".txt"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return None


def is_text_file(filepath):
    return filepath.lower().endswith(TEXT_EXTENSIONS)
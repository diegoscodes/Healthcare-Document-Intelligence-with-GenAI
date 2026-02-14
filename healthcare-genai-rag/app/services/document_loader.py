from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_pdf_pages_text(pdf_path: Path) -> list[str]:
    """
    Extract text per page from a text-based PDF.

    Returns a list where index 0 corresponds to page 1.
    For pages with no extractable text, an empty string is returned.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages_text: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

    return pages_text
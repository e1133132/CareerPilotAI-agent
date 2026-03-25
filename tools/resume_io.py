from __future__ import annotations

from pathlib import Path


def load_resume_text(path: str) -> str:
    """
    Minimal resume loader for workshop use.

    Supports:
    - Plain text files (UTF-8 / system default fallback)
    - PDF files (extracts text via `pypdf`)
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Resume file not found: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"Resume path is a directory: {p}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            from io import BytesIO

            from pypdf import PdfReader  # type: ignore
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(
                "PDF support requires `pypdf`. Please install it: `pip install pypdf`."
            ) from e

        pdf_bytes = p.read_bytes()
        reader = PdfReader(BytesIO(pdf_bytes))

        pages_text: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            t = t.strip()
            if t:
                pages_text.append(t)

        resume_text = "\n".join(pages_text).strip()
        if not resume_text:
            raise ValueError(
                "No extractable text found in the PDF. If your resume is scanned (images), OCR is required."
            )
        return resume_text

    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text()


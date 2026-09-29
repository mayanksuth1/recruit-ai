import io

import pdfplumber
from fastapi import HTTPException


# A resume is a few pages. A 10 MB PDF can still hold thousands of tiny
# pages, and layout extraction is slow per page, so an uncapped loop lets one
# upload pin a worker for minutes. Text past the cap is never read by scoring.
MAX_PAGES = 15
MAX_CHARS = 60_000


def extract_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:MAX_PAGES])[:MAX_CHARS]
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse PDF file")
    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No extractable text in PDF (scanned image resumes are not supported yet)",
        )
    return text

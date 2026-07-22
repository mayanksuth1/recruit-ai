import io

import pdfplumber
from fastapi import HTTPException


def extract_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse PDF file")
    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No extractable text in PDF (scanned image resumes are not supported yet)",
        )
    return text

"""Bounded PDF text extraction subprocess used by analysis.extract_upload."""
import json
import sys
from pypdf import PdfReader


def extract(path):
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return {"error": "Encrypted PDFs are not supported. Use an unlocked text extract."}
        if len(reader.pages) > 50:
            return {"error": "Use a PDF of at most 50 pages or upload a shorter text extract."}
        texts, size = [], 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            size += len(text)
            if size > 150000:
                return {"error": "PDF text exceeds 150,000 characters. Upload a shorter extract."}
            if text.strip():
                texts.append(f"[Page {number}]\n{text}")
        return {"text": "\n\n".join(texts)}
    except Exception:
        return {"error": "Could not parse this PDF. Try saving its text as a UTF-8 .txt file."}


if __name__ == "__main__":
    sys.stdout.buffer.write(json.dumps(extract(sys.argv[1])).encode("utf-8"))

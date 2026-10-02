"""Extract evidence passages with explicit rules; no generated facts or external AI."""
import re
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from html.parser import HTMLParser

MAX_TEXT = 150000
RULES = {
    "Scope of work": r"\b(scope|statement of work|performance work statement|shall provide|contractor shall|services|deliverables?|tasks?)\b",
    "Eligibility requirements": r"\b(eligible|eligibility|set.aside|small business|certif\w*|NAICS|SAM registration|registered in SAM|clearance|citizenship|HUBZone|8\(a\))\b",
    "Important dates": r"\b(deadline|due|closing|site visit|questions? by|period of performance|option years?|base years?|[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}|20[0-9]{2}-[0-9]{2}-[0-9]{2}|January|February|March|April|May|June|July|August|September|October|November|December)\b",
    "Required documents": r"\b(submit|submission|proposal|quotation|quote|resume|past performance|attachment|SF\s?1449|SF\s?33|representations|certifications|volume)\b",
    "Technical requirements": r"\b(technical|software|hardware|network\w*|cyber\w*|security|NIST|CMMC|FedRAMP|cloud|integration|Windows|Linux|SLA|uptime|encryption|help\s?desk)\b",
    "Potential bid concerns": r"\b(sole.source|brand.name|only one source|clearance|mandatory|must|shall not|not eligible|restricted|incumbent|on.site|bond|insurance|liquidated damages)\b",
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden-1)
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_to_text(value):
    parser = PlainText()
    parser.feed(value)
    return re.sub(r"\n\s*\n+", "\n\n", "".join(parser.parts)).strip()


def analyze_text(text):
    if not text.strip():
        return None
    clipped = len(text) > MAX_TEXT
    # Split into evidence units, retaining source order; never invent a summary sentence.
    passages = [p.strip() for p in re.split(r"\n\s*\n|(?<!U\.S\.)(?<!U\.S\.C\.)(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s+(?=[A-Z])", text[:MAX_TEXT]) if p.strip()]
    evidence = [{"ref": f"P{i+1}", "text": p} for i, p in enumerate(passages)]
    sections = []
    for name, rule in RULES.items():
        matches = [p for p in evidence if re.search(rule, p["text"], re.I)]
        sections.append({"name": name, "passages": matches[:12], "omitted": max(0, len(matches)-12)})
    summary = sections[0]["passages"][:3]
    return {"sections": sections, "summary": summary, "passages": evidence, "clipped": clipped,
            "characters": min(len(text), MAX_TEXT), "method": "Keyword rules v1; extractive evidence only"}


def extract_upload(file):
    suffix = Path(file.filename or "").suffix.lower()
    content = file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Files must be smaller than 5 MB.")
    if suffix == ".txt":
        try:
            result = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Save the text file with UTF-8 encoding.") from None
    elif suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("This file is not a valid PDF.")
        # Isolate parsing, bound the time, and delete temporary source bytes afterwards.
        with tempfile.TemporaryDirectory(prefix="fco-review-") as directory:
            path = Path(directory) / "document.pdf"
            path.write_bytes(content)
            try:
                completed = subprocess.run([sys.executable, "-m", "app.pdf_worker", str(path)],
                    cwd=Path(__file__).resolve().parent.parent, capture_output=True, timeout=20)
            except subprocess.TimeoutExpired:
                raise ValueError("PDF extraction exceeded 20 seconds. Upload a shorter text extract.") from None
            try:
                payload = json.loads(completed.stdout)
            except (ValueError, UnicodeDecodeError):
                raise ValueError("Could not read this PDF. Try a text extract.") from None
            if payload.get("error"):
                raise ValueError(payload["error"])
            result = payload.get("text", "")
    else:
        raise ValueError("Upload a .txt or text-based .pdf file.")
    if not result.strip():
        raise ValueError("No readable text found. Scanned PDFs require OCR before upload.")
    if len(result) > MAX_TEXT:
        raise ValueError("Use an extract of at most 150,000 characters; this document is too long.")
    return result.strip()

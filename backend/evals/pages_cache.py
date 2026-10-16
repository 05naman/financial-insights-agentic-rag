"""Parsing a long PDF takes minutes; experiments reuse a cached copy of the raw pages (data/ is git-ignored)."""

import json
from pathlib import Path

from app.ingestion.pdf_loader import load_pdf
from app.ingestion.schemas import PageContent

CACHE = Path(__file__).resolve().parents[1] / "data" / "cache"


def raw_pages(pdf: Path) -> list[PageContent]:
    """Pages exactly as extracted (before header stripping); re-parsed only if the PDF changed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"{pdf.stem}-{int(pdf.stat().st_mtime)}-{pdf.stat().st_size}.json"
    if key.exists():
        return [PageContent(**p) for p in json.loads(key.read_text())]
    pages = load_pdf(pdf, strip=False)
    key.write_text(json.dumps([{"page": p.page, "text": p.text} for p in pages]))
    return pages

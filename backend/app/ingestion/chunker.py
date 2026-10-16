import re
import uuid

from app.ingestion.classify import classify_chunk
from app.ingestion.schemas import Chunk, ChunkType, PageContent

_NAMESPACE = uuid.UUID("6f1f0a52-0c7e-4f4e-9a55-3c5f4b1d2a10")
MAX_TABLE_CHARS = 4000
MIN_CHUNK_CHARS = 30
TINY_TEXT_CHARS = 80  # a text chunk with less real text than this is just a heading or a page label
UNIT_HINT_CHARS = 200  # a short line before a table often holds the unit, e.g. "(₹ in Crores)"
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    """Split on paragraph boundaries into ~size char pieces with a small overlap."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > size:  # hard-split a paragraph that is itself too long
            if current:
                pieces.append(current)
                current = ""
            pieces.append(para[:size])
            para = para[size - overlap :]
        if current and len(current) + len(para) + 2 > size:
            pieces.append(current)
            current = current[-overlap:] + "\n\n" + para if overlap else para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def _split_table(md: str) -> list[str]:
    """Keep a table whole; if huge, split by rows and repeat the header rows."""
    if len(md) <= MAX_TABLE_CHARS:
        return [md]
    lines = md.splitlines()
    header, rows = lines[:2], lines[2:]
    out, cur = [], list(header)
    for row in rows:
        if sum(len(x) + 1 for x in cur) + len(row) > MAX_TABLE_CHARS and len(cur) > len(header):
            out.append("\n".join(cur))
            cur = list(header)
        cur.append(row)
    out.append("\n".join(cur))
    return out


def _segments(page_text: str) -> list[tuple[ChunkType, str, str]]:
    """Split page markdown into ('text'|'table', body, context) where context is the nearest
    heading plus a short preceding line (units), attached to tables so they stay interpretable."""
    out: list[tuple[ChunkType, str, str]] = []
    heading = ""
    prose: list[str] = []
    table: list[str] = []
    last_para = ""

    def flush_prose() -> None:
        nonlocal last_para
        if prose:
            body = "\n".join(prose).strip()
            if body:
                out.append(("text", body, ""))
                paras = [p for p in body.split("\n\n") if p.strip()]
                last_para = paras[-1].strip() if paras else ""
            prose.clear()

    def flush_table() -> None:
        if table:
            hint = last_para if 0 < len(last_para) <= UNIT_HINT_CHARS else ""
            context = "\n".join(x for x in (heading, hint) if x)
            out.append(("table", "\n".join(table), context))
            table.clear()

    for line in page_text.splitlines():
        if _is_table_line(line):
            flush_prose()
            table.append(line.strip())
            continue
        flush_table()
        if (m := _HEADING.match(line.strip())) is not None:
            heading = re.sub(r"[*_]+", "", m.group(1)).strip()
        prose.append(line)
    flush_prose()
    flush_table()
    return out


def chunk_pages(
    pages: list[PageContent],
    *,
    document_id: int,
    ticker: str,
    fiscal_year: int,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    drop_tiny_text: bool = False,
) -> list[Chunk]:
    chunks: list[Chunk] = []

    def add(text: str, page: int, kind: ChunkType, idx: int) -> None:
        if len(text.strip()) < MIN_CHUNK_CHARS:
            return
        cid = str(uuid.uuid5(_NAMESPACE, f"{document_id}:{page}:{kind}:{idx}"))
        chunks.append(
            Chunk(
                cid, text, ticker, fiscal_year, page, kind, document_id, classify_chunk(text, kind)
            )
        )

    for p in pages:
        counters = {"text": 0, "table": 0}
        segments = _segments(p.text)
        for kind, body, context in segments:
            real = re.sub(r"[#*_|\-\s]+", " ", body).strip()
            # a heading alone is already carried by the table that follows it, so it only adds noise
            if (
                drop_tiny_text
                and kind == "text"
                and len(real) < TINY_TEXT_CHARS
                and len(segments) > 1
            ):
                continue
            pieces = (
                _split_text(body, chunk_size, chunk_overlap)
                if kind == "text"
                else _split_table(body)
            )
            for piece in pieces:
                text = f"{context}\n\n{piece}" if context and kind == "table" else piece
                add(text, p.page, kind, counters[kind])
                counters[kind] += 1
    return chunks

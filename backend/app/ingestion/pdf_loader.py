import re
from collections import Counter
from pathlib import Path

import pymupdf4llm

from app.ingestion.schemas import PageContent

_MIN_PAGES_FOR_BOILERPLATE = 8
_BOILERPLATE_SHARE = 0.4  # a line on >=40% of pages is a running header/footer
_BLANKS = re.compile(r"\n{3,}")


# Some PDFs letter-space their bold rows, and the text layer then reads "2, 7 1, 423" for 2,71,423.
_SPACED = re.compile(r"\d[ ,.]|[ ,.]\d|\( \d|\d \)")
_NUMBER_CELL = re.compile(r"^\(?\s*-?\d[\d,. ]*\d%?\)?$")
_GROUPED = re.compile(r"^\(?-?(\d{1,3}(,\d{2,3})+|\d{1,4})(\.\d+)?%?\)?$")


def repair_spaced_numbers(markdown: str) -> str:
    """Close stray spaces inside numbers in table cells ('49, 454' -> '49,454') so figures can be searched,
    quoted and verified. Only whole-cell numbers are touched, and only if the result is a valid grouping, so
    two separate numbers are never glued together."""
    out: list[str] = []
    for line in markdown.splitlines():
        if not line.lstrip().startswith("|"):
            out.append(line)
            continue
        cells = line.split("|")
        for i, cell in enumerate(cells):
            core = cell.replace("*", "").strip()
            if " " not in core or not _NUMBER_CELL.match(core) or not _SPACED.search(core):
                continue
            fixed = re.sub(r"\s+", "", core)
            if not _GROUPED.match(fixed):
                continue  # e.g. "2025 2026": two numbers, leave alone
            bold = "**" if "**" in cell else ""
            cells[i] = f"{bold}{fixed}{bold}"
        out.append("|".join(cells))
    return "\n".join(out)


_BOLD = re.compile(r"\*\*([^*|\n]*?)\*\*")
_UNIT_RUPEE = re.compile(
    r"(?:\(\s*)?`?\bH`?\s*(?=crores?\b|lakhs?\b|millions?\b|billions?\b)", re.IGNORECASE
)
_SPLIT_CAPITAL = re.compile(r"\b([B-HJ-Z]) ([a-z]{2,})\b")
_WORD_RE = re.compile(r"[a-z]{4,}")
_CAPS_RUN = re.compile(r"\b[A-Z]{1,6}(?: [A-Z]{1,6}){1,5}\b")  # e.g. "TOTAL IN COME"
_CAPS_FIXES = (
    (re.compile(r"\bAN D\b"), "AND"),
    (re.compile(r"\bTH E\b"), "THE"),
    (re.compile(r"\bFO R\b"), "FOR"),
)
_MIN_JOINED = 5  # a joined word shorter than this is too likely to be a real pair of words
_MIN_WORD_COUNT = 3


def _balance_bold(text: str) -> str:
    """`**Y **` is not bold in markdown and prints its asterisks: move the spaces outside the markers."""

    def fix(m: re.Match[str]) -> str:
        inner = m.group(1)
        core = inner.strip()
        if not core:
            return inner
        lead, trail = inner[: len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()) :]
        return f"{lead}**{core}**{trail}"

    return _BOLD.sub(fix, text)


def repair_markdown_artifacts(pages: list[PageContent]) -> list[PageContent]:
    """Clean extraction artifacts that hurt both reading and search:

    - broken bold markers (`**Y **`)
    - a rupee sign read as "H" in unit lines: "(`H`crores)" -> "(₹ crores)"
    - letter-spaced words ("Y ear", "N ote"): rejoined only when the joined word is common in this very
      document and the fragment after the capital is not itself a word."""
    vocab: Counter[str] = Counter()
    for p in pages:
        vocab.update(_WORD_RE.findall(p.text.lower()))
    known = {w for w, n in vocab.items() if n >= _MIN_WORD_COUNT}

    def merge(m: re.Match[str]) -> str:
        head, rest = m.group(1), m.group(2)
        return head + rest if (head + rest).lower() in known and rest not in known else m.group(0)

    def join_caps(m: re.Match[str]) -> str:
        """In an all-caps run, glue fragments back together when the result is a word of this document."""
        toks = m.group(0).split(" ")
        out_toks: list[str] = []
        i = 0
        while i < len(toks):
            for k in (4, 3, 2):
                group = toks[i : i + k]
                joined = "".join(group)
                if (
                    len(group) == k
                    and len(joined) >= _MIN_JOINED
                    and joined.lower() in known
                    and any(len(t) <= 3 for t in group)
                ):
                    out_toks.append(joined)
                    i += k
                    break
            else:
                out_toks.append(toks[i])
                i += 1
        return " ".join(out_toks)

    out = []
    for p in pages:
        text = _balance_bold(p.text)
        text = _CAPS_RUN.sub(join_caps, text)
        for pattern, fixed in _CAPS_FIXES:
            text = pattern.sub(fixed, text)
        text = _UNIT_RUPEE.sub(
            lambda m: "(₹ " if m.group(0).lstrip().startswith("(") else "₹ ", text
        )
        text = _SPLIT_CAPITAL.sub(merge, text)
        out.append(PageContent(p.page, text))
    return out


def _norm(line: str) -> str:
    return re.sub(r"[\s*_#]+", " ", line).strip().lower()


def strip_boilerplate(
    pages: list[PageContent],
    min_pages: int = _MIN_PAGES_FOR_BOILERPLATE,
    share: float = _BOILERPLATE_SHARE,
) -> list[PageContent]:
    """Remove running headers/footers (short non-table lines repeated across many pages)."""
    if len(pages) < min_pages:
        return pages
    counts: Counter[str] = Counter()
    for p in pages:
        counts.update({_norm(ln) for ln in p.text.splitlines() if _is_candidate(ln)})
    cutoff = max(3, int(len(pages) * share))
    repeated = {line for line, n in counts.items() if n >= cutoff}
    cleaned = []
    for p in pages:
        lines = [
            ln for ln in p.text.splitlines() if not (_is_candidate(ln) and _norm(ln) in repeated)
        ]
        cleaned.append(PageContent(p.page, _BLANKS.sub("\n\n", "\n".join(lines)).strip()))
    return cleaned


def _is_candidate(line: str) -> bool:
    s = line.strip()
    return bool(s) and len(s) < 100 and not s.startswith(("|", "#"))


def load_pdf(
    path: str | Path, *, strip: bool = True, boilerplate_share: float = _BOILERPLATE_SHARE
) -> list[PageContent]:
    """Extract per-page markdown using layout analysis (tables keep their row labels)."""
    chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False)
    pages = [
        PageContent(
            page=c["metadata"].get("page_number", i), text=repair_spaced_numbers(c["text"].strip())
        )
        for i, c in enumerate(chunks, start=1)
    ]
    pages = repair_markdown_artifacts(pages)
    return strip_boilerplate(pages, share=boilerplate_share) if strip else pages

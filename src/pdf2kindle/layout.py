"""Turn per-page lines into a flat sequence of reflowable blocks for the whole book."""

import re
from collections import Counter
from dataclasses import dataclass, field

from pdf2kindle import bengali
from pdf2kindle.model import Figure, Line, PageMode, PageResult, TocEntry

NOISE_ZONE = 0.1  # top/bottom share of the page where running headers/footers live
_DIGITS = re.compile(r"[0-9০-৯]+")
_PAGE_NUMBER = re.compile(r"^[\s\-–—(\[]*([0-9০-৯]+|[ivxlcdm]+)[\s\-–—)\]]*$", re.IGNORECASE)
_NOTE_MARK = re.compile(r"^([0-9০-৯]+|[*†‡§])")
_TERMINAL = tuple(".!?।॥:;\"'”’)»…")


@dataclass
class Block:
    kind: str  # "p" | "h" | "figure" | "page"
    page: int
    text: str = ""
    level: int = 0  # headings: 1 or 2
    lang: str = "en"
    figure: Figure | None = None
    notes: list[str] = field(default_factory=list)  # footnotes found on this block's page


def body_size(pages: list[PageResult]) -> float:
    sizes: Counter[float] = Counter()
    for page in pages:
        if page.mode == PageMode.TEXT:
            for line in page.lines:
                sizes[round(line.size)] += len(line.text)
    return float(sizes.most_common(1)[0][0]) if sizes else 12.0


def _noise_key(text: str) -> str:
    return _DIGITS.sub("#", text.strip().lower())


def find_noise(pages: list[PageResult]) -> set[tuple[int, int]]:
    """(page index, line index) of running headers, footers and bare page numbers."""
    text_pages = [p for p in pages if p.mode == PageMode.TEXT and p.lines]
    zone: list[tuple[int, int, str]] = []
    for page in text_pages:
        for i, line in enumerate(page.lines):
            if line.bottom < page.height * NOISE_ZONE or line.top > page.height * (1 - NOISE_ZONE):
                zone.append((page.index, i, line.text))
    seen: Counter[str] = Counter()
    for key in {(p, _noise_key(t)) for p, _, t in zone}:
        seen[key[1]] += 1
    repeat = max(3, int(0.3 * len(text_pages)))
    return {(p, i) for p, i, t in zone if seen[_noise_key(t)] >= repeat or _PAGE_NUMBER.match(t)}


def _split_notes(lines: list[Line], body: float) -> tuple[list[Line], list[str]]:
    """Footnotes: the page's trailing run of small lines, starting with a marker."""
    cut = len(lines)
    while cut > 0 and lines[cut - 1].size < 0.85 * body:
        cut -= 1
    for start in range(cut, len(lines)):
        if _NOTE_MARK.match(lines[start].text):
            notes: list[str] = []
            for line in lines[start:]:
                if _NOTE_MARK.match(line.text) or not notes:
                    notes.append(line.text)
                else:
                    notes[-1] = _join(notes[-1], line.text)
            return lines[:start], notes
    return lines, []


def _join(left: str, right: str) -> str:
    """Join two wrapped lines, undoing end-of-line hyphenation."""
    if left.endswith("-") and len(left) > 1 and left[-2].isalpha() and right[:1].islower():
        return left[:-1] + right
    if left.endswith("-") and right[:1] and bengali.is_bengali_char(right[0]):
        return left[:-1] + right
    return f"{left} {right}"


def _heading_level(line: Line, body: float) -> int:
    if len(line.text) > 120 or line.size < 1.3 * body:
        return 0
    return 1 if line.size >= 1.6 * body else 2


def _page_blocks(page: PageResult, lines: list[Line], body: float) -> list[Block]:
    blocks: list[Block] = []
    left = min((ln.x0 for ln in lines), default=0)
    right = max((ln.x1 for ln in lines), default=page.width)
    gaps = sorted(b.top - a.bottom for a, b in zip(lines, lines[1:], strict=False))
    normal_gap = gaps[len(gaps) // 2] if gaps else 0
    figures = sorted(page.figures, key=lambda f: f.top)
    prev: Line | None = None
    for line in lines:
        while figures and figures[0].top < line.top:
            blocks.append(Block("figure", page.index, figure=figures.pop(0)))
            prev = None
        level = _heading_level(line, body)
        last = blocks[-1] if blocks else None
        if level:
            if last and last.kind == "h" and prev and prev.size == line.size:
                last.text = f"{last.text} {line.text}"
            else:
                blocks.append(Block("h", page.index, line.text, level=level))
        elif (
            last is None
            or last.kind != "p"
            or prev is None
            or line.group != prev.group
            or line.top - prev.bottom > max(normal_gap * 1.8, prev.size * 0.5)
            or line.x0 - left > line.size * 0.8
            or (prev.x1 < right - 4 * prev.size and prev.text.endswith(_TERMINAL))
        ):
            blocks.append(Block("p", page.index, line.text))
        else:
            last.text = _join(last.text, line.text)
        prev = line
    blocks.extend(Block("figure", page.index, figure=f) for f in figures)
    return blocks


def build_blocks(
    pages: list[PageResult], strip_noise: bool = True, lang: str | None = None
) -> list[Block]:
    body = body_size(pages)
    noise = find_noise(pages) if strip_noise else set()
    out: list[Block] = []
    for page in sorted(pages, key=lambda p: p.index):
        if page.mode == PageMode.IMAGE:
            out.append(Block("page", page.index))
            continue
        lines = [ln for i, ln in enumerate(page.lines) if (page.index, i) not in noise]
        lines, notes = _split_notes(lines, body)
        blocks = _page_blocks(page, lines, body)
        if blocks and out and _continues(out[-1], blocks[0]):
            out[-1].text = _join(out[-1].text, blocks.pop(0).text)
        if notes:
            (blocks or out or [Block("p", page.index)])[-1].notes.extend(notes)
        out.extend(blocks)
    for block in out:
        if block.text:
            block.lang = lang or bengali.detect_lang(block.text)
    return out


def _continues(prev: Block, nxt: Block) -> bool:
    """A paragraph running over a page break."""
    return (
        prev.kind == "p"
        and nxt.kind == "p"
        and nxt.page == prev.page + 1
        and not prev.text.endswith(_TERMINAL)
    )


def headings_toc(blocks: list[Block]) -> list[TocEntry]:
    return [TocEntry(b.text, b.page, b.level) for b in blocks if b.kind == "h"]

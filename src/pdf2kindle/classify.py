"""Decide each page's kind: Text, Legacy-Encoded, Scanned or Complex."""

import re
from dataclasses import dataclass

from pdf2kindle import bengali
from pdf2kindle.legacy import bijoy
from pdf2kindle.model import Line, PageKind
from pdf2kindle.pdf import RawPage

MIN_TEXT_CHARS = 15
BROKEN_BENGALI = 0.02  # share of malformed Bengali words that marks a text layer as unusable
FAILED_LEGACY = 0.10
FULL_PAGE_IMAGE = 0.9  # a page this covered by one image is a scan, whatever text it carries
_WORD = re.compile(
    r"^[\"'“‘(\[]*([A-Za-z]+(?:['’-][A-Za-z]+)*|[0-9][0-9.,:/-]*)[\"'”’)\].,;:!?…-]*$"
)
_VOWEL = re.compile(r"[aeiouyAEIOUY]")
_MATH = set("∑∫√∂∞≈≠≤≥±×÷∏∆∇αβγδεθλμπσφω")


@dataclass
class Verdict:
    kind: PageKind
    reason: str
    needs_ocr: bool
    lines: list[Line]


def _rows(lines: list[Line]) -> list[list[Line]]:
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda ln: ln.top):
        if rows and abs(rows[-1][0].top - line.top) < 3:
            rows[-1].append(line)
        else:
            rows.append([line])
    return rows


def complex_reason(lines: list[Line], width: float) -> str:
    """Why this page's layout can't be reflowed, or '' if it can."""
    rows = _rows(lines)
    if len(rows) >= 6:
        table_rows = sum(1 for r in rows if len(r) >= 3)
        if table_rows >= 4 and table_rows / len(rows) >= 0.3:
            return "table layout"
        mid = width / 2
        split = sum(
            1 for r in rows if len(r) == 2 and min(ln.x1 for ln in r) < mid < max(ln.x0 for ln in r)
        )
        if len(rows) >= 8 and split / len(rows) >= 0.5:
            return "multi-column layout"
    text = "".join(ln.text for ln in lines)
    if text and sum(c in _MATH for c in text) / len(text) > 0.03:
        return "mathematical notation"
    return ""


def latin_plausibility(text: str) -> float:
    """Share of tokens that look like real words or numbers (1.0 for clean English).

    Scanners often embed an invisible OCR layer made with the wrong language; for a Bengali
    scan that layer is junk like `c+t torqat :o`, which fails this check.
    """
    tokens = text.split()
    if not tokens:
        return 1.0
    good = 0
    for token in tokens:
        m = _WORD.match(token)
        if m and (m[1][0].isdigit() or (_VOWEL.search(m[1]) and len(m[1]) <= 24)):
            good += 1
    return good / len(tokens)


def classify(raw: RawPage) -> Verdict:
    area = raw.width * raw.height
    image_cover = max(((f.x1 - f.x0) * (f.bottom - f.top) / area for f in raw.figures), default=0.0)
    if raw.chars < MIN_TEXT_CHARS:
        if image_cover > 0.5:
            return Verdict(PageKind.SCANNED, "no text layer", True, [])
        return Verdict(PageKind.TEXT, "blank page", False, raw.lines)

    text = raw.text
    scan = image_cover >= FULL_PAGE_IMAGE and raw.legacy_chars == 0
    if raw.legacy_chars > 0.3 * raw.chars or (
        not scan and bengali.bengali_ratio(text) < 0.1 and bijoy.bijoy_score(text) > 0.5
    ):
        lines = raw.lines
        if raw.legacy_chars <= 0.3 * raw.chars:  # detected by text shape, not font name
            lines = [_replace_text(ln, bijoy.to_unicode(ln.text)) for ln in lines]
        converted = "\n".join(ln.text for ln in lines)
        if bengali.invalid_sequence_ratio(converted) > FAILED_LEGACY:
            return Verdict(PageKind.LEGACY, "Bijoy remapping failed, OCR used", True, [])
        return _check_complex(Verdict(PageKind.LEGACY, "Bijoy text remapped", False, lines), raw)

    if bengali.bengali_ratio(text) > 0.3:
        visual = bengali.looks_visual_order(text)
        lines = (
            [_replace_text(ln, bengali.move_pre_kars(ln.text)) for ln in raw.lines]
            if visual
            else raw.lines
        )
        fixed = "\n".join(ln.text for ln in lines)
        if bengali.invalid_sequence_ratio(fixed) > BROKEN_BENGALI:
            return Verdict(PageKind.SCANNED, "broken Bengali text layer, OCR used", True, [])
        reason = "Bengali text, visual order fixed" if visual else "text layer"
        return _check_complex(Verdict(PageKind.TEXT, reason, False, lines), raw)

    if latin_plausibility(text) < (0.85 if scan else 0.5):
        reason = "scan with unreadable OCR layer" if scan else "unreadable text layer"
        return Verdict(PageKind.SCANNED, f"{reason}, OCR used", True, [])
    reason = "scan with existing OCR layer" if scan else "text layer"
    return _check_complex(Verdict(PageKind.TEXT, reason, False, raw.lines), raw)


def _check_complex(verdict: Verdict, raw: RawPage) -> Verdict:
    reason = complex_reason(verdict.lines, raw.width)
    if reason:
        return Verdict(PageKind.COMPLEX, reason, False, verdict.lines)
    return verdict


def _replace_text(line: Line, text: str) -> Line:
    return Line(**{**line.__dict__, "text": text})

"""Decide each page's kind: Text, Legacy-Encoded, Scanned or Complex."""

from dataclasses import dataclass

from pdf2kindle import bengali
from pdf2kindle.legacy import bijoy
from pdf2kindle.model import Line, PageKind
from pdf2kindle.pdf import RawPage

MIN_TEXT_CHARS = 15
BROKEN_BENGALI = 0.02  # share of malformed Bengali words that marks a text layer as unusable
FAILED_LEGACY = 0.10
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


def classify(raw: RawPage) -> Verdict:
    area = raw.width * raw.height
    image_cover = max(((f.x1 - f.x0) * (f.bottom - f.top) / area for f in raw.figures), default=0.0)
    if raw.chars < MIN_TEXT_CHARS:
        if image_cover > 0.5:
            return Verdict(PageKind.SCANNED, "no text layer", True, [])
        return Verdict(PageKind.TEXT, "blank page", False, raw.lines)

    text = raw.text
    if raw.legacy_chars > 0.3 * raw.chars or (
        bengali.bengali_ratio(text) < 0.1 and bijoy.bijoy_score(text) > 0.5
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

    return _check_complex(Verdict(PageKind.TEXT, "text layer", False, raw.lines), raw)


def _check_complex(verdict: Verdict, raw: RawPage) -> Verdict:
    reason = complex_reason(verdict.lines, raw.width)
    if reason:
        return Verdict(PageKind.COMPLEX, reason, False, verdict.lines)
    return verdict


def _replace_text(line: Line, text: str) -> Line:
    return Line(**{**line.__dict__, "text": text})

"""Reading a Source PDF: pypdfium2 for rendering/bookmarks/metadata, pdfminer for text."""

import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LAParams,
    LTAnno,
    LTChar,
    LTFigure,
    LTImage,
    LTPage,
    LTTextContainer,
    LTTextLine,
)
from PIL import Image

from pdf2kindle.legacy import bijoy
from pdf2kindle.model import Figure, Line, TocEntry

_SPACES = re.compile(r"[ \t ]+")
_BOLD = re.compile(r"bold|black|heavy|semibold|,b$", re.IGNORECASE)


@dataclass
class RawPage:
    """pdfminer's view of one page before classification."""

    index: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    chars: int = 0
    legacy_chars: int = 0

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


# PDFium is not thread-safe even across separate documents, so every call in the process
# (open, render, close, …) goes through this one lock.
_PDFIUM = threading.RLock()


class SourcePdf:
    """Thread-safe wrapper over pypdfium2."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = _PDFIUM
        with self._lock:
            self._doc = pdfium.PdfDocument(path)

    def close(self) -> None:
        with self._lock:
            self._doc.close()

    def __len__(self) -> int:
        with self._lock:
            return len(self._doc)

    def render(self, index: int, dpi: float = 300, max_width: int | None = None) -> Image.Image:
        with self._lock:
            page = self._doc[index]
            scale = dpi / 72
            if max_width:
                scale = min(scale, max_width / page.get_width())
            image = page.render(scale=scale).to_pil().convert("RGB")
            page.close()
        return image

    def bookmarks(self) -> list[TocEntry]:
        entries = []
        with self._lock:
            for item in self._doc.get_toc():
                dest = item.get_dest()
                index = dest.get_index() if dest else None
                title = _SPACES.sub(" ", item.get_title() or "").strip()
                if index is None or not title:
                    continue
                entries.append(TocEntry(title=title, page=index, level=min(item.level + 1, 2)))
        return entries

    def metadata(self) -> dict[str, str]:
        with self._lock:
            meta = self._doc.get_metadata_dict(skip_empty=True)
        return {"title": meta.get("Title", "").strip(), "author": meta.get("Author", "").strip()}


def _line(obj: LTTextLine, height: float) -> tuple[Line | None, int, int]:
    """Build a Line, converting runs set in a Bijoy font; returns (line, chars, legacy)."""
    runs: list[tuple[bool, list[str]]] = []
    sizes: list[float] = []
    bold = 0
    chars = legacy = 0
    for ch in obj:
        if isinstance(ch, LTChar):
            is_legacy = bijoy.is_bijoy_font(ch.fontname)
            chars += 1
            legacy += is_legacy
            sizes.append(ch.size)
            bold += bool(_BOLD.search(ch.fontname))
        elif isinstance(ch, LTAnno):
            is_legacy = runs[-1][0] if runs else False
        else:
            continue
        text = ch.get_text()
        if text == "\n":
            continue
        if runs and runs[-1][0] == is_legacy:
            runs[-1][1].append(text)
        else:
            runs.append((is_legacy, [text]))
    text = "".join(bijoy.to_unicode("".join(t)) if lg else "".join(t) for lg, t in runs)
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return None, chars, legacy
    sizes.sort()
    line = Line(
        text=text,
        x0=obj.x0,
        x1=obj.x1,
        top=height - obj.y1,
        bottom=height - obj.y0,
        size=round(sizes[len(sizes) // 2], 2) if sizes else 0.0,
        bold=bold > chars / 2,
    )
    return line, chars, legacy


def _walk(page: LTPage, raw: RawPage) -> None:
    area = raw.width * raw.height

    def visit(obj) -> None:
        if isinstance(obj, LTTextLine):
            line, chars, legacy = _line(obj, raw.height)
            raw.chars += chars
            raw.legacy_chars += legacy
            if line:
                raw.lines.append(line)
        elif isinstance(obj, LTTextContainer):
            for child in obj:
                visit(child)
        elif isinstance(obj, LTFigure | LTImage):
            if obj.width * obj.height > 0.02 * area:
                raw.figures.append(Figure(obj.x0, obj.x1, raw.height - obj.y1, raw.height - obj.y0))
            elif isinstance(obj, LTFigure):
                for child in obj:
                    visit(child)

    for obj in page:
        visit(obj)
    raw.lines.sort(key=lambda ln: (round(ln.top), ln.x0))


def iter_raw_pages(path: Path, pages: set[int] | None = None) -> Iterator[RawPage]:
    """Yield every page's text lines and figure boxes, in one pass over the file."""
    params = LAParams(line_margin=0.3, char_margin=2.0, word_margin=0.1)
    for index, page in enumerate(extract_pages(path, laparams=params)):
        if pages is not None and index not in pages:
            continue
        raw = RawPage(index=index, width=page.width, height=page.height)
        _walk(page, raw)
        yield raw

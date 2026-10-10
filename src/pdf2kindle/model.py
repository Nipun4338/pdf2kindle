"""Plain data shared across the pipeline. Everything round-trips through JSON for caching."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class PageKind(StrEnum):
    TEXT = "text"
    LEGACY = "legacy"  # Legacy-Encoded Page
    SCANNED = "scanned"
    COMPLEX = "complex"


class PageMode(StrEnum):
    TEXT = "text"
    IMAGE = "image"  # Image Fallback


@dataclass
class Line:
    """One line of text with its position in PDF points, origin at the page's top-left."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool = False
    group: int = 0  # lines in different groups never share a paragraph


@dataclass
class Figure:
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class PageResult:
    """What analysing one Source PDF page produced; cached per page."""

    index: int
    kind: PageKind
    mode: PageMode
    width: float
    height: float
    lang: str = "en"
    confidence: float | None = None  # OCR confidence 0-100, None when no OCR ran
    reason: str = ""  # why this kind/mode was chosen, shown in the Conversion Report
    lines: list[Line] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PageResult":
        d = dict(d)
        d["kind"] = PageKind(d["kind"])
        d["mode"] = PageMode(d["mode"])
        d["lines"] = [Line(**ln) for ln in d.get("lines", [])]
        d["figures"] = [Figure(**f) for f in d.get("figures", [])]
        return cls(**d)


@dataclass
class TocEntry:
    title: str
    page: int  # 0-based Source PDF page index
    level: int = 1  # 1 = chapter (starts a new EPUB file), 2 = section inside it

    def to_dict(self) -> dict:
        return asdict(self)

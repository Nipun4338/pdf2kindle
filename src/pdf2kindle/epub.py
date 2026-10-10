"""Write a Kindle-friendly EPUB 3 (with an EPUB 2 NCX for older Kindles) by hand."""

import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from importlib import resources
from pathlib import Path

FONT_FILES = ("NotoSerifBengali-Regular.ttf", "NotoSerifBengali-Bold.ttf")

CSS = """\
body { margin: 0 2%; line-height: 1.5; }
p { margin: 0; text-indent: 1.5em; text-align: justify; }
h1, h2 { text-align: center; page-break-after: avoid; margin: 1.5em 0 1em; }
h1 { font-size: 1.6em; } h2 { font-size: 1.3em; }
h1 + p, h2 + p, .fig + p { text-indent: 0; }
.fig { text-align: center; margin: 1em 0; }
.fig img { max-width: 100%; }
.page { text-align: center; page-break-before: always; page-break-after: always; margin: 0; }
.page img { max-width: 100%; max-height: 100%; }
.notes { margin-top: 2em; border-top: 1px solid #000; font-size: 0.85em; }
.notes p { text-indent: 0; margin-bottom: 0.4em; }
.cover { text-align: center; margin: 0; } .cover img { max-width: 100%; max-height: 100%; }
"""
BENGALI_CSS = """\
@font-face { font-family: "Noto Serif Bengali"; font-weight: normal;
  src: url("fonts/NotoSerifBengali-Regular.ttf"); }
@font-face { font-family: "Noto Serif Bengali"; font-weight: bold;
  src: url("fonts/NotoSerifBengali-Bold.ttf"); }
.bn { font-family: "Noto Serif Bengali", serif; }
"""


@dataclass
class Chapter:
    """One XHTML file. `body` is ready-made XHTML; `anchors` are ids available for the TOC."""

    title: str
    body: str
    lang: str


@dataclass
class NavPoint:
    title: str
    chapter: int
    anchor: str | None
    level: int


@dataclass
class EpubBook:
    title: str
    author: str
    lang: str
    chapters: list[Chapter]
    nav: list[NavPoint]
    images: dict[str, bytes] = field(default_factory=dict)  # name → JPEG bytes
    cover: bytes | None = None
    embed_bengali_font: bool = False
    identifier: str = field(default_factory=lambda: f"urn:uuid:{uuid.uuid4()}")


def _xhtml(title: str, lang: str, body: str, css: bool = True) -> str:
    link = '<link rel="stylesheet" type="text/css" href="../style.css"/>' if css else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" '
        f'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">\n'
        f'<head><meta charset="utf-8"/><title>{escape(title)}</title>{link}</head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _chapter_file(i: int) -> str:
    return f"text/ch{i:04d}.xhtml"


def _nav_tree(points: list[NavPoint], href) -> str:
    """Nested <ol>/<li> list. A deeper entry only nests under an existing parent entry, so
    any sequence of levels (even one starting with a sub-section) gives valid XHTML."""
    roots: list[tuple[NavPoint, list]] = []
    for p in points:
        siblings, level = roots, 1
        while level < p.level and siblings:
            siblings = siblings[-1][1]
            level += 1
        siblings.append((p, []))

    def render(nodes: list[tuple[NavPoint, list]]) -> str:
        items = (
            f'<li><a href="{href(p)}">{escape(p.title)}</a>{render(kids) if kids else ""}</li>'
            for p, kids in nodes
        )
        return f"<ol>{''.join(items)}</ol>"

    return render(roots)


def _ncx(book: EpubBook, nav: list[NavPoint], href) -> str:
    points = []
    for n, p in enumerate(nav, 1):
        points.append(
            f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{escape(p.title)}</text>'
            f'</navLabel><content src="{href(p)}"/></navPoint>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="{escape(book.identifier)}"/></head>'
        f"<docTitle><text>{escape(book.title)}</text></docTitle>"
        f"<navMap>{''.join(points)}</navMap></ncx>"
    )


def write_epub(book: EpubBook, out: Path) -> int:
    """Write `book` to `out`; returns the file size in bytes."""
    nav_points = book.nav or [NavPoint(book.title, 0, None, 1)]

    def href(p: NavPoint) -> str:
        path = _chapter_file(p.chapter)
        return f"{path}#{p.anchor}" if p.anchor else path

    manifest: list[str] = []
    spine: list[str] = []
    files: dict[str, bytes | str] = {}

    files["style.css"] = CSS + (BENGALI_CSS if book.embed_bengali_font else "")
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')

    if book.cover:
        files["images/cover.jpg"] = book.cover
        manifest.append(
            '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" '
            'properties="cover-image"/>'
        )
        files["text/cover.xhtml"] = _xhtml(
            book.title,
            book.lang,
            '<div class="cover"><img src="../images/cover.jpg" alt=""/></div>',
        )
        manifest.append(
            '<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.append('<itemref idref="cover"/>')

    toc_body = (
        f'<nav epub:type="toc" id="toc"><h1>{escape(book.title)}</h1>'
        f"{_nav_tree(nav_points, href)}</nav>"
    )
    files["nav.xhtml"] = _xhtml(book.title, book.lang, toc_body, css=False)
    manifest.append(
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    )
    files["toc.ncx"] = _ncx(book, nav_points, href)
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

    for i, ch in enumerate(book.chapters):
        files[_chapter_file(i)] = _xhtml(ch.title or book.title, ch.lang, ch.body)
        manifest.append(
            f'<item id="ch{i:04d}" href="{_chapter_file(i)}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="ch{i:04d}"/>')

    for name, data in book.images.items():
        files[f"images/{name}"] = data
        manifest.append(
            f'<item id="img-{name.rsplit(".", 1)[0]}" href="images/{name}" '
            'media-type="image/jpeg"/>'
        )

    if book.embed_bengali_font:
        fonts = resources.files("pdf2kindle.assets") / "fonts"
        for n, name in enumerate(FONT_FILES):
            files[f"fonts/{name}"] = (fonts / name).read_bytes()
            manifest.append(f'<item id="font{n}" href="fonts/{name}" media-type="font/ttf"/>')

    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cover_meta = '<meta name="cover" content="cover-image"/>' if book.cover else ""
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" '
        f'xml:lang="{book.lang}">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="uid">{escape(book.identifier)}</dc:identifier>'
        f"<dc:title>{escape(book.title)}</dc:title>"
        f"<dc:creator>{escape(book.author or 'Unknown')}</dc:creator>"
        f"<dc:language>{book.lang}</dc:language>"
        f'<meta property="dcterms:modified">{modified}</meta>{cover_meta}'
        f"</metadata><manifest>{''.join(manifest)}</manifest>"
        f'<spine toc="ncx">{"".join(spine)}</spine></package>'
    )
    files["content.opf"] = opf

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
            zipfile.ZIP_DEFLATED,
        )
        for name, data in files.items():
            z.writestr(f"OEBPS/{name}", data, zipfile.ZIP_DEFLATED)
    tmp.replace(out)
    return out.stat().st_size

"""Blocks + TOC → an EpubBook: chapter splitting, anchors, figures and Image Fallback pages."""

import difflib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape

from PIL import Image, ImageOps

from pdf2kindle.epub import Chapter, EpubBook, NavPoint
from pdf2kindle.layout import Block
from pdf2kindle.model import TocEntry

KINDLE_WIDTH = 1264
MAX_BLOCKS_PER_FILE = 400
_LOOSE = re.compile(r"[\W_]+")


@dataclass
class ImageSettings:
    max_width: int = KINDLE_WIDTH
    quality: int = 80
    grayscale: bool = False


def jpeg(image: Image.Image, settings: ImageSettings) -> bytes:
    if image.width > settings.max_width:
        height = round(image.height * settings.max_width / image.width)
        image = image.resize((settings.max_width, height), Image.Resampling.LANCZOS)
    image = ImageOps.grayscale(image) if settings.grayscale else image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=settings.quality, optimize=True, progressive=False)
    return buf.getvalue()


def _similar(a: str, b: str) -> float:
    a, b = _LOOSE.sub("", a.lower()), _LOOSE.sub("", b.lower())
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def toc_targets(blocks: list[Block], toc: list[TocEntry]) -> list[tuple[int, TocEntry]]:
    """Map each TOC entry to the block where it starts, in reading order."""
    targets: list[tuple[int, TocEntry]] = []
    used: set[int] = set()
    for entry in toc:
        on_page = [i for i, b in enumerate(blocks) if b.page == entry.page and i not in used]
        best = max(
            (i for i in on_page if blocks[i].kind == "h"),
            key=lambda i: _similar(blocks[i].text, entry.title),
            default=None,
        )
        if best is None or _similar(blocks[best].text, entry.title) < 0.6:
            after = [i for i, b in enumerate(blocks) if b.page >= entry.page and i not in used]
            best = on_page[0] if on_page else (after[0] if after else None)
        if best is None:
            continue
        used.add(best)
        targets.append((best, entry))
    return sorted(targets, key=lambda t: t[0])


def assemble(
    blocks: list[Block],
    toc: list[TocEntry],
    *,
    title: str,
    author: str,
    lang: str,
    render_page: Callable[[int, int], Image.Image],
    page_widths: dict[int, float],
    image_settings: ImageSettings,
    cover: bytes | None,
) -> EpubBook:
    """`render_page(index, width_px)` renders a Source PDF page; `page_widths` are in points."""
    targets = toc_targets(blocks, toc)
    anchor_at = {i: f"toc{n}" for n, (i, _) in enumerate(targets)}
    starts = sorted({0, *(i for i, e in targets if e.level == 1)})

    images: dict[str, bytes] = {}
    chapters: list[Chapter] = []
    nav: list[NavPoint] = []
    chapter_of: dict[int, int] = {}

    def figure_html(block: Block) -> str:
        fig = block.figure
        page = render_page(block.page, KINDLE_WIDTH * 2)
        scale = page.width / page_widths[block.page]
        crop = page.crop(
            (
                int(fig.x0 * scale),
                int(fig.top * scale),
                int(fig.x1 * scale),
                int(fig.bottom * scale),
            )
        )
        name = f"fig{len(images):04d}.jpg"
        images[name] = jpeg(crop, image_settings)
        return f'<div class="fig"><img src="../images/{name}" alt=""/></div>'

    def page_html(block: Block) -> str:
        name = f"page{block.page + 1:04d}.jpg"
        images[name] = jpeg(render_page(block.page, image_settings.max_width), image_settings)
        return f'<div class="page"><img src="../images/{name}" alt="Page {block.page + 1}"/></div>'

    for c, start in enumerate(starts):
        end = starts[c + 1] if c + 1 < len(starts) else len(blocks)
        for chunk_start in range(start, max(end, start + 1), MAX_BLOCKS_PER_FILE):
            chunk = range(chunk_start, min(end, chunk_start + MAX_BLOCKS_PER_FILE))
            parts: list[str] = []
            notes: list[str] = []
            for i in chunk:
                block = blocks[i]
                chapter_of[i] = len(chapters)
                attr = f' id="{anchor_at[i]}"' if i in anchor_at else ""
                cls = ' class="bn"' if block.lang == "bn" else ""
                if block.kind == "h":
                    tag = f"h{block.level}"
                    parts.append(
                        f'<{tag}{attr}{cls} lang="{block.lang}">{escape(block.text)}</{tag}>'
                    )
                elif block.kind == "p":
                    parts.append(f'<p{attr}{cls} lang="{block.lang}">{escape(block.text)}</p>')
                elif block.kind == "figure":
                    parts.append(f"<div{attr}></div>" if attr else "")
                    parts.append(figure_html(block))
                elif block.kind == "page":
                    parts.append(f"<div{attr}></div>" if attr else "")
                    parts.append(page_html(block))
                notes.extend(block.notes)
            if notes:
                note_cls = ' class="bn"' if lang == "bn" else ""
                parts.append(
                    '<div class="notes">'
                    + "".join(f"<p{note_cls}>{escape(n)}</p>" for n in notes)
                    + "</div>"
                )
            chapter_title = next((e.title for i, e in targets if i == chunk_start), title)
            chapters.append(Chapter(chapter_title, "\n".join(p for p in parts if p), lang))

    for i, entry in targets:
        chapter = chapter_of.get(i, 0)
        is_file_start = entry.level == 1
        nav.append(
            NavPoint(entry.title, chapter, None if is_file_start else anchor_at[i], entry.level)
        )

    return EpubBook(
        title=title,
        author=author,
        lang=lang,
        chapters=chapters or [Chapter(title, "<p></p>", lang)],
        nav=nav,
        images=images,
        cover=cover,
        embed_bengali_font=any(b.lang == "bn" for b in blocks),
    )

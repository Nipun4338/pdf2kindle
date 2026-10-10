"""Conversions: on-disk storage, the background pipeline, export and retention."""

import io
import json
import logging
import os
import queue
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image

from pdf2kindle import bengali, classify, layout
from pdf2kindle.assemble import ImageSettings, assemble, jpeg
from pdf2kindle.epub import write_epub
from pdf2kindle.model import PageKind, PageMode, PageResult, TocEntry
from pdf2kindle.ocr import OCR_DPI, Engine, default_engine, preprocess
from pdf2kindle.pdf import SourcePdf, iter_raw_pages

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 70.0
MAX_EPUB_BYTES = 50 * 1024 * 1024
# Progressively smaller images until the book fits Send-to-Kindle's email limit.
SIZE_STEPS = [(1264, 80), (1264, 60), (1000, 50), (800, 40)]


class Status:
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class Settings:
    lang: str = "auto"  # auto | bn | en
    strip_noise: bool = True
    grayscale: bool = False


class Store:
    """One folder per Conversion under `root`."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def dir(self, cid: str) -> Path:
        if not cid.isalnum():
            raise KeyError(cid)
        return self.root / cid

    def create(self, filename: str, pdf: bytes, settings: Settings) -> str:
        cid = uuid.uuid4().hex[:12]
        d = self.dir(cid)
        (d / "pages").mkdir(parents=True)
        (d / "source.pdf").write_bytes(pdf)
        self.save(
            cid,
            {
                "id": cid,
                "filename": filename,
                "created": datetime.now(UTC).isoformat(),
                "status": Status.QUEUED,
                "error": "",
                "progress": {"done": 0, "total": 0},
                "settings": settings.__dict__,
                "metadata": {"title": Path(filename).stem, "author": ""},
                "toc": [],
                "overrides": {},
                "cover": "page1",
                "exported": None,
            },
        )
        return cid

    def load(self, cid: str) -> dict:
        path = self.dir(cid) / "meta.json"
        if not path.exists():
            raise KeyError(cid)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, cid: str, meta: dict) -> None:
        path = self.dir(cid) / "meta.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def update(self, cid: str, **changes) -> dict:
        with self._lock:
            meta = self.load(cid)
            meta.update(changes)
            self.save(cid, meta)
            return meta

    def all(self) -> list[dict]:
        metas = []
        for d in self.root.iterdir():
            try:
                metas.append(self.load(d.name))
            except (KeyError, ValueError, OSError):
                continue
        return sorted(metas, key=lambda m: m["created"], reverse=True)

    def delete(self, cid: str) -> None:
        shutil.rmtree(self.dir(cid), ignore_errors=True)

    def page_path(self, cid: str, index: int) -> Path:
        return self.dir(cid) / "pages" / f"{index:05d}.json"

    def pages(self, cid: str) -> list[PageResult]:
        files = sorted((self.dir(cid) / "pages").glob("*.json"))
        return [PageResult.from_dict(json.loads(f.read_text(encoding="utf-8"))) for f in files]

    def save_page(self, cid: str, page: PageResult) -> None:
        path = self.page_path(cid, page.index)
        path.write_text(json.dumps(page.to_dict(), ensure_ascii=False), encoding="utf-8")

    def purge_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        removed = 0
        for meta in self.all():
            if datetime.fromisoformat(meta["created"]) < cutoff:
                self.delete(meta["id"])
                removed += 1
        return removed


# --- pipeline -------------------------------------------------------------------------


def _ocr_langs(engine: Engine, setting: str) -> str:
    wanted = {"bn": ["ben"], "en": ["eng"]}.get(setting, ["ben", "eng"])
    available = getattr(engine, "languages", lambda: set(wanted))()
    langs = [lang for lang in wanted if lang in available] or ["eng"]
    return "+".join(langs)


def ocr_page(
    src: SourcePdf, index: int, width: float, height: float, engine: Engine, langs: str
) -> tuple[list, float]:
    image = preprocess(src.render(index, dpi=OCR_DPI), OCR_DPI)
    lines, confidence = engine.recognize(image, langs)
    # Pixel → point coordinates (deskew may have grown the canvas slightly; close enough).
    sx, sy = width / image.width, height / image.height
    for ln in lines:
        ln.x0, ln.x1, ln.top, ln.bottom = ln.x0 * sx, ln.x1 * sx, ln.top * sy, ln.bottom * sy
        ln.size = ln.size * sy
    return lines, confidence


def analyse(
    store: Store, cid: str, engine: Engine | None = None, workers: int | None = None
) -> None:
    """Classify every page (OCR where needed), caching each page, then propose a TOC."""
    meta = store.update(cid, status=Status.PROCESSING, error="")
    settings = Settings(**meta["settings"])
    pdf_path = store.dir(cid) / "source.pdf"
    src = SourcePdf(pdf_path)
    engine = engine or default_engine()
    langs = _ocr_langs(engine, settings.lang) if engine.available() else ""
    total = len(src)
    cached = {i for i in range(total) if store.page_path(cid, i).exists()}
    done = len(cached)
    store.update(cid, progress={"done": done, "total": total})
    progress_lock = threading.Lock()

    def finish(page: PageResult) -> None:
        nonlocal done
        store.save_page(cid, page)
        with progress_lock:
            done += 1
            store.update(cid, progress={"done": done, "total": total})

    def run_ocr(page: PageResult) -> None:
        try:
            page.lines, page.confidence = ocr_page(
                src, page.index, page.width, page.height, engine, langs
            )
            text = "\n".join(ln.text for ln in page.lines)
            page.lang = bengali.detect_lang(text) if text else page.lang
            if page.confidence < MIN_CONFIDENCE:
                page.mode = PageMode.IMAGE
                page.reason += f"; low OCR confidence ({page.confidence:.0f}%)"
            else:
                page.mode = PageMode.TEXT
        except Exception as exc:  # one bad page must not sink the whole book
            log.exception("OCR failed on page %s", page.index)
            page.mode, page.reason = PageMode.IMAGE, f"{page.reason}; OCR error: {exc}"
        finish(page)

    pool = ThreadPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) // 2))
    futures = []
    try:
        for raw in iter_raw_pages(pdf_path, set(range(total)) - cached):
            verdict = classify.classify(raw)
            text = "\n".join(ln.text for ln in verdict.lines)
            page = PageResult(
                index=raw.index,
                kind=verdict.kind,
                mode=PageMode.IMAGE if verdict.kind == PageKind.COMPLEX else PageMode.TEXT,
                width=raw.width,
                height=raw.height,
                lang=bengali.detect_lang(text) if text else "en",
                reason=verdict.reason,
                lines=verdict.lines,
                figures=raw.figures if not verdict.needs_ocr else [],
            )
            if verdict.needs_ocr:
                if not langs:
                    page.mode = PageMode.IMAGE
                    page.reason += "; no OCR engine installed"
                    finish(page)
                else:
                    futures.append(pool.submit(run_ocr, page))
            else:
                finish(page)
        for f in futures:
            f.result()
    finally:
        pool.shutdown(wait=True)

    meta = store.load(cid)
    pdf_meta = src.metadata()
    toc = src.bookmarks()
    src.close()
    if not toc:
        blocks = layout.build_blocks(store.pages(cid), settings.strip_noise)
        toc = layout.headings_toc(blocks)
    store.update(
        cid,
        status=Status.READY,
        toc=[e.to_dict() for e in toc],
        metadata={
            "title": pdf_meta["title"] or meta["metadata"]["title"],
            "author": pdf_meta["author"] or meta["metadata"]["author"],
        },
    )


def effective_pages(store: Store, cid: str, meta: dict) -> list[PageResult]:
    """Cached pages with the user's text ↔ image overrides applied."""
    pages = store.pages(cid)
    for page in pages:
        override = meta["overrides"].get(str(page.index))
        if override:
            page.mode = PageMode(override)
    return pages


def book_lang(pages: list[PageResult], setting: str) -> str:
    if setting in ("bn", "en"):
        return setting
    weight = {"bn": 0, "en": 0}
    for p in pages:
        weight[p.lang] = weight.get(p.lang, 0) + sum(len(ln.text) for ln in p.lines)
    return "bn" if weight["bn"] > weight["en"] else "en"


def export(store: Store, cid: str) -> Path:
    meta = store.load(cid)
    settings = Settings(**meta["settings"])
    pages = effective_pages(store, cid, meta)
    lang = book_lang(pages, settings.lang)
    blocks = layout.build_blocks(
        pages, settings.strip_noise, lang=None if settings.lang == "auto" else settings.lang
    )
    toc = [TocEntry(**e) for e in meta["toc"]]
    src = SourcePdf(store.dir(cid) / "source.pdf")
    out = store.dir(cid) / "book.epub"
    try:

        def render(index: int, width: int) -> Image.Image:
            return src.render(index, dpi=400, max_width=width)

        cover_file = store.dir(cid) / "cover-upload"
        for max_width, quality in SIZE_STEPS:
            image_settings = ImageSettings(max_width, quality, settings.grayscale)
            cover_img = (
                Image.open(io.BytesIO(cover_file.read_bytes()))
                if meta["cover"] == "upload" and cover_file.exists()
                else render(0, max_width)
            )
            book = assemble(
                blocks,
                toc,
                title=meta["metadata"]["title"] or "Untitled",
                author=meta["metadata"]["author"],
                lang=lang,
                render_page=render,
                page_widths={p.index: p.width for p in pages},
                image_settings=image_settings,
                cover=jpeg(cover_img, image_settings),
            )
            size = write_epub(book, out)
            if size <= MAX_EPUB_BYTES:
                break
    finally:
        src.close()
    store.update(cid, exported=datetime.now(UTC).isoformat())
    return out


# --- background worker ----------------------------------------------------------------


class Worker:
    """Runs Conversions one at a time, in arrival order, on a daemon thread."""

    def __init__(self, store: Store, engine_factory=default_engine, retention_days: int = 30):
        self.store = store
        self.engine_factory = engine_factory
        self.retention_days = retention_days
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="conversions")
        self._last_purge = 0.0

    def start(self) -> None:
        for meta in reversed(self.store.all()):  # resume anything interrupted by a restart
            if meta["status"] in (Status.QUEUED, Status.PROCESSING):
                self._queue.put(meta["id"])
        self._thread.start()

    def submit(self, cid: str) -> None:
        self._queue.put(cid)

    def _purge(self) -> None:
        if time.monotonic() - self._last_purge > 3600:
            self._last_purge = time.monotonic()
            removed = self.store.purge_older_than(self.retention_days)
            if removed:
                log.info("removed %d conversions older than %d days", removed, self.retention_days)

    def _run(self) -> None:
        while True:
            self._purge()
            try:
                cid = self._queue.get(timeout=60)
            except queue.Empty:
                continue
            try:
                analyse(self.store, cid, self.engine_factory())
            except KeyError:
                continue  # deleted while queued
            except Exception as exc:
                log.exception("conversion %s failed", cid)
                try:
                    self.store.update(cid, status=Status.FAILED, error=str(exc))
                except KeyError:
                    pass

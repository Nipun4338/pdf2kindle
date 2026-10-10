"""The local web UI: upload → progress → review (Conversion Report, TOC, metadata) → download."""

import io
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pdf2kindle.conversion import Settings, Status, Store, Worker, effective_pages, export
from pdf2kindle.model import PageMode
from pdf2kindle.ocr import default_engine
from pdf2kindle.pdf import SourcePdf

HERE = Path(__file__).parent
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB


def default_data_dir() -> Path:
    return Path(os.environ.get("PDF2KINDLE_DATA_DIR", Path.home() / ".pdf2kindle"))


def create_app(
    data_dir: Path | None = None, engine_factory=default_engine, retention_days: int | None = None
) -> FastAPI:
    store = Store((data_dir or default_data_dir()) / "conversions")
    days = retention_days or int(os.environ.get("PDF2KINDLE_RETENTION_DAYS", "30"))
    worker = Worker(store, engine_factory, days)
    templates = Jinja2Templates(directory=HERE / "templates")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker.start()
        yield

    app = FastAPI(title="pdf2kindle", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.state.store, app.state.worker = store, worker

    def load(cid: str) -> dict:
        try:
            return store.load(cid)
        except KeyError:
            raise HTTPException(404, "No such conversion") from None

    def back(cid: str, anchor: str = "") -> RedirectResponse:
        return RedirectResponse(f"/conversions/{cid}{anchor}", status_code=303)

    @app.get("/")
    def index(request: Request):
        engine = engine_factory()
        return templates.TemplateResponse(
            request,
            "index.html",
            {"conversions": store.all(), "ocr": engine.available(), "retention": days},
        )

    @app.post("/conversions")
    async def create(
        file: Annotated[UploadFile, File()],
        lang: Annotated[str, Form()] = "auto",
        strip_noise: Annotated[bool, Form()] = False,
        grayscale: Annotated[bool, Form()] = False,
    ):
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "PDF is larger than 1 GB")
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "That file is not a PDF")
        settings = Settings(
            lang if lang in ("auto", "bn", "en") else "auto", strip_noise, grayscale
        )
        cid = store.create(file.filename or "book.pdf", data, settings)
        worker.submit(cid)
        return back(cid)

    @app.get("/conversions/{cid}")
    def show(request: Request, cid: str):
        meta = load(cid)
        pages = effective_pages(store, cid, meta) if meta["status"] == Status.READY else []
        epub = store.dir(cid) / "book.epub"
        return templates.TemplateResponse(
            request,
            "conversion.html",
            {
                "c": meta,
                "pages": pages,
                "image_pages": sum(p.mode == PageMode.IMAGE for p in pages),
                "epub_size": epub.stat().st_size if epub.exists() else None,
            },
        )

    @app.get("/conversions/{cid}/status")
    def status(cid: str):
        meta = load(cid)
        return JSONResponse({"status": meta["status"], "error": meta["error"], **meta["progress"]})

    @app.post("/conversions/{cid}/settings")
    async def save_settings(request: Request, cid: str):
        meta = load(cid)
        form = await request.form()
        meta["metadata"] = {
            "title": str(form.get("title", "")).strip(),
            "author": str(form.get("author", "")).strip(),
        }
        meta["settings"]["strip_noise"] = "strip_noise" in form
        meta["settings"]["grayscale"] = "grayscale" in form
        toc = []
        for key in form:
            m = re.fullmatch(r"toc_title_(\d+)", key)
            if not m or f"toc_delete_{m[1]}" in form:
                continue
            title = str(form[key]).strip()
            try:
                page = int(form.get(f"toc_page_{m[1]}", 0)) - 1
                level = 2 if form.get(f"toc_level_{m[1]}") == "2" else 1
            except ValueError:
                continue
            if title and 0 <= page < meta["progress"]["total"]:
                toc.append({"title": title, "page": page, "level": level})
        meta["toc"] = sorted(toc, key=lambda e: e["page"])
        cover = form.get("cover_file")
        if cover is not None and getattr(cover, "filename", ""):
            (store.dir(cid) / "cover-upload").write_bytes(await cover.read())
            meta["cover"] = "upload"
        elif form.get("cover") == "page1":
            meta["cover"] = "page1"
        store.update(cid, **{k: meta[k] for k in ("metadata", "settings", "toc", "cover")})
        if "export" in form:
            export(store, cid)
            return back(cid, "#download")
        return back(cid, "#review")

    @app.post("/conversions/{cid}/pages/{index}/mode")
    def toggle_mode(cid: str, index: int):
        meta = load(cid)
        page = next((p for p in effective_pages(store, cid, meta) if p.index == index), None)
        if page is None:
            raise HTTPException(404, "No such page")
        new = PageMode.TEXT if page.mode == PageMode.IMAGE else PageMode.IMAGE
        overrides = {**meta["overrides"], str(index): new.value}
        store.update(cid, overrides=overrides)
        return back(cid, f"#page-{index}")

    @app.get("/conversions/{cid}/pages/{index}.jpg")
    def thumbnail(cid: str, index: int):
        load(cid)
        src = SourcePdf(store.dir(cid) / "source.pdf")
        try:
            if not 0 <= index < len(src):
                raise HTTPException(404, "No such page")
            image = src.render(index, dpi=72, max_width=360)
        finally:
            src.close()
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=70)
        return Response(
            buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"}
        )

    @app.get("/conversions/{cid}/book.epub")
    def download(cid: str):
        meta = load(cid)
        path = store.dir(cid) / "book.epub"
        if not path.exists():
            raise HTTPException(404, "Export the book first")
        name = re.sub(r'[\\/:*?"<>|]+', "", meta["metadata"]["title"]).strip() or "book"
        return FileResponse(path, media_type="application/epub+zip", filename=f"{name}.epub")

    @app.post("/conversions/{cid}/delete")
    def delete(cid: str):
        load(cid)
        store.delete(cid)
        return RedirectResponse("/", status_code=303)

    return app

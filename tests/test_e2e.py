"""Drive the real app in Chromium: upload → progress → review → build → download."""

import socket
import threading
import time

import pytest
import uvicorn

from pdf2kindle.web import create_app
from tests.conftest import epub_text

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(tmp_path_factory.mktemp("data"))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def convert_in_ui(browser, server, pdf, tmp_path, title):
    page = browser.new_page()
    page.goto(server)
    page.set_input_files("#file", str(pdf))
    page.click("text=Start conversion")
    page.wait_for_selector("text=Conversion report", timeout=300_000)
    page.fill("input[name=title]", title)
    page.click("#build")
    page.wait_for_selector("text=Download EPUB")
    with page.expect_download() as download:
        page.click("text=Download EPUB")
    out = tmp_path / download.value.suggested_filename
    download.value.save_as(out)
    page.close()
    return out


def test_english_pdf_to_epub(browser, server, pdfs, tmp_path, epubcheck):
    out = convert_in_ui(browser, server, pdfs["english"], tmp_path, "Keeper")
    assert out.name == "Keeper.epub"
    epubcheck(out)
    assert "The lighthouse keeper rose before the gulls" in epub_text(out)


def test_bijoy_pdf_to_epub(browser, server, pdfs, tmp_path, epubcheck):
    out = convert_in_ui(browser, server, pdfs["bijoy"], tmp_path, "আমার বই")
    epubcheck(out)
    assert "আমার সোনার বাংলা" in epub_text(out)


@pytest.mark.ocr
def test_scanned_bengali_pdf_to_epub(browser, server, pdfs, tmp_path, epubcheck, tesseract):
    out = convert_in_ui(browser, server, pdfs["scanned_bn"], tmp_path, "নদীর গল্প")
    epubcheck(out)
    assert "মাঝি" in epub_text(out)

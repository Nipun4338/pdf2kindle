"""OCR of scanned and broken-text-layer Bengali pages. Needs Tesseract with ben+eng."""

import pytest
from PIL import Image, ImageDraw

from pdf2kindle import bengali
from pdf2kindle.conversion import Settings, Store, analyse, export
from pdf2kindle.model import PageMode
from pdf2kindle.ocr import deskew, otsu_threshold
from tests.conftest import epub_text


def test_otsu_splits_ink_from_paper():
    image = Image.new("L", (100, 100), 230)
    ImageDraw.Draw(image).rectangle((10, 10, 40, 40), fill=20)
    assert 20 <= otsu_threshold(image) < 230


def test_deskew_straightens_rotated_lines():
    image = Image.new("L", (800, 600), 255)
    draw = ImageDraw.Draw(image)
    for y in range(60, 560, 40):
        draw.rectangle((60, y, 740, y + 12), fill=0)
    tilted = image.rotate(2, expand=False, fillcolor=255)
    assert deskew(tilted).size != tilted.size  # a correction was applied


@pytest.mark.ocr
@pytest.mark.parametrize("fixture", ["scanned_bn", "bengali"])
def test_bengali_ocr(tmp_path, pdfs, tesseract, epubcheck, fixture):
    store = Store(tmp_path)
    cid = store.create("b.pdf", pdfs[fixture].read_bytes(), Settings())
    analyse(store, cid, tesseract)
    body = [p for p in store.pages(cid) if p.index > 0]
    assert all(p.confidence is not None for p in body)
    assert any(p.mode == PageMode.TEXT for p in body)
    out = export(store, cid)
    epubcheck(out)
    text = epub_text(out)
    for word in ("নদীর", "গ্রাম", "মাঝি", "গল্প"):
        assert word in text
    assert bengali.invalid_sequence_ratio(text) < 0.05

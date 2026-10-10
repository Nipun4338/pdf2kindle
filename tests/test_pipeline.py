"""Classification, layout and export against generated fixture PDFs (no OCR needed)."""

import zipfile

import pytest

from pdf2kindle.classify import classify
from pdf2kindle.conversion import Settings, Status, Store, analyse, export
from pdf2kindle.layout import build_blocks
from pdf2kindle.model import PageKind, PageMode
from pdf2kindle.pdf import iter_raw_pages
from tests.conftest import NoOcr, epub_text
from tests.fixtures import BIJOY_LINES, EN_PARAGRAPHS


def kinds(path):
    return [classify(raw).kind for raw in iter_raw_pages(path)]


def test_english_pages_are_text(pdfs):
    assert set(kinds(pdfs["english"])) == {PageKind.TEXT}


def test_bijoy_page_is_legacy(pdfs):
    assert kinds(pdfs["bijoy"]) == [PageKind.LEGACY]


def test_table_page_is_complex(pdfs):
    assert kinds(pdfs["complex"])[:2] == [PageKind.COMPLEX, PageKind.COMPLEX]
    assert kinds(pdfs["complex"])[2] == PageKind.TEXT


def test_broken_bengali_text_layer_counts_as_scanned(pdfs):
    # Chromium drops conjuncts and writes vowel signs in glyph order, like many real PDFs.
    assert kinds(pdfs["bengali"])[1:] == [PageKind.SCANNED] * 4


def test_image_only_pdf_is_scanned(pdfs):
    assert set(kinds(pdfs["scanned_bn"])) == {PageKind.SCANNED}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "conversions")


def convert(store, pdf, **settings):
    cid = store.create(pdf.name, pdf.read_bytes(), Settings(**settings))
    analyse(store, cid, NoOcr(), workers=1)
    return cid


def test_english_book(store, pdfs, epubcheck):
    cid = convert(store, pdfs["english"])
    meta = store.load(cid)
    assert meta["status"] == Status.READY
    assert [e["title"] for e in meta["toc"]] == ["The Island", "The Storm"]

    out = export(store, cid)
    epubcheck(out)
    text = epub_text(out)
    # Paragraphs are rebuilt whole: no line breaks, no end-of-line hyphens.
    assert EN_PARAGRAPHS[1] in text
    # Running header and page numbers are gone; only the title page keeps the title.
    assert text.count("The Keeper of the Light") == 1
    assert '<div class="notes"><p>1 A footnote at the foot of the first chapter.</p></div>' in text
    with zipfile.ZipFile(out) as z:
        assert "OEBPS/fonts/NotoSerifBengali-Regular.ttf" not in z.namelist()
        nav = z.read("OEBPS/nav.xhtml").decode()
    assert "The Island" in nav and "The Storm" in nav


def test_keep_noise_setting(store, pdfs):
    cid = convert(store, pdfs["english"], strip_noise=False)
    pages = store.pages(cid)
    blocks = build_blocks(pages, strip_noise=False)
    assert sum("The Keeper of the Light" in b.text for b in blocks) > 1


def test_bijoy_book(store, pdfs, epubcheck):
    cid = convert(store, pdfs["bijoy"])
    out = export(store, cid)
    epubcheck(out)
    text = epub_text(out)
    for _, unicode in BIJOY_LINES:
        assert unicode in text
    assert 'lang="bn"' in text
    with zipfile.ZipFile(out) as z:
        assert "OEBPS/fonts/NotoSerifBengali-Regular.ttf" in z.namelist()


def test_complex_pages_become_images(store, pdfs, epubcheck):
    cid = convert(store, pdfs["complex"])
    modes = [p.mode for p in store.pages(cid)]
    assert modes == [PageMode.IMAGE, PageMode.IMAGE, PageMode.TEXT]
    out = export(store, cid)
    epubcheck(out)
    with zipfile.ZipFile(out) as z:
        assert {"OEBPS/images/page0001.jpg", "OEBPS/images/page0002.jpg"} <= set(z.namelist())


def test_without_ocr_scanned_pages_fall_back_to_images(store, pdfs, epubcheck):
    cid = convert(store, pdfs["scanned_bn"])
    pages = store.pages(cid)
    assert all(p.mode == PageMode.IMAGE for p in pages)
    assert "no OCR engine installed" in pages[0].reason
    epubcheck(export(store, cid))


def test_override_switches_page_mode(store, pdfs):
    cid = convert(store, pdfs["complex"])
    store.update(cid, overrides={"0": "text"})
    out = export(store, cid)
    assert "Item 1" in epub_text(out)


def test_purge_removes_old_conversions(store, pdfs):
    cid = convert(store, pdfs["bijoy"])
    store.update(cid, created="2000-01-01T00:00:00+00:00")
    assert store.purge_older_than(30) == 1
    assert store.all() == []


def test_pdfium_is_safe_across_threads(pdfs):
    # The report page loads many thumbnails at once while an export may be rendering.
    from concurrent.futures import ThreadPoolExecutor

    from pdf2kindle.pdf import SourcePdf

    def thumb(i):
        src = SourcePdf(pdfs["english"])
        try:
            return src.render(i % len(src), dpi=72, max_width=200).width
        finally:
            src.close()

    with ThreadPoolExecutor(8) as pool:
        assert all(w > 0 for w in pool.map(thumb, range(80)))


@pytest.mark.parametrize("levels", [[2, 1, 2, 2, 1], [1, 2, 2, 1, 2], [2, 2], [1, 1], [1, 2, 1]])
def test_nav_is_well_formed_for_any_toc_levels(levels, tmp_path):
    import xml.etree.ElementTree as ET

    from pdf2kindle.epub import Chapter, EpubBook, NavPoint, write_epub

    nav = [NavPoint(f"Entry {i}", 0, f"a{i}", lv) for i, lv in enumerate(levels)]
    book = EpubBook("T", "A", "en", [Chapter("T", "<p>x</p>", "en")], nav)
    out = tmp_path / "b.epub"
    write_epub(book, out)
    with zipfile.ZipFile(out) as z:
        root = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    assert len(root.findall(".//x:a", ns)) == len(levels)
    for ol in root.iter("{http://www.w3.org/1999/xhtml}ol"):
        assert all(child.tag.endswith("li") for child in ol)


def test_scan_with_junk_ocr_layer_is_reocrd():
    from pdf2kindle.classify import latin_plausibility

    junk = 'c+t torqat :o sacrEr l*nTf5 q<E.ra En niq E"li ffiiist c+g ciFr"l'
    assert latin_plausibility(junk) < 0.5
    assert latin_plausibility(" ".join(EN_PARAGRAPHS)) > 0.95

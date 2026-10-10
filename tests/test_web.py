import time

import pytest
from fastapi.testclient import TestClient

from pdf2kindle.web import create_app
from tests.conftest import NoOcr, epub_text


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, engine_factory=NoOcr)) as c:
        yield c


def wait_ready(client, cid):
    for _ in range(200):
        status = client.get(f"/conversions/{cid}/status").json()
        if status["status"] in ("ready", "failed"):
            return status
        time.sleep(0.1)
    raise AssertionError("conversion did not finish")


def upload(client, path, **form):
    with path.open("rb") as f:
        res = client.post(
            "/conversions",
            files={"file": (path.name, f, "application/pdf")},
            data={"lang": "auto", "strip_noise": "true", **form},
            follow_redirects=False,
        )
    assert res.status_code == 303
    return res.headers["location"].rsplit("/", 1)[-1]


def test_upload_review_export_download(client, pdfs, tmp_path):
    assert "Tesseract isn't installed" in client.get("/").text
    cid = upload(client, pdfs["english"])
    assert wait_ready(client, cid) == {"status": "ready", "error": "", "done": 7, "total": 7}

    page = client.get(f"/conversions/{cid}").text
    assert "The Island" in page and "Conversion report" in page

    res = client.post(
        f"/conversions/{cid}/settings",
        data={
            "title": "The Keeper of the Light",
            "author": "A. Writer",
            "cover": "page1",
            "strip_noise": "on",
            "toc_title_0": "Part One: The Island",
            "toc_page_0": "2",
            "toc_level_0": "1",
            "toc_title_1": "The Storm",
            "toc_page_1": "5",
            "toc_delete_1": "on",
            "toc_title_2": "Footnote page",
            "toc_page_2": "4",
            "toc_level_2": "2",
            "export": "1",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303

    res = client.get(f"/conversions/{cid}/book.epub")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/epub+zip"
    assert (
        "The%20Keeper%20of%20the%20Light.epub" in res.headers["content-disposition"]
        or "The Keeper of the Light.epub" in res.headers["content-disposition"]
    )
    book = tmp_path / "book.epub"
    book.write_bytes(res.content)
    import zipfile

    with zipfile.ZipFile(book) as z:
        nav = z.read("OEBPS/nav.xhtml").decode()
        opf = z.read("OEBPS/content.opf").decode()
    assert "Part One: The Island" in nav and "Footnote page" in nav and "The Storm" not in nav
    assert "<dc:creator>A. Writer</dc:creator>" in opf
    assert "The lighthouse keeper" in epub_text(book)


def test_page_mode_toggle_and_thumbnail(client, pdfs):
    cid = upload(client, pdfs["complex"])
    wait_ready(client, cid)
    assert client.get(f"/conversions/{cid}/pages/0.jpg").headers["content-type"] == "image/jpeg"
    client.post(f"/conversions/{cid}/pages/0/mode")
    assert client.app.state.store.load(cid)["overrides"] == {"0": "text"}


def test_rejects_non_pdf(client):
    res = client.post("/conversions", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert res.status_code == 400


def test_delete(client, pdfs):
    cid = upload(client, pdfs["bijoy"])
    wait_ready(client, cid)
    client.post(f"/conversions/{cid}/delete")
    assert client.get(f"/conversions/{cid}").status_code == 404


def test_unknown_or_malicious_ids_are_404(client):
    assert client.get("/conversions/nope").status_code == 404
    assert client.get("/conversions/..%2F..%2Fetc/status").status_code == 404

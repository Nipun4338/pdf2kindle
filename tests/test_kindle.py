"""Books must survive Amazon's own conversion, not just epubcheck. Needs Kindle Previewer 3."""

import pytest

from pdf2kindle.conversion import Settings, Store, analyse, export
from tests.conftest import NoOcr

pytestmark = pytest.mark.kindle


@pytest.mark.parametrize("fixture", ["english", "bijoy", "complex"])
def test_amazon_converts_the_book(tmp_path, pdfs, kindle_convert, fixture):
    store = Store(tmp_path)
    cid = store.create(f"{fixture}.pdf", pdfs[fixture].read_bytes(), Settings())
    analyse(store, cid, NoOcr(), workers=1)
    status, errors = kindle_convert(export(store, cid))
    assert (status, errors) == ("Success", [])

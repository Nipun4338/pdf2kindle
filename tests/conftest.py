import csv
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from pdf2kindle.ocr import TesseractEngine
from tests import fixtures

ROOT = Path(__file__).resolve().parents[1]


class NoOcr:
    """An Engine stand-in for machines without Tesseract."""

    name = "none"

    def available(self) -> bool:
        return False


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory) -> dict[str, Path]:
    return fixtures.build_all(tmp_path_factory.mktemp("pdfs"))


@pytest.fixture(scope="session")
def tesseract() -> TesseractEngine:
    engine = TesseractEngine()
    if not engine.available() or not {"ben", "eng"} <= engine.languages():
        pytest.skip("Tesseract with ben+eng data is not installed")
    return engine


def _epubcheck_jar() -> Path | None:
    if os.environ.get("EPUBCHECK_JAR"):
        return Path(os.environ["EPUBCHECK_JAR"])
    found = sorted(ROOT.glob("tools/epubcheck-*/epubcheck.jar"))
    return found[-1] if found else None


@pytest.fixture(scope="session")
def epubcheck():
    jar = _epubcheck_jar()
    if not jar or not jar.exists() or not shutil.which("java"):
        pytest.skip("epubcheck not available (set EPUBCHECK_JAR or run scripts/get-epubcheck)")

    def check(path: Path) -> None:
        # Java on Windows can't always open non-ASCII paths (e.g. Bengali titles).
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "book.epub"
            shutil.copy(path, copy)
            result = subprocess.run(
                ["java", "-jar", str(jar), str(copy)], capture_output=True, text=True
            )
        assert result.returncode == 0, result.stdout + result.stderr

    return check


def _kindle_previewer() -> list[str] | None:
    """Command prefix for Kindle Previewer 3's converter, if installed."""
    if os.environ.get("KINDLE_PREVIEWER"):
        return [os.environ["KINDLE_PREVIEWER"]]
    bat = Path(os.environ.get("APPDATA", "")) / "Amazon" / "kindlepreviewer.bat"
    return ["cmd", "/c", str(bat)] if os.name == "nt" and bat.exists() else None


@pytest.fixture(scope="session")
def kindle_convert():
    """Run Amazon's own EPUB → Kindle conversion; returns (status, errors)."""
    cmd = _kindle_previewer()
    if not cmd:
        pytest.skip("Kindle Previewer 3 is not installed")

    def convert(epub: Path) -> tuple[str, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "book.epub", Path(tmp) / "out"
            shutil.copy(epub, src)
            out.mkdir()  # the converter silently does nothing if this doesn't exist
            subprocess.run(
                [*cmd, str(src), "-convert", "-output", str(out), "-locale", "en"],
                capture_output=True,
                timeout=900,
            )
            with open(out / "Summary_Log.csv", encoding="utf-8-sig") as f:
                header, row = list(csv.reader(f))[:2]
            summary = dict(zip(header, row, strict=False))
            errors = []
            log = Path(summary["Log File Path"])
            if log.exists():
                with open(log, encoding="utf-8-sig") as f:
                    errors = [r[1] for r in csv.reader(f) if r and r[0] == "Error"]
            return summary["Conversion Status"], errors

    return convert


def epub_text(path: Path) -> str:
    """All chapter XHTML of an EPUB, concatenated."""
    with zipfile.ZipFile(path) as z:
        return "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist()) if "/text/ch" in n)

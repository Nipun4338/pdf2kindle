"""Generate the fixture PDFs used by tests. Nothing copyrighted: all text is written here.

Chromium (via Playwright) makes realistic, properly shaped PDFs with bookmarks; the Bijoy
fixture is written by hand because it needs a font literally named SutonnyMJ.
"""

from pathlib import Path

import pypdfium2 as pdfium

FONT_DIR = Path(__file__).resolve().parents[1] / "src" / "pdf2kindle" / "assets" / "fonts"

EN_PARAGRAPHS = [
    "The lighthouse keeper rose before the gulls and climbed the iron stairs with a lamp "
    "in one hand and a notebook in the other. Every morning he wrote down the colour of "
    "the sea, the direction of the wind, and the names of the boats that passed.",
    "Nobody had asked him to keep such a record. He kept it because the island was quiet "
    "and the days were long, and because a careful list made the world feel a little more "
    "understandable to a man who lived so far from everyone else.",
    "When the storm finally came it arrived without warning, bending the grass flat and "
    "throwing spray against the windows of the lower rooms until the glass sang.",
]
BN_PARAGRAPHS = [
    "নদীর ধারে একটি ছোট গ্রাম ছিল। সেই গ্রামে এক বৃদ্ধ মাঝি থাকতেন, যিনি প্রতিদিন "
    "ভোরবেলা নৌকা নিয়ে নদীতে যেতেন এবং সন্ধ্যায় ফিরে আসতেন।",
    "গ্রামের ছেলেমেয়েরা তাঁর কাছে গল্প শুনতে ভালোবাসত। তিনি তাদের দূরের দেশের কথা, "
    "ঝড়ের রাতের কথা আর নদীর বুকে জেগে ওঠা চরের কথা বলতেন।",
    "একদিন আকাশ কালো করে মেঘ জমল। মাঝি বুঝলেন আজ নদী শান্ত থাকবে না, তবু তিনি "
    "ঘাটে গিয়ে নৌকাটি শক্ত করে বেঁধে রাখলেন।",
]
# The same idea in Bijoy (SutonnyMJ) encoding, with the Unicode we expect back.
BIJOY_LINES = [
    ("Avgvi ‡mvbvi evsjv, Avwg ‡Zvgvq fv‡jvevwm|", "আমার সোনার বাংলা, আমি তোমায় ভালোবাসি।"),
    ("evsjv‡`‡ki cÖwZwU MÖv‡g b`x Av‡Q|", "বাংলাদেশের প্রতিটি গ্রামে নদী আছে।"),
    ("Kg© I ag© `ywUB gvby‡li Rb¨ cÖ‡qvRb|", "কর্ম ও ধর্ম দুটিই মানুষের জন্য প্রয়োজন।"),
]

_REGULAR = (FONT_DIR / "NotoSerifBengali-Regular.ttf").as_uri()
_BOLD = (FONT_DIR / "NotoSerifBengali-Bold.ttf").as_uri()
_CSS = f"""
@font-face {{ font-family: NotoBn; src: url('{_REGULAR}'); }}
@font-face {{ font-family: NotoBn; font-weight: bold; src: url('{_BOLD}'); }}
body {{ font-family: Georgia, NotoBn, serif; font-size: 12pt; line-height: 1.5; }}
h1 {{ font-size: 24pt; page-break-before: always; }}
h1:first-of-type {{ page-break-before: avoid; }}
p {{ text-align: justify; hyphens: auto; }}
.note {{ font-size: 8pt; border-top: 1px solid #999; margin-top: 2em; }}
"""
_HEADER = '<div style="font-size:8pt;width:100%;text-align:center;">{}</div>'
_FOOTER = (
    '<div style="font-size:8pt;width:100%;text-align:center;">'
    '<span class="pageNumber"></span></div>'
)


def _book_html(lang: str, title: str, chapters: list[str], paragraphs: list[str]) -> str:
    body = [f'<p style="font-size:30pt;text-align:center;margin-top:30%">{title}</p>']
    for i, name in enumerate(chapters):
        body.append(f'<h1 style="page-break-before:always">{name}</h1>')
        for _ in range(4):
            body.extend(f"<p>{p}</p>" for p in paragraphs)
        if i == 0:
            body.append('<p class="note">1 A footnote at the foot of the first chapter.</p>')
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<style>{_CSS}</style></head><body>{''.join(body)}</body></html>"
    )


def _print(html: str, out: Path, header: str) -> Path:
    from playwright.sync_api import sync_playwright

    src = out.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(src.as_uri())
        page.wait_for_load_state("networkidle")
        page.pdf(
            path=str(out),
            format="A5",
            margin={"top": "2cm", "bottom": "2cm", "left": "1.5cm", "right": "1.5cm"},
            display_header_footer=True,
            header_template=_HEADER.format(header),
            footer_template=_FOOTER,
            outline=True,
            tagged=True,
        )
        browser.close()
    src.unlink()
    return out


def english_pdf(out: Path) -> Path:
    html = _book_html("en", "The Keeper of the Light", ["The Island", "The Storm"], EN_PARAGRAPHS)
    return _print(html, out, "The Keeper of the Light")


def bengali_pdf(out: Path) -> Path:
    html = _book_html("bn", "নদীর গল্প", ["প্রথম অধ্যায়", "দ্বিতীয় অধ্যায়"], BN_PARAGRAPHS)
    return _print(html, out, "নদীর গল্প")


def complex_pdf(out: Path) -> Path:
    rows = "".join(
        f"<tr><td>Item {i}</td><td>{i * 3}</td><td>{i * 7}</td><td>{i * 11}</td></tr>"
        for i in range(1, 25)
    )
    html = (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{_CSS}'
        "td{padding:2px 18px}</style></head><body>"
        f"<h1>Tables</h1><table>{rows}</table>"
        f'<h1 style="page-break-before:always">Prose</h1><p>{EN_PARAGRAPHS[0]}</p>'
        "</body></html>"
    )
    return _print(html, out, "Complex")


def bijoy_pdf(out: Path) -> Path:
    """A hand-written PDF whose text is Bijoy-encoded in a font named SutonnyMJ."""
    lines = [b for b, _ in BIJOY_LINES] * 6
    ops = ["BT", "/F1 14 Tf", "16 TL", "50 780 Td"]
    for line in lines:
        esc = line.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(")
        ops.append(f"({esc.replace(b')', b'\\)').decode('latin-1')}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /SutonnyMJ /Encoding /WinAnsiEncoding "
        b"/FirstChar 32 /LastChar 255 /Widths [" + b" 500" * 224 + b" ] /FontDescriptor 6 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /FontDescriptor /FontName /SutonnyMJ /Flags 32 /FontBBox [0 -200 1000 900] "
        b"/ItalicAngle 0 /Ascent 900 /Descent -200 /CapHeight 700 /StemV 80 >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objs, 1):
        offsets.append(len(data))
        data += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    data += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    out.write_bytes(bytes(data))
    return out


def scanned_pdf(source: Path, out: Path, dpi: int = 200) -> Path:
    """Rasterise `source` into an image-only PDF (no text layer), like a scan."""
    pdf = pdfium.PdfDocument(source)
    images = [page.render(scale=dpi / 72).to_pil().convert("L") for page in pdf]
    pdf.close()
    images[0].save(out, save_all=True, append_images=images[1:], resolution=dpi)
    return out


def build_all(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "english": english_pdf(directory / "english.pdf"),
        "bengali": bengali_pdf(directory / "bengali.pdf"),
        "complex": complex_pdf(directory / "complex.pdf"),
        "bijoy": bijoy_pdf(directory / "bijoy.pdf"),
    }
    paths["scanned_bn"] = scanned_pdf(paths["bengali"], directory / "scanned_bn.pdf")
    return paths


if __name__ == "__main__":
    import sys

    for name, path in build_all(Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures")).items():
        print(name, path)

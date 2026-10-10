"""`pdf2kindle serve` runs the web UI; `pdf2kindle convert` converts one file headlessly."""

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf2kindle")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the web UI (default)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data-dir", type=Path)
    serve.add_argument("--open", action="store_true", help="open the UI in your browser")

    convert = sub.add_parser("convert", help="convert a PDF to EPUB without the UI")
    convert.add_argument("pdf", type=Path)
    convert.add_argument("epub", type=Path, nargs="?")
    convert.add_argument("--lang", choices=["auto", "bn", "en"], default="auto")
    convert.add_argument(
        "--keep-noise", action="store_true", help="keep running headers, footers and page numbers"
    )
    convert.add_argument("--grayscale", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "convert":
        from pdf2kindle.conversion import Settings, Status, Store, analyse, export

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            cid = store.create(
                args.pdf.name,
                args.pdf.read_bytes(),
                Settings(args.lang, not args.keep_noise, args.grayscale),
            )
            analyse(store, cid)
            meta = store.load(cid)
            if meta["status"] != Status.READY:
                print(f"failed: {meta['error']}", file=sys.stderr)
                return 1
            out = args.epub or args.pdf.with_suffix(".epub")
            shutil.copy(export(store, cid), out)
            images = sum(p.mode == "image" for p in store.pages(cid))
            print(f"wrote {out} ({meta['progress']['total']} pages, {images} as images)")
        return 0

    import uvicorn

    from pdf2kindle.web import create_app

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8000)
    url = f"http://{host}:{port}"
    print(f"pdf2kindle running at {url}  (press Ctrl+C to stop)")
    if getattr(args, "open", False):
        import threading
        import webbrowser

        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(create_app(getattr(args, "data_dir", None)), host=host, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env sh
# One-click launcher for macOS/Linux: sets up pdf2kindle on first run, then starts it.
set -eu
cd "$(dirname "$0")"

if [ ! -x .venv/bin/pdf2kindle ]; then
  echo "=== First run: installing pdf2kindle ==="
  if command -v uv >/dev/null 2>&1; then
    uv sync --no-dev
  else
    python3 -m uv --version >/dev/null 2>&1 || python3 -m pip install --user --quiet uv
    python3 -m uv sync --no-dev
  fi
fi

if ! command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract OCR is not installed; scanned pages will be kept as page images."
  echo "  macOS: brew install tesseract    Debian/Ubuntu: sudo apt install tesseract-ocr"
fi

TESSDATA="$HOME/.pdf2kindle/tessdata"
if [ ! -f "$TESSDATA/ben.traineddata" ]; then
  echo "Downloading Bengali and English OCR models (about 37 MB, first run only)..."
  mkdir -p "$TESSDATA"
  for lang in ben eng osd; do
    curl -fsSL -o "$TESSDATA/$lang.traineddata" \
      "https://github.com/tesseract-ocr/tessdata_best/raw/main/$lang.traineddata"
  done
fi

exec .venv/bin/pdf2kindle serve --open

#!/usr/bin/env sh
# Download the W3C EPUB validator into tools/ (used by the test suite). Needs Java 11+.
set -eu
VERSION="${EPUBCHECK_VERSION:-5.2.1}"
cd "$(dirname "$0")/.."
mkdir -p tools
curl -fsSL -o tools/epubcheck.zip \
  "https://github.com/w3c/epubcheck/releases/download/v$VERSION/epubcheck-$VERSION.zip"
unzip -q -o tools/epubcheck.zip -d tools
rm tools/epubcheck.zip
echo "tools/epubcheck-$VERSION/epubcheck.jar"

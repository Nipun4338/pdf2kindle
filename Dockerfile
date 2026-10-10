FROM python:3.12-slim

ARG TESSDATA_URL=https://github.com/tesseract-ocr/tessdata_best/raw/main
ENV TESSDATA_PREFIX=/opt/tessdata \
    PDF2KINDLE_DATA_DIR=/data \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr curl ca-certificates \
 && mkdir -p "$TESSDATA_PREFIX" \
 && for lang in ben eng osd; do \
      curl -fsSL -o "$TESSDATA_PREFIX/$lang.traineddata" "$TESSDATA_URL/$lang.traineddata"; \
    done \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
CMD ["/app/.venv/bin/pdf2kindle", "serve", "--host", "0.0.0.0", "--port", "8000"]

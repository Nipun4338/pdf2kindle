"""OCR Engines. Every Engine is free and runs locally (ADR 0002)."""

import os
import shutil
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageFilter, ImageOps

from pdf2kindle import bengali
from pdf2kindle.model import Line

OCR_DPI = 300


class Engine(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, image: Image.Image, langs: str) -> tuple[list[Line], float]:
        """Lines in pixel coordinates of `image`, plus mean confidence 0-100."""
        ...


def _row_profile_score(image: Image.Image) -> float:
    rows = image.resize((1, image.height), Image.Resampling.BOX).tobytes()
    mean = sum(rows) / len(rows)
    return sum((r - mean) ** 2 for r in rows)


def deskew(gray: Image.Image, max_angle: float = 3.0, step: float = 0.5) -> Image.Image:
    """Straighten small rotations: the right angle makes text rows sharpest."""
    thumb = ImageOps.invert(gray.resize((gray.width // 4, gray.height // 4)))
    angles = [i * step for i in range(int(-max_angle / step), int(max_angle / step) + 1)]
    best = max(angles, key=lambda a: _row_profile_score(thumb.rotate(a, fillcolor=0)))
    if best == 0:
        return gray
    return gray.rotate(best, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def otsu_threshold(gray: Image.Image) -> int:
    hist = gray.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = weight_b = 0
    best, threshold = 0.0, 128
    for i, h in enumerate(hist):
        weight_b += h
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += i * h
        mean_b, mean_f = sum_b / weight_b, (sum_all - sum_b) / weight_f
        between = weight_b * weight_f * (mean_b - mean_f) ** 2
        if between > best:
            best, threshold = between, i
    return threshold


def preprocess(image: Image.Image, dpi: float) -> Image.Image:
    gray = ImageOps.grayscale(image)
    if dpi < OCR_DPI:  # upscale low-resolution scans; Tesseract wants ~300 dpi
        factor = OCR_DPI / dpi
        gray = gray.resize(
            (int(gray.width * factor), int(gray.height * factor)), Image.Resampling.LANCZOS
        )
    gray = deskew(gray.filter(ImageFilter.MedianFilter(3)))
    t = otsu_threshold(gray)
    return gray.point(lambda p: 255 if p > t else 0, mode="1").convert("L")


class TesseractEngine:
    name = "tesseract"

    def __init__(self, cmd: str | None = None):
        import pytesseract

        self._tess = pytesseract
        cmd = cmd or os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
        if not cmd and os.name == "nt":
            default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            cmd = default if os.path.exists(default) else None
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        self._cmd = cmd
        # Models in ~/.pdf2kindle/tessdata (e.g. tessdata_best) win unless TESSDATA_PREFIX is set.
        own = Path.home() / ".pdf2kindle" / "tessdata"
        if not os.environ.get("TESSDATA_PREFIX") and own.is_dir():
            os.environ["TESSDATA_PREFIX"] = str(own)  # inherited by the tesseract subprocess

    def available(self) -> bool:
        return bool(self._cmd)

    def languages(self) -> set[str]:
        try:
            return set(self._tess.get_languages(config=""))
        except Exception:
            return set()

    def recognize(self, image: Image.Image, langs: str) -> tuple[list[Line], float]:
        data = self._tess.image_to_data(
            image, lang=langs, config="--psm 3", output_type=self._tess.Output.DICT
        )
        lines: dict[tuple[int, int, int], list[int]] = {}
        for i, word in enumerate(data["text"]):
            if word.strip():
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                lines.setdefault(key, []).append(i)

        result: list[Line] = []
        weighted = chars = 0.0
        par_ids: dict[tuple[int, int], int] = {}
        for (block, par, _), idx in sorted(lines.items(), key=lambda kv: data["top"][kv[1][0]]):
            words = [data["text"][i] for i in idx]
            for i in idx:
                conf = float(data["conf"][i])
                if conf >= 0:
                    weighted += conf * len(data["text"][i])
                    chars += len(data["text"][i])
            lefts = [data["left"][i] for i in idx]
            tops = [data["top"][i] for i in idx]
            bottoms = [data["top"][i] + data["height"][i] for i in idx]
            rights = [data["left"][i] + data["width"][i] for i in idx]
            heights = sorted(data["height"][i] for i in idx)
            result.append(
                Line(
                    text=bengali.normalize_ocr(" ".join(words)),
                    x0=min(lefts),
                    x1=max(rights),
                    top=min(tops),
                    bottom=max(bottoms),
                    size=heights[len(heights) // 2],
                    group=par_ids.setdefault((block, par), len(par_ids) + 1),
                )
            )
        return result, (weighted / chars if chars else 0.0)


def default_engine() -> Engine:
    return TesseractEngine()

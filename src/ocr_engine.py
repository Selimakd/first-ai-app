"""Yerel OCR: EasyOCR (ücret yok, internet sadece ilk model indirmede)."""

from __future__ import annotations

import threading
from typing import Any

import cv2
import numpy as np
from PIL import Image

_reader: Any = None
_lock = threading.Lock()


def get_reader(langs: tuple[str, ...] = ("tr", "en")):
    """EasyOCR Reader tek örnek; ağır yüklemeyi bir kez yapar."""
    global _reader
    with _lock:
        if _reader is None:
            import easyocr

            _reader = easyocr.Reader(list(langs), gpu=False, verbose=False)
        return _reader


def pil_to_bgr(img: Image.Image) -> np.ndarray:
    rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def preprocess_for_ocr(bgr: np.ndarray, scale: float = 1.5) -> np.ndarray:
    """Ekran görüntülerinde küçük yazılar için hafif büyütme + gri ton."""
    h, w = bgr.shape[:2]
    if scale != 1.0:
        bgr = cv2.resize(
            bgr,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Kontrast: çoğu mobil/web arayüzünde okunabilirliği artırır
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray


def read_text(image: Image.Image, upscale: float = 1.5) -> list[tuple[Any, str, float]]:
    """
    Dönüş: EasyOCR formatı — (bbox, metin, güven).
    bbox: dört köşe koordinatı.
    """
    reader = get_reader()
    bgr = pil_to_bgr(image)
    gray = preprocess_for_ocr(bgr, scale=upscale)
    # readtext gri kanal da kabul eder (2D array)
    return reader.readtext(gray, detail=1, paragraph=False)


def y_center(box: Any) -> float:
    pts = box
    ys = [float(p[1]) for p in pts]
    return sum(ys) / len(ys)


def sorted_lines(results: list[tuple[Any, str, float]]) -> list[tuple[Any, str, float]]:
    """Üstten alta okuma sırası (aynı sitede sabit düzen için uygun)."""
    return sorted(results, key=lambda r: (y_center(r[0]), r[0][0][0]))

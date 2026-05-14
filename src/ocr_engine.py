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


# OCR'a giren görüntünün uzun kenar üst sınırı. EasyOCR çıkarımı piksel sayısıyla
# ölçeklenir; mobil screenshot'lar zaten yüksek çözünürlüklü (retina) olduğu için
# kısmak doğruluk kaybetmeden çıkarımı ciddi hızlandırır — HF free tier paylaşımlı
# CPU'da kritik. BES ekranlarında etiket/değer yazıları büyük; 1600px uzun kenarda
# kısa kenar ~900px+ kalır, recognition için fazlasıyla yeterli.
MAX_OCR_LONG_SIDE = 1600


def ocr_target_size(w: int, h: int, scale: float) -> tuple[int, int]:
    """Kullanıcı büyütmesi + uzun-kenar üst sınırı uygulanmış hedef (w, h).

    Önce kullanıcı `scale`'i (küçük yazılı ekranlar için) uygulanır, sonra uzun kenar
    MAX_OCR_LONG_SIDE'ı aşıyorsa oran korunarak kısılır. Büyük mobil ekranlarda slider
    1.0 da 1.5 da olsa sonuç aynı üst sınıra iner.
    """
    tw, th = int(w * scale), int(h * scale)
    long_side = max(tw, th)
    if long_side > MAX_OCR_LONG_SIDE:
        k = MAX_OCR_LONG_SIDE / long_side
        tw, th = int(tw * k), int(th * k)
    return max(tw, 1), max(th, 1)


def preprocess_for_ocr(bgr: np.ndarray, scale: float = 1.5) -> np.ndarray:
    """Ekran görüntüsünü OCR'a hazırla: boyutlandırma + gri ton + kontrast.

    Boyutlandırma: kullanıcı büyütmesi + uzun-kenar üst sınırı (bkz. ocr_target_size).
    Büyük görüntüler kısılır (INTER_AREA), küçükler büyütülür (INTER_CUBIC).
    """
    h, w = bgr.shape[:2]
    tw, th = ocr_target_size(w, h, scale)
    if (tw, th) != (w, h):
        interp = cv2.INTER_AREA if (tw * th) < (w * h) else cv2.INTER_CUBIC
        bgr = cv2.resize(bgr, (tw, th), interpolation=interp)
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

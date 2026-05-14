"""
ocr_engine saf yardımcı fonksiyon testleri.

`ocr_target_size` EasyOCR'a giren görüntü boyutunu belirler — performansın ana
kaldıracı. EasyOCR'ı çağırmaz (easyocr lazy import edilir), bu yüzden hızlı unit test.
"""

from __future__ import annotations

from src.ocr_engine import MAX_OCR_LONG_SIDE, ocr_target_size


def test_buyuk_goruntu_uzun_kenardan_kisilir() -> None:
    """1320×2230 @ 1.5x → 1980×3345 → uzun kenar MAX_OCR_LONG_SIDE'a iner."""
    w, h = ocr_target_size(1320, 2230, 1.5)
    assert max(w, h) == MAX_OCR_LONG_SIDE
    # En-boy oranı korunmalı
    assert abs((w / h) - (1320 / 2230)) < 0.01


def test_buyuk_goruntu_slider_1x_de_ayni_ust_sinira_iner() -> None:
    """Büyük ekranda slider 1.0 da 1.5 da olsa sonuç aynı üst sınır — slider'ın
    zararlı etkisi cap ile sınırlanır."""
    a = ocr_target_size(1320, 2230, 1.0)
    b = ocr_target_size(1320, 2230, 1.5)
    assert a == b
    assert max(a) == MAX_OCR_LONG_SIDE


def test_kucuk_goruntu_buyutulur_cap_devreye_girmez() -> None:
    """600×900 @ 1.5x → 900×1350 — uzun kenar 1600'ün altında, büyütme korunur."""
    w, h = ocr_target_size(600, 900, 1.5)
    assert (w, h) == (900, 1350)


def test_buyutme_sonrasi_sinir_asilirsa_kisilir() -> None:
    """600×1000 @ 2.0x → 1200×2000 → uzun kenar 2000 > 1600 → kısılır."""
    w, h = ocr_target_size(600, 1000, 2.0)
    assert max(w, h) == MAX_OCR_LONG_SIDE


def test_scale_1_ve_sinir_altinda_degismez() -> None:
    """Zaten küçük + scale 1.0 → boyut değişmez."""
    w, h = ocr_target_size(800, 600, 1.0)
    assert (w, h) == (800, 600)


def test_yatay_goruntu_de_uzun_kenardan_kisilir() -> None:
    """Yatay (geniş) görüntüde de uzun kenar = genişlik kısılır."""
    w, h = ocr_target_size(4000, 1000, 1.0)
    assert max(w, h) == MAX_OCR_LONG_SIDE
    assert w > h  # yatay kalmalı


def test_sifir_korumasi() -> None:
    """Aşırı küçük girdi 0'a inmez (min 1)."""
    w, h = ocr_target_size(1, 1, 0.1)
    assert w >= 1 and h >= 1

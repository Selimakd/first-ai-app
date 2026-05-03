"""
extract_from_ocr_lines end-to-end testleri.

Gerçekçi BES ekran görüntüsü OCR çıktıları (EasyOCR'ın tipik ürettiği satır dizileri)
fixture olarak hazırlandı. Parse mantığı değiştiğinde bu testler kırılır ve
regresyonu yakalarız.
"""

from __future__ import annotations

import pytest

from src.bes_parse import extract_from_ocr_lines


# ---------------------------------------------------------------------------
# Senaryo 1: Devlet katkısız basit sözleşme
#    Ödenen ve yatırım etiketleri üst üste, iki tutar altlarında.
# ---------------------------------------------------------------------------


def test_devlet_katkisiz_basit_sozlesme() -> None:
    lines = [
        "BES Sözleşme Detayı",
        "Ödenen Toplam Tutar",
        "Yatırım Getiriniz",
        "50.000,00 TL",
        "12.500,00 TL",
        "Birikiminiz",
        "62.500,00 TL",
        "Hak Edişe Esas Süre",
        "8 yıl",
        "Hak Ediş Oranınız",
        "%60",
        "Hak Ediş Tutarınız",
        "0,00 TL",
    ]
    out = extract_from_ocr_lines(lines)
    assert out.odenen_toplam_tutar == 50_000.00
    assert out.yatirim_getiriniz == 12_500.00
    assert out.birikiminiz == 62_500.00
    assert out.hak_edise_esas_sure == 8.0
    assert out.hak_edis_oraniniz == 60.0


# ---------------------------------------------------------------------------
# Senaryo 2: Uzun süreli sözleşme (>= 10 yıl).
# ---------------------------------------------------------------------------


def test_uzun_sure_sozlesme() -> None:
    lines = [
        "Ödenen Toplam Tutar",
        "Yatırım Getiriniz",
        "100.000,00",
        "35.000,00",
        "Birikiminiz",
        "135.000,00",
        "Hak Edişe Esas Süre 15 yıl",
    ]
    out = extract_from_ocr_lines(lines)
    assert out.odenen_toplam_tutar == 100_000.00
    assert out.yatirim_getiriniz == 35_000.00
    assert out.birikiminiz == 135_000.00
    assert out.hak_edise_esas_sure == 15.0


# ---------------------------------------------------------------------------
# Senaryo 3: Devlet katkılı — devlet katkısı + birikim ayrımı.
#    Birikim üstte, altında "Devlet Katkısı" etiketi; sonra iki tutar.
# ---------------------------------------------------------------------------


def test_devlet_katkili_birikim_iki_satir() -> None:
    lines = [
        "Birikiminiz",
        "Devlet Katkısı",
        "5.000,00",
        "80.000,00",
        "Hak Ediş Tutarınız",
        "3.000,00 TL",
        "Hak Edişe Esas Süre",
        "12 yıl",
    ]
    out = extract_from_ocr_lines(lines)
    # İlk tutar devlet katkısı, ikincisi birikim olmalı.
    assert out.devlet_katkisi == 5_000.00
    assert out.birikiminiz == 80_000.00
    assert out.hak_edis_tutariniz == 3_000.00
    assert out.hak_edise_esas_sure == 12.0


# ---------------------------------------------------------------------------
# Senaryo 4: Yatırım getirisi = birikim yanlış eşleşmesi.
#    OCR bazen ikinci sütundaki birikimi yatırım getirisi sanır.
#    Düzeltme mantığının aktif olup doğru değeri bulması gerekir.
# ---------------------------------------------------------------------------


def test_yatirim_getirisi_birikim_ile_karismaz() -> None:
    # Ödenen=80k, yatırım=20k (gerçek), birikim=100k; OCR ikinci sütunu 100k okuyor.
    lines = [
        "Ödenen Toplam Tutar",
        "Yatırım Getiriniz",
        "80.000,00",
        "20.000,00",
        "Birikiminiz",
        "100.000,00",
        "Hak Edişe Esas Süre 5 yıl",
    ]
    out = extract_from_ocr_lines(lines)
    assert out.odenen_toplam_tutar == 80_000.00
    assert out.yatirim_getiriniz == 20_000.00  # birikim (100k) ile karışmamalı
    assert out.birikiminiz == 100_000.00


# ---------------------------------------------------------------------------
# Senaryo 5: Bos OCR — hiçbir şey set edilmemeli.
# ---------------------------------------------------------------------------


def test_bos_ocr_hic_alan_set_etmez() -> None:
    out = extract_from_ocr_lines([])
    d = out.to_dict()
    assert all(v is None for v in d.values())


def test_alakasiz_metin_none_dondurur() -> None:
    lines = ["Sayfa 1 / 3", "İşlem geçmişi", "Destek hattı: 0850..."]
    out = extract_from_ocr_lines(lines)
    assert out.birikiminiz is None
    assert out.yatirim_getiriniz is None
    assert out.hak_edise_esas_sure is None


# ---------------------------------------------------------------------------
# Senaryo 6: to_dict sözlük yapısı
# ---------------------------------------------------------------------------


def test_to_dict_anahtarlari() -> None:
    out = extract_from_ocr_lines(["Birikiminiz 12.345,67 TL"])
    d = out.to_dict()
    assert set(d.keys()) == {
        "birikiminiz",
        "odenen_toplam_tutar",
        "yatirim_getiriniz",
        "devlet_katkisi",
        "hak_edise_esas_sure",
        "hak_edis_oraniniz",
        "hak_edis_tutariniz",
    }


# ---------------------------------------------------------------------------
# Senaryo 7: Ondalıklı hak edişe esas süre (10,5 yıl gibi OCR'da görülebilir).
# ---------------------------------------------------------------------------


def test_hak_edis_esas_sure_maksimum_alinir() -> None:
    """Süre alanı altında birden çok sayı varsa max kullanılır."""
    lines = [
        "Hak Edişe Esas Süre",
        "3 yıl",
        "10 yıl",
    ]
    out = extract_from_ocr_lines(lines)
    assert out.hak_edise_esas_sure == 10.0


# ---------------------------------------------------------------------------
# Senaryo 8: debug_matches listesi — hangi alanın nereden çıktığı.
# ---------------------------------------------------------------------------


def test_debug_matches_doldurulur() -> None:
    lines = [
        "Ödenen Toplam Tutar",
        "Yatırım Getiriniz",
        "10.000,00",
        "2.000,00",
    ]
    out = extract_from_ocr_lines(lines)
    assert len(out.debug_matches) >= 2
    fields = [m[0] for m in out.debug_matches]
    assert "odenen_toplam_tutar" in fields
    assert "yatirim_getiriniz" in fields

"""
run_pipeline testleri — OCR ham çıktısından tam hesap sonucuna kadar olan
kanal-bağımsız zincir (API / iOS Kısayol bunu kullanır).

`bugun` enjekte edilerek tarih-türetimli süre deterministik test edilir.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.bes_pipeline import run_pipeline


def _box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95) -> tuple[Any, str, float]:
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# ---------------------------------------------------------------------------
# Garanti teklif/sözleşme detayı — tam pipeline (sözleşme başlangıç tarihi + ters
# türetme + açık %0 hak ediş)
# ---------------------------------------------------------------------------


def test_garanti_teklif_detay_tam_pipeline() -> None:
    raw = [
        _box(20, 380, 280, 44, "Yürürlük Tarihi"),
        _box(650, 380, 240, 44, "15/12/2023"),
        _box(20, 620, 380, 40, "Tahsilat Tutarı (Devlet"),
        _box(20, 664, 300, 40, "Katkısı Hariç)"),
        _box(650, 632, 260, 44, "1.690,00 TL"),
        _box(20, 780, 360, 44, "Devlet Katkısı Tutarı"),
        _box(650, 780, 260, 44, "502,00 TL"),
        _box(20, 900, 380, 40, "Birikim Tutarı (Devlet"),
        _box(20, 944, 300, 40, "Katkısı Hariç)"),
        _box(650, 912, 260, 44, "2.635,47 TL"),
        _box(20, 1060, 380, 44, "Devlet Katkısı Birikimi*"),
        _box(650, 1060, 260, 44, "699,18 TL"),
        _box(20, 1340, 340, 40, "Hak Edilen Devlet"),
        _box(20, 1384, 300, 40, "Katkısı Oranı*"),
        _box(650, 1352, 200, 44, "%0.00"),
        _box(20, 1500, 340, 40, "Hak Edilen Devlet"),
        _box(20, 1544, 320, 40, "Katkısı Tutarı**"),
        _box(650, 1512, 200, 44, "0,00 TL"),
    ]
    r = run_pipeline(raw, bugun=date(2026, 5, 5))

    # Çözümlenmiş alanlar
    assert r.odenen_toplam_tutar == 1_690.00
    assert r.birikiminiz == 2_635.47
    assert r.devlet_katkisi == 699.18
    assert r.hak_edis_oraniniz == 0.0
    assert r.hak_edis_tutariniz == 0.0
    assert r.devlet_katkili is True
    # Yatırım getirisi ters türetildi: 2635.47 - 1690.00
    assert r.yatirim_getiriniz == 945.47
    # Süre: floor((2026-05-05 - 2023-12-15)/365.25) = floor(872/365.25) = 2
    assert r.hak_edise_esas_sure == 2.0
    # Hesap: stopaj %15 (2 yıl < 10), kesinti 945.47×0.15=141.82, net 2635.47+0-141.82
    assert r.hesap is not None
    assert r.hesap.uygulanan_stopaj_orani == 0.15
    assert r.hesap.stopaj_kesintisi_tl == 141.82
    assert r.hesap.cikista_net_tl == 2_493.65
    assert r.eksik_alanlar == []


# ---------------------------------------------------------------------------
# Garanti mobil kompakt — BES Giriş Tarihi (sistem giriş) → süre + UYARI notu
# ---------------------------------------------------------------------------


def test_garanti_mobil_kompakt_bes_giris_uyarisi() -> None:
    raw = [
        _box(20, 100, 200, 30, "BES Giriş Tarihi"),
        _box(800, 100, 180, 30, "25/01/2009"),
        _box(20, 200, 220, 30, "Emeklilik Tarihiniz"),
        _box(800, 200, 180, 30, "04/08/2041"),
        _box(20, 400, 150, 30, "Birikiminiz"),
        _box(800, 400, 180, 30, "609.820,01 TL"),
        _box(20, 500, 240, 30, "Ödenen Toplam Tutar"),
        _box(800, 500, 180, 30, "119.192,22 TL"),
        _box(20, 600, 200, 30, "Yatırım Getiriniz"),
        _box(800, 600, 180, 30, "490.627,79 TL"),
        _box(20, 700, 320, 30, "Devlet Katkısı Birikiminiz"),
        _box(800, 700, 180, 30, "82.799,73 TL"),
    ]
    r = run_pipeline(raw, bugun=date(2026, 5, 5))

    assert r.birikiminiz == 609_820.01
    assert r.yatirim_getiriniz == 490_627.79
    assert r.devlet_katkisi == 82_799.73
    assert r.devlet_katkili is True
    # Süre BES Giriş Tarihi'nden: floor((2026-05-05 - 2009-01-25)/365.25) = 17
    assert r.hak_edise_esas_sure == 17.0
    # BES Giriş uyarısı notlarda olmalı
    assert any("BES Giriş Tarihi" in n and "⚠️" in n for n in r.notlar)
    # 17 yıl ≥ 10 → hak ediş %60, stopaj %10
    assert r.hak_edis_oraniniz == 60.0
    assert r.hesap is not None
    assert r.hesap.uygulanan_stopaj_orani == 0.10


# ---------------------------------------------------------------------------
# Devlet katkısız — hak ediş tutarı gerekmez
# ---------------------------------------------------------------------------


def test_devlet_katkisiz_pipeline() -> None:
    raw = [
        _box(20, 100, 200, 30, "Birikiminiz"),
        _box(400, 100, 160, 30, "100.000,00 TL"),
        _box(20, 200, 240, 30, "Ödenen Toplam Tutar"),
        _box(400, 200, 160, 30, "80.000,00 TL"),
        _box(20, 300, 200, 30, "Yatırım Getiriniz"),
        _box(400, 300, 160, 30, "20.000,00 TL"),
        _box(20, 400, 220, 30, "Hak Edişe Esas Süre"),
        _box(400, 400, 80, 30, "12 yıl"),
    ]
    r = run_pipeline(raw, bugun=date(2026, 5, 5))

    assert r.devlet_katkili is False
    assert r.birikiminiz == 100_000.00
    assert r.yatirim_getiriniz == 20_000.00
    assert r.hak_edise_esas_sure == 12.0
    # Devlet katkısız → hak ediş tutarı eksik sayılmaz
    assert r.eksik_alanlar == []
    assert r.hesap is not None
    # 12 yıl ≥ 10 → %10 stopaj; net = birikim - stopaj (hak ediş formülde yok)
    assert r.hesap.uygulanan_stopaj_orani == 0.10
    assert r.hesap.stopaj_kesintisi_tl == 2_000.00
    assert r.hesap.cikista_net_tl == 98_000.00


# ---------------------------------------------------------------------------
# Eksik alan — hesap yapılamaz, eksik_alanlar dolu, çökmez
# ---------------------------------------------------------------------------


def test_eksik_alan_hesap_yapilamaz() -> None:
    raw = [
        _box(20, 100, 200, 30, "Birikiminiz"),
        _box(400, 100, 160, 30, "100.000,00 TL"),
        # Yatırım getirisi yok, süre yok, ödenen yok → türetilemez
    ]
    r = run_pipeline(raw, bugun=date(2026, 5, 5))
    assert r.hesap is None
    assert "Yatırım getiriniz" in r.eksik_alanlar
    assert "Hak edişe esas süre (yıl)" in r.eksik_alanlar


def test_bos_girdi_cokmeden_doner() -> None:
    r = run_pipeline([], bugun=date(2026, 5, 5))
    assert r.hesap is None
    assert r.birikiminiz is None
    assert len(r.eksik_alanlar) > 0


# ---------------------------------------------------------------------------
# Süre kaynak önceliği: sözleşme başlangıç tarihi, BES giriş tarihinden ÖNCE gelir
# ---------------------------------------------------------------------------


def test_sure_onceligi_sozlesme_baslangic_bes_giristen_once() -> None:
    """Ekranda hem 'Yürürlük Tarihi' hem 'BES Giriş Tarihi' varsa → Yürürlük kullanılır,
    BES giriş uyarısı GÖSTERİLMEZ (çünkü o kaynak kullanılmadı)."""
    raw = [
        _box(20, 100, 200, 30, "BES Giriş Tarihi"),
        _box(800, 100, 180, 30, "25/01/2009"),
        _box(20, 250, 280, 44, "Yürürlük Tarihi"),
        _box(650, 250, 240, 44, "15/12/2023"),
        _box(20, 400, 150, 30, "Birikiminiz"),
        _box(800, 400, 180, 30, "600.000,00 TL"),
        _box(20, 500, 200, 30, "Yatırım Getiriniz"),
        _box(800, 500, 180, 30, "480.000,00 TL"),
        _box(20, 600, 320, 30, "Devlet Katkısı Birikiminiz"),
        _box(800, 600, 180, 30, "80.000,00 TL"),
    ]
    r = run_pipeline(raw, bugun=date(2026, 5, 5))
    # Yürürlük 15/12/2023 → 2 yıl (BES giriş 2009 olsaydı 17 yıl olurdu)
    assert r.hak_edise_esas_sure == 2.0
    assert any("sözleşme başlangıç" in n for n in r.notlar)
    assert not any("BES Giriş Tarihi" in n for n in r.notlar)

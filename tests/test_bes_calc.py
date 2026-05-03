"""
bes_calc.py davranış testleri.

Not: Bu testler şu anki iki-kademeli stopaj mantığını (%10 / %15) kilitler.
%5 (emeklilik/vefat/maluliyet) kademesi eklendikten sonra, ilgili test
fonksiyonları yeni API'yi (cikis_nedeni parametresi) kapsayacak şekilde
güncellenecektir.
"""

from __future__ import annotations

import pytest

from src.bes_calc import (
    HAK_EDIS_STOPAJ_ESIK_YIL,
    STOPAJ_ORANI_KISA,
    STOPAJ_ORANI_UZUN,
    CikisHesabi,
    cikista_ele_gecen_tl,
    format_tl,
    hak_edis_orani_from_sure,
    hak_edis_tutari_from_oran,
    stopaj_kesintisi_tl,
    stopaj_orani,
)


# ---------------------------------------------------------------------------
# hak_edis_orani_from_sure — EGM kademeli oran (yaş şartı yok)
# ---------------------------------------------------------------------------


class TestHakEdisOraniFromSure:
    """3y → %15, 6y → %35, 10y → %60. < 3 yıl → %0."""

    def test_iki_yil_sifir(self) -> None:
        assert hak_edis_orani_from_sure(2) == 0.0

    def test_uc_yil_yuzde_onbes(self) -> None:
        assert hak_edis_orani_from_sure(3) == 15.0

    def test_bes_yil_yuzde_onbes(self) -> None:
        assert hak_edis_orani_from_sure(5) == 15.0

    def test_alti_yil_yuzde_otuzbes(self) -> None:
        assert hak_edis_orani_from_sure(6) == 35.0

    def test_dokuz_yil_yuzde_otuzbes(self) -> None:
        assert hak_edis_orani_from_sure(9) == 35.0

    def test_on_yil_yuzde_altmis(self) -> None:
        assert hak_edis_orani_from_sure(10) == 60.0

    def test_ondort_yil_yuzde_altmis(self) -> None:
        assert hak_edis_orani_from_sure(14) == 60.0

    def test_otuz_yil_yuzde_altmis(self) -> None:
        assert hak_edis_orani_from_sure(30) == 60.0

    def test_sifir_yil_sifir(self) -> None:
        assert hak_edis_orani_from_sure(0) == 0.0

    def test_kademe_kesin_sınır_tam_uc(self) -> None:
        # 2.99 → 0, 3.0 → 15
        assert hak_edis_orani_from_sure(2.99) == 0.0
        assert hak_edis_orani_from_sure(3.0) == 15.0


class TestHakEdisTutariFromOran:
    """Hak ediş tutarı = devlet_katkisi × oran/100, kuruşa yuvarlar."""

    def test_basit_hesap(self) -> None:
        # 82.799,73 × 60% = 49.679,84
        assert hak_edis_tutari_from_oran(82799.73, 60.0) == 49679.84

    def test_yuzde_sifir(self) -> None:
        assert hak_edis_tutari_from_oran(50_000, 0.0) == 0.0

    def test_yuzde_yuz(self) -> None:
        assert hak_edis_tutari_from_oran(50_000, 100.0) == 50_000.0

    def test_kurus_yuvarlama(self) -> None:
        # 100,01 × 33% = 33.0033 → 33.00
        assert hak_edis_tutari_from_oran(100.01, 33.0) == 33.00


# ---------------------------------------------------------------------------
# stopaj_orani
# ---------------------------------------------------------------------------


class TestStopajOrani:
    """Stopaj oranı: >=10 yıl → %10, aksi halde %15."""

    def test_kisa_sure_on_altinda_yuzde_onbes(self) -> None:
        assert stopaj_orani(5) == STOPAJ_ORANI_KISA == 0.15

    def test_sifir_yil_yuzde_onbes(self) -> None:
        assert stopaj_orani(0) == 0.15

    def test_dokuz_dokuzyuzdoksandokuz_yil_yuzde_onbes(self) -> None:
        """Sınıra çok yakın ama altında: hâlâ %15."""
        assert stopaj_orani(9.999) == 0.15

    def test_tam_on_yil_yuzde_on(self) -> None:
        """Sınır dâhil: 10 yılda %10'a düşer."""
        assert stopaj_orani(HAK_EDIS_STOPAJ_ESIK_YIL) == STOPAJ_ORANI_UZUN == 0.10

    def test_uzun_sure_yuzde_on(self) -> None:
        assert stopaj_orani(15) == 0.10

    def test_cok_uzun_sure_yuzde_on(self) -> None:
        assert stopaj_orani(40) == 0.10


# ---------------------------------------------------------------------------
# stopaj_kesintisi_tl
# ---------------------------------------------------------------------------


class TestStopajKesintisi:
    def test_kisa_sure_yuzde_onbes(self) -> None:
        """20.000 × 0.15 = 3.000"""
        assert stopaj_kesintisi_tl(20_000, 5) == pytest.approx(3_000.0)

    def test_uzun_sure_yuzde_on(self) -> None:
        """20.000 × 0.10 = 2.000"""
        assert stopaj_kesintisi_tl(20_000, 12) == pytest.approx(2_000.0)

    def test_sinir_degeri_tam_on(self) -> None:
        """Tam 10 yıl: %10 kullanılır."""
        assert stopaj_kesintisi_tl(10_000, 10) == pytest.approx(1_000.0)

    def test_sifir_getiri_sifir_kesinti(self) -> None:
        assert stopaj_kesintisi_tl(0, 20) == 0.0

    def test_kusuratli_getiri(self) -> None:
        """1234.56 × 0.10 = 123.456 (yuvarlamasız)."""
        assert stopaj_kesintisi_tl(1234.56, 12) == pytest.approx(123.456)


# ---------------------------------------------------------------------------
# cikista_ele_gecen_tl
# ---------------------------------------------------------------------------


class TestCikistaEleGecenDevletKatkisiz:
    """Katkısız: net = birikim - stopaj. hak_edis_tutari hesaba katılmaz."""

    def test_kisa_sure_hesap(self) -> None:
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=0,
            yatirim_getiriniz=20_000,
            hak_edise_esas_sure_yil=5,
            devlet_katkili_sozlesme=False,
        )
        assert h.uygulanan_stopaj_orani == 0.15
        assert h.stopaj_kesintisi_tl == 3_000.00
        assert h.cikista_net_tl == 97_000.00

    def test_uzun_sure_hesap(self) -> None:
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=0,
            yatirim_getiriniz=20_000,
            hak_edise_esas_sure_yil=12,
            devlet_katkili_sozlesme=False,
        )
        assert h.uygulanan_stopaj_orani == 0.10
        assert h.stopaj_kesintisi_tl == 2_000.00
        assert h.cikista_net_tl == 98_000.00

    def test_hak_edis_tutari_gormezden_gelinir(self) -> None:
        """Katkısız sözleşmede 50.000 hak ediş gelse de net aynı."""
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=50_000,  # yok sayılmalı
            yatirim_getiriniz=10_000,
            hak_edise_esas_sure_yil=12,
            devlet_katkili_sozlesme=False,
        )
        assert h.cikista_net_tl == 99_000.00  # 100k - 1k (10% × 10k)

    def test_sifir_degerler(self) -> None:
        h = cikista_ele_gecen_tl(0, 0, 0, 0, devlet_katkili_sozlesme=False)
        assert h.uygulanan_stopaj_orani == 0.15
        assert h.stopaj_kesintisi_tl == 0.0
        assert h.cikista_net_tl == 0.0


class TestCikistaEleGecenDevletKatkili:
    """Katkılı: net = birikim + hak_edis_tutari - stopaj."""

    def test_kisa_sure_katkili(self) -> None:
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=20_000,
            yatirim_getiriniz=15_000,
            hak_edise_esas_sure_yil=7,
            devlet_katkili_sozlesme=True,
        )
        assert h.uygulanan_stopaj_orani == 0.15
        assert h.stopaj_kesintisi_tl == 2_250.00  # 15k × 15%
        assert h.cikista_net_tl == 117_750.00  # 100k + 20k - 2.25k

    def test_uzun_sure_katkili(self) -> None:
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=20_000,
            yatirim_getiriniz=15_000,
            hak_edise_esas_sure_yil=15,
            devlet_katkili_sozlesme=True,
        )
        assert h.uygulanan_stopaj_orani == 0.10
        assert h.stopaj_kesintisi_tl == 1_500.00  # 15k × 10%
        assert h.cikista_net_tl == 118_500.00  # 100k + 20k - 1.5k

    def test_default_devlet_katkili_true(self) -> None:
        """Parametresiz çağrı devlet katkılı davranışı kullanır (varsayılan)."""
        h = cikista_ele_gecen_tl(
            birikiminiz=100_000,
            hak_edis_tutariniz=20_000,
            yatirim_getiriniz=10_000,
            hak_edise_esas_sure_yil=12,
        )
        # Varsayılan katkılı → hak_edis eklenir
        assert h.cikista_net_tl == 100_000 + 20_000 - 1_000  # = 119_000.00


class TestCikisHesabiDataclass:
    """CikisHesabi frozen dataclass: alan sırası/isimleri sabit."""

    def test_alanlar(self) -> None:
        h = cikista_ele_gecen_tl(100, 0, 50, 12, devlet_katkili_sozlesme=False)
        assert isinstance(h, CikisHesabi)
        assert hasattr(h, "uygulanan_stopaj_orani")
        assert hasattr(h, "stopaj_kesintisi_tl")
        assert hasattr(h, "cikista_net_tl")

    def test_frozen(self) -> None:
        h = cikista_ele_gecen_tl(100, 0, 50, 12, devlet_katkili_sozlesme=False)
        with pytest.raises((AttributeError, Exception)):
            h.cikista_net_tl = 999  # type: ignore[misc]


class TestYuvarlama:
    """round(·, 2) davranışı: küsuratlı getiride 2 ondalık kalmalı."""

    def test_iki_ondalik_yuvarlama(self) -> None:
        # 1234.567 × 0.10 = 123.4567 → 123.46
        h = cikista_ele_gecen_tl(
            birikiminiz=50_000,
            hak_edis_tutariniz=0,
            yatirim_getiriniz=1234.567,
            hak_edise_esas_sure_yil=12,
            devlet_katkili_sozlesme=False,
        )
        assert h.stopaj_kesintisi_tl == 123.46
        assert h.cikista_net_tl == round(50_000 - 123.46, 2)


# ---------------------------------------------------------------------------
# format_tl
# ---------------------------------------------------------------------------


class TestFormatTl:
    def test_basit_tam_sayi(self) -> None:
        assert format_tl(1234) == "1.234,00"

    def test_kusuratli(self) -> None:
        assert format_tl(1234.56) == "1.234,56"

    def test_milyonlu(self) -> None:
        assert format_tl(1_234_567.89) == "1.234.567,89"

    def test_yuzden_kucuk(self) -> None:
        assert format_tl(42.1) == "42,10"

    def test_sifir(self) -> None:
        assert format_tl(0) == "0,00"

    def test_negatif(self) -> None:
        assert format_tl(-1234.5) == "-1.234,50"

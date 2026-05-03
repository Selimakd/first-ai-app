"""
bes_parse.py içindeki saf (I/O'suz) yardımcı fonksiyonlar için testler.

OCR / EasyOCR gerekmez; sadece string işleme davranışı.
"""

from __future__ import annotations

import pytest

from src.bes_parse import (
    fold_tr_ascii,
    first_amount_in_text,
    first_scalar_in_text,
    infer_devlet_katkili_sozlesme,
    match_field,
    normalize_line,
    parse_oran_from_text,
    tr_amount_to_float,
)


# ---------------------------------------------------------------------------
# tr_amount_to_float — TR para formatını float'a çevirir.
# ---------------------------------------------------------------------------


class TestTrAmountToFloat:
    def test_tr_binlik_nokta_ondalik_virgul(self) -> None:
        assert tr_amount_to_float("1.234,56") == 1234.56

    def test_milyonluk(self) -> None:
        assert tr_amount_to_float("1.234.567,89") == 1234567.89

    def test_ondalik_yok(self) -> None:
        assert tr_amount_to_float("1.234") == 1234.0

    def test_sadece_virgul(self) -> None:
        assert tr_amount_to_float("12,5") == 12.5

    def test_sade_tam_sayi(self) -> None:
        assert tr_amount_to_float("42") == 42.0

    def test_tl_suffix(self) -> None:
        assert tr_amount_to_float("1.234,56 TL") == 1234.56

    def test_try_suffix(self) -> None:
        assert tr_amount_to_float("999,90 TRY") == 999.90

    def test_tl_sembol(self) -> None:
        assert tr_amount_to_float("₺1.000,00") == 1000.0

    def test_bosluk_icinde(self) -> None:
        assert tr_amount_to_float("  1.234,56  ") == 1234.56

    def test_bos_string(self) -> None:
        assert tr_amount_to_float("") is None

    def test_gecersiz(self) -> None:
        assert tr_amount_to_float("abc") is None

    def test_sadece_harf_ve_sembol(self) -> None:
        assert tr_amount_to_float("TL") is None


# ---------------------------------------------------------------------------
# fold_tr_ascii — TR aksanlarını ASCII'ye indirir, küçük harf yapar.
# ---------------------------------------------------------------------------


class TestFoldTrAscii:
    def test_i_noktali(self) -> None:
        assert fold_tr_ascii("İSTANBUL") == "istanbul"

    def test_yumusak_g(self) -> None:
        assert fold_tr_ascii("Ğüzel") == "guzel"

    def test_tum_tr_karakterler(self) -> None:
        assert fold_tr_ascii("ÇĞİÖŞÜçğıöşü") == "cgiosucgiosu"

    def test_zaten_ascii(self) -> None:
        assert fold_tr_ascii("hello") == "hello"

    def test_noktali_kucuk_i(self) -> None:
        # 'ı' → 'i' olmalı (translate tablosuyla)
        assert fold_tr_ascii("ışık") == "isik"


# ---------------------------------------------------------------------------
# normalize_line — fazla boşluk siler, küçük harf.
# ---------------------------------------------------------------------------


class TestNormalizeLine:
    def test_coklu_bosluk(self) -> None:
        assert normalize_line("  Hak   Ediş    Tutarı  ") == "hak ediş tutarı"

    def test_tab_ve_newline(self) -> None:
        assert normalize_line("Ad\tSoyad\n") == "ad soyad"


# ---------------------------------------------------------------------------
# first_amount_in_text / first_scalar_in_text
# ---------------------------------------------------------------------------


class TestFirstAmountInText:
    def test_basit(self) -> None:
        assert first_amount_in_text("Birikiminiz: 12.345,67 TL") == 12345.67

    def test_tl_siz(self) -> None:
        assert first_amount_in_text("tutar 9.876,54") == 9876.54

    def test_sadece_virgul(self) -> None:
        assert first_amount_in_text("42,5") == 42.5

    def test_yok(self) -> None:
        assert first_amount_in_text("sadece metin") is None


class TestFirstScalarInText:
    def test_yil(self) -> None:
        assert first_scalar_in_text("12 yıl") == 12.0

    def test_coklu_ilk_dogru(self) -> None:
        assert first_scalar_in_text("yaş 33, maaş 9000") == 33.0


# ---------------------------------------------------------------------------
# parse_oran_from_text — yüzde oranı yakala.
# ---------------------------------------------------------------------------


class TestParseOranFromText:
    def test_sayi_yuzde(self) -> None:
        assert parse_oran_from_text("60 %") == 60.0

    def test_yuzde_sayi(self) -> None:
        assert parse_oran_from_text("%60") == 60.0

    def test_virgullu_yuzde(self) -> None:
        assert parse_oran_from_text("54,2 %") == 54.2

    def test_etiketli(self) -> None:
        assert parse_oran_from_text("Hak Ediş Oranınız %60") == 60.0

    def test_sifir_di_sari(self) -> None:
        """%0 kabul edilmez (0 < v <= 100 kontrolü)."""
        assert parse_oran_from_text("%0") is None

    def test_yuzden_buyuk_reddedilir(self) -> None:
        assert parse_oran_from_text("%150") is None

    def test_yuzde_isareti_yoksa_none(self) -> None:
        assert parse_oran_from_text("60 yıl") is None


# ---------------------------------------------------------------------------
# match_field — en uzun eşleşen etiket kazanır.
# ---------------------------------------------------------------------------


class TestMatchField:
    def test_birikim(self) -> None:
        assert match_field("birikiminiz 1.234,56") == "birikiminiz"

    def test_hak_edis_tutari(self) -> None:
        assert match_field("hak ediş tutarınız 10.000") == "hak_edis_tutariniz"

    def test_hak_edis_orani(self) -> None:
        # "hak ediş oranınız" daha uzun → "hak_edis_oraniniz" seçilmeli
        assert match_field("hak ediş oranınız %60") == "hak_edis_oraniniz"

    def test_devlet_katkisi(self) -> None:
        assert match_field("devlet katkısı 500") == "devlet_katkisi"

    def test_bilinmeyen(self) -> None:
        assert match_field("rastgele satır") is None


# ---------------------------------------------------------------------------
# infer_devlet_katkili_sozlesme — satır başı başlık.
# ---------------------------------------------------------------------------


class TestInferDevletKatkili:
    def test_bas_liktan_pozitif(self) -> None:
        lines = ["Ödenen Toplam Tutar", "Devlet Katkısı", "5.000,00"]
        assert infer_devlet_katkili_sozlesme(lines) is True

    def test_yatirilan_devlet_katkisi_baslik(self) -> None:
        lines = ["Yatırılan Devlet Katkısı"]
        assert infer_devlet_katkili_sozlesme(lines) is True

    def test_uzun_metin_icindeki_gecis_yanlis_pozitif_degil(self) -> None:
        """Satır uzun / açıklama gibi: başlık sayılmamalı."""
        lines = [
            "Bu metin devlet katkısı ile ilgili mevzuat açıklamasıdır ve sadece bilgilendirme amaçlıdır."
        ]
        assert infer_devlet_katkili_sozlesme(lines) is False

    def test_tamamen_bagimsiz_satirlar(self) -> None:
        lines = ["Birikiminiz", "100.000,00", "Yatırım Getiriniz", "20.000,00"]
        assert infer_devlet_katkili_sozlesme(lines) is False

    def test_bos_liste(self) -> None:
        assert infer_devlet_katkili_sozlesme([]) is False

"""
extract_from_ocr_boxes için sentetik bbox testleri.

EasyOCR'ın tipik çıktı formatı: (bbox, text, conf) — bbox 4 köşe [[x0,y0], [x1,y0], [x1,y1], [x0,y1]].
Bu testler gerçek OCR çağırmaz; bbox koordinatlarını elle kurgulayarak uzamsal eşlemenin
doğruluğunu kilitler.
"""

from __future__ import annotations

from typing import Any

from src.bes_parse import extract_from_ocr_boxes


def _box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95) -> tuple[Any, str, float]:
    """Kolay bbox kurulumu: sol-üst köşe + genişlik/yükseklik."""
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# ---------------------------------------------------------------------------
# Senaryo A: İki sütun — ödenen ve yatırım etiketleri yan yana, tutarlar altta
# ---------------------------------------------------------------------------


def test_iki_sutun_odenen_yatirim() -> None:
    """
    |  Ödenen Toplam Tutar  |  Yatırım Getiriniz  |
    |     50.000,00 TL      |     12.500,00 TL    |
    """
    raw = [
        _box(20, 100, 200, 24, "Ödenen Toplam Tutar"),
        _box(260, 100, 180, 24, "Yatırım Getiriniz"),
        _box(30, 140, 140, 26, "50.000,00 TL"),
        _box(270, 140, 140, 26, "12.500,00 TL"),
        _box(20, 200, 120, 24, "Birikiminiz"),
        _box(30, 240, 150, 26, "62.500,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.odenen_toplam_tutar == 50_000.00
    assert out.yatirim_getiriniz == 12_500.00
    assert out.birikiminiz == 62_500.00


# ---------------------------------------------------------------------------
# Senaryo B: Etiket+değer aynı satırda (tablo stili)
# ---------------------------------------------------------------------------


def test_etiket_deger_ayni_satirda() -> None:
    """
    |  Hak Edişe Esas Süre  |  14 yıl  |
    |  Hak Ediş Oranınız    |  %60     |
    """
    raw = [
        _box(20, 100, 200, 24, "Hak Edişe Esas Süre"),
        _box(260, 100, 80, 24, "14 yıl"),
        _box(20, 140, 200, 24, "Hak Ediş Oranınız"),
        _box(260, 140, 60, 24, "%60"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.hak_edise_esas_sure == 14.0
    assert out.hak_edis_oraniniz == 60.0


# ---------------------------------------------------------------------------
# Senaryo C: Etiket üstte, değer hemen altında (mobil stack)
# ---------------------------------------------------------------------------


def test_etiket_ust_deger_alt() -> None:
    raw = [
        _box(20, 100, 150, 24, "Birikiminiz"),
        _box(20, 140, 170, 26, "135.000,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 135_000.00


# ---------------------------------------------------------------------------
# Senaryo D: Devlet katkılı — «Yatırılan Devlet Katkısı» != «Devlet Katkısı»
#   Yanlışlıkla daha spesifik etiketi devlet_katkisi alanına atama yok.
# ---------------------------------------------------------------------------


def test_yatirilan_devlet_katkisi_devlet_katkisiyla_karismaz() -> None:
    raw = [
        # «Devlet Katkısı» — bu gerçek alan
        _box(20, 100, 150, 24, "Devlet Katkısı"),
        _box(20, 140, 150, 26, "83.187,26 TL"),
        # «Yatırılan Devlet Katkısı» — farklı etiket, devlet_katkisi'ne atanmamalı
        _box(300, 100, 260, 24, "Yatırılan Devlet Katkısı"),
        _box(300, 140, 150, 26, "80.000,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.devlet_katkisi == 83_187.26


# ---------------------------------------------------------------------------
# Senaryo E: 3 kolonlu düzen — süre / oran / tutar
# ---------------------------------------------------------------------------


def test_uc_kolon_sure_oran_tutar() -> None:
    """
    |  Hak Edişe Esas Süre  |  Hak Ediş Oranınız  |  Hak Ediş Tutarınız  |
    |         14            |        %60          |      49.912,35 TL     |
    """
    raw = [
        _box(10, 100, 180, 24, "Hak Edişe Esas Süre"),
        _box(220, 100, 180, 24, "Hak Ediş Oranınız"),
        _box(430, 100, 180, 24, "Hak Ediş Tutarınız"),
        _box(70, 140, 40, 26, "14"),
        _box(280, 140, 50, 26, "%60"),
        _box(440, 140, 160, 26, "49.912,35 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.hak_edise_esas_sure == 14.0
    assert out.hak_edis_oraniniz == 60.0
    assert out.hak_edis_tutariniz == 49_912.35


# ---------------------------------------------------------------------------
# Senaryo F: "1 yıl" — %60 / birikim gibi büyük sayıların son rakamını yıl sanmamalı.
# (Önceki parser bug'ı: "946,6" → 6 olarak seçiliyordu.)
# ---------------------------------------------------------------------------


def test_bir_yil_sure_alinir_tutar_son_rakami_alinmaz() -> None:
    raw = [
        _box(20, 100, 180, 24, "Hak Edişe Esas Süre"),
        _box(220, 100, 60, 24, "1 yıl"),
        # Aynı satırın altında büyük bir tutar — son rakamı "6" yıl sayılmamalı
        _box(20, 140, 170, 26, "946.000,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.hak_edise_esas_sure == 1.0


# ---------------------------------------------------------------------------
# Senaryo G: Boş / bozuk girdi
# ---------------------------------------------------------------------------


def test_bos_giris_hic_alan_yok() -> None:
    out = extract_from_ocr_boxes([])
    assert all(v is None for v in out.to_dict().values())


# ---------------------------------------------------------------------------
# Senaryo H: Tek kutuda etiket + değer (bazen OCR böyle birleştirir)
# ---------------------------------------------------------------------------


def test_tek_kutuda_etiket_ve_deger() -> None:
    raw = [
        _box(20, 100, 300, 24, "Birikiminiz 62.500,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 62_500.00


# ---------------------------------------------------------------------------
# Senaryo I: Aynı değer hem birikim hem yatırım gibi görünürse yatırım iptal
# (OCR'ın yatırım kolonuna yanlışlıkla birikim yazması)
# ---------------------------------------------------------------------------


def test_yatirim_birikim_esit_ise_yatirim_iptal() -> None:
    raw = [
        _box(20, 100, 200, 24, "Ödenen Toplam Tutar"),
        _box(260, 100, 180, 24, "Yatırım Getiriniz"),
        # Her iki tutar da aynı — OCR birikim değerini yatırıma yazmış
        _box(30, 140, 140, 26, "100.000,00"),
        _box(270, 140, 140, 26, "135.000,00"),
        _box(20, 200, 120, 24, "Birikiminiz"),
        _box(30, 240, 150, 26, "135.000,00"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 135_000.00
    assert out.odenen_toplam_tutar == 100_000.00
    # Yatırım=birikim olduğu için bu iptal edilmiş olmalı
    assert out.yatirim_getiriniz is None


# ---------------------------------------------------------------------------
# Senaryo J: Satır sırası karışık (OCR Y bazen gürültülü) — bbox mesafesi kurtarsın
# ---------------------------------------------------------------------------


def test_toplam_birikiminiz_etiketi_birikim_olarak_yakalanir() -> None:
    """
    Bazı sözleşmelerde tek başlık «Toplam Birikiminiz» olur (Birikiminiz yerine).
    Eski exclude listesi bu etiketi yanlışlıkla eliyordu; gerçek değer yerine
    fallback'in yakaladığı «1 YIL» (=1.0) atanıyordu.
    """
    raw = [
        # Üstte gauge: «Toplam Birikiminiz» ve hemen altında değer
        _box(800, 250, 280, 30, "Toplam Birikiminiz"),
        _box(820, 320, 240, 36, "1.161.723,14 TL"),

        # Diğer kartlar
        _box(120, 480, 230, 26, "Ödenen Toplam Tutar"),
        _box(120, 540, 200, 36, "903.372 TL"),
        _box(960, 480, 200, 26, "Yatırım Getiriniz"),
        _box(960, 540, 200, 36, "258.351,14 TL"),

        # Sağ alt: süre/oran/tutar
        _box(1700, 900, 220, 22, "HAK EDİŞE ESAS SÜRE"),
        _box(1700, 940, 80, 32, "1 YIL"),
        _box(1700, 1010, 200, 22, "HAK EDİŞ ORANINIZ"),
        _box(1700, 1050, 80, 32, "% 100"),
        _box(1700, 1130, 220, 22, "HAK EDİŞ TUTARINIZ"),
        _box(1700, 1170, 240, 32, "1.161.723,14 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 1_161_723.14
    assert out.odenen_toplam_tutar == 903_372.00
    assert out.yatirim_getiriniz == 258_351.14
    assert out.hak_edise_esas_sure == 1.0
    assert out.hak_edis_oraniniz == 100.0
    assert out.hak_edis_tutariniz == 1_161_723.14


def test_garanti_mobil_birikim_ekrani() -> None:
    """
    Garanti BES mobil uygulaması — Toplam Birikim sayfası. İki yeni etiket varyantı:
    «Ödenen Tutar» (toplam yok) ve «Fon Getirisi» (yatırım getirisi yerine). Ayrıca
    «Sözleşme No: 15485747» gibi ham rakam dizisi para sayılmamalı.
    """
    raw = [
        _box(70, 50, 510, 70, "Toplam Birikiminiz"),
        _box(870, 50, 480, 70, "Sözleşme Seçin →"),
        _box(420, 280, 590, 50, "Sözleşme No: 15485747"),  # ← para olarak alınmamalı
        _box(380, 350, 670, 90, "1.228.227,00 TL"),
        _box(80, 580, 540, 55, "Son 1 Aylık Değişim:"),
        _box(950, 580, 200, 55, "%8,41 ▲"),
        _box(80, 660, 540, 55, "Son 1 Yıllık Değişim:"),
        _box(950, 660, 280, 55, "%379,18 ▲"),
        _box(80, 870, 380, 50, "Birikim Dağılımı"),
        _box(105, 1010, 130, 100, "%80,2"),
        _box(265, 1010, 460, 100, "Ödenen Tutar"),
        _box(870, 1010, 480, 100, "985.612,00 TL"),
        _box(105, 1230, 130, 100, "%19,8"),
        _box(265, 1230, 480, 100, "Fon Getirisi"),
        _box(870, 1230, 480, 100, "242.615,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 1_228_227.00
    assert out.odenen_toplam_tutar == 985_612.00
    assert out.yatirim_getiriniz == 242_615.00
    # Diğer alanlar bu ekranda yok:
    assert out.devlet_katkisi is None
    assert out.hak_edise_esas_sure is None
    assert out.hak_edis_oraniniz is None
    assert out.hak_edis_tutariniz is None


def test_ham_sayi_dizisi_para_sayilmaz() -> None:
    """«Sözleşme No: 15485747» gibi formatsız sayılar para olarak parse edilmemeli."""
    raw = [
        _box(20, 100, 150, 30, "Birikiminiz"),
        _box(20, 200, 300, 30, "Müşteri No: 9876543"),  # currency suffix yok
        _box(20, 250, 200, 30, "62.500,00 TL"),  # gerçek tutar
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 62_500.00


def test_yuzdelik_para_sayilmaz() -> None:
    """«%80,2» gibi yüzdelik değerler para olarak parse edilmemeli."""
    raw = [
        _box(20, 100, 150, 30, "Birikiminiz"),
        _box(20, 150, 80, 30, "%80,2"),  # yanlışlıkla money seçilmemeli
        _box(20, 200, 200, 30, "62.500,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.birikiminiz == 62_500.00


def test_multi_upload_y_offset_birikim_plus_detay() -> None:
    """
    Garanti'nin iki ekranı birden yüklendiğinde (birikim sayfası + detay sayfası),
    Y-offset uygulanmış bbox'larla 7 alan tek bir parse'da çıkmalı.
    Bu, app.py'deki multi-upload akışının davranışıdır.
    """
    # Sayfa 1 — Garanti birikim ekranı (Y 0-1500 civarı)
    page1 = [
        _box(70, 50, 510, 70, "Toplam Birikiminiz"),
        _box(420, 280, 590, 50, "Sözleşme No: 15485747"),
        _box(380, 350, 670, 90, "1.228.227,00 TL"),
        _box(105, 1010, 130, 100, "%80,2"),
        _box(265, 1010, 460, 100, "Ödenen Tutar"),
        _box(870, 1010, 480, 100, "985.612,00 TL"),
        _box(105, 1230, 130, 100, "%19,8"),
        _box(265, 1230, 480, 100, "Fon Getirisi"),
        _box(870, 1230, 480, 100, "242.615,00 TL"),
    ]
    # Sayfa 2 — detay ekranı; offset (max_y_page1 ≈ 1330 + PAD 2000 = ~3330)
    Y = 3330
    page2 = [
        _box(480, 210 + Y, 580, 80, "Ödenen Toplam Tutar"),
        _box(540, 300 + Y, 400, 90, "985.612 TL"),
        _box(540, 480 + Y, 480, 80, "Yatırım Getiriniz"),
        _box(580, 580 + Y, 360, 90, "242.615 TL"),
        _box(80, 1500 + Y, 480, 50, "HAK EDİŞE ESAS SÜRE"),
        _box(80, 1590 + Y, 140, 80, "1 YIL"),
        _box(80, 1750 + Y, 420, 50, "HAK EDİŞ ORANINIZ"),
        _box(80, 1840 + Y, 180, 80, "% 100"),
        _box(80, 2010 + Y, 460, 50, "HAK EDİŞ TUTARINIZ"),
        _box(80, 2100 + Y, 400, 80, "1.228.227 TL"),
    ]
    out = extract_from_ocr_boxes(page1 + page2)
    # Sayfa 1'den
    assert out.birikiminiz == 1_228_227.00
    # Sayfa 2'den (sayfa 1'deki Ödenen Tutar / Fon Getirisi ile aynı değerler)
    assert out.odenen_toplam_tutar == 985_612.00
    assert out.yatirim_getiriniz == 242_615.00
    assert out.hak_edise_esas_sure == 1.0
    assert out.hak_edis_oraniniz == 100.0
    assert out.hak_edis_tutariniz == 1_228_227.00
    assert out.devlet_katkisi is None


def test_garanti_mobil_detay_ekrani() -> None:
    """
    Garanti BES mobil — Sözleşme Detayı sayfası (tek ekran). 5 alan görünür:
    odenen, yatirim, hak edişe esas süre, hak ediş oranı, hak ediş tutarı.
    Birikim bu ekranda yok; app tarafında ödenen+getiri'den türetilir.
    «KURUM KATKISI HAK EDİŞ DURUMUNUZ» başlığı ve gauge etiketleri («GİRİŞ», «HAK EDİŞ»)
    yanlış pozitif yapmamalı.
    """
    raw = [
        _box(70, 30, 80, 80, "←"),
        _box(400, 30, 480, 80, "Sözleşme Detayı"),
        _box(480, 210, 580, 80, "Ödenen Toplam Tutar"),
        _box(540, 300, 400, 90, "985.612 TL"),
        _box(540, 480, 480, 80, "Yatırım Getiriniz"),
        _box(580, 580, 360, 90, "242.615 TL"),
        _box(80, 740, 800, 60, "KURUM KATKISI HAK EDİŞ DURUMUNUZ"),
        _box(360, 1390, 140, 40, "GİRİŞ"),
        _box(900, 1390, 180, 40, "HAK EDİŞ"),
        _box(80, 1500, 480, 50, "HAK EDİŞE ESAS SÜRE"),
        _box(80, 1590, 140, 80, "1 YIL"),
        _box(80, 1750, 420, 50, "HAK EDİŞ ORANINIZ"),
        _box(80, 1840, 180, 80, "% 100"),
        _box(80, 2010, 460, 50, "HAK EDİŞ TUTARINIZ"),
        _box(80, 2100, 400, 80, "1.228.227 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.odenen_toplam_tutar == 985_612.00
    assert out.yatirim_getiriniz == 242_615.00
    assert out.hak_edise_esas_sure == 1.0
    assert out.hak_edis_oraniniz == 100.0
    assert out.hak_edis_tutariniz == 1_228_227.00
    # Bu ekranda yok:
    assert out.birikiminiz is None
    assert out.devlet_katkisi is None


def test_garanti_devlet_katkili_ust_kart() -> None:
    """
    Garanti devlet katkılı sözleşme detayı — üst kısım. Devlet katkısı ana kalemi
    «Yatırılan Devlet Katkısı» ve «Devlet Katkısı Getirisi» alt kalemleri ile
    karışmamalı. «BİRİKİM KAZANCINIZ» / «DEVLET KATKISI HAK EDİŞ DURUMUNUZ» / yüzdelik
    kazanç oranları yan veriler — alanlara değer atamamalı.
    """
    raw = [
        _box(80, 50, 500, 60, "Ödenen Toplam Tutar"),
        _box(130, 130, 410, 70, "119.192,22 TL"),
        _box(720, 50, 520, 60, "Yatırım Getiriniz"),
        _box(730, 130, 510, 70, "490.627,79 TL"),
        _box(470, 290, 350, 70, "Devlet Katkısı"),
        _box(375, 380, 565, 120, "82.799,73 TL"),
        _box(130, 560, 520, 70, "Yatırılan Devlet Katkısı"),
        _box(180, 640, 330, 80, "31.725,25 TL"),
        _box(730, 560, 500, 70, "Devlet Katkısı Getirisi"),
        _box(780, 640, 320, 80, "51.074,48 TL"),
        _box(80, 830, 480, 50, "BİRİKİM KAZANCINIZ"),
        _box(280, 1240, 200, 80, "%81"),
        _box(680, 1280, 360, 40, "DEVLET KATKISI KAZANCI"),
        _box(680, 1340, 100, 40, "%30,4"),
        _box(80, 1500, 700, 50, "DEVLET KATKISI HAK EDİŞ DURUMUNUZ"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.odenen_toplam_tutar == 119_192.22
    assert out.yatirim_getiriniz == 490_627.79
    assert out.devlet_katkisi == 82_799.73  # ← yatirilan/getirisi karışmasın
    # Bu ekranda yok:
    assert out.birikiminiz is None
    assert out.hak_edise_esas_sure is None
    assert out.hak_edis_oraniniz is None
    assert out.hak_edis_tutariniz is None


def test_garanti_gauge_giris_yili_ayri_kutu() -> None:
    """Gauge altında «2023» ve «GİRİŞ» ayrı kutularda — giris_yili tespit edilmeli."""
    raw = [
        _box(80, 50, 500, 60, "Ödenen Toplam Tutar"),
        _box(180, 110, 300, 70, "1.690 TL"),
        _box(720, 50, 500, 60, "Yatırım Getiriniz"),
        _box(800, 110, 350, 70, "847,67 TL"),
        _box(470, 290, 350, 70, "Devlet Katkısı"),
        _box(440, 380, 460, 100, "689,85 TL"),
        # Gauge altı: 2023 üstte, GİRİŞ altta (ayrı kutular)
        _box(140, 2080, 100, 40, "2023"),
        _box(140, 2130, 100, 40, "GİRİŞ"),
        _box(640, 2080, 100, 40, "2041"),
        _box(620, 2130, 200, 40, "EMEKLİLİK"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.giris_yili == 2023
    # 2041 yıl EMEKLİLİK altında olduğu için yanlışlıkla giriş yılı seçilmemeli
    assert out.devlet_katkisi == 689.85


def test_giris_yili_inline_aynı_kutu() -> None:
    """«2023 GİRİŞ» tek kutuda — yine tespit edilmeli."""
    raw = [
        _box(20, 100, 150, 30, "Birikiminiz"),
        _box(20, 150, 200, 30, "62.500,00 TL"),
        _box(140, 2080, 250, 40, "2023 GİRİŞ"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.giris_yili == 2023


def test_giris_yili_yoksa_none() -> None:
    """GİRİŞ etiketi olmayan ekranda giris_yili None kalır."""
    raw = [
        _box(20, 100, 150, 30, "Birikiminiz"),
        _box(20, 150, 200, 30, "62.500,00 TL"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.giris_yili is None


def test_bbox_sira_karistigi_durumda_dogru_eslesir() -> None:
    """
    OCR çıktıları reader'ın fırlattığı sırada gelsin — bbox mesafesi yine doğru eşlemeli.
    """
    raw = [
        # Bilerek karışık sıralama:
        _box(270, 140, 140, 26, "12.500,00 TL"),
        _box(20, 100, 200, 24, "Ödenen Toplam Tutar"),
        _box(30, 140, 140, 26, "50.000,00 TL"),
        _box(260, 100, 180, 24, "Yatırım Getiriniz"),
    ]
    out = extract_from_ocr_boxes(raw)
    assert out.odenen_toplam_tutar == 50_000.00
    assert out.yatirim_getiriniz == 12_500.00

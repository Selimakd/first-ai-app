"""
Ekran görüntüsünden gözle okunan bbox'ları extract_from_ocr_boxes'a besleyip sonuçları
yazdırır. OCR motoru olmadan parser'ı test etmenin basit yolu: eğer OCR bu görüntüden
bu tuple'ları üretirse, parser doğru alanları çıkarır mı?

Koordinatlar ekran görüntüsünden tahmini olarak alınmıştır — pixel-perfect olması
gerekmez; uzamsal eşlemenin «sağında / altında / hizalı» kararı için yeterli.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bes_parse import extract_from_ocr_boxes


def box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95):
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# Görüntüden gözle okunan yerleşim (senaryo_2 katkili ekran):
# - Sol kart (mavi): Birikiminiz (üstte) / Ödenen + Yatırım (altta, iki sütun)
# - Sağ kart (mor):  Devlet Katkısı (üstte) / Yatırılan Devlet + Devlet Katkısı Getirisi (altta)
# - Alt: Hak Edişe Esas Süre / Hak Ediş Oranınız / Hak Ediş Tutarınız (sağ kolonda stack)
#
# Koordinatlar: x_sol, y_ust, genişlik, yükseklik
raw_boxes = [
    # --- Sol kart: Birikiminiz üstte ---
    box(560, 50, 140, 30, "Birikiminiz"),
    box(520, 95, 260, 44, "614.954,37 TL"),

    # Sol kart altı: iki kolon (Ödenen + Yatırım)
    box(290, 190, 230, 26, "Ödenen Toplam Tutar"),
    box(830, 190, 210, 26, "Yatırım Getiriniz"),
    box(270, 245, 240, 36, "115.942,22 TL"),
    box(820, 245, 240, 36, "499.012,15 TL"),

    # --- Sağ kart: Devlet Katkısı üstte ---
    box(1810, 50, 180, 30, "Devlet Katkısı"),
    box(1810, 95, 240, 44, "83.187,26 TL"),

    # Sağ kart altı: iki kolon
    box(1540, 190, 260, 26, "Yatırılan Devlet Katkısı"),
    box(2110, 190, 240, 26, "Devlet Katkısı Getirisi"),
    box(1540, 245, 200, 36, "31.075,25 TL"),
    box(2110, 245, 200, 36, "52.112,01 TL"),

    # --- Orta / sol alt ---
    box(20, 630, 260, 24, "BİRİKİM KAZANCINIZ"),
    box(170, 680, 120, 22, "KÜMÜL"),
    box(500, 680, 160, 22, "SON 1 YIL"),
    box(220, 725, 180, 22, "TOPLAM KAZANÇ"),
    box(460, 725, 140, 22, "FON KAZANCI"),
    box(440, 870, 80, 22, "DEVLET KATKISI KAZANCI"),
    box(260, 800, 220, 80, "%80,9"),
    box(450, 770, 70, 22, "%49,9"),
    box(450, 890, 60, 22, "%31"),

    # --- Orta: Devlet Katkısı Hak Ediş Durumunuz (gauge — rakamlar 3./6./10. YIL etiketleri) ---
    box(800, 630, 430, 24, "DEVLET KATKISI HAK EDİŞ DURUMUNUZ"),
    box(950, 790, 60, 22, "3. YIL"),
    box(1000, 740, 60, 22, "6. YIL"),
    box(1150, 700, 70, 22, "10. YIL"),
    box(1100, 920, 70, 22, "2012"),
    box(1100, 940, 70, 22, "GİRİŞ"),
    box(1440, 920, 70, 22, "2041"),
    box(1440, 940, 110, 22, "EMEKLİLİK"),

    # --- Sağ alt: Hak edişe esas süre / oran / tutar ---
    box(2200, 665, 220, 22, "HAK EDİŞE ESAS SÜRE"),
    box(2200, 710, 100, 32, "14 YIL"),
    box(2200, 790, 210, 22, "HAK EDİŞ ORANINIZ"),
    box(2200, 830, 70, 32, "% 60"),
    box(2200, 920, 230, 22, "HAK EDİŞ TUTARINIZ"),
    box(2200, 960, 200, 32, "49.912,35 TL"),

    # --- Banner (gürültü) ---
    box(120, 360, 1400, 50, "Fon Koçu hizmetimizin size özel sunduğu fonlarla"),
    box(120, 440, 1200, 50, "birikiminize birlikte yön verelim!"),
    box(2120, 420, 220, 50, "Detaylı Bilgi"),
]


def main() -> int:
    out = extract_from_ocr_boxes(raw_boxes)
    d = out.to_dict()
    expected = {
        "birikiminiz":          614954.37,
        "odenen_toplam_tutar":  115942.22,
        "yatirim_getiriniz":    499012.15,
        "devlet_katkisi":        83187.26,
        "hak_edise_esas_sure":      14,
        "hak_edis_oraniniz":        60,
        "hak_edis_tutariniz":    49912.35,
    }

    print("alan                        beklenen            bulunan         durum")
    print("-" * 74)
    ok = 0
    total = len(expected)
    for k, exp in expected.items():
        got = d.get(k)
        status = "✓" if got == exp else (
            "~" if got is not None and abs(got - exp) <= 0.01 else "✗"
        )
        if status in ("✓", "~"):
            ok += 1
        print(f"{k:<26}  {exp!s:>14}   {got!s:>14}   {status}")
    print("-" * 74)
    print(f"sonuç: {ok}/{total}")

    print("\ndebug_matches:")
    for fid, src, val in out.debug_matches:
        print(f"  {fid:<22}  ← «{src[:60]}» → {val}")

    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

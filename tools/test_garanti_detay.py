"""Garanti mobil — Sözleşme Detayı sayfası bbox simülasyonu."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bes_parse import extract_from_ocr_boxes


def box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95):
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# Garanti mobil — Sözleşme Detayı (1 ekran)
raw = [
    # Üst başlık + geri oku
    box(70, 30, 80, 80, "←"),
    box(400, 30, 480, 80, "Sözleşme Detayı"),

    # Ödenen Toplam Tutar kartı (label üstte ortalanmış, değer altta)
    box(480, 210, 580, 80, "Ödenen Toplam Tutar"),
    box(540, 300, 400, 90, "985.612 TL"),

    # Yatırım Getiriniz kartı
    box(540, 480, 480, 80, "Yatırım Getiriniz"),
    box(580, 580, 360, 90, "242.615 TL"),

    # Section header (noise)
    box(80, 740, 800, 60, "KURUM KATKISI HAK EDİŞ DURUMUNUZ"),

    # Gauge labels (noise)
    box(360, 1390, 140, 40, "GİRİŞ"),
    box(900, 1390, 180, 40, "HAK EDİŞ"),

    # Hak Edişe Esas Süre — sol-hizalı, değer altta
    box(80, 1500, 480, 50, "HAK EDİŞE ESAS SÜRE"),
    box(80, 1590, 140, 80, "1 YIL"),

    # Hak Ediş Oranınız
    box(80, 1750, 420, 50, "HAK EDİŞ ORANINIZ"),
    box(80, 1840, 180, 80, "% 100"),

    # Hak Ediş Tutarınız
    box(80, 2010, 460, 50, "HAK EDİŞ TUTARINIZ"),
    box(80, 2100, 400, 80, "1.228.227 TL"),
]


def main() -> int:
    out = extract_from_ocr_boxes(raw)
    d = out.to_dict()
    expected = {
        "birikiminiz":              None,   # bu ekranda yok
        "odenen_toplam_tutar":   985612.00,
        "yatirim_getiriniz":     242615.00,
        "devlet_katkisi":           None,   # devlet katkısız
        "hak_edise_esas_sure":         1,
        "hak_edis_oraniniz":         100,
        "hak_edis_tutariniz":   1228227.00,
    }
    print("alan                        beklenen         bulunan       durum")
    print("-" * 70)
    ok = 0
    for k, exp in expected.items():
        got = d.get(k)
        if exp is None:
            status = "✓ (boş)" if got is None else f"✗ (gelmemeli, geldi: {got})"
            if got is None: ok += 1
        else:
            status = "✓" if got == exp else (
                "~" if got is not None and abs(got - exp) <= 0.01 else "✗"
            )
            if status in ("✓", "~"): ok += 1
        print(f"{k:<26}  {exp!s:>12}  {got!s:>12}   {status}")
    print("-" * 70)
    print(f"sonuç: {ok}/{len(expected)}")
    print("\ndebug_matches:")
    for fid, src, val in out.debug_matches:
        print(f"  {fid:<22}  ← «{src[:60]}» → {val}")
    return 0 if ok == len(expected) else 1


if __name__ == "__main__":
    raise SystemExit(main())

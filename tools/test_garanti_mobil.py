"""Garanti mobil ekran (birikim sayfası) bbox simülasyonu."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bes_parse import extract_from_ocr_boxes


def box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95):
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# Garanti mobil — Toplam Birikim sayfası (top portion)
# Mobil ekran genişliği ~1280 px (yüksek DPI), yüksekliği ~1380 px görünen kısım
raw = [
    # Üst başlık + sağda "Sözleşme Seçin →"
    box(70, 50, 510, 70, "Toplam Birikiminiz"),
    box(870, 50, 480, 70, "Sözleşme Seçin →"),

    # Donut chart (gerçekte grafik, OCR olmaz). Sağında sözleşme no + tutar:
    box(420, 280, 590, 50, "Sözleşme No: 15485747"),
    box(380, 350, 670, 90, "1.228.227,00 TL"),

    # Değişim satırları
    box(80, 580, 540, 55, "Son 1 Aylık Değişim:"),
    box(950, 580, 200, 55, "%8,41 ▲"),
    box(80, 660, 540, 55, "Son 1 Yıllık Değişim:"),
    box(950, 660, 280, 55, "%379,18 ▲"),

    # Birikim Dağılımı başlığı
    box(80, 870, 380, 50, "Birikim Dağılımı"),
    box(750, 870, 600, 50, "Sözleşme Detayına Git"),

    # Ödenen Tutar satırı: %80,2 yuvarlak + label sol + tutar sağ
    box(105, 1010, 130, 100, "%80,2"),
    box(265, 1010, 460, 100, "Ödenen Tutar"),
    box(870, 1010, 480, 100, "985.612,00 TL"),

    # Fon Getirisi satırı: %19,8 yuvarlak + label sol + tutar sağ
    box(105, 1230, 130, 100, "%19,8"),
    box(265, 1230, 480, 100, "Fon Getirisi"),
    box(870, 1230, 480, 100, "242.615,00 TL"),
]


def main() -> int:
    out = extract_from_ocr_boxes(raw)
    d = out.to_dict()
    expected = {
        "birikiminiz":          1228227.00,
        "odenen_toplam_tutar":   985612.00,
        "yatirim_getiriniz":     242615.00,
        # Bu ekranda yok:
        "devlet_katkisi":           None,
        "hak_edise_esas_sure":      None,
        "hak_edis_oraniniz":        None,
        "hak_edis_tutariniz":       None,
    }

    print("alan                        beklenen         bulunan       durum")
    print("-" * 70)
    ok = 0
    for k, exp in expected.items():
        got = d.get(k)
        if exp is None:
            status = "✓ (boş)" if got is None else f"✗ (gelmemeli, geldi: {got})"
            if got is None:
                ok += 1
        else:
            status = "✓" if got == exp else (
                "~" if got is not None and abs(got - exp) <= 0.01 else "✗"
            )
            if status in ("✓", "~"):
                ok += 1
        print(f"{k:<26}  {exp!s:>12}  {got!s:>12}   {status}")
    print("-" * 70)
    print(f"sonuç: {ok}/{len(expected)}")

    print("\ndebug_matches:")
    for fid, src, val in out.debug_matches:
        print(f"  {fid:<22}  ← «{src[:60]}» → {val}")

    return 0 if ok == len(expected) else 1


if __name__ == "__main__":
    raise SystemExit(main())

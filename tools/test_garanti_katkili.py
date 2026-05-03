"""Garanti devlet katkılı sözleşme detay ekranı bbox simülasyonu."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bes_parse import extract_from_ocr_boxes


def box(x: float, y: float, w: float, h: float, text: str, conf: float = 0.95):
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return (bbox, text, conf)


# Garanti devlet katkılı detay — üst kısım
raw = [
    # Üst mavi kart: Ödenen + Yatırım (yan yana)
    box(80, 50, 500, 60, "Ödenen Toplam Tutar"),
    box(130, 130, 410, 70, "119.192,22 TL"),
    box(720, 50, 520, 60, "Yatırım Getiriniz"),
    box(730, 130, 510, 70, "490.627,79 TL"),

    # Mor kart: Devlet Katkısı (ana)
    box(470, 290, 350, 70, "Devlet Katkısı"),
    box(375, 380, 565, 120, "82.799,73 TL"),

    # Mor kart altı: Yatırılan + Getirisi (devlet_katkisi'ye atanmamalı!)
    box(130, 560, 520, 70, "Yatırılan Devlet Katkısı"),
    box(180, 640, 330, 80, "31.725,25 TL"),
    box(730, 560, 500, 70, "Devlet Katkısı Getirisi"),
    box(780, 640, 320, 80, "51.074,48 TL"),

    # Alt — Birikim kazancınız bölümü (gürültü, yüzdelik)
    box(80, 830, 480, 50, "BİRİKİM KAZANCINIZ"),
    box(280, 940, 180, 40, "KÜMÜL"),
    box(680, 940, 240, 40, "SON 1 YIL"),
    box(280, 1080, 320, 40, "TOPLAM KAZANÇ"),
    box(680, 1080, 200, 40, "FON KAZANCI"),
    box(280, 1240, 200, 80, "%81"),
    box(680, 1140, 100, 40, "%50,6"),
    box(680, 1280, 360, 40, "DEVLET KATKISI KAZANCI"),
    box(680, 1340, 100, 40, "%30,4"),
    box(80, 1500, 700, 50, "DEVLET KATKISI HAK EDİŞ DURUMUNUZ"),
    box(220, 1700, 100, 40, "10. YIL"),
    box(180, 1800, 100, 40, "6. YIL"),
    box(140, 1900, 100, 40, "3. YIL"),
    box(140, 2080, 100, 40, "2012"),
    box(640, 2080, 100, 40, "2041"),
]


def main() -> int:
    out = extract_from_ocr_boxes(raw)
    d = out.to_dict()
    expected = {
        "birikiminiz":              None,    # bu ekranda yok (app auto-derive)
        "odenen_toplam_tutar":   119192.22,
        "yatirim_getiriniz":     490627.79,
        "devlet_katkisi":         82799.73,  # ← yatirilan/getirisi atanmamalı
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

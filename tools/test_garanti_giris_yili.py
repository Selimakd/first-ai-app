"""Garanti devlet katkılı (kısa süre) — gauge'tan giriş yılı tespiti."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bes_parse import extract_from_ocr_boxes


def box(x, y, w, h, text, conf=0.95):
    return ([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], text, conf)


# Garanti — küçük tutarlı devlet katkılı kısa-süre sözleşmesi
raw = [
    # Üst kart
    box(80, 50, 500, 60, "Ödenen Toplam Tutar"),
    box(180, 110, 300, 70, "1.690 TL"),
    box(720, 50, 500, 60, "Yatırım Getiriniz"),
    box(800, 110, 350, 70, "847,67 TL"),

    # Devlet Katkısı kartı
    box(470, 290, 350, 70, "Devlet Katkısı"),
    box(440, 380, 460, 100, "689,85 TL"),

    # Alt: yatırılan + getirisi (excluded)
    box(130, 560, 520, 70, "Yatırılan Devlet Katkısı"),
    box(280, 640, 200, 80, "502 TL"),
    box(730, 560, 500, 70, "Devlet Katkısı Getirisi"),
    box(820, 640, 280, 80, "187,85 TL"),

    # Birikim kazancınız bölümü (yüzdelikler — gürültü)
    box(80, 830, 480, 50, "BİRİKİM KAZANCINIZ"),
    box(280, 1240, 200, 80, "%93,9"),
    box(680, 1140, 100, 40, "%69,8"),
    box(680, 1340, 100, 40, "%24,1"),

    # GAUGE etiketleri (en kritik kısım — buradan giriş yılı)
    box(80, 1500, 700, 50, "DEVLET KATKISI HAK EDİŞ DURUMUNUZ"),
    box(220, 1700, 100, 40, "10. YIL"),
    box(180, 1800, 100, 40, "6. YIL"),
    box(140, 1900, 100, 40, "3. YIL"),
    # Sol alt: 2023 üstte, GİRİŞ altta (ayrı kutular)
    box(140, 2080, 100, 40, "2023"),
    box(140, 2130, 100, 40, "GİRİŞ"),
    # Sağ alt: 2041 üstte, EMEKLİLİK altta
    box(640, 2080, 100, 40, "2041"),
    box(620, 2130, 200, 40, "EMEKLİLİK"),
]


def main() -> int:
    out = extract_from_ocr_boxes(raw)
    expected = {
        "odenen_toplam_tutar":  1690.00,
        "yatirim_getiriniz":     847.67,
        "devlet_katkisi":        689.85,
        "birikiminiz":              None,
        "hak_edise_esas_sure":      None,
        "hak_edis_oraniniz":        None,
        "hak_edis_tutariniz":       None,
    }
    d = out.to_dict()
    print("alan                        beklenen        bulunan       durum")
    print("-" * 70)
    ok = 0
    for k, exp in expected.items():
        got = d.get(k)
        if exp is None:
            status = "✓ (boş)" if got is None else f"✗ ({got})"
            if got is None: ok += 1
        else:
            status = "✓" if got == exp else (
                "~" if got is not None and abs(got - exp) <= 0.01 else "✗"
            )
            if status in ("✓", "~"): ok += 1
        print(f"{k:<26}  {exp!s:>10}  {got!s:>12}   {status}")
    print(f"\ngiris_yili: {out.giris_yili!s:>10}   beklenen: 2023   "
          f"{'✓' if out.giris_yili == 2023 else '✗'}")
    print("-" * 70)
    print(f"sonuç: {ok}/{len(expected)} (alan) + giriş yılı")
    print("\ndebug_matches:")
    for fid, src, val in out.debug_matches:
        print(f"  {fid:<22}  ← «{src[:60]}» → {val}")
    if out.giris_yili:
        from datetime import datetime
        cur = datetime.now().year
        sure_tahmin = cur - out.giris_yili
        print(f"\nSüre tahmini: {cur} - {out.giris_yili} = {sure_tahmin} yıl")
    return 0 if ok == len(expected) and out.giris_yili == 2023 else 1


if __name__ == "__main__":
    raise SystemExit(main())

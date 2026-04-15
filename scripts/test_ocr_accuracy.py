#!/usr/bin/env python3
"""test_screenshots/ içindeki PNG’lerde OCR + parse çalıştırır; isteğe bağlı beklenen değerlerle karşılaştırır.

Kullanım (proje kökünden):
  ./venv/bin/python scripts/test_ocr_accuracy.py

Beklenen değerleri güncellemek için BEKLENEN sözlüğünü düzenleyin (None = kontrol etme).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image

from src.bes_parse import extract_from_ocr_lines
from src.ocr_engine import read_text, sorted_lines

# Elle doğrulama için referans (sizin ekranınızdaki gerçek değerler — güncelleyin)
BEKLENEN: dict[str, float | None] = {
    "birikiminiz": 607_774.49,
    "odenen_toplam_tutar": 115_942.22,
    "yatirim_getiriniz": 491_832.27,
    "devlet_katkisi": 82_586.30,
    "hak_edise_esas_sure": 14.0,
    "hak_edis_oraniniz": 54.2,  # veya 60.0 — ekrana göre düzeltin
    "hak_edis_tutariniz": 48973.3,
}


def main() -> None:
    folder = ROOT / "test_screenshots"
    paths = sorted(folder.glob("*.png"))
    if not paths:
        print(f"Dosya yok: {folder} — PNG’leri buraya koyun.")
        sys.exit(1)

    agg_lines: list[str] = []
    for p in paths:
        img = Image.open(p)
        r = read_text(img, upscale=1.5)
        lines = [t for _, t, _ in sorted_lines(r)]
        agg_lines.extend(lines)

    ex = extract_from_ocr_lines(agg_lines)
    got = ex.to_dict()
    print("=== Parse sonucu ===")
    for k, v in got.items():
        print(f"  {k}: {v}")

    print("\n=== Beklenen ile karşılaştırma (None olan alanlar atlanır) ===")
    tol = 0.02
    ok = 0
    total = 0
    for key, expected in BEKLENEN.items():
        if expected is None:
            continue
        total += 1
        g = got.get(key)
        if g is None:
            print(f"  {key}: EKSİK (beklenen {expected})")
            continue
        if abs(float(g) - float(expected)) <= tol:
            print(f"  {key}: OK (≈ {expected})")
            ok += 1
        else:
            print(f"  {key}: FARK  beklenen={expected}  bulunan={g}")

    if total:
        print(f"\nDoğruluk: {ok}/{total} alan ({100 * ok / total:.0f}%)")
    else:
        print("\nBEKLENEN içinde tanımlı sayı yok; sadece çıktıyı kontrol edin.")


if __name__ == "__main__":
    main()

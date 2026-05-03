"""
Uçtan uca ekran görüntüsü testleri.

Her fixture klasörü (`tests/fixtures/screenshots/<senaryo_adi>/`) iki dosya içerir:
  - `ekran.png` / `.jpg` / `.jpeg` / `.webp` — BES ekran görüntüsü
  - `beklenen.json` — beklenen alanlar ve isteğe bağlı hesap sonucu

Her senaryo bağımsız pytest parametresidir. Biri kırılsa diğerleri koşmaya devam eder.
Varsayılan `pytest` koşusunda bu testler **atlanır** (slow marker); koşmak için:
    pytest -m slow

Fixture ekleme kılavuzu: `tests/fixtures/screenshots/README.md`
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from src.bes_calc import cikista_ele_gecen_tl
from src.bes_parse import extract_from_ocr_boxes, extract_from_ocr_lines  # noqa: F401

# OCR engine import'u opsiyonel: EasyOCR kurulu değilse fixture testleri skip.
try:
    from src.ocr_engine import read_text, sorted_lines

    _OCR_AVAILABLE = True
    _OCR_IMPORT_ERR = ""
except Exception as e:  # pragma: no cover
    _OCR_AVAILABLE = False
    _OCR_IMPORT_ERR = str(e)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "screenshots"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_ALAN_ADLARI = (
    "birikiminiz",
    "odenen_toplam_tutar",
    "yatirim_getiriniz",
    "devlet_katkisi",
    "hak_edise_esas_sure",
    "hak_edis_oraniniz",
    "hak_edis_tutariniz",
)


def _discover_fixtures() -> list[str]:
    """fixtures/screenshots altındaki her alt klasör bir senaryo; beklenen.json olanları bul."""
    if not FIXTURES_DIR.exists():
        return []
    out: list[str] = []
    for sub in sorted(FIXTURES_DIR.iterdir()):
        if not sub.is_dir():
            continue
        if (sub / "beklenen.json").exists():
            out.append(sub.name)
    return out


def _find_image(senaryo_dir: Path) -> Path | None:
    for ext in _IMAGE_EXTS:
        for p in senaryo_dir.glob(f"ekran{ext}"):
            return p
        # Bazen kullanıcı "ekran1.png" vb. kullanabilir; ilk bulunanı al
        for p in sorted(senaryo_dir.glob(f"*{ext}")):
            return p
    return None


_FIXTURES = _discover_fixtures()


@pytest.mark.slow
@pytest.mark.skipif(not _OCR_AVAILABLE, reason=f"OCR engine kurulu değil: {_OCR_IMPORT_ERR}")
@pytest.mark.skipif(not _FIXTURES, reason="tests/fixtures/screenshots altında senaryo yok")
@pytest.mark.parametrize("senaryo", _FIXTURES)
def test_screenshot_e2e(senaryo: str) -> None:
    senaryo_dir = FIXTURES_DIR / senaryo
    expected_path = senaryo_dir / "beklenen.json"
    expected: dict[str, Any] = json.loads(expected_path.read_text(encoding="utf-8"))

    image_path = _find_image(senaryo_dir)
    if image_path is None:
        pytest.skip(
            f"Senaryo '{senaryo}': görüntü dosyası yok "
            f"(ekran.png/jpg/jpeg/webp ekleyin)."
        )

    upscale = float(expected.get("upscale", 1.5))

    # 1) OCR
    image = Image.open(image_path)
    raw = read_text(image, upscale=upscale)
    ordered = sorted_lines(raw)
    lines = [t for _, t, _ in ordered]

    # 2) Parse — bbox-aware yol (kolonlu düzen için). `ordered` hâlâ (bbox, text, conf) tuple'ları.
    extracted = extract_from_ocr_boxes(ordered)
    actual = extracted.to_dict()

    # 3) Beklenen alanları karşılaştır (null ise atla)
    alan_hatalari: list[str] = []
    for alan, bekleniyor in expected.get("beklenen_alanlar", {}).items():
        if alan not in _ALAN_ADLARI:
            pytest.fail(f"beklenen.json içinde geçersiz alan adı: {alan!r}")
        if bekleniyor is None:
            continue
        gercek = actual.get(alan)
        if gercek is None:
            alan_hatalari.append(f"- {alan}: OCR bulamadı (beklenen {bekleniyor})")
            continue
        if not _approx_eq(float(bekleniyor), float(gercek)):
            alan_hatalari.append(f"- {alan}: beklenen={bekleniyor}, bulunan={gercek}")

    # 4) Beklenen hesap varsa çalıştır
    hesap_hatalari: list[str] = []
    beklenen_hesap = expected.get("beklenen_hesap")
    if beklenen_hesap:
        sozlesme_tipi = expected.get("sozlesme_tipi", "devlet_katkisiz")
        devlet_katkili = sozlesme_tipi == "devlet_katkili"
        try:
            h = cikista_ele_gecen_tl(
                birikiminiz=float(actual["birikiminiz"]),
                hak_edis_tutariniz=float(actual.get("hak_edis_tutariniz") or 0.0),
                yatirim_getiriniz=float(actual["yatirim_getiriniz"]),
                hak_edise_esas_sure_yil=float(actual["hak_edise_esas_sure"]),
                devlet_katkili_sozlesme=devlet_katkili,
            )
        except (TypeError, ValueError, KeyError) as e:
            hesap_hatalari.append(f"Hesap çalıştırılamadı (eksik alan?): {e}")
        else:
            hesap_mapping = {
                "uygulanan_stopaj_orani": h.uygulanan_stopaj_orani,
                "stopaj_kesintisi_tl": h.stopaj_kesintisi_tl,
                "cikista_net_tl": h.cikista_net_tl,
            }
            for anahtar, bekleniyor in beklenen_hesap.items():
                if bekleniyor is None:
                    continue
                if anahtar not in hesap_mapping:
                    pytest.fail(f"beklenen_hesap içinde geçersiz anahtar: {anahtar!r}")
                gercek = hesap_mapping[anahtar]
                if not _approx_eq(float(bekleniyor), float(gercek)):
                    hesap_hatalari.append(
                        f"- {anahtar}: beklenen={bekleniyor}, bulunan={gercek}"
                    )

    # 5) Raporla
    hatalar = alan_hatalari + hesap_hatalari
    if hatalar:
        ocr_metni = "\n".join(f"    {ln}" for ln in lines)
        aciklama = expected.get("aciklama", "")
        pytest.fail(
            f"Senaryo '{senaryo}' başarısız ({aciklama}):\n"
            + "\n".join(hatalar)
            + f"\n\n  Ham OCR satırları ({len(lines)} adet):\n{ocr_metni}",
            pytrace=False,
        )


def _approx_eq(a: float, b: float, *, rtol: float = 1e-6, atol: float = 0.01) -> bool:
    """TL tutarları için kuruş (0.01) toleransı; oranlar için göreli tolerans."""
    return abs(a - b) <= max(atol, rtol * max(abs(a), abs(b)))

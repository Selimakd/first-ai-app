"""
api.py testleri — OCR'sız (hızlı) kısımlar: metin biçimleme, routing, auth,
hatalı girdi. Gerçek OCR çalıştıran uçtan uca test `slow` işaretli.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import api
from src.bes_calc import CikisHesabi
from src.bes_pipeline import PipelineResult

client = TestClient(api.app)


# ---------------------------------------------------------------------------
# _format_result — saf metin biçimleme
# ---------------------------------------------------------------------------


def test_format_result_tam_hesap() -> None:
    r = PipelineResult(
        birikiminiz=2635.47,
        odenen_toplam_tutar=1690.00,
        yatirim_getiriniz=945.47,
        devlet_katkisi=699.18,
        hak_edise_esas_sure=2.0,
        hak_edis_oraniniz=0.0,
        hak_edis_tutariniz=0.0,
        devlet_katkili=True,
        hesap=CikisHesabi(
            uygulanan_stopaj_orani=0.15,
            stopaj_kesintisi_tl=141.82,
            cikista_net_tl=2493.65,
        ),
        notlar=["Yatırım getirisi türetildi: ..."],
    )
    out = api._format_result(r)
    assert "Net çıkış: 2.493,65 TL" in out
    assert "Stopaj (%15): 141,82 TL" in out
    assert "Birikim: 2.635,47 TL" in out
    assert "ℹ️ Notlar:" in out


def test_format_result_eksik_alan() -> None:
    r = PipelineResult(
        birikiminiz=100000.0,
        eksik_alanlar=["Yatırım getiriniz", "Hak edişe esas süre (yıl)"],
    )
    out = api._format_result(r)
    assert "Hesap yapılamadı" in out
    assert "Yatırım getiriniz" in out
    assert "Net çıkış" not in out


# ---------------------------------------------------------------------------
# Routing — root / health
# ---------------------------------------------------------------------------


def test_root_ve_health() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "BES Çıkış Hesabı API" in r.text

    h = client.get("/health")
    assert h.status_code == 200
    assert h.text == "ok"


# ---------------------------------------------------------------------------
# /hesapla — OCR'a ulaşmadan dönen yollar (auth, boş dosya)
# ---------------------------------------------------------------------------


def test_hesapla_yanlis_parola_reddedilir(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_PASSWORD set iken yanlış parola → OCR'a hiç gitmeden okunur metin döner."""
    monkeypatch.setattr(api, "_APP_PASSWORD", "dogru-parola")
    resp = client.post(
        "/hesapla",
        files={"file": ("x.png", b"fake", "image/png")},
        data={"password": "yanlis"},
    )
    assert resp.status_code == 200
    assert "Geçersiz parola" in resp.text


def test_hesapla_bos_dosya(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parola kapalı (lokal mod) + boş dosya → okunur hata metni, çökmez."""
    monkeypatch.setattr(api, "_APP_PASSWORD", "")
    resp = client.post(
        "/hesapla",
        files={"file": ("bos.png", b"", "image/png")},
    )
    assert resp.status_code == 200
    assert "Boş dosya" in resp.text


def test_hesapla_bozuk_goruntu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Görüntü olmayan içerik → okunur hata metni, 500 değil."""
    monkeypatch.setattr(api, "_APP_PASSWORD", "")
    resp = client.post(
        "/hesapla",
        files={"file": ("bozuk.png", b"bu bir gorsel degil", "image/png")},
    )
    assert resp.status_code == 200
    assert "Görüntü açılamadı" in resp.text


# ---------------------------------------------------------------------------
# Uçtan uca — gerçek OCR (slow; EasyOCR + fixture PNG gerekir)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_hesapla_e2e_gercek_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture PNG → gerçek OCR → pipeline → metin sonuç. PNG yoksa skip."""
    from pathlib import Path

    monkeypatch.setattr(api, "_APP_PASSWORD", "")
    fixtures = Path(__file__).parent / "fixtures" / "screenshots"
    img_path = None
    for sub in sorted(fixtures.glob("senaryo_*")):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            cands = list(sub.glob(f"*{ext}"))
            if cands:
                img_path = cands[0]
                break
        if img_path:
            break
    if img_path is None:
        pytest.skip("fixtures/screenshots altında PNG yok (gitignored, lokalde ekleyin)")

    with open(img_path, "rb") as f:
        resp = client.post("/hesapla", files={"file": (img_path.name, f.read(), "image/png")})
    assert resp.status_code == 200
    # En azından "BES Çıkış Hesabı" başlığı dönmeli (hesap veya eksik-alan mesajı)
    assert "BES Çıkış Hesabı" in resp.text

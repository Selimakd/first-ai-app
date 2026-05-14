"""BES hesap API — kanal-bağımsız HTTP ucu (iOS Kısayol; ileride Telegram bot).

`POST /hesapla`: BES ekran görüntüsü (form-data alanı `file`) → OCR → `run_pipeline`
→ insan-okunur metin sonuç. Web arayüzü (`app.py` / Streamlit) bundan TAMAMEN
bağımsız çalışır; ikisi de `src/` çekirdeğini (parse + pipeline + calc) paylaşır.

Çalıştırma:
    uvicorn api:app --host 0.0.0.0 --port 8501
HF Spaces'te `start.sh`, `APP_MODE=api` ortam değişkeni set ise bunu başlatır
(web Space'i APP_MODE'suz kalır → Streamlit). İkisi ayrı HF Space, tek repo.

Yanıt politikası: iOS Kısayol "Get Contents of URL" → "Show Notification" akışı
için tüm yanıtlar **200 + düz metin** — hata durumları bile okunabilir metin döner
(JSON hata gövdesi Kısayol'da çirkin görünür).
"""

from __future__ import annotations

import io
import os

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import PlainTextResponse
from PIL import Image

from src.bes_calc import format_tl
from src.bes_pipeline import PipelineResult, run_pipeline
from src.ocr_engine import read_text, sorted_lines

app = FastAPI(title="BES Çıkış Hesabı API", version="1.0")

# Web arayüzüyle aynı parola. Set ise /hesapla form alanı `password` zorunlu.
# Set değilse (lokal geliştirme) parola sorulmaz.
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    pw = ", password=<parola>" if _APP_PASSWORD else ""
    return (
        "BES Çıkış Hesabı API\n"
        f"POST /hesapla  (form-data: file=<ekran görüntüsü>{pw})\n"
        "Web arayüzü ayrı bir adreste çalışır."
    )


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


def _format_result(r: PipelineResult) -> str:
    """PipelineResult → iOS bildiriminde gösterilecek düz metin."""
    satir: list[str] = ["BES Çıkış Hesabı", ""]

    if r.birikiminiz is not None:
        satir.append(f"Birikim: {format_tl(r.birikiminiz)} TL")
    if r.yatirim_getiriniz is not None:
        satir.append(f"Yatırım getirisi: {format_tl(r.yatirim_getiriniz)} TL")
    if r.devlet_katkili and r.devlet_katkisi is not None:
        satir.append(f"Devlet katkısı: {format_tl(r.devlet_katkisi)} TL")
    if r.hak_edise_esas_sure is not None:
        satir.append(f"Süre: {r.hak_edise_esas_sure:g} yıl")
    if r.devlet_katkili and r.hak_edis_oraniniz is not None:
        he = (
            format_tl(r.hak_edis_tutariniz) + " TL"
            if r.hak_edis_tutariniz is not None
            else "—"
        )
        satir.append(f"Hak ediş: %{r.hak_edis_oraniniz:g} → {he}")

    if r.hesap is not None:
        pct = r.hesap.uygulanan_stopaj_orani * 100
        satir.append("")
        satir.append(f"Stopaj (%{pct:g}): {format_tl(r.hesap.stopaj_kesintisi_tl)} TL")
        satir.append("─────────────────")
        satir.append(f"Net çıkış: {format_tl(r.hesap.cikista_net_tl)} TL")
    else:
        satir.append("")
        satir.append("⚠️ Hesap yapılamadı — eksik alanlar:")
        for ad in r.eksik_alanlar:
            satir.append(f"• {ad}")
        satir.append(
            "Daha net bir ekran görüntüsü ya da sözleşme detay ekranını gönderin."
        )

    if r.notlar:
        satir.append("")
        satir.append("ℹ️ Notlar:")
        for n in r.notlar:
            satir.append(f"• {n}")

    return "\n".join(satir)


@app.post("/hesapla", response_class=PlainTextResponse)
async def hesapla(
    file: UploadFile = File(...),
    password: str = Form(default=""),
) -> str:
    # Parola (APP_PASSWORD set ise zorunlu). 4xx yerine 200+metin — Kısayol dostu.
    if _APP_PASSWORD and password != _APP_PASSWORD:
        return "⚠️ Geçersiz parola — iOS Kısayol ayarlarındaki parolayı kontrol edin."

    raw = await file.read()
    if not raw:
        return "⚠️ Boş dosya geldi — ekran görüntüsünü tekrar gönderin."

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as e:  # noqa: BLE001 — kullanıcıya okunur mesaj döndürmek istiyoruz
        return f"⚠️ Görüntü açılamadı ({e}). PNG/JPG bir ekran görüntüsü gönderin."

    try:
        results = read_text(image)
        ordered = sorted_lines(results)
        r = run_pipeline(ordered)
    except Exception as e:  # noqa: BLE001
        return f"⚠️ İşleme hatası: {e}. Lütfen tekrar deneyin."

    return _format_result(r)

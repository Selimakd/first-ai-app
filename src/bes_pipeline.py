"""BES OCR → hesap pipeline'ı — kanal-bağımsız çekirdek.

`extract_from_ocr_boxes` (parse) + `app.py`'deki OCR-sonrası auto-derive zincirinin
saf hâli + `cikista_ele_gecen_tl` (hesap). Streamlit / `st.session_state`'e bağımlı
DEĞİL — bu yüzden hem web arayüzü dışındaki kanallar (API → iOS Kısayol, ileride
Telegram bot) hem de testler aynı mantığı tek yerden kullanabilir.

NOT: `app.py` kendi inline auto-derive kopyasını KORUR (web arayüzüne dokunulmadı).
İleride app.py de bu pipeline'a refactor edilebilir; şimdilik mantık iki yerde —
ikisi de aynı semantiği uygular, regression testleri (test_bes_pipeline.py +
test_bes_parse_boxes.py) kilitler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .bes_calc import (
    CikisHesabi,
    cikista_ele_gecen_tl,
    hak_edis_orani_from_sure,
    hak_edis_tutari_from_oran,
)
from .bes_parse import (
    BesExtracted,
    extract_from_ocr_boxes,
    infer_devlet_katkili_sozlesme,
)


@dataclass
class PipelineResult:
    """run_pipeline çıktısı — çözümlenmiş alanlar + hesap + insan-okunur notlar."""

    # Çözümlenmiş alanlar (türetmeler dahil)
    birikiminiz: float | None = None
    odenen_toplam_tutar: float | None = None
    yatirim_getiriniz: float | None = None
    devlet_katkisi: float | None = None
    hak_edise_esas_sure: float | None = None
    hak_edis_oraniniz: float | None = None
    hak_edis_tutariniz: float | None = None
    devlet_katkili: bool = False
    # Hesap (yapılabildiyse; eksik alan varsa None)
    hesap: CikisHesabi | None = None
    eksik_alanlar: list[str] = field(default_factory=list)
    # İnsan-okunur notlar: türetme açıklamaları + uyarılar
    notlar: list[str] = field(default_factory=list)
    # Tanı için ham OCR satırları
    raw_lines: list[str] = field(default_factory=list)


def _yil_floor_from_date(baslangic: date, bugun: date) -> int:
    """Tam yıl (ay/gün dahil) — floor((bugün - başlangıç) / 365.25)."""
    return max(0, int((bugun - baslangic).days // 365.25))


def run_pipeline(
    raw_ocr_boxes: list[tuple[Any, str, float]],
    *,
    bugun: date | None = None,
) -> PipelineResult:
    """OCR ham çıktısı (bbox, text, conf listesi) → tam hesap sonucu.

    `app.py`'deki OCR-sonrası auto-derive zincirinin kanal-bağımsız aynası:
      1. parse (extract_from_ocr_boxes)
      2. birikim forward-derive (Ödenen + Getiri)
      3. yatırım getirisi ters türetme (Birikim − Ödenen)
      4. süre türetme: sözleşme başlangıç tarihi > BES giriş tarihi > gauge giriş yılı
      5. sözleşme tipi auto-detect (devlet katkılı / katkısız)
      6. devlet katkılı ise hak ediş oran/tutar türetme (EGM kademe)
      7. cikista_ele_gecen_tl

    `bugun` test için enjekte edilebilir; verilmezse date.today().
    """
    if bugun is None:
        bugun = date.today()

    ext: BesExtracted = extract_from_ocr_boxes(raw_ocr_boxes)
    d = ext.to_dict()
    r = PipelineResult(raw_lines=list(ext.raw_lines))

    # 2. Birikim forward-derive: "Birikim = Ödenen + Getiri" kimliği.
    #    round(.., 2): para her zaman kuruş hassasiyetinde — float toplama drift'ini ele.
    if (
        d.get("birikiminiz") is None
        and d.get("odenen_toplam_tutar") is not None
        and d.get("yatirim_getiriniz") is not None
    ):
        d["birikiminiz"] = round(
            d["odenen_toplam_tutar"] + d["yatirim_getiriniz"], 2
        )
        r.notlar.append(
            f"Birikim türetildi: Ödenen + Getiri = {d['birikiminiz']:.2f}"
        )

    # 3. Yatırım getirisi TERS türetme: bazı ekranlarda "Yatırım Getiriniz" ayrı kalem
    #    değil (Garanti teklif/sözleşme detayı) → Getiri = Birikim − Ödenen.
    #    round(.., 2): 2635.47 - 1690.0 = 945.4699999999998 gibi float artığını ele.
    if (
        d.get("yatirim_getiriniz") is None
        and d.get("birikiminiz") is not None
        and d.get("odenen_toplam_tutar") is not None
    ):
        d["yatirim_getiriniz"] = round(
            d["birikiminiz"] - d["odenen_toplam_tutar"], 2
        )
        r.notlar.append(
            f"Yatırım getirisi türetildi: Birikim − Ödenen = {d['yatirim_getiriniz']:.2f}"
        )

    # 4. Süre türetme — öncelik: sözleşme başlangıç > BES giriş (uyarılı) > gauge
    if d.get("hak_edise_esas_sure") is None:
        if ext.sozlesme_baslangic_tarihi is not None:
            sy_t = _yil_floor_from_date(ext.sozlesme_baslangic_tarihi, bugun)
            d["hak_edise_esas_sure"] = float(sy_t)
            r.notlar.append(
                "Süre sözleşme başlangıç tarihinden hesaplandı: "
                f"{ext.sozlesme_baslangic_tarihi.strftime('%d/%m/%Y')} → {sy_t} yıl."
            )
        elif ext.bes_giris_tarihi is not None:
            sy_t = _yil_floor_from_date(ext.bes_giris_tarihi, bugun)
            d["hak_edise_esas_sure"] = float(sy_t)
            r.notlar.append(
                "⚠️ Süre BES Giriş Tarihi'nden hesaplandı: "
                f"{ext.bes_giris_tarihi.strftime('%d/%m/%Y')} → {sy_t} yıl. "
                "Bu BES sistemine ilk giriş tarihidir; sonradan yeni bir sözleşme "
                "açtıysanız gerçek süre daha kısadır — kontrol edin."
            )
        elif ext.giris_yili is not None:
            sy_t = max(0, bugun.year - ext.giris_yili - 1)
            d["hak_edise_esas_sure"] = float(sy_t)
            r.notlar.append(
                f"Süre gauge giriş yılından tahmin edildi: {ext.giris_yili} → "
                f"~{sy_t} yıl (conservative; gerçek {sy_t}–{sy_t + 1} yıl arası)."
            )

    # 5. Sözleşme tipi auto-detect: devlet_katkisi kalemi tutarıyla bulunduysa veya
    #    satır-bazlı başlık taraması katkılı diyorsa → devlet katkılı.
    devlet_katkili = (
        d.get("devlet_katkisi") is not None and (d.get("devlet_katkisi") or 0) > 0
    ) or infer_devlet_katkili_sozlesme(ext.raw_lines)
    r.devlet_katkili = devlet_katkili

    # 6. Hak ediş oran/tutar türetme — devlet katkılı + devlet katkısı + süre varsa.
    dk = d.get("devlet_katkisi")
    sy = d.get("hak_edise_esas_sure")
    if devlet_katkili and dk is not None and sy is not None:
        if d.get("hak_edis_oraniniz") is None:
            d["hak_edis_oraniniz"] = hak_edis_orani_from_sure(sy)
            r.notlar.append(
                f"Hak ediş oranı süreden türetildi: {sy:g} yıl → "
                f"%{d['hak_edis_oraniniz']:g} (EGM kademe)."
            )
        if d.get("hak_edis_tutariniz") is None:
            d["hak_edis_tutariniz"] = hak_edis_tutari_from_oran(
                dk, d["hak_edis_oraniniz"]
            )
            r.notlar.append(
                f"Hak ediş tutarı türetildi: {dk:.2f} × %{d['hak_edis_oraniniz']:g} "
                f"= {d['hak_edis_tutariniz']:.2f}"
            )

    # Çözümlenmiş alanları sonuca yaz
    r.birikiminiz = d.get("birikiminiz")
    r.odenen_toplam_tutar = d.get("odenen_toplam_tutar")
    r.yatirim_getiriniz = d.get("yatirim_getiriniz")
    r.devlet_katkisi = d.get("devlet_katkisi")
    r.hak_edise_esas_sure = d.get("hak_edise_esas_sure")
    r.hak_edis_oraniniz = d.get("hak_edis_oraniniz")
    r.hak_edis_tutariniz = d.get("hak_edis_tutariniz")

    # 7. Hesap — gerekli alanlar dolu mu?
    if devlet_katkili:
        gerekli = {
            "Birikiminiz": r.birikiminiz,
            "Hak ediş tutarınız": r.hak_edis_tutariniz,
            "Yatırım getiriniz": r.yatirim_getiriniz,
            "Hak edişe esas süre (yıl)": r.hak_edise_esas_sure,
        }
    else:
        gerekli = {
            "Birikiminiz": r.birikiminiz,
            "Yatırım getiriniz": r.yatirim_getiriniz,
            "Hak edişe esas süre (yıl)": r.hak_edise_esas_sure,
        }
    r.eksik_alanlar = [ad for ad, v in gerekli.items() if v is None]

    if not r.eksik_alanlar:
        r.hesap = cikista_ele_gecen_tl(
            r.birikiminiz,  # type: ignore[arg-type]
            r.hak_edis_tutariniz if r.hak_edis_tutariniz is not None else 0.0,
            r.yatirim_getiriniz,  # type: ignore[arg-type]
            r.hak_edise_esas_sure,  # type: ignore[arg-type]
            devlet_katkili_sozlesme=devlet_katkili,
        )

    return r

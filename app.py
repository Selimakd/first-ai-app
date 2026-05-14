"""
BES ekran görüntüsü — yerel OCR (ücretsiz).

Birden fazla ekran görüntüsü (sayfayı kaydırarak çekilen parçalar) yüklenebilir;
OCR sonuçları alanlara birleştirilir.

Çalıştırma:
  ./run.sh
  (veya: source venv/bin/activate && streamlit run app.py — Cursor’da "Connection lost"
  olursa ./run.sh kullanın; ~/.streamlit yazımı sandbox’ta engellenebiliyor.)
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime

import streamlit as st
from PIL import Image

from src.bes_calc import (
    cikista_ele_gecen_tl,
    format_tl,
    hak_edis_orani_from_sure,
    hak_edis_tutari_from_oran,
    stopaj_kesintisi_tl,
    stopaj_orani,
)
from src.bes_parse import (
    extract_from_ocr_boxes,
    extract_from_ocr_lines,
    infer_devlet_katkili_sozlesme,
    tr_amount_to_float,
)
from src.ocr_engine import get_reader, ocr_target_size, read_text, sorted_lines

# Tarayıcı sekmesi + sayfa başlığı; yeni sürümün yüklendiğini görmek için anlamlı her değişiklikte artırın (1.1 → 1.2 …).
APP_VERSION = "2.2"
APP_DISPLAY_NAME = f"BES Çıkış Hesabı V{APP_VERSION}"

FIELD_ROWS: list[tuple[str, str]] = [
    ("birikiminiz", "Birikiminiz (TL)"),
    ("odenen_toplam_tutar", "Ödenen Toplam Tutar (TL)"),
    ("yatirim_getiriniz", "Yatırım Getiriniz (TL)"),
    ("devlet_katkisi", "Devlet Katkısı (TL)"),
    ("hak_edise_esas_sure", "Hak Edişe Esas Süre (yıl)"),
    ("hak_edis_oraniniz", "Hak Ediş Oranınız (örn. 60 veya %60)"),
    ("hak_edis_tutariniz", "Hak Ediş Tutarınız (TL)"),
]


def _widget_key(field_id: str) -> str:
    return f"inp_{field_id}"


def _init_field_widgets() -> None:
    for key, _ in FIELD_ROWS:
        wk = _widget_key(key)
        if wk not in st.session_state:
            st.session_state[wk] = ""


def _normalize_uploaded_files(uploaded) -> list:
    if uploaded is None:
        return []
    return uploaded if isinstance(uploaded, list) else [uploaded]


def _apply_extraction_to_widgets(extracted: dict, mode: str) -> None:
    for key, val in extracted.items():
        if val is None:
            continue
        wk = _widget_key(key)
        if wk not in st.session_state:
            st.session_state[wk] = ""
        current = str(st.session_state[wk]).strip()
        new_s = str(val).replace(".", ",")
        if mode == "Üzerine yaz" or not current:
            st.session_state[wk] = new_s


st.set_page_config(page_title=APP_DISPLAY_NAME, layout="wide")

# Parola gate (HF Spaces deployment). APP_PASSWORD env var set değilse (lokal dev)
# kapı açık. HF Spaces "Settings → Repository secrets" altından girilir.
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
if _APP_PASSWORD and not st.session_state.get("_auth_ok"):
    st.title(APP_DISPLAY_NAME)
    st.subheader("Şifre")
    _pwd = st.text_input("Şifre", type="password", label_visibility="collapsed")
    if _pwd:
        if _pwd == _APP_PASSWORD:
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("Yanlış şifre")
    st.stop()

st.title(APP_DISPLAY_NAME)
st.caption(
    "Veriler yalnızca bu bilgisayarda işlenir. OCR: EasyOCR (Türkçe + İngilizce). "
    "Tek sayfaya sığmayan ekranlar için aynı oturumda birden fazla görüntü yükleyip OCR çalıştırabilirsiniz."
)

with st.expander("Tekrar dene — önerilen adımlar", expanded=False):
    st.markdown(
        """
1. **Sıfırla** — Aşağıdaki **Her şeyi sıfırla** ile alanları ve OCR geçmişini temizleyin.  
2. **Dosya seçiciyi yenileyin** — Streamlit seçili dosyayı bazen tutar: **F5 / sayfayı yenile** veya yükleyicide **×** ile kaldırıp görüntüleri yeniden seçin.  
3. **Üzerine yaz** — Varsayılan budur; farklı sözleşmede eski rakamların kalması için **Yalnızca boş** seçiliyse değişmez.  
4. **Büyütme** — Yazı küçükse **OCR için büyütmeyi** 2.0–2.5 yapın.  
5. **Çok parça** — Tüm kırpımları **aynı anda** seçip tek **OCR çalıştır** kullanın.  
6. **Ham metin** — Hâlâ yanlışsa *Ham OCR metni*nde etiket + rakamın yan yana görünüp görünmediğine bakın; gerekirse alanı elle düzeltin.
        """
    )

_init_field_widgets()

_CIKIS_SOZLESME_OPTIONS = ("devlet_katkisiz", "devlet_katkili")
if "cikis_sozlesme_tipi" not in st.session_state:
    st.session_state.cikis_sozlesme_tipi = "devlet_katkisiz"
elif st.session_state.get("cikis_sozlesme_tipi") not in _CIKIS_SOZLESME_OPTIONS:
    st.session_state.cikis_sozlesme_tipi = "devlet_katkisiz"

if "ocr_chunks" not in st.session_state:
    st.session_state.ocr_chunks = []

# Widget anahtarları (inp_*) yalnızca ilgili text_input çizilmeden önce güncellenebilir.
if st.session_state.pop("_do_clear_all", False):
    for key, _ in FIELD_ROWS:
        st.session_state[_widget_key(key)] = ""
    st.session_state.ocr_chunks = []
    st.session_state.pop("last_ocr_birlesik", None)
    st.session_state.pop("last_ocr_eslesme", None)
    st.session_state.pop("_birikim_ocr_turetildi", None)
    st.session_state.pop("_getiri_ocr_turetildi", None)
    st.session_state.pop("_oran_ocr_turetildi", None)
    st.session_state.pop("_he_ocr_turetildi", None)
    st.session_state.pop("_sure_giris_yili_turetildi", None)
    st.session_state.pop("_sure_baslangic_tarihinden_turetildi", None)
    st.session_state.pop("_sure_sozlesme_tarihinden_turetildi", None)
    st.session_state.pop("_last_ocr_file_sig", None)
    st.session_state["cikis_sozlesme_tipi"] = "devlet_katkisiz"
    st.rerun()

if st.session_state.pop("_do_clear_fields", False):
    for key, _ in FIELD_ROWS:
        st.session_state[_widget_key(key)] = ""
    st.rerun()

uploaded = st.file_uploader(
    "Ekran görüntüleri (PNG / JPG) — birden fazla seçebilirsiniz",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

files = _normalize_uploaded_files(uploaded)

# Tek dosyada otomatik OCR — yeni dosya yüklendiğinde butona basmadan çalışsın.
# Çoklu dosyada hâlâ butona basılır (kullanıcı tüm parçaları seçtikten sonra).
_current_file_sig: tuple | None = None
if files:
    f0 = files[0]
    _current_file_sig = (f0.name, getattr(f0, "size", None), len(files))
else:
    st.session_state.pop("_last_ocr_file_sig", None)
_auto_run = (
    files is not None
    and len(files) == 1
    and _current_file_sig is not None
    and _current_file_sig != st.session_state.get("_last_ocr_file_sig")
)

col_left, col_right = st.columns(2)
with col_left:
    upscale = st.slider("OCR için büyütme (küçük yazılarda artırın)", 1.0, 2.5, 1.5, 0.1)
    merge_mode = st.radio(
        "Yeni OCR sonucunu alanlara nasıl uygulayalım?",
        ("Yalnızca boş alanları doldur", "Üzerine yaz"),
        index=1,
        horizontal=True,
        help="Farklı sözleşme / yeni görüntü: **Üzerine yaz** (varsayılan). Aynı oturumda ikinci "
        "kırpımı eklerken mevcut değerleri korumak için **Yalnızca boş**.",
    )
    st.checkbox(
        "OCR sonrası sözleşme tipini otomatik seç (devlet katkılı / katkısız)",
        value=True,
        key="ocr_auto_cikis_tipi",
        help="Varsayılan açık: OCR'da «Devlet Katkısı» kalemi tutarıyla birlikte bulunursa "
        "**devlet katkılı**, yoksa **devlet katkısız** seçilir. Kapatırsan radyo sizde kalır.",
    )

with col_right:
    if files:
        n_show = min(len(files), 4)
        prev_cols = st.columns(n_show)
        for i in range(n_show):
            f = files[i]
            f.seek(0)
            with prev_cols[i]:
                st.image(Image.open(f), use_container_width=True)
                st.caption(f.name[:28] + ("…" if len(f.name) > 28 else ""))
        if len(files) > 4:
            st.caption(f"… ve {len(files) - 4} görüntü daha (hepsi OCR’da işlenir)")

run = st.button(
    "OCR çalıştır",
    type="primary",
    disabled=len(files) == 0,
    help="Tek dosya yüklediğinde OCR otomatik çalışır; çoklu dosya seçtiyseniz buradan tetikleyin.",
)
if (run or _auto_run) and files:
    apply_mode = "Üzerine yaz" if merge_mode == "Üzerine yaz" else "Yalnızca boş"
    agg_lines: list[str] = []
    agg_boxes: list = []  # (bbox, text, conf) — bbox-aware parse için
    chunk_logs: list[dict] = []
    # Çoklu görüntüde her dosyanın bbox Y koordinatlarını üst üste bindirmemek için
    # offset uygula — sanki tüm görüntüler tek uzun resme yapıştırılmış gibi davranır.
    # PAD: dosyalar arasında değer-etiket çağrışımını önlemek için bolca boşluk.
    Y_PAD_BETWEEN_FILES = 2000
    y_offset = 0
    # Performans enstrümantasyonu: model hazırlama (ilk yüklemede ağır) ile saf OCR
    # çıkarımını AYIR. get_reader() singleton — cache çalışıyorsa 2. çalıştırmada ~0 sn.
    _t_reader0 = time.perf_counter()
    with st.spinner("OCR motoru hazırlanıyor…"):
        get_reader()
    _reader_prep_s = time.perf_counter() - _t_reader0
    # (dosya, orijinal_w, orijinal_h, efektif_w, efektif_h, çıkarım_sn)
    _ocr_timings: list[tuple[str, int, int, int, int, float]] = []
    for f in files:
        f.seek(0)
        image = Image.open(f)
        _img_w, _img_h = image.size
        _eff_w, _eff_h = ocr_target_size(_img_w, _img_h, upscale)
        _t_ocr0 = time.perf_counter()
        with st.spinner(f"OCR: {f.name}…"):
            results = read_text(image, upscale=upscale)
        _ocr_timings.append(
            (f.name, _img_w, _img_h, _eff_w, _eff_h, time.perf_counter() - _t_ocr0)
        )
        ordered = sorted_lines(results)
        lines = [t for _, t, _ in ordered]
        agg_lines.extend(lines)

        if y_offset > 0:
            shifted = []
            for bbox, text, conf in ordered:
                new_bbox = [[float(p[0]), float(p[1]) + y_offset] for p in bbox]
                shifted.append((new_bbox, text, conf))
            agg_boxes.extend(shifted)
        else:
            agg_boxes.extend(ordered)

        # Bu görüntüdeki en alt Y'yi bul, sıradaki dosya için offset güncelle
        max_y_this = 0.0
        for bbox, _, _ in ordered:
            for p in bbox:
                if p[1] > max_y_this:
                    max_y_this = float(p[1])
        y_offset += max_y_this + Y_PAD_BETWEEN_FILES

        part = extract_from_ocr_boxes(ordered)
        chunk_logs.append(
            {
                "dosya": f.name,
                "metin": "\n".join(lines),
                "eslesmeler": list(part.debug_matches),
            }
        )
    # Tüm dosyaları tek bbox listesi gibi parse et (Y-offset sayesinde ayrı bölgeler)
    merged_extract = extract_from_ocr_boxes(agg_boxes)
    extracted_dict = merged_extract.to_dict()

    # Birikim auto-derive: OCR'da birikim alanı bulunamadı ama Ödenen + Yatırım
    # Getirisi varsa, "Birikim = Ödenen + Getiri" kimliğinden türet ve widget'a yaz
    # (kullanıcı kutuda görmek istiyor). Override etmek isterse üstüne yazabilir.
    if (
        extracted_dict.get("birikiminiz") is None
        and extracted_dict.get("odenen_toplam_tutar") is not None
        and extracted_dict.get("yatirim_getiriniz") is not None
    ):
        extracted_dict["birikiminiz"] = (
            extracted_dict["odenen_toplam_tutar"]
            + extracted_dict["yatirim_getiriniz"]
        )
        st.session_state["_birikim_ocr_turetildi"] = True
    else:
        st.session_state.pop("_birikim_ocr_turetildi", None)

    # Yatırım getirisi TERS türetme: Garanti teklif/sözleşme detayı ekranında "Yatırım
    # Getiriniz" alanı YOK ama "Birikim Tutarı" + "Tahsilat Tutarı" var → aynı kimlikten
    # (Getiri = Birikim − Ödenen) ters yönde türet. Birikim forward-derive ile mutually
    # exclusive (biri birikim'i diğeri getiri'yi doldurur).
    if (
        extracted_dict.get("yatirim_getiriniz") is None
        and extracted_dict.get("birikiminiz") is not None
        and extracted_dict.get("odenen_toplam_tutar") is not None
    ):
        extracted_dict["yatirim_getiriniz"] = (
            extracted_dict["birikiminiz"] - extracted_dict["odenen_toplam_tutar"]
        )
        st.session_state["_getiri_ocr_turetildi"] = True
    else:
        st.session_state.pop("_getiri_ocr_turetildi", None)

    # Süre OCR'da yoksa, ÜÇ kaynaktan öncelik sırasıyla türet:
    #   1. Sözleşme başlangıç tarihi (Yürürlük/Hakediş Baz/Teklif) — stopaj+hak ediş için
    #      DOĞRU kaynak. Tam tarih → floor((bugün-tarih)/365.25) ile kesin yıl.
    #   2. BES Giriş Tarihi — BES sistemine İLK giriş; sözleşme başlangıcına EŞİT
    #      OLMAYABİLİR (eski üye + yeni sözleşme). Kullanılırsa UI'da uyarı gösterilir.
    #   3. Gauge'taki «YYYY GİRİŞ» — ay/gün yok; (current_year - gy - 1) conservative
    #      tıraş (overshoot riski yerine undershoot → kullanıcı elle düzeltir).
    # Önce tüm süre-türetme bayraklarını temizle, sonra uygun kaynağı işaretle.
    for _k in (
        "_sure_sozlesme_tarihinden_turetildi",
        "_sure_baslangic_tarihinden_turetildi",
        "_sure_giris_yili_turetildi",
    ):
        st.session_state.pop(_k, None)
    if extracted_dict.get("hak_edise_esas_sure") is None:
        today = datetime.now().date()
        if merged_extract.sozlesme_baslangic_tarihi is not None:
            sbt = merged_extract.sozlesme_baslangic_tarihi
            sure_yil = max(0, int((today - sbt).days // 365.25))
            extracted_dict["hak_edise_esas_sure"] = float(sure_yil)
            st.session_state["_sure_sozlesme_tarihinden_turetildi"] = (sbt, today, sure_yil)
        elif merged_extract.bes_giris_tarihi is not None:
            bgt = merged_extract.bes_giris_tarihi
            sure_yil = max(0, int((today - bgt).days // 365.25))
            extracted_dict["hak_edise_esas_sure"] = float(sure_yil)
            st.session_state["_sure_baslangic_tarihinden_turetildi"] = (bgt, today, sure_yil)
        elif merged_extract.giris_yili is not None:
            gy = merged_extract.giris_yili
            cy = today.year
            sure_tahmin = max(0, cy - gy - 1)
            extracted_dict["hak_edise_esas_sure"] = float(sure_tahmin)
            st.session_state["_sure_giris_yili_turetildi"] = (gy, cy, sure_tahmin)

    # Devlet katkılı sözleşmede (devlet_katkisi OCR'dan geldiyse) hak ediş oran ve
    # tutarını süreden türet — EGM kademeleri (3y/6y/10y → %15/%35/%60).
    sure_x = extracted_dict.get("hak_edise_esas_sure")
    dk_x = extracted_dict.get("devlet_katkisi")
    if dk_x is not None and sure_x is not None:
        if extracted_dict.get("hak_edis_oraniniz") is None:
            extracted_dict["hak_edis_oraniniz"] = hak_edis_orani_from_sure(sure_x)
            st.session_state["_oran_ocr_turetildi"] = True
        else:
            st.session_state.pop("_oran_ocr_turetildi", None)
        if extracted_dict.get("hak_edis_tutariniz") is None:
            oran_x = extracted_dict["hak_edis_oraniniz"]
            extracted_dict["hak_edis_tutariniz"] = hak_edis_tutari_from_oran(dk_x, oran_x)
            st.session_state["_he_ocr_turetildi"] = True
        else:
            st.session_state.pop("_he_ocr_turetildi", None)
    else:
        st.session_state.pop("_oran_ocr_turetildi", None)
        st.session_state.pop("_he_ocr_turetildi", None)

    _apply_extraction_to_widgets(extracted_dict, apply_mode)

    if st.session_state.get("ocr_auto_cikis_tipi"):
        # En güvenilir sinyal: parser «Devlet Katkısı» kalemini tutarıyla bulduysa
        # (sıkı exclude listesi var, yatırılan/getirisi karışmaz). Bulamadıysa line-based
        # başlık taraması yedek.
        is_katkili = (
            merged_extract.devlet_katkisi is not None
            and merged_extract.devlet_katkisi > 0
        ) or infer_devlet_katkili_sozlesme(agg_lines)
        st.session_state["cikis_sozlesme_tipi"] = (
            "devlet_katkili" if is_katkili else "devlet_katkisiz"
        )

    if merge_mode == "Üzerine yaz":
        st.success("OCR tamam; tanınan alanlar yeni değerlerle güncellendi.")
    else:
        st.info(
            "OCR tamam; **yalnızca boş** kutular dolduruldu — dolu alanlar eski sözleşmeden kalabilir. "
            "Farklı sözleşmede **Üzerine yaz** seçin."
        )

    # Performans dökümü: model hazırlama vs saf OCR çıkarımı + görüntü boyutları.
    # «model hazırlama» her çalıştırmada ~25 sn ise → konteyner restart / reader cache
    # çalışmıyor. «çıkarım» yüksekse → büyük görüntü + yavaş CPU, görüntü kısma gerekir.
    _ocr_toplam = sum(t[5] for t in _ocr_timings)
    _zaman_satir = (
        f"⏱️ **OCR zamanlaması** — Model hazırlama: **{_reader_prep_s:.1f} sn** · "
        f"Çıkarım (toplam {len(_ocr_timings)} görüntü): **{_ocr_toplam:.1f} sn** · "
        f"Parser: <0.1 sn"
    )
    _boyut_satir = " | ".join(
        f"{ad[:16]}: {w}×{h}px → OCR {ew}×{eh}px → {sn:.1f} sn"
        for ad, w, h, ew, eh, sn in _ocr_timings
    )
    st.caption(_zaman_satir + ("  \n" + _boyut_satir if _boyut_satir else ""))

    yg_ocr = merged_extract.yatirim_getiriniz
    sy_ocr = merged_extract.hak_edise_esas_sure
    if yg_ocr is not None and sy_ocr is not None:
        oran_ocr = stopaj_orani(sy_ocr)
        sk_ocr = round(stopaj_kesintisi_tl(yg_ocr, sy_ocr), 2)
        pct_ocr = oran_ocr * 100
        o1, o2, o3 = st.columns(3)
        with o1:
            st.metric("Stopaj kesintisi (OCR)", format_tl(sk_ocr) + " TL")
        with o2:
            st.metric("Stopaj oranı (OCR)", f"%{pct_ocr:g}")
        with o3:
            st.metric("Hak edişe esas süre (OCR)", f"{sy_ocr:g} yıl")
        st.caption(
            f"**Kullanılan tutar:** {format_tl(yg_ocr)} TL × **%{pct_ocr:g}** = **{format_tl(sk_ocr)}** TL. "
            "Alan kutusundaki yatırım getirisi farklıysa OCR yanlış eşlemiş olabilir; kutuyu kontrol edin."
        )
    else:
        eksik_stopaj = []
        if yg_ocr is None:
            eksik_stopaj.append("yatırım getiriniz")
        if sy_ocr is None:
            eksik_stopaj.append("hak edişe esas süre")
        st.caption(
            "Stopaj tahmini gösterilemedi — OCR bu turda şunları bulamadı: "
            + ", ".join(eksik_stopaj)
            + "."
        )

    st.session_state.ocr_chunks.extend(chunk_logs)
    st.session_state.last_ocr_birlesik = "\n".join(agg_lines)
    st.session_state.last_ocr_eslesme = list(merged_extract.debug_matches)
    # Aynı dosya için OCR'ın tekrar tetiklenmemesi için sig'i kaydet
    if _current_file_sig is not None:
        st.session_state["_last_ocr_file_sig"] = _current_file_sig

st.subheader("Alanlar (OCR veya elle)")
st.caption("Türk formatı: 1.234,56 — alanları istediğiniz gibi düzenleyebilirsiniz.")

c1, c2, c3 = st.columns(3)
for i, (key, label) in enumerate(FIELD_ROWS):
    col = [c1, c2, c3][i % 3]
    with col:
        wk = _widget_key(key)
        raw = st.text_input(
            label,
            key=wk,
            help="Boş bırakılabilir.",
        )
        if raw.strip():
            if key == "hak_edis_oraniniz":
                s = raw.strip().replace("%", "").replace(" ", "").replace(",", ".")
                try:
                    float(s)
                except ValueError:
                    st.caption("Geçersiz oran")
            elif tr_amount_to_float(raw) is None:
                st.caption("Sayı okunamadı")

if st.session_state.ocr_chunks:
    with st.expander("Ham OCR metni (son çalıştırma — birleşik)", expanded=False):
        st.text_area(
            "birlesik",
            value=st.session_state.get("last_ocr_birlesik", ""),
            height=280,
            disabled=True,
            label_visibility="collapsed",
        )
    with st.expander("OCR geçmişi (dosya dosya)", expanded=False):
        for idx, ch in enumerate(reversed(st.session_state.ocr_chunks[-12:]), start=1):
            st.markdown(f"**{ch['dosya']}**")
            st.text(ch["metin"][:4000] + ("…" if len(ch["metin"]) > 4000 else ""))
            if ch.get("eslesmeler"):
                st.caption("Eşleşmeler: " + ", ".join(f"{a}→{c}" for a, _, c in ch["eslesmeler"]))
            st.divider()
    if st.session_state.get("last_ocr_eslesme"):
        st.subheader("Son birleşik OCR eşleşmeleri")
        for fname, line, amt in st.session_state.last_ocr_eslesme:
            st.write(f"**{fname}** ← `{line}` → {amt}")

c_clr0, c_clr1, c_clr2 = st.columns(3)
with c_clr0:
    if st.button("Her şeyi sıfırla (alanlar + OCR)", type="primary"):
        st.session_state["_do_clear_all"] = True
        st.rerun()
with c_clr1:
    if st.button("Sadece alanları temizle"):
        st.session_state["_do_clear_fields"] = True
        st.rerun()
with c_clr2:
    if st.button("Sadece OCR geçmişini sil"):
        st.session_state.ocr_chunks = []
        st.session_state.pop("last_ocr_birlesik", None)
        st.session_state.pop("last_ocr_eslesme", None)
        st.rerun()

st.subheader("Çıkış hesabı")
st.caption(
    "Sözleşme tipi: sol sütunda **OCR sonrası sözleşme tipini otomatik seç** kutusu kapalıyken OCR radyoyu değiştirmez. "
    "Açıkken yalnızca **satır başında** kısa «devlet katkısı» / «yatırılan devlet katkısı» başlığı aranır."
)
sozlesme_cikis = st.radio(
    "Sözleşme tipi (çıkış formülü)",
    _CIKIS_SOZLESME_OPTIONS,
    format_func=lambda x: (
        "Devlet katkısız — Birikiminiz − stopaj"
        if x == "devlet_katkisiz"
        else "Devlet katkılı — Birikiminiz + Hak ediş tutarınız − stopaj"
    ),
    horizontal=True,
    key="cikis_sozlesme_tipi",
    help="Varsayılan: katkısız (soldaki seçenek). Katkılı BES ekranı için sağdakini seçin.",
)
st.caption(
    "Stopaj kesintisi = Yatırım getiriniz × stopaj oranı (≥10 yıl hak edişe esas süre → %10, "
    "aksi halde %15). "
    + (
        "Net çıkış: Birikiminiz + Hak ediş tutarınız − stopaj."
        if sozlesme_cikis == "devlet_katkili"
        else "Net çıkış: Birikiminiz − stopaj (hak ediş tutarı bu formülde yok)."
    )
)


def _read_tl(k: str) -> float | None:
    raw = (st.session_state.get(_widget_key(k)) or "").strip()
    return tr_amount_to_float(raw) if raw else None


def _read_scalar(k: str) -> float | None:
    raw = (st.session_state.get(_widget_key(k)) or "").strip()
    if not raw:
        return None
    v = tr_amount_to_float(raw)
    if v is not None:
        return v
    try:
        return float(raw.replace(",", ".").replace("%", "").strip())
    except ValueError:
        return None


b = _read_tl("birikiminiz")
dk = _read_tl("devlet_katkisi")
he = _read_tl("hak_edis_tutariniz")
yg = _read_tl("yatirim_getiriniz")
sy = _read_scalar("hak_edise_esas_sure")
odenen = _read_tl("odenen_toplam_tutar")
oran_goster = (st.session_state.get(_widget_key("hak_edis_oraniniz")) or "").strip()

# «Birikim = Ödenen Toplam Tutar + Yatırım Getirisi» BES'in temel kimliğidir
# (devlet katkısı varsa ayrı kalemdir, birikim'e dahil değildir). Bazı şirket
# ekranlarında (Garanti detay sayfası gibi) birikim alanı doğrudan görünmez ama
# ödenen + getiri görünür → türetiyoruz.
#   * OCR sırasında türetildiyse Birikim widget'ı zaten doldurulmuş olur (bkz: yukarısı).
#   * Kullanıcı sadece manuel ödenen+getiri girdiyse burada türetiriz (widget boş kalır
#     ama hesap için yine doğru değer kullanılır).
b_turetildi_manuel = False
if b is None and odenen is not None and yg is not None:
    b = odenen + yg
    b_turetildi_manuel = True
b_turetildi = b_turetildi_manuel or st.session_state.get("_birikim_ocr_turetildi", False)

devlet_katkili = sozlesme_cikis == "devlet_katkili"

# Manuel akışta hak ediş oran/tutar türetme: kullanıcı OCR sonrası süreyi elle yazdığında
# (örneğin gauge'ta YYYY GİRİŞ olmayan layout'larda) hesap akışı bu blokla tamamlanır.
# OCR sırasındaki paralel türetme yukarıda — bu blok yalnızca devlet katkılı senaryoda devreye girer.
oran_user_input = _read_scalar("hak_edis_oraniniz")
oran_turetildi_manuel = False
he_turetildi_manuel = False
if devlet_katkili and dk is not None and sy is not None:
    if oran_user_input is not None:
        oran_for_calc = oran_user_input
    else:
        oran_for_calc = hak_edis_orani_from_sure(sy)
        oran_turetildi_manuel = he is None  # kullanıcı he'yi elle yazdıysa oran info'su gereksiz
    if he is None:
        he = hak_edis_tutari_from_oran(dk, oran_for_calc)
        he_turetildi_manuel = True

if devlet_katkili:
    gerekli = {
        "Birikiminiz": b,
        "Hak ediş tutarınız": he,
        "Yatırım getiriniz": yg,
        "Hak edişe esas süre (yıl)": sy,
    }
else:
    gerekli = {
        "Birikiminiz": b,
        "Yatırım getiriniz": yg,
        "Hak edişe esas süre (yıl)": sy,
    }
eksik = [ad for ad, v in gerekli.items() if v is None]

hesap_hazir = (
    b is not None
    and yg is not None
    and sy is not None
    and (he is not None if devlet_katkili else True)
)

if eksik:
    st.warning("Hesap için şu alanlar dolu olmalı: " + ", ".join(eksik))
elif hesap_hazir:
    he_kullan = he if he is not None else 0.0  # info notlarında da kullanılıyor — önce tanımla
    if b_turetildi:
        st.info(
            f"**Birikim otomatik türetildi:** Ödenen ({format_tl(odenen)}) + "
            f"Yatırım Getirisi ({format_tl(yg)}) = **{format_tl(b)} TL**. "
            "Birikim alanı boştu; üst kutuya elle bir değer yazarsanız o değer kullanılır."
        )
    if st.session_state.get("_getiri_ocr_turetildi") and odenen is not None:
        st.info(
            f"**Yatırım getirisi otomatik türetildi:** Birikim Tutarı ({format_tl(b)}) − "
            f"Ödenen/Tahsilat ({format_tl(odenen)}) = **{format_tl(yg)} TL**. "
            "Bu ekranda «Yatırım Getiriniz» ayrı bir kalem değildi; kutuya elle "
            "yazarsanız o değer kullanılır."
        )
    sure_info_sbt = st.session_state.get("_sure_sozlesme_tarihinden_turetildi")
    if sure_info_sbt:
        sbt, today_d, sy_t = sure_info_sbt
        st.info(
            f"**Süre sözleşme başlangıç tarihinden hesaplandı:** {sbt.strftime('%d/%m/%Y')} → "
            f"bugün ({today_d.strftime('%d/%m/%Y')}) = **{sy_t} yıl** "
            "(Yürürlük / Hakediş Baz / Teklif Başlangıç tarihinden; ay/gün dahil tam yıl). "
            "Stopaj ve hak ediş bu süreye göre hesaplanır."
        )
    sure_info_bgt = st.session_state.get("_sure_baslangic_tarihinden_turetildi")
    if sure_info_bgt:
        bgt, today_d, sy_t = sure_info_bgt
        st.warning(
            f"**Süre BES Giriş Tarihi'nden hesaplandı:** {bgt.strftime('%d/%m/%Y')} → "
            f"bugün ({today_d.strftime('%d/%m/%Y')}) = **{sy_t} yıl**. "
            "⚠️ Bu tarih **BES sistemine ilk giriş** tarihinizdir — sözleşme başlangıcı "
            "değil. Sonradan **yeni bir sözleşme** açtıysanız gerçek süre daha kısadır; "
            "stopaj/hak ediş yanlış çıkmaması için «Hak edişe esas süre» kutusunu elle "
            "düzeltin."
        )
    sure_info = st.session_state.get("_sure_giris_yili_turetildi")
    if sure_info:
        gy, cy, st_ = sure_info
        st.info(
            f"**Süre tahmin edildi:** Gauge'taki giriş yılı **{gy}**, bugün **{cy}** → "
            f"conservative tahmin **{st_} yıl** (calendar farkı {cy - gy} − 1 = {st_}, "
            "ay/gün bilinmediği için 1 yıl tıraş). "
            "Gerçek süren {min}–{max} yıl arasıdır; kademe sınırlarına ({line}) "
            "denk düşüyorsa **alanı elle düzeltin** — örn. tam 3 yıl doldurduysan kutuya 3 yaz.".format(
                min=st_, max=st_ + 1, line="%0/%15/%35/%60"
            )
        )
    if st.session_state.get("_oran_ocr_turetildi") or oran_turetildi_manuel:
        st.info(
            "**Hak ediş oranı otomatik türetildi:** EGM kademeli oranı "
            "(< 3 yıl %0, 3–6 yıl %15, 6–10 yıl %35, ≥ 10 yıl %60). "
            f"Süre **{sy:g} yıl** → **%{int(hak_edis_orani_from_sure(sy))}**. "
            "Yaş şartı dikkate alınmaz; kutuya elle yazarsanız o kullanılır."
        )
    if (st.session_state.get("_he_ocr_turetildi") or he_turetildi_manuel) and dk is not None and dk > 0:
        st.info(
            f"**Hak ediş tutarı otomatik türetildi:** Devlet katkısı ({format_tl(dk)}) × "
            f"oran ({(he_kullan / dk * 100):.0f}%) = **{format_tl(he_kullan)} TL**."
        )
    h = cikista_ele_gecen_tl(
        b,
        he_kullan,
        yg,
        sy,
        devlet_katkili_sozlesme=devlet_katkili,
    )
    m1, m2, m3 = st.columns(3)
    pct = h.uygulanan_stopaj_orani * 100
    m1.metric("Uygulanan stopaj oranı", f"%{pct:g}")
    m2.metric("Stopaj kesintisi", format_tl(h.stopaj_kesintisi_tl) + " TL")
    m3.metric("Çıkışta güncel birikim (net)", format_tl(h.cikista_net_tl) + " TL")
    st.caption(
        f"Stopaj hesabı: **{format_tl(yg)}** TL (yatırım getiriniz) × **%{pct:g}** = **{format_tl(h.stopaj_kesintisi_tl)}** TL. "
        "Buradaki tutar, alandaki «Yatırım Getiriniz» ile aynı olmalıdır."
    )
    with st.expander("Ara değerler"):
        st.write(f"Birikiminiz: **{format_tl(b)}** TL")
        if dk is not None:
            st.write(f"Devlet katkısı (bilgi): **{format_tl(dk)}** TL")
        if devlet_katkili:
            st.write(f"Hak ediş tutarınız: **{format_tl(he_kullan)}** TL")
        else:
            st.caption("Bu sözleşme tipinde net = Birikiminiz − stopaj; hak ediş tutarı formülde kullanılmaz.")
        st.write(f"Yatırım getiriniz: **{format_tl(yg)}** TL")
        st.write(f"Hak edişe esas süre: **{sy:g}** yıl → stopaj oranı **%{pct:g}**")
        if odenen is not None:
            st.write(f"Ödenen toplam tutar (bilgi): **{format_tl(odenen)}** TL")
        if oran_goster:
            st.write(f"Hak ediş oranınız (bilgi): **{oran_goster}**")

st.info(
    "Etiket eşleşmeleri `src/bes_parse.py` içindeki FIELD_PHRASES listesindedir; değer etiketin "
    "hemen sonrasından (veya bir alt satırdan) okunur — yanlış eşleşmeyi azaltmak için kısa/güvensiz "
    "kelimeler kullanılmaz."
)

if not files and not st.session_state.ocr_chunks:
    st.info("Üstten bir veya birden fazla ekran görüntüsü seçip **OCR çalıştır** deyin; alanları elle de doldurabilirsiniz.")

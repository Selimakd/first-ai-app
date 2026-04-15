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

import streamlit as st
from PIL import Image

from src.bes_calc import cikista_ele_gecen_tl, format_tl, stopaj_kesintisi_tl, stopaj_orani
from src.bes_parse import extract_from_ocr_lines, infer_devlet_katkili_sozlesme, tr_amount_to_float
from src.ocr_engine import read_text, sorted_lines

# Tarayıcı sekmesi + sayfa başlığı; yeni sürümün yüklendiğini görmek için anlamlı her değişiklikte artırın (1.1 → 1.2 …).
APP_VERSION = "2.0"
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
        value=False,
        key="ocr_auto_cikis_tipi",
        help="Varsayılan kapalı: radyo sizin seçiminizde kalır. Açıkken yalnızca OCR satırı «devlet katkısı» "
        "ile **başlıyorsa** (kısa başlık satırı) katkılı seçilir; aksi halde katkısız.",
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

run = st.button("OCR çalıştır", type="primary", disabled=len(files) == 0)
if run and files:
    apply_mode = "Üzerine yaz" if merge_mode == "Üzerine yaz" else "Yalnızca boş"
    agg_lines: list[str] = []
    chunk_logs: list[dict] = []
    for f in files:
        f.seek(0)
        image = Image.open(f)
        with st.spinner(f"OCR: {f.name}…"):
            results = read_text(image, upscale=upscale)
        ordered = sorted_lines(results)
        lines = [t for _, t, _ in ordered]
        agg_lines.extend(lines)
        part = extract_from_ocr_lines(lines)
        chunk_logs.append(
            {
                "dosya": f.name,
                "metin": "\n".join(lines),
                "eslesmeler": list(part.debug_matches),
            }
        )
    merged_extract = extract_from_ocr_lines(agg_lines)
    _apply_extraction_to_widgets(merged_extract.to_dict(), apply_mode)

    if st.session_state.get("ocr_auto_cikis_tipi"):
        st.session_state["cikis_sozlesme_tipi"] = (
            "devlet_katkili" if infer_devlet_katkili_sozlesme(agg_lines) else "devlet_katkisiz"
        )

    if merge_mode == "Üzerine yaz":
        st.success("OCR tamam; tanınan alanlar yeni değerlerle güncellendi.")
    else:
        st.info(
            "OCR tamam; **yalnızca boş** kutular dolduruldu — dolu alanlar eski sözleşmeden kalabilir. "
            "Farklı sözleşmede **Üzerine yaz** seçin."
        )

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

devlet_katkili = sozlesme_cikis == "devlet_katkili"
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
    he_kullan = he if he is not None else 0.0
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

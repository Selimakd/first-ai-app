"""BES ekran görüntüsü OCR metninden tutar çıkarma (Türkçe format).

İki yol:

* ``extract_from_ocr_lines(lines)`` — düz metin satır listesi alır; heuristic parse. Eski
  davranış, sentetik unit testler ve geri uyumluluk için tutulur.
* ``extract_from_ocr_boxes(boxes)`` — EasyOCR ham çıktısı (bbox + text + conf) alır.
  Etiket↔değer eşlemesini **2B uzamsal yakınlık** ile kurar: her etiket için önce sağında
  (aynı satır) sonra altında (aynı sütun) en yakın uygun değer seçilir. Ekran görüntüsü
  uçtan uca testlerinde bu yol kullanılır — kolon düzeni OCR satır sırası ile bozulduğunda
  bile doğru eşleşir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Kind = Literal["money", "sure", "oran"]

FIELD_PHRASES: dict[str, tuple[str, ...]] = {
    "odenen_toplam_tutar": (
        "ödenen toplam tutar",
        "odenen toplam tutar",
        "ödenen toplam",
        "odenen toplam",
        "ödenen tutar",  # Garanti mobil
        "odenen tutar",
        "tahsilat tutarı",  # Garanti teklif/sözleşme detayı — "Tahsilat Tutarı (Devlet Katkısı Hariç)"
        "tahsilat tutari",
    ),
    "hak_edise_esas_sure": (
        "hak edişe esas süre",
        "hak edise esas sure",
        "hak edişe esas",
        "hak edise esas",
    ),
    "hak_edis_oraniniz": (
        # En uzun/spesifik phrase'ler önce — _find_label_box uzun eşleşmeyi tercih eder.
        "hak edilen devlet katkısı oranı",  # Garanti teklif/sözleşme detayı
        "hak edilen devlet katkisi orani",
        "hak ediş oranınız",
        "hak edis oraniniz",
        "hak ediş oranı",
        "hak edis orani",
    ),
    "hak_edis_tutariniz": (
        "hak edilen devlet katkısı tutarı",  # Garanti teklif/sözleşme detayı
        "hak edilen devlet katkisi tutari",
        "hak ediş tutarınız",
        "hak edis tutariniz",
        "hak ediş tutarı",
        "hak edis tutari",
        "hak ediş tutar",
        "hak edis tutar",
    ),
    "yatirim_getiriniz": (
        "yatırım getiriniz",
        "yatirim getiriniz",
        "yatırım getirisi",
        "yatirim getirisi",
        "fon getirisi",  # Garanti mobil
    ),
    "devlet_katkisi": (
        # Garanti mobil kompakt varyant: tek başlık altında yatırılan + getiri toplamı
        # ("Devlet Katkısı Birikiminiz" / "Devlet Katkısı Birikimi"). Eski varyantlarda
        # "Devlet Katkısı" zaten toplam idi — uzun phrase _find_label_box'ta öncelikli
        # olduğu için her iki varyantta da doğru kutu seçilir.
        "devlet katkısı birikiminiz",
        "devlet katkisi birikiminiz",
        "devlet katkısı birikimi",  # Garanti teklif/sözleşme detayı
        "devlet katkisi birikimi",
        "devlet katkısı birikim",
        "devlet katkisi birikim",
        "devlet katkısı",
        "devlet katkisi",
    ),
    "birikiminiz": (
        # NOT: "toplam birikiminiz" BİLEREK phrase olarak yok. Bazı ekranlarda
        # ("devlet katkılı" Fon Koçu gibi) HEM "Birikiminiz" (gerçek birikim) HEM
        # "Toplam Birikiminiz" (birikim + devlet katkısı = grand total) bulunur.
        # "birikiminiz" zaten "toplam birikiminiz"in alt dizisi → phrase olarak onu
        # da yakalar; _find_label_box'ın -extra eşitlik bozucusu daha temiz olan
        # "Birikiminiz" kutusunu seçer. Tek başlık "Toplam Birikiminiz" olan
        # ekranlarda da tek aday olarak yine doğru yakalanır.
        "birikim tutarı",  # Garanti teklif/sözleşme detayı — "Birikim Tutarı (Devlet Katkısı Hariç)"
        "birikim tutari",
        "birikiminiz",
        "birikimınız",
        "birikiminız",
    ),
}

FIELD_KIND: dict[str, Kind] = {
    "odenen_toplam_tutar": "money",
    "hak_edise_esas_sure": "sure",
    "hak_edis_oraniniz": "oran",
    "hak_edis_tutariniz": "money",
    "yatirim_getiriniz": "money",
    "devlet_katkisi": "money",
    "birikiminiz": "money",
}

FIELD_ORDER: tuple[str, ...] = (
    "odenen_toplam_tutar",
    "hak_edise_esas_sure",
    "hak_edis_oraniniz",
    "hak_edis_tutariniz",
    "yatirim_getiriniz",
    "devlet_katkisi",
    "birikiminiz",
)

FIELD_KEYWORDS = FIELD_PHRASES

# Sözleşme tipi: yalnızca satır başı «etiket» gibi görünen kalıplar (içerikte geçen alt dizi = yanlış pozitif).
# Satır yalnızca başlık (+ isteğe bağlı : / TL); «devlet katkisi hak» gibi ek kelime = eşleşmez.
_DEVLET_SECTION_HEAD_RE = re.compile(
    r"^(?:yatirilan\s+devlet\s+katkisi(?:\s+getirisi)?|devlet\s+katkisi(?:\s+getirisi)?)"
    r"(?:\s*:\s*)?(?:\s*(?:tl|try|₺))?\s*$",
    re.IGNORECASE,
)
# Uzun açıklama / mevzuat satırlarında aynı kelimeler geçebilir; başlık sayma.
_DEVLET_INFER_SKIP_LINE_RE = re.compile(
    r"\b(mevzuat|kanunun|kanuni|bilgilendirme|aydinlatma|aydınlatma|metni|açiklamasidir|açıklamasıdır)\b",
    re.IGNORECASE,
)
_DEVLET_INFER_MAX_LINE_LEN = 100

AMOUNT_PATTERN = re.compile(
    r"(?P<num>\d{1,3}(?:\.\d{3})*(?:,\d{1,4})?|\d+(?:,\d{1,4})?)\s*(?:TL|TRY|₺)?",
    re.IGNORECASE,
)

SCALAR_PATTERN = re.compile(
    r"(?P<num>\d{1,3}(?:\.\d{3})*(?:,\d{1,4})?|\d+(?:,\d{1,4})?)",
)

# Türkçe arayüzde sık: "54,2 %" veya "Hak Ediş Oranınız %60"
ORAN_PATTERN_NUM_FIRST = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{1,4})?|\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
ORAN_PATTERN_PCT_FIRST = re.compile(
    r"%\s*(?P<num>\d{1,3}(?:[.,]\d{1,4})?)",
    re.IGNORECASE,
)

# Sadece etiket satırı (tutar yok); okumayı bir sonraki tutar satırına kaydırmak için
_LABEL_SKIP = re.compile(
    r"^(ödenen|odenen|yatırım|yatirim|yatırılan|yatirilan|devlet|katkı|katki|getiri|getiriniz|fon|koçu|koç|detay|bilgi|hizmet|birikiminize|vere|yön|yön|ediş|edis|hak|durum|kümül|kumul|son|yıl|yil|toplam|kazanç|kazanc|@)\b",
    re.IGNORECASE,
)

_DEVLET_KATKISI_LINE = re.compile(r"^devlet\s+katkisi\s*:?\s*(tl)?\s*$", re.IGNORECASE)
_BIRIKIMINIZ_LINE = re.compile(r"^birikiminiz\s*:?\s*(tl)?\s*$", re.IGNORECASE)


def normalize_line(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def fold_tr_ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = s.translate(str.maketrans("ıİ", "ii"))
    return s


def tr_amount_to_float(raw: str) -> float | None:
    s = raw.strip().replace(" ", "").replace("₺", "").replace("TL", "").replace("TRY", "")
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s:
        main, frac = s.rsplit(",", 1)
        main = main.replace(".", "")
        try:
            return float(f"{main}.{frac}")
        except ValueError:
            return None
    if s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[-1]) == 3):
        return float(s.replace(".", ""))
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def first_amount_in_text(text: str) -> float | None:
    m = AMOUNT_PATTERN.search(text.replace(" ", ""))
    if not m:
        m = AMOUNT_PATTERN.search(text)
    if not m:
        return None
    return tr_amount_to_float(m.group("num"))


def first_scalar_in_text(text: str) -> float | None:
    m = SCALAR_PATTERN.search(text)
    if not m:
        return None
    return tr_amount_to_float(m.group("num"))


def parse_oran_from_text(text: str) -> float | None:
    """Örn. 54,2 % | 60 % | %60 | % 60 | Hak Ediş Oranınız %60"""
    compact = text.replace(" ", "")
    for rx in (ORAN_PATTERN_NUM_FIRST,):
        m = rx.search(compact)
        if not m:
            m = rx.search(text)
        if m:
            try:
                v = float(m.group("num").replace(",", "."))
                if 0 < v <= 100:
                    return v
            except ValueError:
                pass
    m2 = ORAN_PATTERN_PCT_FIRST.search(compact)
    if not m2:
        m2 = ORAN_PATTERN_PCT_FIRST.search(text)
    if m2:
        try:
            v = float(m2.group("num").replace(",", "."))
            if 0 < v <= 100:
                return v
        except ValueError:
            pass
    return None


def _phrase_in_line(fl: str, fp: str) -> int:
    return fl.find(fp)


def _collect_money_sequence(folded_lines: list[str], start_j: int, max_lines: int = 14) -> list[float]:
    """Ardışık satırlarda geçen tutarlar (sıra korunur)."""
    out: list[float] = []
    end = min(start_j + max_lines, len(folded_lines))
    for j in range(start_j, end):
        v = first_amount_in_text(folded_lines[j])
        if v is not None and v > 0:
            out.append(v)
    return out


def _is_noise_label_line(fl: str) -> bool:
    if first_amount_in_text(fl) is not None:
        return False
    s = fl.strip()
    if len(s) <= 2:
        return True
    if _LABEL_SKIP.match(s):
        return True
    return False


def _extract_devlet_katkisi_only_line(folded_lines: list[str], lines: list[str]) -> tuple[float | None, str]:
    """Satır yalnızca 'devlet katkısı' ise bir sonraki tutar satırı devlet katkısıdır (yatırılan devlet ile karışmaz)."""
    for i, fl in enumerate(folded_lines):
        if not _DEVLET_KATKISI_LINE.match(fl.strip()):
            continue
        for j in range(i + 1, min(i + 5, len(folded_lines))):
            if _is_noise_label_line(folded_lines[j]):
                continue
            v = first_amount_in_text(folded_lines[j])
            if v is not None:
                return v, lines[j]
    return None, ""


def _extract_birikiminiz_two_row(folded_lines: list[str], lines: list[str]) -> tuple[float | None, str]:
    """Birikiminiz üstte, hemen altında Devlet Katkısı etiketi; sonra iki tutar (önce devlet, sonra birikim)."""
    for i, fl in enumerate(folded_lines):
        if _phrase_in_line(fl, "birikiminiz") < 0:
            continue
        if i + 1 >= len(folded_lines):
            break
        if not _DEVLET_KATKISI_LINE.match(folded_lines[i + 1].strip()):
            continue
        seq = _collect_money_sequence(folded_lines, i + 2, max_lines=6)
        if len(seq) >= 2:
            return seq[1], f"{lines[i]} → … → {lines[min(i+2+1, len(lines)-1)]}"
        if len(seq) == 1:
            return seq[0], lines[i]
    return None, ""


def _find_label_line_index(folded_lines: list[str], phrases: tuple[str, ...]) -> int:
    """Etiketin geçtiği satır indeksi (bölünmüş OCR için 2–3 satır birleşimi)."""
    n = len(folded_lines)
    for i in range(n):
        fl = folded_lines[i]
        for ph in phrases:
            if fold_tr_ascii(ph) in fl:
                return i
    for w in (2, 3):
        for i in range(max(0, n - w + 1)):
            joint = " ".join(folded_lines[i : i + w])
            for ph in phrases:
                if fold_tr_ascii(ph) in joint:
                    return i + w - 1
    return -1


def _first_amount_after_label(
    folded_lines: list[str],
    lines: list[str],
    label_idx: int,
    phrases: tuple[str, ...],
    range_end: int,
) -> tuple[float | None, str]:
    """Etiket satırından itibaren (aynı satır tail dahil) range_end hariç ilk anlamlı tutar."""
    n = len(folded_lines)
    if label_idx < 0:
        return None, ""
    hi = min(max(range_end, label_idx + 1), n)
    fl = folded_lines[label_idx]
    for ph in phrases:
        fp = fold_tr_ascii(ph)
        pos = fl.find(fp)
        if pos >= 0:
            tail = fl[pos + len(fp) :]
            v = first_amount_in_text(tail)
            if v is not None and v > 100:
                return v, lines[label_idx]
            break
    for j in range(label_idx + 1, hi):
        nfl = folded_lines[j]
        if _DEVLET_KATKISI_LINE.match(nfl.strip()):
            continue
        if _is_noise_label_line(nfl):
            continue
        v = first_amount_in_text(nfl)
        if v is not None and v > 100:
            return v, lines[j]
    return None, ""


def _near_same_money(a: float, b: float) -> bool:
    """OCR yuvarlama / birikim = yatırım yanlış eşlemesi için tolerans."""
    tol = max(1.0, 1e-4 * max(abs(a), abs(b)))
    return abs(a - b) <= tol


def _money_amounts_below_odenen_yatirim_block(
    folded_lines: list[str],
    lines: list[str],
    io: int,
    iy: int,
) -> list[float]:
    """Ödenen/yatırım etiketlerinin altındaki tüm anlamlı tutarlar (sırayla)."""
    n = len(folded_lines)
    bot = max(io, iy)
    seq: list[float] = []
    for j in range(bot + 1, min(bot + 19, n)):
        fl = folded_lines[j]
        if _BIRIKIMINIZ_LINE.match(fl.strip()):
            break
        if _phrase_in_line(fl, fold_tr_ascii("birikiminiz")) >= 0 and first_amount_in_text(fl) is None:
            break
        if _phrase_in_line(fl, fold_tr_ascii("devlet katkısı")) >= 0 and _DEVLET_KATKISI_LINE.match(fl.strip()):
            continue
        v = first_amount_in_text(fl)
        if v is not None and v > 100:
            seq.append(v)
    return seq


def _money_pair_below_stacked_labels(
    folded_lines: list[str],
    lines: list[str],
    io: int,
    iy: int,
) -> tuple[float | None, float | None, str]:
    """Ödenen + yatırım etiketleri üst üste; tutarlar altta sırayla (önce ödenen, sonra yatırım)."""
    seq = _money_amounts_below_odenen_yatirim_block(folded_lines, lines, io, iy)
    if len(seq) >= 2:
        return seq[0], seq[1], "etiket altı sıralı iki tutar (ödenen → yatırım)"
    if len(seq) == 1:
        return seq[0], None, "yalnızca bir tutar (çift blok)"
    return None, None, ""


def _extract_odenen_yatirim_pair(folded_lines: list[str], lines: list[str]) -> tuple[float | None, float | None, str]:
    """Ödenen ve yatırım tutarları: her biri kendi etiketi ile sonraki blok sınırı arasında (birikim araya girse min/max yapılmaz)."""
    od_phrases = FIELD_PHRASES["odenen_toplam_tutar"]
    yg_phrases = FIELD_PHRASES["yatirim_getiriniz"]
    io = _find_label_line_index(folded_lines, od_phrases)
    iy = _find_label_line_index(folded_lines, yg_phrases)
    n = len(folded_lines)

    if io >= 0 and iy >= 0:
        od, yg, dbg = _money_pair_below_stacked_labels(folded_lines, lines, io, iy)
        if od is not None or yg is not None:
            return od, yg, dbg
        if io < iy:
            od, _ = _first_amount_after_label(folded_lines, lines, io, od_phrases, min(io + 18, n))
            yg, _ = _first_amount_after_label(folded_lines, lines, iy, yg_phrases, min(iy + 18, n))
        else:
            yg, _ = _first_amount_after_label(folded_lines, lines, iy, yg_phrases, min(iy + 18, n))
            od, _ = _first_amount_after_label(folded_lines, lines, io, od_phrases, min(io + 18, n))
        parts = []
        if od is not None:
            parts.append(f"ödenen={od}")
        if yg is not None:
            parts.append(f"yatırım={yg}")
        return od, yg, ("yedek tek etiket taraması: " + ", ".join(parts)) if parts else ""

    # Yalnızca bir etiket: tek blok taraması (eski davranışa yakın)
    if io >= 0:
        od, _ = _first_amount_after_label(folded_lines, lines, io, od_phrases, min(io + 18, n))
        return od, None, "yalnız ödenen etiketi" if od is not None else ""
    if iy >= 0:
        yg, _ = _first_amount_after_label(folded_lines, lines, iy, yg_phrases, min(iy + 18, n))
        return None, yg, "yalnız yatırım etiketi" if yg is not None else ""
    return None, None, ""


def _years_after_hak_edis_esas(folded_lines: list[str], lines: list[str]) -> float | None:
    idx = -1
    fp = fold_tr_ascii("hak edise esas")
    for i, fl in enumerate(folded_lines):
        if fp in fl or "hak edise esas sure" in fl or "hak edise esas" in fl:
            idx = i
            break
    if idx < 0:
        return None
    years: list[float] = []
    for j in range(idx + 1, min(idx + 8, len(folded_lines))):
        line = folded_lines[j]
        for m in re.finditer(r"(\d{1,2})\s*(?:\.?\s*)?(?:yil|yıl)\b", line, re.IGNORECASE):
            y = float(m.group(1))
            if 1 <= y <= 50:
                years.append(y)
        if not re.search(r"yil|yıl", line, re.IGNORECASE):
            # Yalnızca kendi başına sayı satırı ("14", " 5 ") — "946,6" gibi binlik
            # sayıların son rakamını yanlışlıkla yıl saymamak için ondalık/binlik
            # ayraçlarını reddet.
            stripped = line.strip()
            if re.fullmatch(r"\d{1,2}", stripped):
                y = float(stripped)
                if 1 <= y <= 50:
                    years.append(y)
    return max(years) if years else None


def _extract_hak_edis_tutari(folded_lines: list[str], lines: list[str]) -> tuple[float | None, str]:
    """Etiketten sonra OCR bazen küçük parça (928,8) verir; gerçek tutar genelde TL'li veya daha büyük satırdadır."""
    phrases = FIELD_PHRASES["hak_edis_tutariniz"]
    n = len(folded_lines)
    start = -1
    for i in range(n):
        fl = folded_lines[i]
        for ph in phrases:
            fp = fold_tr_ascii(ph)
            if fp in fl:
                start = i
                break
        if start >= 0:
            break
        for w in (2, 3):
            if i + w > n:
                break
            joint = " ".join(folded_lines[i : i + w])
            for ph in phrases:
                fp = fold_tr_ascii(ph)
                if fp in joint:
                    start = i + w - 1
                    break
            if start >= 0:
                break
        if start >= 0:
            break
    if start < 0:
        return None, ""

    candidates: list[tuple[int, float, str, bool]] = []
    fl0 = folded_lines[start]
    orig0 = lines[start]
    for ph in phrases:
        fp = fold_tr_ascii(ph)
        pos = fl0.find(fp)
        if pos >= 0:
            tail = fl0[pos + len(fp) :]
            v = first_amount_in_text(tail)
            if v is not None and v > 0:
                has_tl = "tl" in orig0.lower() or "₺" in orig0 or "try" in orig0.lower()
                candidates.append((start, v, orig0, has_tl))
            break

    for j in range(start + 1, min(start + 17, n)):
        orig = lines[j]
        fl = folded_lines[j]
        v = first_amount_in_text(fl)
        if v is None or v <= 0:
            continue
        has_tl = "tl" in orig.lower() or "₺" in orig or "try" in orig.lower()
        candidates.append((j, v, orig, has_tl))

    if not candidates:
        return None, ""

    for j, v, orig, has_tl in candidates:
        if has_tl and v >= 100:
            return v, orig
    for j, v, orig, _ in candidates:
        if v >= 1_000:
            return v, orig
    j, v, orig, _ = candidates[0]
    return v, orig


def _oran_after_hak_edis(folded_lines: list[str], lines: list[str]) -> tuple[float | None, str]:
    """Etiket bölünük okunabildiği için satırda hak+oran veya oraniniz yeterli."""
    idx = -1
    for i, fl in enumerate(folded_lines):
        if ("hak" in fl or "edis" in fl) and "oran" in fl:
            idx = i
            break
        if "oraniniz" in fl or "oranınız" in fl.lower():
            idx = i
            break
    if idx < 0:
        return None, ""
    for j in range(idx, min(idx + 8, len(folded_lines))):
        fl = folded_lines[j]
        v = parse_oran_from_text(fl)
        if v is not None and 5 < v <= 100:
            return v, lines[j]
    return None, ""


@dataclass
class BesExtracted:
    birikiminiz: float | None = None
    odenen_toplam_tutar: float | None = None
    yatirim_getiriniz: float | None = None
    devlet_katkisi: float | None = None
    hak_edise_esas_sure: float | None = None
    hak_edis_oraniniz: float | None = None
    hak_edis_tutariniz: float | None = None
    # Sözleşme giriş yılı — Garanti gibi ekranlarda gauge altındaki «YYYY GİRİŞ»
    # etiketinden bbox-aware tarama ile çıkarılır. App tarafında süre tahmini için
    # kullanılır (current_year - giris_yili). to_dict()'e dahil DEĞİL — widget alanı
    # değil, ek metadata.
    giris_yili: int | None = None
    # BES Giriş Tarihi (DD/MM/YYYY) — Garanti mobil kompakt ekranı bunu açıkça
    # gösterir. BES sistemine İLK giriş tarihidir; sözleşme başlangıcına eşit
    # olmayabilir. App'te sozlesme_baslangic_tarihi yoksa yedek olarak kullanılır.
    # Yine to_dict()'te yok — metadata.
    bes_giris_tarihi: date | None = None
    # Sözleşme başlangıç tarihi (Yürürlük / Hakediş Baz / Teklif Başlangıç) — stopaj
    # ve hak ediş süresi için DOĞRU kaynak. Varsa bes_giris_tarihi ve giris_yili'na
    # tercih edilir. Garanti teklif/sözleşme detayı ekranında görünür. Metadata.
    sozlesme_baslangic_tarihi: date | None = None
    raw_lines: list[str] = field(default_factory=list)
    debug_matches: list[tuple[str, str, float | None]] = field(default_factory=list)

    def to_dict(self) -> dict[str, float | None]:
        return {
            "birikiminiz": self.birikiminiz,
            "odenen_toplam_tutar": self.odenen_toplam_tutar,
            "yatirim_getiriniz": self.yatirim_getiriniz,
            "devlet_katkisi": self.devlet_katkisi,
            "hak_edise_esas_sure": self.hak_edise_esas_sure,
            "hak_edis_oraniniz": self.hak_edis_oraniniz,
            "hak_edis_tutariniz": self.hak_edis_tutariniz,
        }


def _scan_money_after_phrase(
    folded_lines: list[str],
    lines: list[str],
    phrases: tuple[str, ...],
    field_id: str,
) -> tuple[float | None, str]:
    """Etiket satırından sonra birkaç satır tara; ara etiketleri atla."""
    kind = FIELD_KIND[field_id]
    if kind != "money":
        return None, ""
    n = len(folded_lines)
    for i in range(n):
        fl = folded_lines[i]
        for ph in phrases:
            fp = fold_tr_ascii(ph)
            pos = fl.find(fp)
            if pos < 0:
                continue
            tail = fl[pos + len(fp) :]
            v = first_amount_in_text(tail)
            if v is not None:
                return v, lines[i]
            for j in range(i + 1, min(i + 14, n)):
                nfl = folded_lines[j]
                if _is_noise_label_line(nfl):
                    continue
                v = first_amount_in_text(nfl)
                if v is not None:
                    return v, lines[j]
    for w in (2, 3):
        for i in range(n - w + 1):
            joint = " ".join(folded_lines[i : i + w])
            for ph in phrases:
                fp = fold_tr_ascii(ph)
                pos = joint.find(fp)
                if pos < 0:
                    continue
                tail = joint[pos + len(fp) :]
                v = first_amount_in_text(tail)
                if v is not None:
                    return v, " | ".join(lines[i : i + w])
                start_line = i + w - 1
                for j in range(start_line + 1, min(start_line + 12, n)):
                    if _is_noise_label_line(folded_lines[j]):
                        continue
                    v = first_amount_in_text(folded_lines[j])
                    if v is not None:
                        return v, lines[j]
    return None, ""


def infer_devlet_katkili_sozlesme(lines: list[str]) -> bool:
    """
    OCR'da devlet katkılı sözleşme ekranı: satır, **başlık gibi** «devlet katkısı» / «yatırılan devlet katkısı»
    ile başlamalı; uzun metin / içerik satırı veya rastgele alt dizi sayılmaz.
    """
    if not lines:
        return False
    for L in lines:
        s = fold_tr_ascii(normalize_line(L)).strip()
        if len(s) < 14 or len(s) > _DEVLET_INFER_MAX_LINE_LEN:
            continue
        if _DEVLET_INFER_SKIP_LINE_RE.search(s):
            continue
        if _DEVLET_SECTION_HEAD_RE.match(s):
            return True
    return False


def extract_from_ocr_lines(lines: list[str]) -> BesExtracted:
    out = BesExtracted(raw_lines=list(lines))
    if not lines:
        return out

    folded = [fold_tr_ascii(normalize_line(L)) for L in lines]
    filled: set[str] = set()

    od, yg, pair_dbg = _extract_odenen_yatirim_pair(folded, lines)
    if od is not None:
        out.odenen_toplam_tutar = od
        filled.add("odenen_toplam_tutar")
        out.debug_matches.append(("odenen_toplam_tutar", pair_dbg or "ödenen/yatırım çifti", od))
    if yg is not None:
        out.yatirim_getiriniz = yg
        filled.add("yatirim_getiriniz")
        out.debug_matches.append(("yatirim_getiriniz", pair_dbg or "ödenen/yatırım çifti", yg))

    dv, dsrc = _extract_devlet_katkisi_only_line(folded, lines)
    if dv is not None:
        out.devlet_katkisi = dv
        filled.add("devlet_katkisi")
        out.debug_matches.append(("devlet_katkisi", dsrc, dv))

    bk, bsrc = _extract_birikiminiz_two_row(folded, lines)
    if bk is not None:
        out.birikiminiz = bk
        filled.add("birikiminiz")
        out.debug_matches.append(("birikiminiz", bsrc, bk))

    # İkinci sütun bazen birikim tutarı; yatırım getirisi = birikim sanılırsa stopaj şişer.
    if (
        out.yatirim_getiriniz is not None
        and out.birikiminiz is not None
        and _near_same_money(out.yatirim_getiriniz, out.birikiminiz)
    ):
        filled.discard("yatirim_getiriniz")
        out.debug_matches = [m for m in out.debug_matches if m[0] != "yatirim_getiriniz"]
        io_fix = _find_label_line_index(folded, FIELD_PHRASES["odenen_toplam_tutar"])
        iy_fix = _find_label_line_index(folded, FIELD_PHRASES["yatirim_getiriniz"])
        bad_yg = out.yatirim_getiriniz
        out.yatirim_getiriniz = None
        val, src = _scan_money_after_phrase(
            folded, lines, FIELD_PHRASES["yatirim_getiriniz"], "yatirim_getiriniz"
        )
        if val is not None and not _near_same_money(val, out.birikiminiz):
            out.yatirim_getiriniz = val
            filled.add("yatirim_getiriniz")
            out.debug_matches.append(
                ("yatirim_getiriniz", f"düzeltme (≈birikim {bad_yg:g} elendi): {src[:72]}", val)
            )
        elif io_fix >= 0 and iy_fix >= 0:
            seq_fix = _money_amounts_below_odenen_yatirim_block(folded, lines, io_fix, iy_fix)
            od_ref = out.odenen_toplam_tutar
            picked: float | None = None
            for x in seq_fix:
                if _near_same_money(x, out.birikiminiz):
                    continue
                if od_ref is not None and _near_same_money(x, od_ref):
                    continue
                if x < out.birikiminiz * 0.999:
                    picked = x
                    break
            if picked is not None:
                out.yatirim_getiriniz = picked
                filled.add("yatirim_getiriniz")
                out.debug_matches.append(
                    (
                        "yatirim_getiriniz",
                        f"düzeltme blok sırası (birikim {bad_yg:g} atlandı)",
                        picked,
                    )
                )

    hy = _years_after_hak_edis_esas(folded, lines)
    if hy is not None:
        out.hak_edise_esas_sure = hy
        filled.add("hak_edise_esas_sure")
        out.debug_matches.append(("hak_edise_esas_sure", "hak edişe esas süre (yıl max)", hy))

    ho, hsrc = _oran_after_hak_edis(folded, lines)
    if ho is not None:
        out.hak_edis_oraniniz = ho
        filled.add("hak_edis_oraniniz")
        out.debug_matches.append(("hak_edis_oraniniz", hsrc, ho))

    ht, htsrc = _extract_hak_edis_tutari(folded, lines)
    if ht is not None:
        out.hak_edis_tutariniz = ht
        filled.add("hak_edis_tutariniz")
        out.debug_matches.append(("hak_edis_tutariniz", htsrc, ht))

    for fid in FIELD_ORDER:
        if fid in filled:
            continue
        phrases = FIELD_PHRASES[fid]
        kind = FIELD_KIND[fid]
        if kind == "money":
            val, src = _scan_money_after_phrase(folded, lines, phrases, fid)
            if val is not None:
                setattr(out, fid, val)
                filled.add(fid)
                out.debug_matches.append((fid, src, val))
        elif kind == "sure":
            for i in range(len(folded)):
                joint = folded[i] if i == 0 else ""
                for w in (1, 2, 3):
                    joint = " ".join(folded[i : i + w])
                    for ph in phrases:
                        fp = fold_tr_ascii(ph)
                        if fp not in joint:
                            continue
                        pos = joint.find(fp)
                        tail = joint[pos + len(fp) :]
                        v = first_scalar_in_text(tail)
                        if v is not None and 0 < v <= 80:
                            out.hak_edise_esas_sure = v
                            filled.add("hak_edise_esas_sure")
                            out.debug_matches.append((fid, " | ".join(lines[i : i + w]), v))
                            break
                    if fid in filled:
                        break
                if fid in filled:
                    break
        elif kind == "oran":
            for i in range(len(folded)):
                for ph in phrases:
                    fp = fold_tr_ascii(ph)
                    if fp not in folded[i]:
                        continue
                    pos = folded[i].find(fp)
                    tail = folded[i][pos + len(fp) :]
                    v = parse_oran_from_text(tail) or (
                        first_scalar_in_text(tail) if first_scalar_in_text(tail) is not None else None
                    )
                    if v is not None and 0 < v <= 100:
                        setattr(out, fid, v)
                        filled.add(fid)
                        out.debug_matches.append((fid, lines[i], v))
                        break
                if fid in filled:
                    break

    return out


def match_field(norm_line: str) -> str | None:
    folded = fold_tr_ascii(norm_line)
    best_len = 0
    best: str | None = None
    for field_id, phrases in FIELD_PHRASES.items():
        for ph in phrases:
            fp = fold_tr_ascii(ph)
            if fp in folded and len(fp) > best_len:
                best_len = len(fp)
                best = field_id
    return best


# ============================================================================
# bbox-aware extraction (2B uzamsal eşleme)
# ----------------------------------------------------------------------------
# OCR çıktısı yalnızca metin satırları olarak düşünüldüğünde kolonlu düzen
# (aynı satırda birden fazla etiket, altlarında değerler) yanlış eşleşir. EasyOCR
# zaten her kutu için bbox döndürüyor; bu koordinatları kullanarak «etiketin
# sağında aynı satırda» veya «altında aynı sütunda» en yakın uygun değeri seçiyoruz.
# ============================================================================


# Etiket eşlemesinde dışlanacak alt-dizgeler: aynı kelimeyi içerip BAŞKA alanı temsil
# eden başlıklar bu listeyle elenir.
#   - devlet_katkisi: "Yatırılan Devlet Katkısı" ve "Devlet Katkısı Getirisi" farklı
#     kalemlerdir; "Devlet Katkısı" ana toplamla karışmamalı. Ayrıca "Hak Edilen Devlet
#     Katkısı *" (hak ediş alanları) ve "Devlet Katkısı Hakediş Baz Tarihi" (tarih) de
#     devlet_katkisi tutarı değildir.
#   - birikiminiz:   "Toplam Birikiminiz" GERÇEK birikim olduğu için exclude DEĞİL —
#     bazı şirketlerde tek başlık o şekilde geçer. "devlet katkisi birikim" exclude'u
#     "Devlet Katkısı Birikimi/Birikiminiz" (devlet katkısı toplamı) kutusunu eler AMA
#     "Birikim Tutarı (Devlet Katkısı Hariç)" (gerçek birikim) kutusunu elemmez —
#     o folded metinde "devlet katkisi birikim" alt dizisi yoktur.
_FIELD_LABEL_EXCLUDE: dict[str, tuple[str, ...]] = {
    "devlet_katkisi": (
        "yatirilan devlet katkisi",
        "yatirilan devlet katkisi getirisi",
        "devlet katkisi getirisi",
        "hak edilen devlet katkisi",  # "Hak Edilen Devlet Katkısı Oranı/Tutarı" — hak ediş alanları
        "devlet katkisi hakedis",     # "Devlet Katkısı Hakediş Baz Tarihi" — tarih
    ),
    "birikiminiz": (
        "yatirilan",
        "devlet katkisi birikim",
    ),
}


@dataclass(frozen=True)
class _BBox:
    """OCR çıktısının geometri + metin temsili."""

    text: str
    folded: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    conf: float = 0.0

    @property
    def x_cen(self) -> float:
        return 0.5 * (self.x_min + self.x_max)

    @property
    def y_cen(self) -> float:
        return 0.5 * (self.y_min + self.y_max)

    @property
    def h(self) -> float:
        return self.y_max - self.y_min

    @property
    def w(self) -> float:
        return self.x_max - self.x_min


def _to_bbox(raw_bbox: Any, text: str, conf: float = 0.0) -> _BBox:
    xs = [float(p[0]) for p in raw_bbox]
    ys = [float(p[1]) for p in raw_bbox]
    folded = fold_tr_ascii(normalize_line(text))
    return _BBox(
        text=text,
        folded=folded,
        x_min=min(xs),
        x_max=max(xs),
        y_min=min(ys),
        y_max=max(ys),
        conf=float(conf),
    )


def boxes_from_ocr(raw: list[tuple[Any, str, float]]) -> list[_BBox]:
    """EasyOCR ham çıktısını (bbox, text, conf) iç _BBox listesine çevir."""
    out: list[_BBox] = []
    for item in raw:
        try:
            rb, txt, cf = item
        except (ValueError, TypeError):
            continue
        if not txt:
            continue
        out.append(_to_bbox(rb, txt, cf))
    return out


def _box_matches_phrase(box: _BBox, phrase: str) -> bool:
    fp = fold_tr_ascii(phrase)
    return fp in box.folded


def _box_is_any_label(box: _BBox) -> bool:
    """Bu kutu bilinen herhangi bir alan etiketini içeriyor mu?"""
    for phrases in FIELD_PHRASES.values():
        for ph in phrases:
            if _box_matches_phrase(box, ph):
                return True
    return False


def _union_bbox(a: _BBox, b: _BBox) -> _BBox:
    """İki kutunun birleşik (union) bbox'ı — çok satıra bölünmüş etiketleri tek kutu gibi
    temsil etmek için. text/folded boşlukla birleşir, geometri union'lanır."""
    return _BBox(
        text=a.text + " " + b.text,
        folded=a.folded + " " + b.folded,
        x_min=min(a.x_min, b.x_min),
        x_max=max(a.x_max, b.x_max),
        y_min=min(a.y_min, b.y_min),
        y_max=max(a.y_max, b.y_max),
        conf=min(a.conf, b.conf),
    )


def _find_label_box(
    boxes: list[_BBox],
    phrases: tuple[str, ...],
    exclude_substrings: tuple[str, ...] = (),
) -> _BBox | None:
    """En iyi etiket kutusunu bul.

    Tercih:
    1. En uzun eşleşen ifade (daha spesifik)
    2. Eşit uzunlukta → metin fazlalığı en az olan (daha «temiz etiket» görünen) kutu

    Çok satıra bölünmüş etiketler (örn. "Hak Edilen Devlet" + "Katkısı Oranı*" iki ayrı
    OCR kutusu) için dikey komşu 2–3 kutu birleştirilip union bbox olarak da denenir.
    Dönen kutu union bbox olduğunda spatial value detection doğru y-aralığını görür.
    """
    ex_folded = tuple(fold_tr_ascii(x) for x in exclude_substrings)
    best: _BBox | None = None
    best_key: tuple[int, int] = (-1, 10**9)

    def _consider(cand: _BBox) -> None:
        nonlocal best, best_key
        if any(ex in cand.folded for ex in ex_folded):
            return
        for ph in phrases:
            fp = fold_tr_ascii(ph)
            if fp not in cand.folded:
                continue
            extra = len(cand.folded) - len(fp)
            key = (len(fp), -extra)  # uzun ifade + az fazlalık
            if key > best_key:
                best_key = key
                best = cand

    # 1) Tek kutu
    for box in boxes:
        _consider(box)

    # 2) Dikey komşu birleşimler (base + en fazla 2 satır) — çok satıra bölünmüş
    #    etiketler. Sıralı komşuya GÜVENMEYİZ: değer kutuları (sağ sütun) OCR
    #    sıralamasında etiket satırlarının arasına girer. Her kutu için "hemen altında
    #    + x-örtüşen + en yakın" kutuyu zincirleyerek bul.
    for base in boxes:
        acc = base
        joined_ids = {id(base)}
        for _ in range(2):
            nxt: _BBox | None = None
            nxt_gap = 1e18
            for nb in boxes:
                if id(nb) in joined_ids:
                    continue
                x_ov = max(0.0, min(acc.x_max, nb.x_max) - max(acc.x_min, nb.x_min))
                if x_ov <= 0:
                    continue
                y_gap = nb.y_min - acc.y_max
                if y_gap < -0.3 * max(acc.h, 1.0) or y_gap > 1.5 * max(acc.h, nb.h, 1.0):
                    continue
                if y_gap < nxt_gap:
                    nxt = nb
                    nxt_gap = y_gap
            if nxt is None:
                break
            acc = _union_bbox(acc, nxt)
            joined_ids.add(id(nxt))
            _consider(acc)

    return best


def _vertical_overlap(a: _BBox, b: _BBox) -> float:
    return max(0.0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min))


def _horizontal_overlap(a: _BBox, b: _BBox) -> float:
    return max(0.0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min))


_CURRENCY_SUFFIX_RE = re.compile(r"(?:TL|TRY|₺)", re.IGNORECASE)
_TR_DECIMAL_RE = re.compile(r"\d,\d{1,2}(?!\d)")  # 1234,56 — virgül ondalık (max 2 hane)
_TR_THOUSANDS_RE = re.compile(r"\d{1,3}\.\d{3}(?!\d)")  # nokta binlik en az bir grup


def _looks_like_currency(text: str) -> bool:
    """BES ekran tutarı gibi mi? TL/₺/TRY suffix, virgül-ondalık, veya nokta-binlik formatı."""
    if _CURRENCY_SUFFIX_RE.search(text):
        return True
    if _TR_DECIMAL_RE.search(text):
        return True
    if _TR_THOUSANDS_RE.search(text):
        return True
    return False


def _parse_money(text: str) -> float | None:
    # «%80,2» gibi yüzdelik gürültüyü ele: % içerirse para değildir
    if "%" in text:
        return None
    v = first_amount_in_text(text)
    if v is None:
        return None
    # Düz rakam dizileri («Sözleşme No: 15485747» gibi) para sayılmaz — gerçek bir
    # BES tutarı her zaman TL suffix'i veya Türkçe ondalık/binlik formatı taşır.
    if not _looks_like_currency(text):
        return None
    # v < 1 genelde OCR gürültüsü; AMA açık TL/₺/TRY suffix'li "0,00 TL" geçerli bir
    # tutardır (yeni sözleşmede "Hak Edilen Devlet Katkısı Tutarı: 0,00 TL"). Suffix
    # yoksa küçük değer ele.
    if v < 1 and not _CURRENCY_SUFFIX_RE.search(text):
        return None
    return v


def _parse_sure(text: str) -> float | None:
    """'14 yıl', '1 yıl', ' 5' gibi: yıl birimi varsa al; tek sayılar için 0<v<=80."""
    # Önce «... yıl» araması
    for m in re.finditer(r"(\d{1,2})\s*(?:\.?\s*)?(?:yil|yıl)\b", text, re.IGNORECASE):
        y = float(m.group(1))
        if 1 <= y <= 80:
            return y
    # Yıl kelimesi yok → sadece tamsayı/ondalık (tek başına kutuda olabilir)
    stripped = text.strip()
    # Yalnızca sayı gibi görünüyorsa (max 3 karakter, %/TL içermiyor)
    if re.fullmatch(r"\d{1,2}(?:[.,]\d{1,2})?", stripped):
        try:
            v = float(stripped.replace(",", "."))
        except ValueError:
            return None
        if 1 <= v <= 80:
            return v
    return None


def _parse_oran(text: str) -> float | None:
    v = parse_oran_from_text(text)
    if v is not None:
        return v
    stripped = text.strip().replace(" ", "")
    # "%0" / "%0.00" / "%0,00" / "0%" — tamamen sıfır oran (yeni sözleşmede hak ediş %0).
    # parse_oran_from_text sıfırı reddediyor (0 < v kontrolü); açık tamamen-sıfır kalıbını
    # burada ele al. "%0,5" gibi sıfırdan büyük değerler bu fullmatch'e takılmaz.
    if re.fullmatch(r"%?0+(?:[.,]0+)?%?", stripped):
        return 0.0
    # "%60" olmadan "60" da olabilir; sadece sayıysa ve 0<v<=100 ise al
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{1,4})?", stripped):
        try:
            v2 = float(stripped.replace(",", "."))
        except ValueError:
            return None
        if 0 < v2 <= 100:
            return v2
    return None


_VALUE_PARSERS: dict[Kind, Any] = {
    "money": _parse_money,
    "sure": _parse_sure,
    "oran": _parse_oran,
}


def _spatial_candidates(
    label: _BBox,
    boxes: list[_BBox],
    value_fn: Any,
    *,
    exclude_label_boxes: bool,
) -> list[tuple[int, float, float, _BBox]]:
    """Etiket için uzamsal olarak uygun değer kutularını döndür.

    Dönen tuple: (öncelik, mesafe, parsed_value, kutu). Öncelik:
        0 — sağında aynı satır (Y çakışması yüksek, sağda)
        1 — altında aynı sütun (X merkezleri yakın veya X çakışması var)
    """
    h = max(label.h, 1.0)
    w = max(label.w, 1.0)
    out: list[tuple[int, float, float, _BBox]] = []
    for b in boxes:
        if b is label:
            continue
        if exclude_label_boxes and _box_is_any_label(b):
            continue
        v = value_fn(b.text)
        if v is None:
            continue

        y_ov = _vertical_overlap(label, b)
        x_ov = _horizontal_overlap(label, b)
        # Aynı satır: yüksek Y örtüşmesi + değer etiketin sağında (x_max'ın yanında ya da
        # sonrasında; %10'luk örtüşme toleransı).
        same_row = (
            y_ov >= 0.5 * min(h, b.h)
            and b.x_min >= label.x_max - 0.1 * w
        )
        if same_row:
            dist = max(0.0, b.x_min - label.x_max)
            # Aşırı sağa uzayan kutular etiketle ilgili olmayabilir
            if dist <= max(label.w * 6.0, 400.0):
                out.append((0, dist, v, b))
                continue

        # Altında aynı sütun: b.y_cen > label.y_cen + 0.5h ve X örtüşmesi var ya da
        # X merkezleri label.w'un içinde
        below = b.y_min >= label.y_cen
        if below:
            x_cen_dist = abs(b.x_cen - label.x_cen)
            x_aligned = x_ov > 0 or x_cen_dist < max(w, b.w) * 0.7
            if x_aligned:
                vert = b.y_min - label.y_max
                # Aşırı uzak (bir ekran yüksekliğinden fazla) kutular saymasın
                if vert <= max(h * 10.0, 300.0):
                    penalty = x_cen_dist * 0.2
                    out.append((1, vert + penalty, v, b))
    return out


def _pick_value(
    label: _BBox,
    boxes: list[_BBox],
    value_fn: Any,
    *,
    exclude_label_boxes: bool = True,
    used: set[int] | None = None,
) -> tuple[float | None, _BBox | None]:
    """En iyi uzamsal aday. ``used`` verilirse bu id'ler dışlanır."""
    cands = _spatial_candidates(label, boxes, value_fn, exclude_label_boxes=exclude_label_boxes)
    if used:
        cands = [c for c in cands if id(c[3]) not in used]
    if not cands:
        return None, None
    cands.sort(key=lambda x: (x[0], x[1]))
    _, _, v, b = cands[0]
    return v, b


_BES_GIRIS_PHRASES: tuple[str, ...] = (
    # Spesifik öncelikli (uzun phrase _find_label_box'ta tercih edilir).
    "bes giriş tarihi",
    "bes giris tarihi",
    # Garanti "Otomatik BES" varyantında etiket iki satıra bölünür ("Otomatik BES" +
    # "Giriş Tarihi" iki ayrı OCR kutusu) → tek başına "BES" içeren phrase yetmez.
    # "giriş tarihi" daha gevşek; "Emeklilik Tarihiniz" içermez (güvenli).
    "giriş tarihi",
    "giris tarihi",
    "bes giriş",
    "bes giris",
)
# DD/MM/YYYY veya DD.MM.YYYY veya DD-MM-YYYY (TR formatları). Yıl 1990–2100.
_DATE_DDMMYYYY_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")


def _parse_date_string(text: str) -> date | None:
    m = _DATE_DDMMYYYY_RE.search(text)
    if not m:
        return None
    try:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1990 <= y <= 2100:
            return date(y, mo, d)
    except (ValueError, OverflowError):
        pass
    return None


def _detect_date_near_label(boxes: list[_BBox], phrases: tuple[str, ...]) -> date | None:
    """Verilen etiket phrase'lerine en yakın DD/MM/YYYY tarihini bbox uzamsal yakınlıkla çıkar.

    Öncelik:
      0 — aynı satır sağda (en güçlü sinyal)
      1 — sağda ama dikey biraz kaymış — "Otomatik BES / Giriş Tarihi" gibi 2 satıra
          bölünmüş etiketler. Tarih genelde ilk satıra hizalı, eşleşen label kutusu (alt
          satır) ile aynı row'da olmaz. ±2 label height tolerans; uzaktaki tarihler
          ("Emeklilik Tarihiniz" 3-4h aşağıda) karışmaz.
      2 — altında aynı sütun
    """
    label = _find_label_box(boxes, phrases)
    if label is None:
        return None
    # Inline (etiket kutusunun kendi metni içinde tarih varsa)
    inline = _parse_date_string(label.text)
    if inline is not None:
        return inline
    h = max(label.h, 1.0)
    w = max(label.w, 1.0)
    best_score: tuple[int, float] | None = None
    best_date: date | None = None
    for b in boxes:
        if b is label:
            continue
        d_obj = _parse_date_string(b.text)
        if d_obj is None:
            continue
        y_ov = _vertical_overlap(label, b)
        x_ov = _horizontal_overlap(label, b)
        right_of_label = b.x_min >= label.x_max - 0.1 * w
        if y_ov >= 0.5 * min(h, b.h) and right_of_label:
            score = (0, max(0.0, b.x_min - label.x_max))
        elif right_of_label and abs(b.y_cen - label.y_cen) <= 2.0 * h:
            score = (1, abs(b.y_cen - label.y_cen))
        else:
            below = b.y_min >= label.y_cen
            x_aligned = x_ov > 0 or abs(b.x_cen - label.x_cen) < max(w, b.w) * 0.7
            if not (below and x_aligned):
                continue
            score = (2, b.y_min - label.y_max)
        if best_score is None or score < best_score:
            best_score = score
            best_date = d_obj
    return best_date


def _detect_bes_giris_tarihi(boxes: list[_BBox]) -> date | None:
    """«BES Giriş Tarihi» — BES sistemine İLK giriş tarihi (sözleşme başlangıcı DEĞİL).

    Garanti mobil kompakt ve "Otomatik BES" ekranlarında görünür. DİKKAT: stopaj/hak ediş
    sözleşme bazlı hesaplanır — bu tarih sözleşme başlangıcına eşit DEĞİLSE (kullanıcı eski
    BES üyesi ama yeni sözleşme açmışsa) yanlış süre verir. App tarafında
    `sozlesme_baslangic_tarihi` varsa ona öncelik verilir; bu yalnızca yedek.
    """
    return _detect_date_near_label(boxes, _BES_GIRIS_PHRASES)


# Sözleşme başlangıç tarihi — Garanti teklif/sözleşme detayı ekranında birkaç eşdeğer
# etiketle gösterilir. Öncelik: Yürürlük > Hakediş Baz > Teklif Başlangıç. Pratikte
# üçü de aynı tarih; biri OCR'da bölünüp okunamazsa diğeri yedek olur.
_YURURLUK_PHRASES: tuple[str, ...] = (
    "yürürlük tarihi",
    "yururluk tarihi",
    "yürürlük",
    "yururluk",
)
_HAKEDIS_BAZ_PHRASES: tuple[str, ...] = (
    "devlet katkısı hakediş baz tarihi",
    "devlet katkisi hakedis baz tarihi",
    "hakediş baz tarihi",
    "hakedis baz tarihi",
    "hakediş baz",
    "hakedis baz",
)
_TEKLIF_BASLANGIC_PHRASES: tuple[str, ...] = (
    "teklif başlangıç tarihi",
    "teklif baslangic tarihi",
    "teklif başlangıç",
    "teklif baslangic",
)


def _detect_sozlesme_baslangic_tarihi(boxes: list[_BBox]) -> date | None:
    """Sözleşme başlangıç tarihi — stopaj/hak ediş süresi için DOĞRU kaynak.

    "BES Giriş Tarihi" (sistem giriş) yerine bunu kullanmak gerekir: aynı kişi 2009'da
    BES'e girip 2026'da yeni bir sözleşme açmış olabilir; stopaj ve hak ediş kademeleri
    sözleşme bazlıdır. Öncelik sırası: Yürürlük Tarihi > Devlet Katkısı Hakediş Baz
    Tarihi > Teklif Başlangıç Tarihi (üçü genelde aynı; biri okunamazsa diğeri yedek).
    """
    for phrases in (_YURURLUK_PHRASES, _HAKEDIS_BAZ_PHRASES, _TEKLIF_BASLANGIC_PHRASES):
        d = _detect_date_near_label(boxes, phrases)
        if d is not None:
            return d
    return None


_GIRIS_LABEL_RE = re.compile(r"^\s*(?:GİRİŞ|GIRIS|giriş|giris)\s*$", re.IGNORECASE)
_GIRIS_INLINE_RE = re.compile(
    r"\b(20\d{2})\s*(?:GİRİŞ|giriş|GIRIS|giris)\b|"
    r"(?:GİRİŞ|giriş|GIRIS|giris)\s*[:\-]?\s*(20\d{2})\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _detect_giris_yili(boxes: list[_BBox]) -> int | None:
    """Gauge altındaki «YYYY GİRİŞ» etiketinden giriş yılını çıkar.

    İki yol:
    1. Aynı kutuda «2023 GİRİŞ» veya «GİRİŞ 2023» varsa direkt al.
    2. Ayrı kutularda — «GİRİŞ» etiketi + üstünde/yanında 4 haneli yıl kutusu varsa
       en yakın olanı al (aynı kolon).
    """
    # Inline
    for b in boxes:
        m = _GIRIS_INLINE_RE.search(b.text)
        if m:
            yil = int(m.group(1) or m.group(2))
            if 2000 <= yil <= 2100:
                return yil

    # Spatial: GİRİŞ label + nearby year box
    for label in boxes:
        if not _GIRIS_LABEL_RE.search(label.text.strip()):
            continue
        candidates: list[tuple[float, int]] = []
        for b in boxes:
            if b is label:
                continue
            m = _YEAR_RE.search(b.text)
            if not m:
                continue
            yil = int(m.group(1))
            if not 2000 <= yil <= 2100:
                continue
            x_overlap = max(0.0, min(b.x_max, label.x_max) - max(b.x_min, label.x_min))
            x_cen_dist = abs(b.x_cen - label.x_cen)
            if not (x_overlap > 0 or x_cen_dist < max(label.w, b.w) * 1.5):
                continue
            dist = abs(b.y_cen - label.y_cen)
            if dist > max(label.h, b.h) * 8:
                continue
            candidates.append((dist, yil))
        if candidates:
            candidates.sort()
            return candidates[0][1]
    return None


def extract_from_ocr_boxes(raw: list[tuple[Any, str, float]]) -> BesExtracted:
    """bbox-aware ana giriş noktası.

    `raw` EasyOCR ham çıktısıdır: her eleman (bbox, text, conf) biçiminde.
    `extract_from_ocr_lines`'tan farkı: etiket→değer eşlemesi 2B yakınlıkla kurulur;
    OCR satır sırasının kolonlu düzende bozduğu durumları tolere eder.
    """
    # Boş/uyumsuz giriş: satır tabanlı parse'a düşür (eşdeğer davranış).
    boxes = boxes_from_ocr(raw)
    lines_fallback = [b.text for b in boxes]
    if not boxes:
        return BesExtracted()

    out = BesExtracted(raw_lines=lines_fallback)
    filled: set[str] = set()
    used_value_boxes: set[int] = set()  # aynı kutu iki alana atanmasın

    # Alan sırası: önce daha spesifik/etiketleri net olanlar
    order: tuple[str, ...] = (
        "odenen_toplam_tutar",
        "yatirim_getiriniz",
        "birikiminiz",
        "devlet_katkisi",
        "hak_edis_tutariniz",
        "hak_edise_esas_sure",
        "hak_edis_oraniniz",
    )

    for fid in order:
        phrases = FIELD_PHRASES[fid]
        kind = FIELD_KIND[fid]
        value_fn = _VALUE_PARSERS[kind]
        exclude = _FIELD_LABEL_EXCLUDE.get(fid, ())

        label = _find_label_box(boxes, phrases, exclude_substrings=exclude)
        if label is None:
            continue

        # 1) Aynı kutu içinde etiketin sonrası ("Birikiminiz 62.500,00" gibi tek kutu)
        same_box_val: float | None = None
        for ph in phrases:
            fp = fold_tr_ascii(ph)
            pos = label.folded.find(fp)
            if pos >= 0:
                tail = label.text[pos + len(fp) :] if pos + len(fp) <= len(label.text) else ""
                if not tail:
                    # folded versiyonda ara
                    tail = label.folded[pos + len(fp) :]
                cand = value_fn(tail)
                if cand is not None:
                    same_box_val = cand
                    break

        val: float | None = same_box_val
        src_box: _BBox | None = None if same_box_val is None else label

        if val is None:
            val, src_box = _pick_value(
                label, boxes, value_fn, exclude_label_boxes=True, used=used_value_boxes
            )

        if val is None:
            continue

        setattr(out, fid, val)
        filled.add(fid)
        src_text = (src_box.text if src_box is not None else label.text)
        out.debug_matches.append((fid, f"{label.text} → {src_text}", val))
        if src_box is not None and src_box is not label:
            used_value_boxes.add(id(src_box))

    # Düzeltme: yatirim_getiriniz birikim ile eşit bulunduysa (OCR ikinci sütunu
    # yanlış seçmişse) alan iptal edilir. Bilinçli olarak temizliyoruz, bu yüzden
    # fallback'in üzerine yazmaması için filled'da bırakıyoruz.
    if (
        out.yatirim_getiriniz is not None
        and out.birikiminiz is not None
        and _near_same_money(out.yatirim_getiriniz, out.birikiminiz)
    ):
        out.yatirim_getiriniz = None
        # filled'dan çıkarmıyoruz — "explicitly cleared" olarak işaretli kalsın
        out.debug_matches = [
            m for m in out.debug_matches if m[0] != "yatirim_getiriniz"
        ]
        out.debug_matches.append(
            ("yatirim_getiriniz", "[iptal: birikim ile eşit]", None)
        )

    # Tamamen bulunamamış alanlar için satır tabanlı parse'a düş
    missing = [f for f in FIELD_ORDER if f not in filled]
    if missing:
        fallback = extract_from_ocr_lines(lines_fallback)
        for f in missing:
            v = getattr(fallback, f, None)
            if v is None:
                continue
            setattr(out, f, v)
            filled.add(f)
            out.debug_matches.append((f, f"[fallback satır parse]", v))

    # Sözleşme giriş yılı — gauge altındaki «YYYY GİRİŞ» etiketinden
    out.giris_yili = _detect_giris_yili(boxes)
    # BES Giriş Tarihi (sistem giriş) — giris_yili'na tercih edilir, ama
    # sozlesme_baslangic_tarihi'ndan SONRA gelir (app.py auto-derive zinciri).
    out.bes_giris_tarihi = _detect_bes_giris_tarihi(boxes)
    # Sözleşme başlangıç tarihi — stopaj/hak ediş için doğru kaynak, en yüksek öncelik.
    out.sozlesme_baslangic_tarihi = _detect_sozlesme_baslangic_tarihi(boxes)

    return out

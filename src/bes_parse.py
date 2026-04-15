"""BES ekran görüntüsü OCR metninden tutar çıkarma (Türkçe format).

Koç / benzeri ekranlarda etiketler üst üste, tutarlar altta iki satır halinde gelebiliyor;
tek satır / tek alt satır yeterli olmayabilir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["money", "sure", "oran"]

FIELD_PHRASES: dict[str, tuple[str, ...]] = {
    "odenen_toplam_tutar": (
        "ödenen toplam tutar",
        "odenen toplam tutar",
        "ödenen toplam",
        "odenen toplam",
    ),
    "hak_edise_esas_sure": (
        "hak edişe esas süre",
        "hak edise esas sure",
        "hak edişe esas",
        "hak edise esas",
    ),
    "hak_edis_oraniniz": (
        "hak ediş oranınız",
        "hak edis oraniniz",
        "hak ediş oranı",
        "hak edis orani",
    ),
    "hak_edis_tutariniz": (
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
    ),
    "devlet_katkisi": (
        "devlet katkısı",
        "devlet katkisi",
    ),
    "birikiminiz": (
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
            m2 = re.search(r"\b(\d{1,2})\s*$", line.strip())
            if m2 and 1 <= float(m2.group(1)) <= 50:
                years.append(float(m2.group(1)))
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

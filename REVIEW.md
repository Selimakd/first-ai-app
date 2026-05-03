# BES Çıkış Hesabı — Kod Review

_Tarih: 2026-04-23_

## TL;DR
- Çekirdek mantık (hesap + OCR ayrımı) sağlam.
- Streamlit Cloud sorununun büyük ihtimalle nedeni **EasyOCR + PyTorch'un ücretsiz katman RAM/disk limitlerini aşması**. Çözüm: torch'u CPU-only pinlemek veya OCR'ı isteğe bağlı yapmak.
- `bes_calc.py` içinde **%5 stopaj kademesi eksik** — emeklilik/vefat/maluliyet nedenli çıkışlar bu kademeye girer.
- OCR'daki oran regex'inde küçük bir "nokta ayraç" hatası var.
- Ufak tefek hijyen: venv repo içinde, test yok, FIELD_KEYWORDS dead code.

---

## 1. Streamlit Cloud uyumsuzluğu (ana sorun)

`requirements.txt` üzerinden çekilen `easyocr`, bağımlılık olarak **PyTorch** getiriyor. Streamlit Community Cloud ücretsiz katmanının limitleri:

| Kaynak | Limit | EasyOCR + torch + OpenCV ihtiyacı |
|---|---|---|
| RAM | ~1 GB | 700 MB–1.2 GB (başlangıç) |
| Disk | ~1 GB | torch (~500 MB) + model indirmesi (~150 MB) |
| Cold start | ~90 sn | EasyOCR model indirmesi + torch import aşabilir |

Ayrıca pip varsayılan olarak CUDA'lı torch çekmeye çalışabilir — cloud'da hem gereksiz hem yavaş.

**Önerilen `requirements.txt` (CPU-only torch ile):**

```
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.3.1+cpu
torchvision==0.18.1+cpu
easyocr>=1.7.0
streamlit>=1.28.0
Pillow>=10.0.0
numpy>=1.24.0,<2.0
opencv-python-headless>=4.8.0
```

**Daha kalıcı çözüm:** OCR'ı cloud sürümünde opsiyonel yap. `app.py` başında:

```python
try:
    from src.ocr_engine import read_text, sorted_lines
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
```

OCR butonunu `if OCR_AVAILABLE` ile kapsüle al. Cloud sürümünde EasyOCR yoksa kullanıcı sadece elle giriş + hesap görür, çökme olmaz.

**Alternatif hosting:** Hugging Face Spaces ücretsiz katmanı 16 GB RAM sunuyor; EasyOCR için çok daha uygun.

---

## 2. `src/bes_calc.py` — %5 stopaj kademesi eksik

Şu anki mantık iki kademeli:

```python
STOPAJ_ORANI_KISA = 0.15  # < 10 yıl
STOPAJ_ORANI_UZUN = 0.10  # ≥ 10 yıl
```

Türk BES mevzuatında **üç kademe** var (çıkış nedenine göre):

| Çıkış nedeni | Süre | Stopaj |
|---|---|---|
| Emeklilik, vefat, maluliyet | ≥ 10 yıl | **%5** |
| Diğer (cayma, 10 yıl sonra normal çıkış vs.) | ≥ 10 yıl | %10 |
| Hak kazanmadan çıkış | < 10 yıl | %15 |

Uygulamaya eklenmesi gereken:
- `stopaj_orani()` fonksiyonuna `cikis_nedeni: Literal["emeklilik_maluliyet_vefat", "diger"]` parametresi.
- `app.py` içinde sözleşme tipi radyosunun yanına "Çıkış nedeni" radyosu.

Örnek yama:

```python
def stopaj_orani(hak_edise_esas_sure_yil: float,
                 cikis_nedeni: str = "diger") -> float:
    if hak_edise_esas_sure_yil >= 10 and cikis_nedeni == "emeklilik_maluliyet_vefat":
        return 0.05
    if hak_edise_esas_sure_yil >= 10:
        return 0.10
    return 0.15
```

---

## 3. Formül çift hesap — tek kaynak prensibi

`app.py`'de iki yerde paralel stopaj hesaplanıyor:

- **Satır 192–193** (OCR sonrası özet):
  ```python
  oran_ocr = stopaj_orani(sy_ocr)
  sk_ocr = round(stopaj_kesintisi_tl(yg_ocr, sy_ocr), 2)
  ```
- **Satır 363** (ana hesap):
  ```python
  h = cikista_ele_gecen_tl(b, he_kullan, yg, sy, ...)
  ```

Her iki yerde de round aynı ama ileride `cikista_ele_gecen_tl`'i değiştirirsen OCR özeti eskimiş mantığı gösterir. OCR özetinde de `cikista_ele_gecen_tl`'in dönüş nesnesinden okumak iyi olur.

---

## 4. `src/bes_parse.py` — oran regex hatası

Satır 106–109:

```python
ORAN_PATTERN_NUM_FIRST = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{1,4})?|\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
```

Sorun: Python regex `|` operatöründe soldan sağa denenir ve ilk başarılı eşleşme alınır. "60.5%" metninde ilk alternatif `\d{1,3}(?:,\d{1,4})?` sadece `60`'ı yakalar ve `.5` atılır → yanlış oran.

Güvenli hâli:

```python
ORAN_PATTERN_NUM_FIRST = re.compile(
    r"(?P<num>\d{1,3}[.,]\d{1,4}|\d{1,3})\s*%",
    re.IGNORECASE,
)
```

BES ekranları genelde virgül kullandığı için pratikte tetiklenmemiş olabilir, ama riski sıfıra indirir.

---

## 5. Hijyen

- `venv/` klasörü repo içinde (Python 3.9 ve 3.14 ikilisiyle). `.gitignore`'a eklenmesi şart; repo kocaman olmuş.
- `tests/` yok. `bes_calc.py` saf fonksiyonlar, 10 dk'da `pytest` yazılır:
  ```python
  def test_stopaj_kisa(): assert stopaj_orani(5) == 0.15
  def test_stopaj_uzun(): assert stopaj_orani(10) == 0.10
  def test_cikis_net_katkisiz():
      h = cikista_ele_gecen_tl(100_000, 0, 20_000, 12, devlet_katkili_sozlesme=False)
      assert h.stopaj_kesintisi_tl == 2000
      assert h.cikista_net_tl == 98_000
  ```
- `bes_parse.py` satır 80: `FIELD_KEYWORDS = FIELD_PHRASES` — kullanılmıyor, dead code.
- `tr_amount_to_float` iyi yazılmış ama negatif değer kontrolü yok — BES ekranlarında pek çıkmaz ama "−123,45" gelirse `-` karakterini atıyor.

---

## 6. UI / mimari

- `app.py` 400 satır, tamamı modül seviyesinde prosedürel. `_render_fields()`, `_render_hesap()`, `_handle_ocr_run()` gibi 3-4 fonksiyona bölmek okunurluğu çok artırır.
- `use_container_width=True` bugün geçerli ama Streamlit `width="stretch"` API'sine geçiyor; sürüm yükseltmesinde uyarı görürsen bu yüzden.
- Session state temizleme bayrakları (`_do_clear_all` / `_do_clear_fields`) + `st.rerun()` deseni doğru.

---

## 7. İyi yanlar (unutulmasın)

- `stopaj_orani` / `stopaj_kesintisi_tl` / `cikista_ele_gecen_tl` ayrımı → test edilebilir, saf.
- `get_reader()` içinde `threading.Lock` ile singleton → rerun'da model tekrar yüklenmiyor, önemli.
- `_near_same_money` ile "yatırım getirisi = birikim" ikiz-okuma düzeltmesi akıllıca; stopaj şişmesini önlüyor.
- `infer_devlet_katkili_sozlesme` — satır başı regex ile yanlış pozitifleri engellemek doğru tasarım.
- Üç ayrı temizleme butonu son kullanıcı ergonomisi açısından çok iyi.

---

## Öncelik sırası

1. **`bes_calc.py`'ye %5 stopaj kademesini ekle** (doğruluk).
2. **`requirements.txt`'e CPU-only torch pinleme** veya OCR'ı opsiyonel yap (Streamlit Cloud).
3. **Oran regex düzeltmesi** (düşük olasılık ama kolay fix).
4. **`venv/` ignore + `.gitignore`**.
5. **`pytest` ile bes_calc testleri**.
6. (opsiyonel) `app.py`'yi fonksiyonlara böl.

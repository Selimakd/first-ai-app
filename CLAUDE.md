# BES Çıkış Hesaplama Uygulaması — Proje Rehberi

## Ne yapar

Streamlit web uygulaması: BES (Bireysel Emeklilik Sistemi) sözleşme detay ekran
görüntülerini OCR'lar, **çıkışta ele geçen net tutarı** hesaplar (stopaj kesintisi
dahil). Devlet katkılı + katkısız iki sözleşme tipi destekli.

OCR yereldir (EasyOCR, ücretsiz). Veriler kullanıcının makinesinden çıkmaz.

## Çalıştırma

```bash
./run.sh
# veya: source venv/bin/activate && streamlit run app.py
# Tarayıcı: http://localhost:8501
```

`start_streamlit.command` Finder'dan çift-tık ile başlatır (macOS).

## Test koşusu

```bash
venv/bin/python -m pytest -v           # Hızlı unit testler
venv/bin/python -m pytest -v -m slow   # E2E ekran görüntüsü testleri (slow, EasyOCR gerekir)
```

Yeni e2e fixture eklemek için: `tests/fixtures/screenshots/README.md`'yi oku.

## Repo yapısı

```
src/
├── bes_parse.py     # OCR çıktısı → BesExtracted (alanlar). bbox-aware + line fallback.
├── bes_calc.py      # Stopaj, hak ediş kademeleri, çıkış formülü.
├── bes_pipeline.py  # Kanal-bağımsız parse+türetme+hesap zinciri (run_pipeline).
└── ocr_engine.py    # EasyOCR wrapper. Lazy reader cache. Görüntü uzun-kenar kısma.

tests/
├── test_bes_calc.py           # Stopaj + hak ediş oran tabloları (saf testler)
├── test_bes_parse_helpers.py  # Sayı parse, fold_tr_ascii, vb.
├── test_bes_parse_extract.py  # extract_from_ocr_lines (eski) sentetik testler
├── test_bes_parse_boxes.py    # extract_from_ocr_boxes (yeni) sentetik bbox testler
├── test_bes_pipeline.py       # run_pipeline (kanal-bağımsız çekirdek) testleri
├── test_ocr_engine.py         # ocr_target_size (görüntü boyutlandırma) testleri
├── test_api.py                # api.py — metin biçimleme, routing, auth (+ slow e2e)
└── test_e2e_screenshots.py    # Fixture görüntülerle uçtan uca (slow)

tools/
├── run_tests.sh                  # Hızlı + slow ardışık koşum
├── manual_bbox_test.py           # Senaryo 2 bbox simülasyonu
├── test_garanti_*.py             # Garanti senaryo simülasyonları
└── ...

docs/
└── ios-kisayol.md   # iOS Kısayol kanalı kurulumu (API Space + Shortcut adımları).

app.py             # Streamlit UI (web kanalı). OCR akışı, auto-derive, sözleşme tipi.
api.py             # FastAPI (API kanalı — iOS Kısayol). POST /hesapla → run_pipeline.
start.sh           # APP_MODE'a göre streamlit (web) veya uvicorn (api) başlatır.
run.sh             # HOME'u proje içine yönlendiren launcher (sandbox uyumlu).
start_streamlit.command  # Finder çift-tık launcher.
```

## Kanallar (web + API, ortak çekirdek)

Web arayüzü (`app.py`/Streamlit) ve API (`api.py`/FastAPI) **aynı `src/` çekirdeğini**
paylaşır. `bes_pipeline.run_pipeline` OCR ham çıktısından tam hesaba kadar olan
zinciri kapsar (parse → birikim/getiri türetme → süre türetme → sözleşme tipi →
hak ediş → hesap) — Streamlit/session_state bağımsız.

Tek git repo iki HF Space'i besler: `start.sh` `APP_MODE` env değişkenine bakar
(`api` → uvicorn, diğer/unset → streamlit). API Space'inde `APP_MODE=api` Space
variable set edilir. Web Space dokunulmaz.

NOT: `app.py` şu an kendi inline auto-derive kopyasını korur (web arayüzü güvenliği
için); `bes_pipeline` ile aynı semantiği uygular, regression testleri kilitler.
İleride app.py de pipeline'a refactor edilebilir.

## Mimari kararlar

### Bbox-aware parsing (ana yol)

`extract_from_ocr_boxes(raw_ocr_tuples)` — EasyOCR'ın `(bbox, text, conf)` ham
çıktısını alır, **her etiket için en yakın değer kutusunu uzamsal yakınlıkla** bulur:
1. Önce sağında aynı satır (Y çakışması yüksek)
2. Yoksa altında aynı sütun (X merkezi yakın)

`extract_from_ocr_lines(lines)` — eski düz satır parser'ı, fallback olarak korunur
(bbox bulamadığı alanlar için).

Multi-upload akışında her dosyanın bbox Y koordinatı `Y_PAD_BETWEEN_FILES` ile
offsetlenir → tek tall image gibi parse edilir.

### Auto-derive zinciri (app.py)

OCR sonrası şu mantık devreye girer:
1. **Birikim** boşsa, ödenen + yatırım getirisi varsa → topla. ("Birikim = Ödenen + Getiri" BES kimliği)
2. **Süre** boşsa, gauge'tan `YYYY GİRİŞ` parse edildiyse → `current_year - giris_yili - 1` (conservative tıraş, kademe sınırları için).
3. **Hak ediş oranı** boşsa, devlet katkısı + süre varsa → EGM kademe tablosu (3y/6y/10y → %15/%35/%60).
4. **Hak ediş tutarı** boşsa, devlet katkısı × oran → türet.

Her türetme bir info notu basıyor. Kullanıcı widget'ta override edebilir.

### Sözleşme tipi auto-detect

Checkbox varsayılan açık. Parser `devlet_katkisi` alanını tutarıyla bulduysa →
otomatik "devlet katkılı" radio. Aksi halde "devlet katkısız".

### EGM hak ediş kademeleri (yaş şartı yok)

```
< 3 yıl  → %0
3-6 yıl  → %15
6-10 yıl → %35
≥ 10 yıl → %60
```

Mevzuat: 4632 sayılı Kanun Ek Madde 1 + Devlet Katkısı Yönetmeliği.

## Coding conventions

- Türkçe yorum, Türkçe değişken adları (alan adları), İngilizce fonksiyon adları.
- Dataclass'lar `frozen=True` (immutable).
- `from __future__ import annotations` her dosyada.
- Para alanları her zaman currency-format zorunlu (`_looks_like_currency`).
- Yüzdelik içeren text para olarak parse edilmez.
- Streamlit widget'larına yazma BÜTÜN widget'lar render edilmeden ÖNCE yapılır.

## Geliştirme akışı

1. Yeni şirket / yeni ekran tipi: önce sentetik bbox simülasyonu (`tools/test_*.py`).
2. Parser değişimi → unit test (`tests/test_bes_parse_boxes.py`'a regression).
3. UI değişimi → app.py + manuel tarayıcı testi (Streamlit hot-reload destekler).
4. Streamlit restart sadece import değişimlerinden sonra şart.

## Sandbox / Cursor notları

- `~/.streamlit` yazımı kısıtlı sandbox'ta `run.sh` HOME'u proje içine taşır.
- Python 3.14 venv (Apple Silicon homebrew). Linux sandbox ile binary uyumsuz.

## Açık iş listesi → bkz `TODO.md`

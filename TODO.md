# Açık İş Listesi

Cowork modunda yapılanların ardından kalanlar. Öncelik sırasıyla:

## Yüksek öncelik

### 1. Web deployment
Streamlit Cloud free tier'a EasyOCR fitmiyor (1GB RAM). 3 yol:
- **Tailscale + Mac always-on** — özel, ücretsiz, basit
- **HF Spaces** + parola gate — public URL, Mac kapalıyken çalışır
- **Streamlit Cloud** + dış OCR API (Google Vision, ücretsiz tier) — refactor gerekir

İlgili dosya: `REVIEW.md`.

## Orta öncelik

### 2. Diğer şirket varyasyonları
Şu an Garanti web + mobil + 2 katkılı senaryo destekli. Test edilmemiş:
Anadolu Hayat, Allianz, Ziraat, AvivaSA, Aegon, vb. Her şirketin etiket
sözcüğü + layout farklı; `FIELD_PHRASES`'e yeni sinonimler + bbox toleransı.

Yeni şirket eklemek için akış:
1. Kullanıcıdan ekran görüntüsü al
2. `tools/test_<sirket>_*.py` ile sentetik bbox simülasyonu
3. Eksik phrase'leri `FIELD_PHRASES`'e ekle
4. Test geçince `tests/fixtures/screenshots/senaryo_<sirket>_*/` altına PNG + `beklenen.json`
5. Regression olarak `test_bes_parse_boxes.py`'a unit test ekle

### 3. Çıkış ledger / hesap geçmişi
Streamlit session_state geçici. Kullanıcı farklı sözleşmeleri / tarihleri
karşılaştırmak isteyebilir. Local SQLite'a geçmiş kaydı (kullanıcı opt-in).

### 4. PDF rapor üretimi
"Çıkış sonucunu PDF olarak kaydet" — kullanıcı muhasebeci / eşine paylaşmak
isteyebilir. ReportLab veya weasyprint.

### 5. Sözleşme başlangıç tarihi tam parse (gün/ay/yıl) — ertelendi
Şu an gauge'taki sadece YYYY okunuyor → süre tahmini yıl bazında, ±1 hata var.
Garanti'de muhtemelen başka bir ekranda tam tarih (`07.06.2023` gibi) görünür.
Onu OCR'la, `floor((bugün - başlangıç) / 365.25)` ile **kesin yıl** çıkar.

`bes_parse.py`'a `_detect_sozlesme_baslangic_tarihi(boxes)` ekle. App'te
`giris_yili` yerine bu kullanılabiliyorsa onu tercih et.

**Erteleme nedeni:** İkinci ekran görüntüsü gerektiriyor → kullanıcı pratikliği
düşüyor. Tek-screenshot akışı daha öncelikli.

## Düşük öncelik / temizlik

### 6. .gitignore
`venv/`, `__pycache__/`, `.streamlit_home/`, `*.pyc`, `.DS_Store` ekle.

### 7. ORAN_PATTERN_NUM_FIRST regex küçük bug
`(\d{1,3}(?:,\d{1,4})?|\d+(?:\.\d+)?)\s*%` — alternation sırası kötü. Bkz REVIEW.md.

### 8. Auto-detect "Yatırılan + Getirisi = Devlet Katkısı" identity check
Her devlet katkılı ekranda parser bu identity'yi cross-check edip mismatch'te uyarı verebilir
(OCR yanlışlığı tespiti).

### 9. Çoklu sözleşme desteği
Bir kullanıcının birden fazla BES sözleşmesi olabilir. Şu an tek sözleşme bazlı UI;
çoklu sözleşmeyi tab'lara ayırma fikri.

## Bilinen kısıtlar

- macOS Preview/Safari'den HEIC formatı şu an Streamlit uploader'da desteklenmez (PNG/JPG/WEBP).
- Mobil iOS native app screenshotları için tek-uzun-screenshot Apple desteklemez; user multi-upload veya stitching app kullanır.
- EasyOCR Türkçe modeli ilk koşumda ~150MB indirir. Sonra cache'lenir.
- Streamlit cache eski modülleri tutar — kod değişimi sonrası bazen restart şart (özellikle import değişimi).

## Tamamlananlar (Cowork modunda)

Detaylı task listesi 25+ task, ana başlıklar:
- pytest altyapısı + 90+ unit test
- Bbox-aware parser (`extract_from_ocr_boxes`) + regression testleri
- Multi-upload Y-offset bbox path
- Birikim auto-derive
- Hak ediş oranı + tutarı türetme (EGM kademe)
- Giriş yılı OCR + conservative süre tahmini
- Tek dosyada otomatik OCR
- Sözleşme tipi auto-detect (default açık)
- 2 senaryo fixture (senaryo_1_katkisiz web, senaryo_2_katkili web)
- Garanti web + mobil için phrase varyantları

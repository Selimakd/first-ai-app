# Açık İş Listesi

Cowork modunda yapılanların ardından kalanlar. Öncelik sırasıyla:

## Yüksek öncelik

### 1. Gauge needle / cyan-fill ile süre tespiti (görüntü analizi)
Bazı mobil layout'larda gauge altındaki "YYYY GİRİŞ" yazısı sığmıyor → bizim
mevcut süre auto-derive zinciri (CLAUDE.md #2) çalışmıyor → kullanıcı süreyi
elle girmek zorunda. Manuel akış artık çalışıyor (app.py'a hak ediş tutar/oran
manuel türetmesi eklendi) ama UX ideal değil.

Önerilen yaklaşım: **cyan-fill segment tespiti**.
1. OCR ile "3. YIL", "6. YIL", "10. YIL" text'lerinin pixel koordinatlarını al → gauge merkezi + yarıçapı
2. Her kademe segment'inin orta açısında pixel rengini sample'la
3. Cyan (~RGB 60,200,200) ise dolu, gri ise boş
4. En son dolu segment → süre kademesi (3y/6y/10y eşiklerine göre)

Yeni modül `src/gauge_detect.py`. Auto-derive zincirine #2'den önce eklenir.
Sentetik test fixture (3 kademe için PNG simülasyonu) + e2e regression. Tahmini
1-2 saat. Alternatif (needle açısı) daha hassas ama daha gürültülü, kademe yeterli.

### 2. Web deployment ✅ TAMAMLANDI
HF Spaces + Docker SDK ile deploy edildi. Parola gate (APP_PASSWORD secret).
URL: huggingface.co/spaces/Selimakd/bes-cikis. CPU Basic free tier yeterli.

## Orta öncelik

### 3. Diğer şirket varyasyonları
Şu an Garanti web + mobil + 2 katkılı senaryo destekli. Test edilmemiş:
Anadolu Hayat, Allianz, Ziraat, AvivaSA, Aegon, vb. Her şirketin etiket
sözcüğü + layout farklı; `FIELD_PHRASES`'e yeni sinonimler + bbox toleransı.

Yeni şirket eklemek için akış:
1. Kullanıcıdan ekran görüntüsü al
2. `tools/test_<sirket>_*.py` ile sentetik bbox simülasyonu
3. Eksik phrase'leri `FIELD_PHRASES`'e ekle
4. Test geçince `tests/fixtures/screenshots/senaryo_<sirket>_*/` altına PNG + `beklenen.json`
5. Regression olarak `test_bes_parse_boxes.py`'a unit test ekle

### 4. Çıkış ledger / hesap geçmişi
Streamlit session_state geçici. Kullanıcı farklı sözleşmeleri / tarihleri
karşılaştırmak isteyebilir. Local SQLite'a geçmiş kaydı (kullanıcı opt-in).

### 5. PDF rapor üretimi
"Çıkış sonucunu PDF olarak kaydet" — kullanıcı muhasebeci / eşine paylaşmak
isteyebilir. ReportLab veya weasyprint.

### 6. Sözleşme başlangıç tarihi tam parse (gün/ay/yıl) — ertelendi
Şu an gauge'taki sadece YYYY okunuyor → süre tahmini yıl bazında, ±1 hata var.
Garanti'de muhtemelen başka bir ekranda tam tarih (`07.06.2023` gibi) görünür.
Onu OCR'la, `floor((bugün - başlangıç) / 365.25)` ile **kesin yıl** çıkar.

`bes_parse.py`'a `_detect_sozlesme_baslangic_tarihi(boxes)` ekle. App'te
`giris_yili` yerine bu kullanılabiliyorsa onu tercih et.

**Erteleme nedeni:** İkinci ekran görüntüsü gerektiriyor → kullanıcı pratikliği
düşüyor. Tek-screenshot akışı daha öncelikli. Üstelik #1 (gauge tespiti)
çoğu durumu zaten kapatır.

## Düşük öncelik / temizlik

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

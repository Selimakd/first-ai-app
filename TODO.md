# Açık İş Listesi

Cowork modunda yapılanların ardından kalanlar. Öncelik sırasıyla:

## Yüksek öncelik

### 1. ⚠️ "BES Giriş Tarihi" yerine sözleşme başlangıç tarihi (DOĞRULUK BUG'I)
Mevcut parser Garanti mobil ekranındaki **"BES Giriş Tarihi"** alanını süre
kaynağı olarak kullanıyor — ama bu alan **BES sistemine ilk giriş tarihi**dir,
**sözleşme başlangıç tarihi** değildir. Stopaj kademe (%5/%10/%15) ve hak ediş
kademe (%0/%15/%35/%60) **sözleşme bazlı** hesaplanır → yanlış değer kullanmak
hesabı bozar.

**Örnek:** Kullanıcı 2009'da BES'e ilk girmiş ama 2026'da yeni bir sözleşme
açıp 2027'de çıkıyor. Doğru süre 1 yıl (sözleşmenin ömrü), bizim parser 17 yıl
(sistem giriş) der → stopaj %15 yerine %10, hak ediş %0 yerine %60 hesaplanır.
Devlet katkısının tamamı kayıp olması gerekirken hak edilmiş gibi görünür.

**Yapılacak:**
1. Garanti'nin diğer ekranlarında **sözleşme başlangıç tarihi** nerede gösteriliyor
   araştır (kullanıcı keşfedecek). Bilinen muhtemel ekranlar: "Sözleşme Detayı",
   "Plan Detayı", PDF olarak indirilebilen sözleşme özeti.
2. Parser'a `sozlesme_baslangic_tarihi` alanı ekle (yeni phrase: muhtemelen
   "sözleşme başlangıç tarihi", "sözleşme tarihi", "başlangıç tarihi" varyantları).
3. `BesExtracted.sozlesme_baslangic_tarihi` alanı (`bes_giris_tarihi`'na ek).
4. Auto-derive zinciri sırası:
   - `sozlesme_baslangic_tarihi` varsa: bunu kullan (en kesin)
   - `bes_giris_tarihi` varsa: kullan AMA UI'a uyarı: "Bu tarih BES sistem giriş
     tarihinizdir; eğer sonradan **yeni sözleşme** açtıysanız sözleşme başlangıç
     tarihini elle girin"
   - `giris_yili` (gauge) varsa: conservative tahmin (eski mantık)
5. `tests/test_bes_parse_boxes.py`'a regression: hem yeni alan parse, hem öncelik
   sırası.

**Not:** Bu, deployment'ı kullanan herkes için potansiyel yanlış hesaplama riski
demektir. Acil değil ama yüksek öncelik — kullanıcı araştırması bitince ele alalım.

### 2. Gauge needle / cyan-fill ile süre tespiti (görüntü analizi)
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

### 3. Web deployment ✅ TAMAMLANDI
HF Spaces + Docker SDK ile deploy edildi. Parola gate (APP_PASSWORD secret).
URL: huggingface.co/spaces/Selimakd/bes-cikis. CPU Basic free tier yeterli.

## Orta öncelik

### 4. Diğer şirket varyasyonları
Şu an Garanti web + mobil + 2 katkılı senaryo destekli. Test edilmemiş:
Anadolu Hayat, Allianz, Ziraat, AvivaSA, Aegon, vb. Her şirketin etiket
sözcüğü + layout farklı; `FIELD_PHRASES`'e yeni sinonimler + bbox toleransı.

Yeni şirket eklemek için akış:
1. Kullanıcıdan ekran görüntüsü al
2. `tools/test_<sirket>_*.py` ile sentetik bbox simülasyonu
3. Eksik phrase'leri `FIELD_PHRASES`'e ekle
4. Test geçince `tests/fixtures/screenshots/senaryo_<sirket>_*/` altına PNG + `beklenen.json`
5. Regression olarak `test_bes_parse_boxes.py`'a unit test ekle

### 5. Çıkış ledger / hesap geçmişi
Streamlit session_state geçici. Kullanıcı farklı sözleşmeleri / tarihleri
karşılaştırmak isteyebilir. Local SQLite'a geçmiş kaydı (kullanıcı opt-in).

### 6. PDF rapor üretimi
"Çıkış sonucunu PDF olarak kaydet" — kullanıcı muhasebeci / eşine paylaşmak
isteyebilir. ReportLab veya weasyprint.

### 7. Sözleşme başlangıç tarihi DD/MM/YYYY parse altyapısı ✅ TAMAMLANDI
Tarih regex + bbox-aware spatial detection eklendi. `_detect_bes_giris_tarihi`
`BesExtracted.bes_giris_tarihi` üretiyor. NOT: Şu an "BES Giriş Tarihi" alanını
parse ediyor — bunun sözleşme başlangıç tarihinin doğru kaynağı olmadığı #1'de
açıklandı; altyapı hazır, doğru kaynağa geçişe hazır.

## Düşük öncelik / temizlik

### 8. ORAN_PATTERN_NUM_FIRST regex küçük bug
`(\d{1,3}(?:,\d{1,4})?|\d+(?:\.\d+)?)\s*%` — alternation sırası kötü. Bkz REVIEW.md.

### 9. Auto-detect "Yatırılan + Getirisi = Devlet Katkısı" identity check
Her devlet katkılı ekranda parser bu identity'yi cross-check edip mismatch'te uyarı verebilir
(OCR yanlışlığı tespiti).

### 10. Çoklu sözleşme desteği
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

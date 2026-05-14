# iOS Kısayol kanalı — ekran görüntüsü paylaş, tutarı al

Web arayüzüne ek bir kanal: iPhone'da ekran görüntüsü → **Paylaş** → "BES Hesapla"
kısayolu → sonuç bildirimde. Uygulamadan çıkmadan, galeriye kaydetmeden, 2 dokunuş.

Mimari: `api.py` (FastAPI) `src/` çekirdeğini (`bes_parse` + `bes_pipeline` + `bes_calc`)
kullanır — web arayüzü (`app.py` / Streamlit) bundan tamamen bağımsız. İkisi ayrı HF
Space, **tek git repo** (`start.sh` `APP_MODE` ortam değişkenine göre kanal seçer).

---

## 1. API HF Space'i oluştur (tek seferlik)

1. https://huggingface.co/new-space
   - **Owner:** Selimakd
   - **Space name:** `bes-cikis-api`
   - **SDK:** Docker
   - **Template:** Blank
   - **Hardware:** CPU basic (free)
   - **Visibility:** Public
   - **Create Space**
2. Space → **Settings** → **Variables and secrets**:
   - **New variable** → Name: `APP_MODE`, Value: `api`  ← bu Space'i API moduna alır
   - **New secret** → Name: `APP_PASSWORD`, Value: `bes2026`  ← web arayüzüyle aynı parola
3. Repo'dan API Space'ine push (web Space dokunulmaz):
   ```bash
   git remote add hf-api https://huggingface.co/spaces/Selimakd/bes-cikis-api
   git push hf-api main
   ```
4. Space build edip uvicorn'u başlatır. API adresi:
   **`https://selimakd-bes-cikis-api.hf.space`**
   - Test: tarayıcıda `https://selimakd-bes-cikis-api.hf.space/health` → `ok` görmeli

---

## 2. iOS Kısayol'u oluştur (tek seferlik)

iPhone'da **Kısayollar** (Shortcuts) uygulaması:

1. Sağ üstte **+** → yeni kısayol
2. Üstteki ayarlar (ⓘ veya kısayol adına dokun):
   - Adı: **BES Hesapla**
   - **Paylaşım Sayfasında Göster** (Show in Share Sheet) → **açık**
   - **Paylaşım Sayfası Türleri** → sadece **Görüntüler** (Images) kalsın
3. Eylem ekle: **"URL İçeriğini Al"** (Get Contents of URL)
   - **URL:** `https://selimakd-bes-cikis-api.hf.space/hesapla`
   - **Yöntem (Method):** `POST`
   - **İstek Gövdesi (Request Body):** `Form`
   - **Form alanı ekle** →
     - Alan adı: `file` · Tür: **Dosya (File)** · Değer: **Kısayol Girdisi (Shortcut Input)**
   - **Form alanı ekle** →
     - Alan adı: `password` · Tür: **Metin (Text)** · Değer: `bes2026`
4. Eylem ekle: **"Bildirim Göster"** (Show Notification)
   - İçerik: **"URL İçeriğini Al"** sonucu (önceki adımın çıktısı)
   - (Alternatif: "Sonucu Göster" / Quick Look — daha uzun metni rahat okutur)
5. **Bitti** (Done)

---

## 3. Kullanım

1. BES ekran görüntüsünü al (Garanti mobil / web / teklif-sözleşme detayı — hepsi çalışır)
2. Ekran görüntüsü önizlemesine dokun → **Paylaş**
3. Listeden **BES Hesapla**'ya dokun
4. Birkaç saniye sonra bildirim: net çıkış tutarı + alanlar + notlar

İlk istek (Space uykudaysa) ~30-60 sn sürebilir — konteyner soğuk başlangıç + EasyOCR
model yükleme. Sonraki istekler hızlı. Kısayol'un timeout'u iOS'ta varsayılan olarak
yeterli; gerekirse "URL İçeriğini Al" altında artırılabilir.

---

## Notlar

- **Gizlilik:** Bu kanalda ekran görüntüsü API sunucusuna (HF Space) gider. Web arayüzü
  zaten HF'de çalıştığı için durum değişmiyor; yine de kanalı paylaştığın kişilere
  söyle.
- **Sadece iOS.** Android'de Paylaş menüsü mantığı farklı — Telegram bot kanalı (TODO,
  Faz 2) Android tanıdıklar için daha uygun.
- **Hata mesajları:** API tüm yanıtları 200 + düz metin döndürür (Kısayol dostu). Alan
  okunamazsa "Hesap yapılamadı — eksik alanlar: ..." şeklinde okunur bir mesaj gelir.
- **Web arayüzü etkilenmez:** `app.py` / Streamlit Space'i ayrı; bu kanal onu hiç
  değiştirmez.

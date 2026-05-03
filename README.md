---
title: BES Cikis Hesaplama
sdk: streamlit
sdk_version: 1.40.0
app_file: app.py
pinned: false
---

# BES Çıkış Hesaplama

BES (Bireysel Emeklilik Sistemi) sözleşme detay ekran görüntülerini OCR'lar,
çıkışta ele geçen net tutarı hesaplar (stopaj kesintisi dahil). Devlet katkılı
ve katkısız sözleşme tipi destekli.

OCR yereldir (EasyOCR, Türkçe + İngilizce). Veriler işlendiği container'dan
çıkmaz.

## Yerel çalıştırma

```bash
./run.sh
# veya: source venv/bin/activate && streamlit run app.py
# Tarayıcı: http://localhost:8501
```

Detaylı geliştirici rehberi: `CLAUDE.md`.

## Erişim

Bu Space parolayla korunur. HF Spaces "Settings → Repository secrets" altına
`APP_PASSWORD` adıyla parola girilir; uygulama açıldığında kullanıcıdan istenir.
Yerel geliştirmede `APP_PASSWORD` set edilmediği için parola sorulmaz.

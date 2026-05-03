# Ekran görüntüsü E2E test fixture'ları

Bu klasördeki her alt klasör **bir test senaryosu**. Her senaryo klasöründe iki dosya olur:

```
senaryo_adi/
├── ekran.png         ← Gerçek BES ekran görüntüsü (png/jpg/jpeg/webp)
└── beklenen.json     ← Beklenen alanlar ve hesap sonucu
```

## Yeni senaryo ekleme — 3 adım

1. Yeni bir alt klasör aç: `tests/fixtures/screenshots/ornek_sozlesme/`
2. Ekran görüntüsünü `ekran.png` adıyla içine koy.
3. `beklenen.json`'u aşağıdaki şablonla doldur.

## beklenen.json şablonu

```json
{
  "aciklama": "Kısa açıklama (hangi şirket, hangi tip sözleşme, süre vs.)",
  "upscale": 1.5,
  "sozlesme_tipi": "devlet_katkisiz",

  "beklenen_alanlar": {
    "birikiminiz":          null,
    "odenen_toplam_tutar":  null,
    "yatirim_getiriniz":    null,
    "devlet_katkisi":       null,
    "hak_edise_esas_sure":  null,
    "hak_edis_oraniniz":    null,
    "hak_edis_tutariniz":   null
  },

  "beklenen_hesap": {
    "uygulanan_stopaj_orani": null,
    "stopaj_kesintisi_tl":    null,
    "cikista_net_tl":         null
  }
}
```

### Alan açıklamaları

| Alan | Anlamı |
|---|---|
| `aciklama` | Yalnız okunur bilgi; test çıktısında görülür. |
| `upscale` | OCR'da kullanılacak büyütme oranı (1.0–2.5). Küçük yazılar için artır. |
| `sozlesme_tipi` | `"devlet_katkisiz"` veya `"devlet_katkili"` — hesap formülünü seçer. |
| `beklenen_alanlar` | OCR sonrası parse'ın bulması gereken değerler. Bilinmeyen alanları `null` bırak, test onları görmezden gelir. |
| `beklenen_hesap` | `cikista_ele_gecen_tl` sonucu. `null` alanlar atlanır. |

### Sayı formatı

JSON içinde **nokta ondalık ayraç**, **virgül binlik ayraç yok** — standart JSON sayıları:

```json
"birikiminiz": 62500.00
```

Türk formatında `62.500,00` **yazmayın** — JSON parse'ı kırar.

## Testleri çalıştırma

```bash
# Sadece hızlı unit testler (ekran testleri atlanır):
venv/bin/python -m pytest

# Ekran e2e testleri de dâhil (slow):
venv/bin/python -m pytest -m slow

# Sadece bir senaryoyu koşturmak:
venv/bin/python -m pytest -m slow -k senaryo_1_katkisiz
```

## Kırılan test ne yapmalı?

Test kırılırsa pytest çıktısında:
- Hangi alanın beklenen vs bulunan değerleri olduğunu görürsün.
- Ham OCR satırları basılır → "OCR mu yanlış okudu, parse mı yanlış eşledi" ayrımını yapabilirsin.

Bulgulara göre:
- **OCR yanlış okuyorsa:** `upscale` değerini artırmayı dene.
- **Parse yanlış eşliyorsa:** `src/bes_parse.py` içindeki heuristic'i düzelt, test yeşilleninceye kadar iterate et.
- **Beklenen değer yanlışsa:** `beklenen.json`'u güncelle.

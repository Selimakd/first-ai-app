#!/usr/bin/env bash
# HF Spaces / lokal launcher — APP_MODE ortam değişkenine göre kanal seçer.
#   APP_MODE=api  → uvicorn (BES hesap API; iOS Kısayol / ileride bot kanalı)
#   diğer / unset → streamlit (web arayüzü — mevcut davranış, DEĞİŞMEDİ)
#
# Tek git repo iki HF Space'i besler:
#   - Web Space:  APP_MODE set DEĞİL → Streamlit (eskisiyle birebir aynı komut)
#   - API Space:  APP_MODE=api (Space "Variables" panelinden) → uvicorn
# Her ikisi de 8501 portunda dinler → README.md `app_port: 8501` ikisi için de geçerli.
set -e

if [ "$APP_MODE" = "api" ]; then
    exec uvicorn api:app --host 0.0.0.0 --port 8501
else
    exec streamlit run app.py \
        --server.port=8501 \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --server.enableXsrfProtection=false
fi

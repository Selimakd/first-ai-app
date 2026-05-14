# HF Spaces Docker SDK ile Streamlit. python:3.10-slim + sistem libGL/glib (opencv için).
FROM python:3.10-slim

# Sistem bağımlılıkları (opencv-python-headless ve PIL için yeterli)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces non-root kullanıcı zorunlu — uid 1000 yaygın olarak destekleniyor.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_HOME=/home/user/.streamlit \
    EASYOCR_MODULE_PATH=/home/user/.EasyOCR

WORKDIR $HOME/app

# Önce requirements: layer cache'ini koru
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Uygulama kodu
COPY --chown=user . .

EXPOSE 8501

# start.sh APP_MODE'a göre kanal seçer:
#   APP_MODE unset → streamlit (web arayüzü; eski CMD ile birebir aynı komut)
#   APP_MODE=api   → uvicorn (BES hesap API; iOS Kısayol kanalı)
# Tek repo iki HF Space'i besler — API Space'inde APP_MODE=api Space variable set edilir.
CMD ["bash", "start.sh"]

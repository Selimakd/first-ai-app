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

# headless=true: tarayıcı otomatik açılmasın (container'da X yok)
# address=0.0.0.0: HF Spaces dışarıdan erişebilsin
# enableXsrfProtection=false: HF Spaces iframe wrap için gerekli olabilir
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableXsrfProtection=false"]

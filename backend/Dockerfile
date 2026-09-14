FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# OCR (Tesseract + rus/kaz/eng), PDF rasterization (poppler),
# PDF generation for archival forms (weasyprint: pango/cairo + cyrillic fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-kaz \
        tesseract-ocr-eng \
        poppler-utils \
        curl \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
        ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Приложение работает от непривилегированного пользователя: при компрометации
# процесса (обработка чужих файлов, распознавание, генерация PDF) права root
# в контейнере дали бы лишний рычаг для выхода за его пределы.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /home/app/.cache \
    && chown -R app:app /app /home/app
USER app
ENV HOME=/home/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

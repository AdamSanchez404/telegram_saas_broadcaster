FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создание папок для сохранения данных и сессий
RUN mkdir -p sessions data

VOLUME ["/app/sessions", "/app/data"]

CMD ["python", "main.py"]

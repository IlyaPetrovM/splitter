FROM python:3.11-alpine
COPY --from=mwader/static-ffmpeg:latest-amd64 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:latest-amd64 /ffprobe /usr/local/bin/

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/main.py .

VOLUME ["/shared_storage"]

# Запуск приложения как RabbitMQ consumer
CMD ["python", "main.py"]
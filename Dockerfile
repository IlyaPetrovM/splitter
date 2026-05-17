# Берем бинарник из проверенного образа

# Далее используйте ваш основной образ (python, node, alpine и т.д.)
FROM python:3.11-alpine
COPY --from=mwader/static-ffmpeg:latest-amd64 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:latest-amd64 /ffprobe /usr/local/bin/

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

VOLUME ["/shared_storage"]

EXPOSE 8081

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
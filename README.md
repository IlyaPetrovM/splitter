# Audio Splitter Service

FastAPI микросервис для нарезания аудио файлов на части без переперекодирования.

## Поддерживаемые форматы

- Аудио: mp3, wav, m4a, flac, ogg
- Видео (извлечение аудиодорожки): mp4, mkv, webm

## API

### POST /split

Нарезать аудио файл по длительности или количеству частей.

#### По файлу из хранилища

**По максимальной длительности:**
```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"filename": "audio.mp3", "max_duration": 60}'
```

**По количеству частей:**
```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"filename": "video.mp4", "split_parts": 4}'
```

#### По URL (скачивание во временную папку)

Файл будет автоматически скачан во временную папку, обработан и удален после завершения.

```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/audio.mp3", "split_parts": 4}'
```

**Response:**
```json
{
  "files": [
    "/shared_storage/splitted/audio.mp3/audio.mp3__part__0__30.mp3",
    "/shared_storage/splitted/audio.mp3/audio.mp3__part__30__60.mp3"
  ],
  "download_urls": [
    "/download/shared_storage/splitted/audio.mp3/audio.mp3__part__0__30.mp3",
    "/download/shared_storage/splitted/audio.mp3/audio.mp3__part__30__60.mp3"
  ]
}
```

### GET /download/{file_path}

Скачать обработанный аудиофайл:

```bash
curl -O http://localhost:8081/download/shared_storage/splitted/audio.mp3/audio.mp3__part__0__30.mp3
```

или используя URL из ответа `/split`:

```bash
curl -O http://localhost:8081/download/shared_storage/splitted/audio.mp3/audio.mp3__part__0__30.mp3 -o audio_part_1.mp3
```

### GET /health

Проверка статуса сервиса:
```bash
curl http://localhost:8081/health
```

## Использование

### Docker Compose (рекомендуется)

```bash
docker-compose up -d
```

### Docker

Собрать образ:
```bash
docker build -t audio-splitter .
```

Запустить контейнер:
```bash
docker run -d --name audio-splitter-service -p 8081:8081 -v /path/to/shared_storage:/shared_storage audio-splitter
```

### Пути

Входящие файлы: `/shared_storage`  
Результаты: `/shared_storage/splitted`

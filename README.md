# Audio Splitter Service

FastAPI микросервис для нарезания аудио файлов на части без переперекодирования.

## Поддерживаемые форматы

- Аудио: mp3, wav, m4a, flac, ogg
- Видео (извлечение аудиодорожки): mp4, mkv, webm

## API

### POST /split

Нарезать аудио файл по длительности или количеству частей.

**Параметры запроса:**
- `filename` (string, опционально) - название файла в хранилище
- `url` (string, опционально) - URL для скачивания файла
- `max_duration` (integer, опционально) - максимальная длительность каждого файла в секундах
- `split_parts` (integer, опционально) - количество частей для разделения
- `save_to_storage` (boolean, по умолчанию false) - загрузить результирующие файлы в File Storage Service

**Примечание:** Должны быть указаны либо `filename`, либо `url` (но не оба одновременно). Должны быть указаны либо `max_duration`, либо `split_parts` (но не оба одновременно).

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

#### Сохранение результатов в хранилище

Добавьте параметр `save_to_storage: true` чтобы загрузить результирующие файлы в File Storage Service. При этом:
- Файлы сохраняются во временную папку
- Загружаются в File Storage Service
- Удаляются из временной папки после успешной загрузки

```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"filename": "audio.mp3", "split_parts": 4, "save_to_storage": true}'
```

или с URL:

```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/audio.mp3", "split_parts": 4, "save_to_storage": true}'
```

**Response без save_to_storage (файлы в локальном хранилище):**
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

**Response с save_to_storage=true (файлы в File Storage Service):**
```json
{
  "storage_files": [
    {
      "id": "1777218058633-57656008-audio.mp3__part__0__30.mp3",
      "originalName": "audio.mp3__part__0__30.mp3",
      "size": 1024000,
      "mimeType": "audio/mpeg",
      "path": "/app/storage/1777218058633-57656008-audio.mp3__part__0__30.mp3",
      "uploadedAt": "2026-05-15T10:30:00.000Z"
    }
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

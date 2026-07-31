# Audio Splitter Service

FastAPI микросервис для нарезания аудио файлов на части без переперекодирования.

<img width="986" height="607" alt="image" src="https://github.com/user-attachments/assets/902103e9-20fa-40d6-84a1-ad0bacdfc58b" />


## Поддерживаемые форматы

- Аудио: mp3, wav, m4a, flac, ogg
- Видео (извлечение аудиодорожки): mp4, mkv, webm

## API

### POST /split

Нарезать аудио файл по длительности или количеству частей.

**По максимальной длительности:**
```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"filename": "audio.mp3", "split_parts": 4}'
```

**По количеству частей:**
```bash
curl -X POST http://localhost:8081/split \
  -H "Content-Type: application/json" \
  -d '{"filename": "video.mp4", "split_parts": 4}'
```

**Response:**
```json
{
  "files": [
    "/shared_storage/splitted/audio_0__60",
    "/shared_storage/splitted/audio_60__120"
  ]
}
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

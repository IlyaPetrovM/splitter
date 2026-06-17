# Audio Splitter Service

Микросервис для нарезания аудио файлов на части без переперекодирования. Работает на основе RabbitMQ очередей.

## Поддерживаемые форматы

- Аудио: mp3, wav, m4a, flac, ogg
- Видео (извлечение аудиодорожки): mp4, mkv, webm

## RabbitMQ Interface

Сервис слушает очередь `split_in` для получения команд и отправляет результаты в очередь `split_out`.

### Формат входящего сообщения (split_in)

**Параметры:**
- `filename` (string, опционально) - название файла в хранилище
- `url` (string, опционально) - URL для скачивания файла
- `max_duration` (integer, опционально) - максимальная длительность каждого файла в секундах
- `split_parts` (integer, опционально) - количество частей для разделения
- `save_to_storage` (boolean, по умолчанию false) - загрузить результирующие файлы в File Storage Service

**Примечание:** Должны быть указаны либо `filename`, либо `url` (но не оба одновременно). Должны быть указаны либо `max_duration`, либо `split_parts` (но не оба одновременно).

### Примеры входящих сообщений

#### По файлу из хранилища с max_duration

```json
{
  "task_id": "task_uuid",
  "url": "http://file-storage-service:3001/api/files/audio.mp3",
  "max_duration": 60,
  "save_to_storage": true
}
```

### Формат исходящего сообщения (split_out)

#### При успехе (save_to_storage=true)

```json
{
  "success": true,
  "task_id": "task_uuid",
  "storage_files": [
    {
      "path": "audio.mp3__part__0__30.mp3",
      "uploadedAt": "2026-05-15T10:30:00.000Z"
    }
  ]
}
```

#### При успехе (save_to_storage=false)

```json
{
  "success": true,
  "task_id": "task_uuid",
  "files": [
    "/shared_storage/splitted/audio.mp3/audio.mp3__part__0__30.mp3",
    "/shared_storage/splitted/audio.mp3/audio.mp3__part__30__60.mp3"
  ]
}
```

#### При ошибке

```json
{
  "success": false,
  "task_id": "task_uuid",
  "error": "Error message describing what went wrong"
}
```

## Использование

### Docker Compose (рекомендуется)

```bash
docker-compose up -d
```

Это запустит оба сервиса:
- audio-splitter (подключается к RabbitMQ)
- rabbitmq на портах 5672 (AMQP) и 15672 (Management UI)

### Docker

Собрать образ:
```bash
docker build -t audio-splitter .
```

Запустить контейнер:
```bash
docker run -d --name audio-splitter-service -v /path/to/shared_storage:/shared_storage -e RABBITMQ_HOST=rabbitmq-host audio-splitter
```

### Локальный запуск

Установить зависимости:
```bash
pip install -r requirements.txt
```

Запустить сервис (убедитесь, что RabbitMQ запущен на localhost:5672):
```bash
python main.py
```

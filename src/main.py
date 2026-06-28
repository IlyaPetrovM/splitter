import os
import subprocess
import json
import tempfile
import requests
import pika
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SHARED_STORAGE = "/shared_storage"
SPLITTED_DIR = os.path.join(SHARED_STORAGE, "splitted")
FILE_STORAGE_API = os.getenv("FILE_STORAGE_API", "http://file-storage-service:3001/api/files")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE_IN = "split_in"
RABBITMQ_QUEUE_OUT = "split_out"

os.makedirs(SPLITTED_DIR, exist_ok=True)


def get_audio_duration(file_path: str) -> float:
    logger.info(f"Getting duration for: {file_path}")
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        error_msg = result.stderr.strip() if result.stderr else "ffprobe returned no output"
        raise ValueError(f"ffprobe error: {error_msg}")
    return float(result.stdout.strip())


def extract_audio_track(input_file: str, output_file: str) -> None:
    logger.info(f"Extracting audio from video: {input_file}")
    cmd = [
        "ffmpeg",
        "-i", input_file,
        "-q:a", "0",
        "-map", "a",
        "-y",
        output_file
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    logger.info(f"Audio extracted to: {output_file}")


def download_file(url: str, temp_dir: str) -> str:
    logger.info(f"Downloading file from: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        filename = url.split('/')[-1].split('?')[0] or "downloaded_file"
        file_path = os.path.join(temp_dir, filename)

        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        logger.info(f"File downloaded to: {file_path}")
        return file_path
    except Exception as e:
        raise ValueError(f"Failed to download file: {str(e)}")


def upload_file_to_storage(file_path: str) -> dict:
    logger.info(f"Uploading file to storage: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            response = requests.post(FILE_STORAGE_API, files=files, timeout=30)
            response.raise_for_status()

        result = response.json()
        file_id = result.get('file', {}).get('id')
        logger.info(f"File uploaded to storage with id: {file_id}")
        return result.get('file', {})
    except Exception as e:
        raise ValueError(f"Failed to upload file to storage: {str(e)}")


def split_audio(input_file: str, output_dir: str, original_filename: str,
                segments: list[tuple[float, float]]) -> list[dict]:
    created_files = []

    for i, (start, end) in enumerate(segments):
        ext = Path(original_filename).suffix
        output_file = os.path.join(output_dir, f"{original_filename}__part__{int(start)}__{int(end)}{ext}")

        logger.info(f"Cutting segment {i+1}/{len(segments)}: {start}s-{end}s -> {output_file}")

        cmd = [
            "ffmpeg",
            "-i", input_file,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",
            "-y",
            output_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        segment_duration = end - start
        duration_msec = int(segment_duration * 1000)

        created_files.append({
            "path": output_file,
            "duration_msec": duration_msec
        })

    logger.info(f"Created {len(created_files)} audio segments")
    return created_files


def calculate_segments(duration: float, max_duration: int | None,
                      split_parts: int | None) -> list[tuple[float, float]]:
    segments = []

    if max_duration:
        logger.info(f"Splitting by max_duration: {max_duration}s")
        current_start = 0.0
        while current_start < duration:
            current_end = min(current_start + max_duration, duration)
            segments.append((current_start, current_end))
            current_start = current_end

    elif split_parts:
        logger.info(f"Splitting into {split_parts} parts")
        segment_duration = duration / split_parts
        for i in range(split_parts):
            start = i * segment_duration
            end = (i + 1) * segment_duration if i < split_parts - 1 else duration
            segments.append((start, end))

    return segments


def process_split_request(request_data: dict, channel) -> dict:
    filename = request_data.get("filename")
    url = request_data.get("url")
    max_duration = request_data.get("max_duration")
    split_parts = request_data.get("split_parts")
    save_to_storage = request_data.get("save_to_storage", False)
    task_id = request_data.get("task_id")

    logger.info(f"Processing request: filename={filename}, url={url}, max_duration={max_duration}, split_parts={split_parts}")

    try:
        if not max_duration and not split_parts:
            raise ValueError("Provide max_duration or split_parts")

        if not filename and not url:
            raise ValueError("Provide either filename or url")

        if filename and url:
            raise ValueError("Provide either filename or url, not both")

        temp_dir_obj = None
        temp_split_dir_obj = None
        downloaded_file = None
        original_filename = filename

        if url:
            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_dir = temp_dir_obj.name
            try:
                downloaded_file = download_file(url, temp_dir)
                file_path = downloaded_file
                original_filename = Path(downloaded_file).name
            except Exception as e:
                raise ValueError(f"Download failed: {str(e)}")
        else:
            file_path = os.path.join(SHARED_STORAGE, filename)
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
            original_filename = filename

        logger.info(f"File found: {file_path}")

        video_extensions = {".mp4", ".mkv", ".webm"}
        audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
        file_ext = Path(file_path).suffix.lower()

        processing_file = file_path
        temp_audio = None

        try:
            if file_ext in video_extensions:
                temp_audio = os.path.join(SPLITTED_DIR, f"_temp_audio_{original_filename}.mp3")
                extract_audio_track(file_path, temp_audio)
                processing_file = temp_audio

            elif file_ext not in audio_extensions:
                raise ValueError(f"Unsupported format: {file_ext}")

            try:
                duration = get_audio_duration(processing_file)
                logger.info(f"Duration: {duration:.2f}s")
            except Exception as e:
                raise ValueError(f"Failed to get duration: {str(e)}")

            segments = calculate_segments(duration, max_duration, split_parts)

            if not segments:
                raise ValueError("No segments calculated")

            logger.info(f"Total segments: {len(segments)}")

            temp_split_dir_obj = None
            if save_to_storage:
                temp_split_dir_obj = tempfile.TemporaryDirectory(prefix="splitted_")
                split_dir = temp_split_dir_obj.name
                logger.info(f"Using temporary directory for split files: {split_dir}")
            else:
                split_dir = os.path.join(SPLITTED_DIR, original_filename)
                os.makedirs(split_dir, exist_ok=True)

            try:
                created_files = split_audio(processing_file, split_dir, original_filename, segments)
            except Exception as e:
                raise ValueError(f"Split failed: {str(e)}")

            storage_files = []
            if save_to_storage:
                logger.info(f"Uploading {len(created_files)} files to storage...")
                for file_item in created_files:
                    try:
                        file_path_item = file_item["path"]
                        duration_msec = file_item["duration_msec"]
                        file_info = upload_file_to_storage(file_path_item)
                        storage_files.append({
                            "path": os.path.basename(file_info.get("path", "")),
                            "uploadedAt": file_info.get("uploadedAt"),
                            "duration_msec": duration_msec
                        })
                    except Exception as e:
                        logger.warning(f"Failed to upload {file_path_item}: {str(e)}")
                        raise ValueError(f"Upload to storage failed: {str(e)}")

            logger.info(f"Processing completed")

            if save_to_storage:
                result = {"status": "success", "task_id": task_id, "storage_files": storage_files}
                return result
            else:
                files_result = [
                    {
                        "path": file_item["path"],
                        "duration_msec": file_item["duration_msec"]
                    }
                    for file_item in created_files
                ]
                return {
                    "status": "success",
                    "task_id": task_id,
                    "files": files_result
                }

        finally:
            if temp_audio and os.path.exists(temp_audio):
                os.remove(temp_audio)
                logger.debug(f"Temp audio removed")

            if temp_dir_obj:
                temp_dir_obj.cleanup()
                logger.debug(f"Input temp directory removed")

            if temp_split_dir_obj:
                temp_split_dir_obj.cleanup()
                logger.debug(f"Split temp directory removed")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"{error_msg}")
        return {"status": "error", "task_id": task_id, "error": error_msg}


def on_message_received(channel, method, properties, body):
    logger.info(f"Received message from {RABBITMQ_QUEUE_IN}")

    try:
        request_data = json.loads(body.decode())
        logger.debug(f"Decoded message: {request_data}")
    except Exception as e:
        logger.error(f"Failed to decode message: {str(e)}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    result = process_split_request(request_data, channel)

    try:
        result_message = json.dumps(result)
        channel.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE_OUT,
            body=result_message
        )
        logger.info(f"Sent result to {RABBITMQ_QUEUE_OUT}")
    except Exception as e:
        logger.error(f"Failed to send result: {str(e)}")

    channel.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer():
    logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}")

    try:
        credentials = pika.PlainCredentials('guest', 'guest')
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                credentials=credentials,
                connection_attempts=5,
                retry_delay=2
            )
        )
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
        sys.exit(1)

    channel = connection.channel()

    channel.queue_declare(queue=RABBITMQ_QUEUE_IN, durable=True)
    channel.queue_declare(queue=RABBITMQ_QUEUE_OUT, durable=True)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=RABBITMQ_QUEUE_IN,
        on_message_callback=on_message_received
    )

    logger.info(f"Listening on queue: {RABBITMQ_QUEUE_IN}")
    logger.info(f"Results will be sent to queue: {RABBITMQ_QUEUE_OUT}")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    start_consumer()

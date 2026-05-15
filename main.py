import os
import subprocess
import json
import tempfile
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

SHARED_STORAGE = "/file_storage"
SPLITTED_DIR = os.path.join(SHARED_STORAGE, "splitted")

os.makedirs(SPLITTED_DIR, exist_ok=True)


class SplitRequest(BaseModel):
    filename: str | None = None
    url: str | None = None
    max_duration: int | None = None
    split_parts: int | None = None


def get_audio_duration(file_path: str) -> float:
    """Get duration in seconds using ffmpeg"""
    print(f"[INFO] Getting duration for: {file_path}")
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
    """Extract audio from video file"""
    print(f"[INFO] Extracting audio from video: {input_file}")
    cmd = [
        "ffmpeg",
        "-i", input_file,
        "-q:a", "0",
        "-map", "a",
        "-y",
        output_file
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"[INFO] Audio extracted to: {output_file}")


def download_file(url: str, temp_dir: str) -> str:
    """Download file from URL to temp directory"""
    print(f"[INFO] Downloading file from: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # Extract filename from URL or use default
        filename = url.split('/')[-1].split('?')[0] or "downloaded_file"
        file_path = os.path.join(temp_dir, filename)

        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"[INFO] File downloaded to: {file_path}")
        return file_path
    except Exception as e:
        raise ValueError(f"Failed to download file: {str(e)}")


def split_audio(input_file: str, output_dir: str, original_filename: str,
                segments: list[tuple[float, float]]) -> list[str]:
    """Split audio file at specified time ranges"""
    created_files = []

    for i, (start, end) in enumerate(segments):
        ext = Path(original_filename).suffix
        output_file = os.path.join(output_dir, f"{original_filename}__part__{int(start)}__{int(end)}{ext}")

        print(f"[SPLIT] Cutting segment {i+1}/{len(segments)}: {start}s-{end}s -> {output_file}")

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
        created_files.append(output_file)

    print(f"[SUCCESS] Created {len(created_files)} audio segments")
    return created_files


def calculate_segments(duration: float, max_duration: int | None,
                      split_parts: int | None) -> list[tuple[float, float]]:
    """Calculate split points"""
    segments = []

    if max_duration:
        print(f"[INFO] Splitting by max_duration: {max_duration}s")
        current_start = 0.0
        while current_start < duration:
            current_end = min(current_start + max_duration, duration)
            segments.append((current_start, current_end))
            current_start = current_end

    elif split_parts:
        print(f"[INFO] Splitting into {split_parts} parts")
        segment_duration = duration / split_parts
        for i in range(split_parts):
            start = i * segment_duration
            end = (i + 1) * segment_duration if i < split_parts - 1 else duration
            segments.append((start, end))

    return segments


@app.post("/split")
async def split_endpoint(request: SplitRequest):
    """Split audio file by duration or parts count"""
    print(f"\n[REQUEST] filename={request.filename}, url={request.url}, max_duration={request.max_duration}, split_parts={request.split_parts}")

    if not request.max_duration and not request.split_parts:
        raise HTTPException(status_code=400, detail="Provide max_duration or split_parts")

    if not request.filename and not request.url:
        raise HTTPException(status_code=400, detail="Provide either filename or url")

    if request.filename and request.url:
        raise HTTPException(status_code=400, detail="Provide either filename or url, not both")

    # Handle URL download
    temp_dir_obj = None
    downloaded_file = None
    original_filename = request.filename

    if request.url:
        temp_dir_obj = tempfile.TemporaryDirectory()
        temp_dir = temp_dir_obj.name
        try:
            downloaded_file = download_file(request.url, temp_dir)
            file_path = downloaded_file
            original_filename = Path(downloaded_file).name
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")
    else:
        # Find file from storage
        file_path = os.path.join(SHARED_STORAGE, request.filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        original_filename = request.filename

    print(f"[INFO] File found: {file_path}")

    # Check if video
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
            raise HTTPException(status_code=400, detail=f"Unsupported format: {file_ext}")

        # Get duration
        try:
            duration = get_audio_duration(processing_file)
            print(f"[INFO] Duration: {duration:.2f}s")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to get duration: {str(e)}")

        # Calculate segments
        segments = calculate_segments(duration, request.max_duration, request.split_parts)

        if not segments:
            raise HTTPException(status_code=400, detail="No segments calculated")

        print(f"[INFO] Total segments: {len(segments)}")

        # Split audio
        split_dir = os.path.join(SPLITTED_DIR, original_filename)
        os.makedirs(split_dir, exist_ok=True)

        try:
            created_files = split_audio(processing_file, split_dir, original_filename, segments)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Split failed: {str(e)}")

        print(f"[DONE] Processing completed\n")
        return {"files": created_files}

    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)
            print(f"[INFO] Temp audio removed")

        if temp_dir_obj:
            temp_dir_obj.cleanup()
            print(f"[INFO] Temp directory removed")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)

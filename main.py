import os
import subprocess
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

SHARED_STORAGE = "/shared_storage"
SPLITTED_DIR = os.path.join(SHARED_STORAGE, "splitted")

os.makedirs(SPLITTED_DIR, exist_ok=True)


class SplitRequest(BaseModel):
    filename: str
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


def split_audio(input_file: str, output_dir: str, base_name: str,
                segments: list[tuple[float, float]]) -> list[str]:
    """Split audio file at specified time ranges"""
    created_files = []

    for i, (start, end) in enumerate(segments):
        duration = end - start
        output_file = os.path.join(output_dir, f"{base_name}_{int(start)}__{int(end)}")

        # Preserve original format
        ext = Path(input_file).suffix
        output_file += ext

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
    print(f"\n[REQUEST] filename={request.filename}, max_duration={request.max_duration}, split_parts={request.split_parts}")

    if not request.max_duration and not request.split_parts:
        raise HTTPException(status_code=400, detail="Provide max_duration or split_parts")

    # Find file
    file_path = os.path.join(SHARED_STORAGE, request.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    print(f"[INFO] File found: {file_path}")

    # Check if video
    video_extensions = {".mp4", ".mkv", ".webm"}
    audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
    file_ext = Path(file_path).suffix.lower()

    processing_file = file_path
    temp_audio = None

    if file_ext in video_extensions:
        temp_audio = os.path.join(SPLITTED_DIR, f"_temp_audio_{request.filename}.mp3")
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
    base_name = Path(request.filename).stem
    try:
        created_files = split_audio(processing_file, SPLITTED_DIR, base_name, segments)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Split failed: {str(e)}")
    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)
            print(f"[INFO] Temp audio removed")

    print(f"[DONE] Processing completed\n")
    return {"files": created_files}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)

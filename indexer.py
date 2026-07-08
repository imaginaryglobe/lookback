import base64
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pillow_heif
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

import config
from hashing import path_to_hash_hex, path_to_id
from log_broadcaster import get_indexer_logger

pillow_heif.register_heif_opener()

logger = get_indexer_logger()

EASTERN = ZoneInfo("America/New_York")


def now_eastern_str() -> str:
    return datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z")

CAPTION_PROMPT = (
    "Describe this image in detail. Include: what objects are visible, any text or "
    "documents shown, people or faces (without identifying them), the setting or "
    "location, any sensitive items like IDs, financial documents, medical records, or "
    "personal information. Be specific and thorough."
)

VIDEO_SUMMARY_PROMPT_TEMPLATE = (
    "The following are captions of consecutive frames from a single video, in order:\n\n"
    "{captions}\n\n"
    "Write one concise paragraph summarizing what happens in this video overall."
)

RETRIES = 3
RETRY_DELAY_SECONDS = 5
RETRIEVE_CHUNK_SIZE = 500


class StartupCheckError(Exception):
    pass


def run_startup_checks(http_client: httpx.Client, qdrant_client: QdrantClient) -> None:
    try:
        http_client.get(config.OLLAMA_URL, timeout=5)
    except httpx.HTTPError:
        raise StartupCheckError("Cannot reach Ollama. Run start_tunnel.bat and try again.")

    try:
        qdrant_client.get_collections()
    except Exception:
        raise StartupCheckError("Qdrant is not running. Start Qdrant and try again.")

    if not os.path.exists(config.SSD_PATH):
        raise StartupCheckError(f"SSD not found at {config.SSD_PATH}. Check it is plugged in.")


def ensure_collection(client: QdrantClient) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )


def call_with_retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(RETRIES):
        try:
            return fn(*args, **kwargs)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_exc


def caption_image_bytes(http_client: httpx.Client, jpeg_bytes: bytes) -> str:
    def _call():
        resp = http_client.post(
            f"{config.OLLAMA_URL}/api/generate",
            json={
                "model": config.VISION_MODEL,
                "prompt": CAPTION_PROMPT,
                "images": [base64.b64encode(jpeg_bytes).decode("ascii")],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    return call_with_retry(_call)


def embed_text(http_client: httpx.Client, text: str) -> list:
    def _call():
        resp = http_client.post(
            f"{config.OLLAMA_URL}/api/embeddings",
            json={"model": config.EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    return call_with_retry(_call)


def summarize_captions(http_client: httpx.Client, captions: list) -> str:
    prompt = VIDEO_SUMMARY_PROMPT_TEMPLATE.format(captions="\n".join(f"- {c}" for c in captions))

    def _call():
        resp = http_client.post(
            f"{config.OLLAMA_URL}/api/generate",
            json={"model": config.QUERY_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    return call_with_retry(_call)


CAPTION_MAX_DIMENSION = 1024  # moondream downsamples internally; no captioning benefit above this


def load_image_as_jpeg_bytes(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((CAPTION_MAX_DIMENSION, CAPTION_MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def scan_ssd() -> list:
    supported = set(config.SUPPORTED_IMAGE_EXTENSIONS) | set(config.SUPPORTED_VIDEO_EXTENSIONS)
    excluded_dirs = {d.lower() for d in config.EXCLUDED_DIR_NAMES}
    found = []
    for root, dirs, files in os.walk(config.SSD_PATH):
        dirs[:] = [d for d in dirs if d.lower() not in excluded_dirs]
        for name in files:
            if name.startswith("."):
                continue  # macOS AppleDouble metadata sidecar files (._IMG_xxx.jpg), not real media
            ext = os.path.splitext(name)[1].lower()
            if ext in supported:
                found.append(os.path.join(root, name))
    return found


def get_already_indexed_ids(client: QdrantClient, ids: list) -> set:
    indexed = set()
    for i in range(0, len(ids), RETRIEVE_CHUNK_SIZE):
        chunk = ids[i:i + RETRIEVE_CHUNK_SIZE]
        points = client.retrieve(
            collection_name=config.QDRANT_COLLECTION,
            ids=chunk,
            with_payload=["status"],
        )
        for p in points:
            if p.payload.get("status") == "indexed":
                indexed.add(p.id)
    return indexed


def save_thumbnail_from_pil(img: Image.Image, hash_hex: str) -> None:
    os.makedirs(config.THUMBNAILS_PATH, exist_ok=True)
    thumb = img.convert("RGB").copy()
    thumb.thumbnail((300, 10_000))
    thumb.save(os.path.join(config.THUMBNAILS_PATH, f"{hash_hex}.jpg"), format="JPEG")


def process_image(http_client: httpx.Client, path: str) -> str:
    jpeg_bytes = load_image_as_jpeg_bytes(path)
    caption = caption_image_bytes(http_client, jpeg_bytes)
    save_thumbnail_from_pil(Image.open(io.BytesIO(jpeg_bytes)), path_to_hash_hex(path))
    return caption


def get_video_duration_seconds(video_path: str):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.decode().strip())
    except ValueError:
        return None


def extract_video_frames(video_path: str, out_dir: str) -> list:
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "frame_%04d.jpg")

    duration = get_video_duration_seconds(video_path)
    if duration is not None and duration < config.SHORT_VIDEO_THRESHOLD_SECONDS:
        interval = config.SHORT_VIDEO_FRAME_INTERVAL_SECONDS
    else:
        interval = config.VIDEO_FRAME_INTERVAL_SECONDS

    fps = f"1/{interval}"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"fps={fps}", "-strict", "unofficial", pattern],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode(errors='replace')}")
    frames = sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.lower().endswith(".jpg")
    )

    if not frames:
        # Even the denser interval didn't fit (e.g. a clip under 5s, or duration
        # was unknown). Fall back to a single frame at the start.
        fallback_result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-strict", "unofficial", pattern],
            capture_output=True,
        )
        if fallback_result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {fallback_result.stderr.decode(errors='replace')}")
        frames = sorted(
            os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.lower().endswith(".jpg")
        )

    max_frames = 20
    if len(frames) > max_frames:
        keep = set(frames[i] for i in range(0, len(frames), len(frames) // max_frames))
        for f in frames:
            if f not in keep:
                try:
                    os.remove(f)
                except OSError:
                    pass
        frames = sorted(keep)

    return frames


def process_video(http_client: httpx.Client, path: str) -> str:
    hash_hex = path_to_hash_hex(path)
    frame_dir = os.path.join(config.FRAMES_PATH, hash_hex)
    try:
        frames = extract_video_frames(path, frame_dir)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found -- install via `winget install ffmpeg`")

    if not frames:
        raise RuntimeError("no frames extracted from video")

    captions = []
    for i, frame_path in enumerate(frames):
        with open(frame_path, "rb") as f:
            jpeg_bytes = f.read()
        captions.append(caption_image_bytes(http_client, jpeg_bytes))
        if i == 0:
            save_thumbnail_from_pil(Image.open(io.BytesIO(jpeg_bytes)), hash_hex)

    summary = summarize_captions(http_client, captions)

    for frame_path in frames:
        try:
            os.remove(frame_path)
        except OSError:
            pass
    try:
        os.rmdir(frame_dir)
    except OSError:
        pass

    return summary


def write_progress(state: dict) -> None:
    with open(config.INDEX_PROGRESS_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_stats() -> dict:
    if os.path.exists(config.INDEX_STATS_FILE):
        try:
            with open(config.INDEX_STATS_FILE) as f:
                data = json.load(f)
                return {
                    "total_files": data.get("total_files", 0),
                    "total_seconds": data.get("total_seconds", 0.0),
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {"total_files": 0, "total_seconds": 0.0}


def save_stats(stats: dict) -> None:
    with open(config.INDEX_STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def format_file_size(path: str) -> str:
    try:
        size_bytes = os.path.getsize(path)
    except OSError:
        return "unknown size"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024 or unit == "GB":
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024


def run_indexer(mode: str = "incremental", stop_event=None) -> None:
    http_client = httpx.Client()
    qdrant_client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)

    run_startup_checks(http_client, qdrant_client)
    ensure_collection(qdrant_client)

    if mode == "full":
        logger.info("Full re-index requested: deleting existing collection.")
        qdrant_client.delete_collection(config.QDRANT_COLLECTION)
        ensure_collection(qdrant_client)

    all_files = scan_ssd()
    all_ids = [path_to_id(p) for p in all_files]
    already_indexed = get_already_indexed_ids(qdrant_client, all_ids)

    todo = [(p, pid) for p, pid in zip(all_files, all_ids) if pid not in already_indexed]

    logger.info(
        f"Found {len(all_files)} files. Already indexed: {len(already_indexed)}. "
        f"Remaining: {len(todo)}."
    )

    stats = load_stats()
    already_indexed_count = len(already_indexed)
    total_files = len(all_files)

    def current_avg():
        return (stats["total_seconds"] / stats["total_files"]) if stats["total_files"] else None

    def write_progress_with_eta(processed_count, current_file):
        avg = current_avg()
        remaining = len(todo) - processed_count
        eta_seconds = int(avg * remaining) if avg is not None else None
        write_progress({
            "processed": already_indexed_count + processed_count,
            "total_this_run": total_files,
            "current_file": current_file,
            "avg_seconds_per_file": round(avg, 1) if avg is not None else None,
            "eta_seconds": eta_seconds,
            "last_updated": now_eastern_str(),
        })
        return avg, eta_seconds

    write_progress_with_eta(0, None)

    processed = 0

    for path, point_id in todo:
        if stop_event is not None and stop_event.is_set():
            logger.info(f"Stopped by request after {processed}/{len(todo)} files this run.")
            return

        logger.info(f"Processing: {path} ({format_file_size(path)})")
        write_progress_with_eta(processed, path)

        file_start = time.time()
        ext = os.path.splitext(path)[1].lower()
        file_type = "video" if ext in config.SUPPORTED_VIDEO_EXTENSIONS else "image"
        status = "indexed"
        caption = None

        try:
            if file_type == "image":
                caption = process_image(http_client, path)
            else:
                caption = process_video(http_client, path)
        except Exception as e:
            logger.info(f"FAILED {path}: {e}")
            status = "failed"
            caption = str(e)

        if status == "indexed" and not caption.strip():
            logger.info(f"FAILED {path}: caption was empty")
            status = "failed"

        embedding = None
        if status == "indexed":
            try:
                embedding = embed_text(http_client, caption)
                if not embedding or len(embedding) != 768:
                    logger.info(f"FAILED (embedding) {path}: embedding was empty or wrong size")
                    status = "failed"
                    embedding = None
            except Exception as e:
                logger.info(f"FAILED (embedding) {path}: {e}")
                status = "failed"

        try:
            file_size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
            date_modified = datetime.fromtimestamp(
                os.path.getmtime(path), tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except OSError:
            file_size_mb = 0.0
            date_modified = ""

        payload = {
            "path": path,
            "filename": os.path.basename(path),
            "extension": ext,
            "type": file_type,
            "caption": caption or "",
            "date_modified": date_modified,
            "file_size_mb": file_size_mb,
            "status": status,
        }

        vector = embedding if embedding is not None else [0.0] * 768
        try:
            qdrant_client.upsert(
                collection_name=config.QDRANT_COLLECTION,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
        except Exception as e:
            # Never let a single bad file crash the whole run -- mark it
            # failed and move on. This is the safety net; whatever bug
            # caused Qdrant to reject the point should also be fixed at
            # its source, but this guarantees the overnight run survives.
            logger.info(f"FAILED (upsert) {path}: {e}")
            status = "failed"
            try:
                payload["status"] = "failed"
                qdrant_client.upsert(
                    collection_name=config.QDRANT_COLLECTION,
                    points=[PointStruct(id=point_id, vector=[0.0] * 768, payload=payload)],
                )
            except Exception:
                pass  # give up recording this one; it'll simply be retried next run

        if status == "indexed":
            stats["total_files"] += 1
            stats["total_seconds"] += time.time() - file_start
            save_stats(stats)

        processed += 1
        if processed % config.INDEXING_BATCH_SIZE == 0 or processed == len(todo):
            avg, eta_seconds = write_progress_with_eta(processed, None)
            if avg is not None:
                eta_h, rem = divmod(eta_seconds, 3600)
                eta_m = rem // 60
                logger.info(
                    f"Indexed {processed}/{len(todo)} -- avg {avg:.1f}s/file "
                    f"(lifetime average) -- ETA {eta_h}h {eta_m}m"
                )
            else:
                logger.info(f"Indexed {processed}/{len(todo)}")

    logger.info("Indexing run complete.")


if __name__ == "__main__":
    mode = "full" if "--full" in sys.argv else "incremental"
    try:
        run_indexer(mode)
    except StartupCheckError as e:
        print(str(e))
        sys.exit(1)

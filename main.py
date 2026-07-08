import asyncio
import io
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sse_starlette.sse import EventSourceResponse

import config
import indexer
import log_broadcaster
from hashing import path_to_hash_hex

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

qdrant_client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
http_client = httpx.Client()

_index_lock = threading.Lock()
_indexing_in_progress = False
_stop_event = threading.Event()

SSD_ROOT = Path(config.SSD_PATH).resolve()


class SearchRequest(BaseModel):
    query: str
    limit: int = config.MAX_SEARCH_RESULTS


class IndexStartRequest(BaseModel):
    mode: str = "incremental"


def _validate_path(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(SSD_ROOT):
        raise HTTPException(status_code=400, detail="Path is outside the configured SSD path.")
    return resolved


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


def _expand_query(query: str) -> str:
    prompt = (
        "A user is searching their personal photo and video library. Their query is: "
        f"'{query}'. Expand this into a list of 8-12 specific, concrete terms or phrases "
        "that might appear in image descriptions matching what they're looking for. "
        "Return only a comma-separated list of terms, nothing else."
    )
    resp = http_client.post(
        f"{config.OLLAMA_URL}/api/generate",
        json={"model": config.QUERY_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    expanded_raw = resp.json()["response"]
    terms = [t.strip() for t in expanded_raw.split(",") if t.strip()]
    return query + " " + " ".join(terms)


def _embed(text: str) -> list:
    resp = http_client.post(
        f"{config.OLLAMA_URL}/api/embeddings",
        json={"model": config.EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _rerank(query: str, results: list) -> list:
    candidates = [
        {"filename": r.payload["filename"], "caption": r.payload["caption"]} for r in results
    ]
    prompt = (
        f"A user searched for: '{query}'.\n"
        f"Here are candidate results as JSON: {json.dumps(candidates)}\n"
        "Return ONLY a JSON array of the 'filename' values, ranked from most to least "
        "relevant to the query. Include at most 10 filenames. No other text."
    )
    try:
        resp = http_client.post(
            f"{config.OLLAMA_URL}/api/generate",
            json={"model": config.QUERY_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["response"]
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        ranked_filenames = json.loads(match.group(0)) if match else []
        by_filename = {r.payload["filename"]: r for r in results}
        ranked = [by_filename[f] for f in ranked_filenames if f in by_filename]
        remaining = [r for r in results if r not in ranked]
        return (ranked + remaining)[:10]
    except Exception:
        return results[:10]


@app.post("/search")
def search(req: SearchRequest):
    expanded = _expand_query(req.query)
    vector = _embed(expanded)
    results = qdrant_client.search(
        collection_name=config.QDRANT_COLLECTION,
        query_vector=vector,
        limit=req.limit,
        with_payload=True,
    )

    ranked = _rerank(req.query, results) if config.RERANK_RESULTS else results

    return [
        {
            "path": r.payload["path"],
            "filename": r.payload["filename"],
            "caption": r.payload["caption"],
            "score": r.score,
            "thumbnail_url": f"/thumbnail?path={r.payload['path']}",
            "type": r.payload["type"],
            "date_modified": r.payload["date_modified"],
        }
        for r in ranked
    ]


@app.get("/thumbnail")
def get_thumbnail(path: str):
    resolved = _validate_path(path)
    hash_hex = path_to_hash_hex(str(resolved))
    cache_path = Path(config.THUMBNAILS_PATH) / f"{hash_hex}.jpg"

    if not cache_path.exists():
        ext = resolved.suffix.lower()
        if ext in config.SUPPORTED_VIDEO_EXTENSIONS:
            raise HTTPException(status_code=404, detail="No cached thumbnail for this video.")
        if not resolved.exists():
            raise HTTPException(status_code=404, detail="Source file not found.")
        img = Image.open(resolved).convert("RGB")
        img.thumbnail((300, 10_000))
        os.makedirs(config.THUMBNAILS_PATH, exist_ok=True)
        img.save(cache_path, format="JPEG")

    return FileResponse(cache_path, media_type="image/jpeg")


@app.get("/open-file")
def open_file(path: str):
    resolved = _validate_path(path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    os.startfile(str(resolved))
    return {"ok": True}


@app.get("/status")
def get_status():
    try:
        count = qdrant_client.count(
            collection_name=config.QDRANT_COLLECTION,
            count_filter=Filter(must=[FieldCondition(key="status", match=MatchValue(value="indexed"))]),
            exact=True,
        ).count
    except Exception:
        count = 0

    last_indexed = None
    progress = {}
    if os.path.exists(config.INDEX_PROGRESS_FILE):
        try:
            with open(config.INDEX_PROGRESS_FILE) as f:
                progress = json.load(f)
                last_indexed = progress.get("last_updated")
        except (OSError, json.JSONDecodeError):
            pass

    def _ping(url: str) -> bool:
        try:
            http_client.get(url, timeout=2)
            return True
        except httpx.HTTPError:
            return False

    return {
        "indexed_count": count,
        "last_indexed": last_indexed,
        "ollama_healthy": _ping(config.OLLAMA_URL),
        "qdrant_healthy": _ping(f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}"),
        "indexing_in_progress": _indexing_in_progress,
        "progress": {
            "processed": progress.get("processed"),
            "total_this_run": progress.get("total_this_run"),
            "current_file": progress.get("current_file"),
            "avg_seconds_per_file": progress.get("avg_seconds_per_file"),
            "eta_seconds": progress.get("eta_seconds"),
        } if _indexing_in_progress else None,
    }


def _run_indexer_thread(mode: str):
    global _indexing_in_progress
    try:
        indexer.run_indexer(mode, stop_event=_stop_event)
    except Exception as e:
        indexer.logger.info(f"Indexing run aborted: {e}")
    finally:
        with _index_lock:
            _indexing_in_progress = False


@app.post("/index/start")
def start_indexing(req: IndexStartRequest):
    global _indexing_in_progress
    with _index_lock:
        if _indexing_in_progress:
            raise HTTPException(status_code=409, detail="Indexing already in progress.")
        _indexing_in_progress = True
        _stop_event.clear()

    thread = threading.Thread(target=_run_indexer_thread, args=(req.mode,), daemon=True)
    thread.start()
    return {"started": True, "mode": req.mode}


@app.post("/index/stop")
def stop_indexing():
    if not _indexing_in_progress:
        raise HTTPException(status_code=409, detail="No indexing run in progress.")
    _stop_event.set()
    return {"stopping": True}


@app.get("/index/progress")
async def index_progress():
    async def event_generator():
        q = log_broadcaster.subscribe()
        try:
            while True:
                try:
                    line = await asyncio.get_event_loop().run_in_executor(None, q.get, True, 15)
                    yield {"data": line}
                except Exception:
                    yield {"event": "ping", "data": ""}
        finally:
            log_broadcaster.unsubscribe(q)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

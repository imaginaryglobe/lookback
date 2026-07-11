import os

from dotenv import load_dotenv

load_dotenv()

# --- Storage ---
SSD_PATH = os.environ["SSD_PATH"]      # Only index media inside this folder
FRAMES_PATH = r".\frames"               # Temp storage for video keyframes
THUMBNAILS_PATH = r".\thumbnails"       # Cached thumbnail storage
INDEX_PROGRESS_FILE = "index_progress.json"  # Local checkpoint/progress cache (not authoritative -- Qdrant is)
INDEX_STATS_FILE = "indexing_stats.json"     # Persisted cumulative avg-seconds-per-file, survives restarts

# --- Web server ---
# 127.0.0.1 (default) only accepts connections from this machine. Set to 0.0.0.0
# only if you deliberately want other devices on your network to reach the UI --
# note that captions/thumbnails can include sensitive content (IDs, documents, etc.)
# and there is no login, so anyone who can reach the port can see them.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# --- Ollama (may be local, or tunneled from a remote machine -- see start_tunnel.bat) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_REMOTE = os.environ.get("OLLAMA_REMOTE", "false").lower() == "true"
VISION_MODEL = os.environ.get("VISION_MODEL", "moondream")        # Vision model for captioning
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")   # Embedding model
QUERY_MODEL = os.environ.get("QUERY_MODEL", "llama3.2")           # Query expansion + reranking model

# --- Qdrant ---
# "embedded" (default) runs Qdrant in-process at QDRANT_PATH -- no Docker/server needed.
# "server" connects to a running Qdrant instance (e.g. via docker-compose.yml) at QDRANT_HOST:QDRANT_PORT.
QDRANT_MODE = os.environ.get("QDRANT_MODE", "embedded")
QDRANT_PATH = os.environ.get("QDRANT_PATH", "./qdrant_data")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "media_index")  # Collection name

# --- Indexing ---
VIDEO_FRAME_INTERVAL_SECONDS = 45      # Extract one frame every N seconds
SHORT_VIDEO_THRESHOLD_SECONDS = 45     # Videos shorter than this use the denser interval below
SHORT_VIDEO_FRAME_INTERVAL_SECONDS = 5 # Frame interval for videos under the threshold
INDEXING_BATCH_SIZE = 10              # Files to process before checkpointing
MAX_SEARCH_RESULTS = 20               # Max results returned per query
RERANK_RESULTS = True                 # Enable LLM reranking for vague queries

# --- File types ---
SUPPORTED_IMAGE_EXTENSIONS = [
    ".jpg", ".jpeg", ".png", ".heic",
    ".heif", ".webp", ".gif", ".bmp", ".tiff"
]
SUPPORTED_VIDEO_EXTENSIONS = [
    ".mp4", ".mov", ".m4v", ".avi", ".mkv"
]

# --- Exclusions ---
EXCLUDED_DIR_NAMES = ["Archive"]  # Skip these directory names anywhere in the scan (case-insensitive)

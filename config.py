import os

from dotenv import load_dotenv

load_dotenv()

# --- Storage ---
SSD_PATH = os.environ["SSD_PATH"]      # Only index media inside this folder
FRAMES_PATH = r".\frames"               # Temp storage for video keyframes
THUMBNAILS_PATH = r".\thumbnails"       # Cached thumbnail storage
INDEX_PROGRESS_FILE = "index_progress.json"  # Local checkpoint/progress cache (not authoritative -- Qdrant is)
INDEX_STATS_FILE = "indexing_stats.json"     # Persisted cumulative avg-seconds-per-file, survives restarts

# --- Ollama (may be local, or tunneled from a remote machine -- see start_tunnel.bat) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_REMOTE = os.environ.get("OLLAMA_REMOTE", "false").lower() == "true"
VISION_MODEL = os.environ.get("VISION_MODEL", "moondream")        # Vision model for captioning
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")   # Embedding model
QUERY_MODEL = os.environ.get("QUERY_MODEL", "llama3.2")           # Query expansion + reranking model

# --- Qdrant ---
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")          # Qdrant runs locally (via Docker)
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))          # Qdrant default port
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

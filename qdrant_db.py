from qdrant_client import QdrantClient

import config


def get_qdrant_client() -> QdrantClient:
    """Embedded mode (default) runs Qdrant in-process, no server required.
    Server mode connects to a running Qdrant instance (e.g. via docker-compose.yml)."""
    if config.QDRANT_MODE == "server":
        return QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
    return QdrantClient(path=config.QDRANT_PATH)

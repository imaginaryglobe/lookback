import hashlib
import os


def path_to_id(path: str) -> int:
    """Deterministic uint64 id for a file path, stable across repeated scans.

    Windows paths are case-insensitive, so normcase+normpath before hashing
    ensures the same file always maps to the same Qdrant point id.
    """
    normalized = os.path.normcase(os.path.normpath(path))
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def path_to_hash_hex(path: str) -> str:
    """Hex string derived the same way as path_to_id, used for thumbnail filenames."""
    normalized = os.path.normcase(os.path.normpath(path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

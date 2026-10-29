"""Shared Qdrant client singleton to prevent file lock contention in embedded mode."""

from pathlib import Path
from qdrant_client import QdrantClient
from backend.app.config import Settings, get_settings

_shared_client: QdrantClient | None = None


def get_shared_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    global _shared_client
    if _shared_client is not None:
        try:
            # Check if still open
            _shared_client.get_collections()
            return _shared_client
        except Exception:
            _shared_client = None

    settings = settings or get_settings()
    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=2.0,
        )
        client.get_collections()
        _shared_client = client
        return _shared_client
    except Exception:
        Path("storage/qdrant").mkdir(parents=True, exist_ok=True)
        try:
            _shared_client = QdrantClient(path="storage/qdrant")
        except Exception:
            _shared_client = QdrantClient(":memory:")
        return _shared_client

"""Cloud deploy mode — BM25-only retrieval, no local PyTorch/sentence-transformers."""
import os


def skip_local_embeddings() -> bool:
    return os.getenv("SKIP_LOCAL_EMBEDDINGS", "").lower() in ("1", "true", "yes")

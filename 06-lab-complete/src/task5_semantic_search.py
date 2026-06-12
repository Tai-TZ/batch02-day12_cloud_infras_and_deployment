"""
Task 5 — Semantic Search Module.

Viết module tìm kiếm ngữ nghĩa (dense retrieval) trên vector store.

Yêu cầu:
    - Input: query string + top_k
    - Output: danh sách chunks có score, sorted descending
    - Phải tương thích với embedding model và vector store ở Task 4
"""

from functools import lru_cache

from src.task4_chunking_indexing import (
    COLLECTION_NAME,
    _get_embedding_model,
    get_weaviate_client,
)


@lru_cache(maxsize=1)
def _cached_embedding_model():
    return _get_embedding_model()


def _embed_query(query: str) -> list[float]:
    model = _cached_embedding_model()
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding.tolist()


def _distance_to_score(distance: float | None) -> float:
    """Chuyển cosine distance của Weaviate thành similarity score."""
    if distance is None:
        return 0.0
    return max(0.0, 1.0 - distance)


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector similarity.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict
        }
        Sorted by score descending.
    """
    from src.cloud_mode import skip_local_embeddings

    if skip_local_embeddings():
        return []

    if not query.strip() or top_k <= 0:
        return []

    from weaviate.classes.query import MetadataQuery
    from weaviate.exceptions import WeaviateConnectionError

    query_embedding = _embed_query(query)

    try:
        client = get_weaviate_client()
    except Exception:
        from src.local_index import search_local_index
        return search_local_index(query_embedding, top_k=top_k)

    try:
        if not client.collections.exists(COLLECTION_NAME):
            from src.local_index import search_local_index
            return search_local_index(query_embedding, top_k=top_k)

        collection = client.collections.get(COLLECTION_NAME)
        response = collection.query.near_vector(
            near_vector=query_embedding,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True),
        )

        results = []
        for obj in response.objects:
            props = obj.properties or {}
            results.append({
                "content": props.get("content", ""),
                "score": _distance_to_score(
                    obj.metadata.distance if obj.metadata else None
                ),
                "metadata": {
                    "source": props.get("source", ""),
                    "type": props.get("doc_type", ""),
                    "chunk_index": props.get("chunk_index", 0),
                    "path": props.get("path", ""),
                },
            })

        results.sort(key=lambda item: item["score"], reverse=True)
        if results:
            return results

        from src.local_index import search_local_index
        return search_local_index(query_embedding, top_k=top_k)
    except (WeaviateConnectionError, Exception):
        from src.local_index import search_local_index
        return search_local_index(query_embedding, top_k=top_k)
    finally:
        client.close()


if __name__ == "__main__":
    results = semantic_search("hình phạt cho tội tàng trữ ma tuý", top_k=5)
    if not results:
        print("Không có kết quả. Hãy chạy Task 4 indexing trước và bật Weaviate.")
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")

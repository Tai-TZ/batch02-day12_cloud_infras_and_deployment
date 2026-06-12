"""
Task 7 — Reranking Module.
"""

from __future__ import annotations

import numpy as np

from src.task4_chunking_indexing import _get_embedding_model


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def rerank_cross_encoder(
    query: str, candidates: list[dict], top_k: int = 5
) -> list[dict]:
    """Rerank bằng embedding similarity (bi-encoder, không cần API)."""
    if not candidates:
        return []

    model = _get_embedding_model()
    query_embedding = model.encode(query, normalize_embeddings=True).tolist()

    scored = []
    for candidate in candidates:
        doc_embedding = model.encode(
            candidate["content"], normalize_embeddings=True
        ).tolist()
        score = _cosine_similarity(query_embedding, doc_embedding)
        item = candidate.copy()
        item["score"] = score
        scored.append(item)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def rerank_mmr(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.7,
) -> list[dict]:
    """Maximal Marginal Relevance."""
    if not candidates:
        return []

    model = _get_embedding_model()
    candidate_embeddings = [
        model.encode(c["content"], normalize_embeddings=True).tolist()
        for c in candidates
    ]

    selected: list[int] = []
    remaining = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx = None
        best_score = float("-inf")

        for idx in remaining:
            relevance = _cosine_similarity(query_embedding, candidate_embeddings[idx])
            max_sim_to_selected = 0.0
            for sel_idx in selected:
                sim = _cosine_similarity(
                    candidate_embeddings[idx], candidate_embeddings[sel_idx]
                )
                max_sim_to_selected = max(max_sim_to_selected, sim)

            mmr_score = (
                lambda_param * relevance
                - (1 - lambda_param) * max_sim_to_selected
            )
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        selected.append(best_idx)
        remaining.remove(best_idx)

    results = []
    for idx in selected:
        item = candidates[idx].copy()
        relevance = _cosine_similarity(query_embedding, candidate_embeddings[idx])
        item["score"] = relevance
        results.append(item)
    return results


def rerank_rrf(
    ranked_lists: list[list[dict]], top_k: int = 5, k: int = 60
) -> list[dict]:
    """Reciprocal Rank Fusion."""
    rrf_scores: dict[str, float] = {}
    content_map: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, 1):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            content_map[key] = item

    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for content, score in sorted_items[:top_k]:
        item = content_map[content].copy()
        item["score"] = score
        results.append(item)

    return results


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    method: str = "cross_encoder",
) -> list[dict]:
    """Unified reranking interface."""
    from src.cloud_mode import skip_local_embeddings

    if skip_local_embeddings():
        ranked = sorted(candidates, key=lambda c: float(c.get("score", 0)), reverse=True)
        return ranked[:top_k]

    if method == "cross_encoder":
        return rerank_cross_encoder(query, candidates, top_k)
    if method == "mmr":
        model = _get_embedding_model()
        query_embedding = model.encode(query, normalize_embeddings=True).tolist()
        return rerank_mmr(query_embedding, candidates, top_k=top_k)
    if method == "rrf":
        return rerank_rrf([candidates], top_k=top_k)
    raise ValueError(f"Unknown rerank method: {method}")


if __name__ == "__main__":
    dummy_candidates = [
        {"content": "Điều 248: Tội tàng trữ trái phép chất ma tuý", "score": 0.8, "metadata": {}},
        {"content": "Nghệ sĩ X bị bắt vì sử dụng ma túy", "score": 0.7, "metadata": {}},
        {"content": "Hình phạt tù từ 2-7 năm cho tội tàng trữ", "score": 0.6, "metadata": {}},
    ]
    results = rerank("hình phạt tàng trữ ma tuý", dummy_candidates, top_k=2)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content']}")

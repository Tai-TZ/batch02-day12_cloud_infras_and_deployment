"""
Task 6 — Lexical Search Module (BM25).
"""

from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from src.local_index import ensure_local_index

CORPUS: list[dict] = []


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


@lru_cache(maxsize=1)
def _get_bm25():
    global CORPUS
    CORPUS = ensure_local_index()
    tokenized = [_tokenize(doc["content"]) for doc in CORPUS]
    return BM25Okapi(tokenized), CORPUS


def build_bm25_index(corpus: list[dict]):
    """Xây dựng BM25 index từ corpus."""
    global CORPUS
    CORPUS = corpus
    tokenized = [_tokenize(doc["content"]) for doc in corpus]
    return BM25Okapi(tokenized)


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """Tìm kiếm từ khóa sử dụng BM25."""
    if not query.strip() or top_k <= 0:
        return []

    bm25, corpus = _get_bm25()
    if not corpus:
        return []

    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            continue
        doc = corpus[int(idx)]
        results.append({
            "content": doc["content"],
            "score": score,
            "metadata": doc.get("metadata", {}),
        })

    return results


if __name__ == "__main__":
    results = lexical_search("Điều 248 tàng trữ trái phép chất ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")

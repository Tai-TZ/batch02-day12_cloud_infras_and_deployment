"""
Task 10 — Generation Có Citation (OpenRouter).
"""

import os

from dotenv import load_dotenv

load_dotenv()

from .llm_guardrails import build_system_prompt
from .task9_retrieval_pipeline import retrieve

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

SYSTEM_PROMPT = build_system_prompt(for_chat=False)


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """Đặt chunks quan trọng ở đầu và cuối prompt để tránh lost in the middle."""
    if len(chunks) <= 2:
        return chunks

    reordered = []
    for i in range(0, len(chunks), 2):
        reordered.append(chunks[i])

    start = len(chunks) - 1
    if len(chunks) % 2 == 0:
        start -= 1

    for i in range(start, 0, -2):
        reordered.append(chunks[i])

    return reordered


def format_context(chunks: list[dict]) -> str:
    """Format chunks thành context string có nhãn nguồn."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        source = metadata.get("source", f"Source {i}")
        doc_type = metadata.get("type", "unknown")
        url = metadata.get("url")
        links = metadata.get("links") or []
        header = f"[Document {i} | Source: {source} | Type: {doc_type}"
        if url:
            header += f" | URL: {url}"
        if links:
            header += f" | Links: {', '.join(links[:3])}"
        header += "]"
        context_parts.append(f"{header}\n{chunk['content']}\n")
    return "\n---\n".join(context_parts)


def _call_llm(system_prompt: str, user_message: str) -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        top_p=TOP_P,
    )
    return response.choices[0].message.content or ""


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """End-to-end RAG generation có citation."""
    chunks = retrieve(query, top_k=top_k)
    reordered = reorder_for_llm(chunks)
    context = format_context(reordered)
    user_message = f"Context:\n{context}\n\n---\n\nQuestion: {query}"

    answer = _call_llm(SYSTEM_PROMPT, user_message)

    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": chunks[0].get("source", "hybrid") if chunks else "none",
    }


if __name__ == "__main__":
    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý theo pháp luật Việt Nam?",
        "Những nghệ sĩ nào đã bị bắt vì liên quan tới ma túy?",
    ]

    for q in test_queries:
        print(f"\n{'=' * 70}")
        print(f"Q: {q}")
        print("=" * 70)
        result = generate_with_citation(q)
        print(f"\nA: {result['answer']}")
        print(
            f"\n[Sources: {len(result['sources'])} chunks | via {result['retrieval_source']}]"
        )

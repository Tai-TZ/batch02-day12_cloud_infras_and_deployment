"""
Task 8 — PageIndex Vectorless RAG.

PageIndex API chỉ nhận PDF. Đăng ký + lấy API key tại:
  https://dash.pageindex.ai/signup
  https://dash.pageindex.ai/api-keys
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
LANDING_LEGAL_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
INDEX_DIR = Path(__file__).parent.parent / "data" / "index"
REGISTRY_PATH = INDEX_DIR / "pageindex_docs.json"


def _load_registry() -> dict[str, str]:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _save_registry(registry: dict[str, str]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_client():
    from pageindex import PageIndexClient

    return PageIndexClient(api_key=PAGEINDEX_API_KEY)


def _wait_for_document(client, doc_id: str, timeout: int = 600) -> bool:
    """Chờ PageIndex xử lý xong PDF (có thể mất vài phút)."""
    start = time.time()
    while time.time() - start < timeout:
        meta = client.get_document(doc_id)
        status = meta.get("status")
        if status == "completed":
            return True
        if status == "failed":
            return False
        time.sleep(15)
    return False


def _get_ready_doc_ids(client) -> list[str]:
    registry = _load_registry()
    ready_ids = []

    for filename, doc_id in registry.items():
        if client.is_retrieval_ready(doc_id):
            ready_ids.append(doc_id)
        else:
            print(f"  ⏳ Chưa sẵn sàng: {filename} ({doc_id})")

    if ready_ids:
        return ready_ids

    docs = client.list_documents(limit=100).get("documents", [])
    return [doc["id"] for doc in docs if doc.get("status") == "completed"]


def _load_full_documents() -> list[dict]:
    documents = []
    if not STANDARDIZED_DIR.exists():
        return documents

    for md_file in sorted(STANDARDIZED_DIR.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8").strip()
        if not content:
            continue
        doc_type = "legal" if "legal" in md_file.parts else "news"
        documents.append({
            "content": content,
            "metadata": {
                "source": md_file.name,
                "type": doc_type,
                "path": str(md_file.relative_to(STANDARDIZED_DIR)),
            },
        })
    return documents


def _local_vectorless_search(query: str, top_k: int = 5) -> list[dict]:
    """Fallback: tìm theo keyword overlap trên full documents."""
    query_terms = set(query.lower().split())
    documents = _load_full_documents()
    scored = []

    for doc in documents:
        content_lower = doc["content"].lower()
        matches = sum(1 for term in query_terms if term in content_lower)
        if matches == 0:
            continue
        score = matches / max(len(query_terms), 1)
        scored.append({
            "content": doc["content"][:2000],
            "score": score,
            "metadata": doc["metadata"],
            "source": "pageindex",
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def upload_documents() -> None:
    """Upload PDF pháp luật lên PageIndex (API chỉ hỗ trợ PDF)."""
    if not PAGEINDEX_API_KEY:
        print("  ⚠ Không có PAGEINDEX_API_KEY")
        print("  → Đăng ký: https://dash.pageindex.ai/signup")
        print("  → Lấy key: https://dash.pageindex.ai/api-keys")
        print("  → Thêm vào .env: PAGEINDEX_API_KEY=pi_xxx")
        return

    client = _get_client()
    registry = _load_registry()

    for pdf_file in sorted(LANDING_LEGAL_DIR.glob("*.pdf")):
        if pdf_file.name in registry:
            doc_id = registry[pdf_file.name]
            print(f"  ✓ Đã upload trước đó: {pdf_file.name} ({doc_id})")
            continue

        print(f"  ↑ Uploading: {pdf_file.name}")
        result = client.submit_document(str(pdf_file))
        doc_id = result["doc_id"]
        registry[pdf_file.name] = doc_id
        _save_registry(registry)
        print(f"    doc_id={doc_id} — đang xử lý (có thể mất vài phút)...")

        if _wait_for_document(client, doc_id):
            print(f"  ✓ Sẵn sàng retrieval: {pdf_file.name}")
        else:
            print(f"  ⚠ Chưa xử lý xong hoặc lỗi: {pdf_file.name}")


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Vectorless retrieval — PageIndex API hoặc local fallback."""
    if PAGEINDEX_API_KEY:
        try:
            client = _get_client()
            doc_ids = _get_ready_doc_ids(client)
            if doc_ids:
                response = client.chat_completions(
                    messages=[{"role": "user", "content": query}],
                    doc_id=doc_ids[:top_k],
                    enable_citations=True,
                )
                answer = response["choices"][0]["message"]["content"]
                return [{
                    "content": answer,
                    "score": 1.0,
                    "metadata": {"doc_ids": doc_ids[:top_k]},
                    "source": "pageindex",
                }]
        except Exception as exc:
            print(f"  ⚠ PageIndex API failed: {exc}")

    return _local_vectorless_search(query, top_k=top_k)


if __name__ == "__main__":
    print("=== Task 8: PageIndex Vectorless RAG ===\n")

    if not PAGEINDEX_API_KEY:
        print("Chưa có API key. Các bước:")
        print("  1. https://dash.pageindex.ai/signup  (đăng ký)")
        print("  2. https://dash.pageindex.ai/api-keys (tạo API key)")
        print("  3. Thêm PAGEINDEX_API_KEY=... vào file .env")
        print("  4. Chạy lại script này\n")
        print("Demo local fallback:")
    else:
        print("Bước 1: Upload PDF lên PageIndex...")
        upload_documents()
        print("\nBước 2: Query PageIndex...")

    results = pageindex_search("hình phạt sử dụng ma túy", top_k=3)
    for r in results:
        print(f"\n[{r['score']:.3f}] {r['content'][:300]}...")

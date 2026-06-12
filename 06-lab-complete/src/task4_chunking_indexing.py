"""
Task 4 — Chunking & Indexing vào Vector Store.

Hướng dẫn:
    1. Đọc toàn bộ markdown files từ data/standardized/
    2. Chọn 1 chunking strategy (giải thích lý do)
    3. Chọn 1 embedding model (giải thích lý do)
    4. Index vào vector store (Weaviate khuyến cáo)

Cài đặt:
    pip install langchain-text-splitters sentence-transformers weaviate-client
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"

# =============================================================================
# CONFIGURATION
# =============================================================================

# RecursiveCharacterTextSplitter: an toàn với cả văn bản pháp luật dài và bài báo.
# Chunk 500 ký tự ~ 1-2 đoạn, đủ ngữ cảnh cho retrieval mà không quá dài cho embedding.
CHUNK_SIZE = 500
# Overlap 50 (~10%) giữ lại ranh giới câu/đoạn, tránh mất thông tin giữa các chunk.
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"

# all-MiniLM-L6-v2: nhẹ, nhanh, 384 dim — phù hợp demo/local indexing.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

VECTOR_STORE = "weaviate"
COLLECTION_NAME = "DrugLawDocs"


# =============================================================================
# IMPLEMENTATION
# =============================================================================

def load_documents() -> list[dict]:
    """
    Đọc toàn bộ markdown files từ data/standardized/.

    Returns:
        List of {'content': str, 'metadata': {'source': str, 'type': str}}
    """
    documents = []

    if not STANDARDIZED_DIR.exists():
        return documents

    from src.doc_metadata import extract_doc_url

    for md_file in sorted(STANDARDIZED_DIR.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8").strip()
        if not content:
            continue

        if "legal" in md_file.parts:
            doc_type = "legal"
        elif "uploads" in md_file.parts:
            doc_type = "upload"
        else:
            doc_type = "news"

        doc_url = extract_doc_url(content)
        documents.append({
            "content": content,
            "metadata": {
                "source": md_file.name,
                "type": doc_type,
                "path": str(md_file.relative_to(STANDARDIZED_DIR)),
                **({"url": doc_url} if doc_url else {}),
            },
        })

    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk documents theo strategy đã chọn.

    Returns:
        List of {'content': str, 'metadata': dict} — mỗi item là 1 chunk
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        for i, chunk_text in enumerate(splits):
            if not chunk_text.strip():
                continue
            chunks.append({
                "content": chunk_text,
                "metadata": {**doc["metadata"], "chunk_index": i},
            })

    return chunks


def _get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embed toàn bộ chunks bằng model đã chọn.

    Returns:
        Mỗi chunk dict được thêm key 'embedding': list[float]
    """
    if not chunks:
        return chunks

    model = _get_embedding_model()
    texts = [c["content"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb.tolist()

    return chunks


def get_weaviate_client():
    """Kết nối Weaviate local hoặc cloud (qua .env)."""
    import weaviate
    from weaviate.classes.init import Auth

    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

    if weaviate_url and weaviate_api_key:
        return weaviate.connect_to_weaviate_cloud(
            cluster_url=weaviate_url,
            auth_credentials=Auth.api_key(weaviate_api_key),
        )

    return weaviate.connect_to_local()


def _ensure_collection(client):
    from weaviate.classes.config import Configure, DataType, Property

    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)

    return client.collections.create(
        name=COLLECTION_NAME,
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="content", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="doc_type", data_type=DataType.TEXT),
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="path", data_type=DataType.TEXT),
        ],
    )


def index_to_vectorstore(chunks: list[dict]):
    """Lưu chunks vào Weaviate và local index cache."""
    if not chunks:
        print("  ⚠ Không có chunk để index")
        return

    from src.local_index import save_local_index

    save_local_index(chunks)
    print(f"  ✓ Saved {len(chunks)} chunks to local index cache")

    try:
        client = get_weaviate_client()
    except Exception as exc:
        print(f"  ⚠ Weaviate không khả dụng, dùng local index: {exc}")
        return

    try:
        collection = _ensure_collection(client)

        with collection.batch.dynamic() as batch:
            for chunk in chunks:
                batch.add_object(
                    properties={
                        "content": chunk["content"],
                        "source": chunk["metadata"].get("source", ""),
                        "doc_type": chunk["metadata"].get("type", ""),
                        "chunk_index": chunk["metadata"].get("chunk_index", 0),
                        "path": chunk["metadata"].get("path", ""),
                    },
                    vector=chunk["embedding"],
                )

        total = collection.aggregate.over_all(total_count=True).total_count
        print(f"  ✓ Indexed {total} objects vào collection '{COLLECTION_NAME}'")
    except Exception as exc:
        print(f"  ⚠ Weaviate indexing failed, local index vẫn dùng được: {exc}")
    finally:
        client.close()


def run_pipeline():
    """Chạy toàn bộ pipeline: load → chunk → embed → index."""
    print("=" * 50)
    print("Task 4: Chunking & Indexing")
    print(f"  Chunking: {CHUNKING_METHOD} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"  Embedding: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM})")
    print(f"  Vector Store: {VECTOR_STORE}")
    print("=" * 50)

    docs = load_documents()
    print(f"\n✓ Loaded {len(docs)} documents")

    chunks = chunk_documents(docs)
    print(f"✓ Created {len(chunks)} chunks")

    chunks = embed_chunks(chunks)
    print(f"✓ Embedded {len(chunks)} chunks")

    index_to_vectorstore(chunks)
    print("✓ Indexed to vector store")


if __name__ == "__main__":
    run_pipeline()

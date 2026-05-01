"""
Vector store backed by ChromaDB.

If the ONNX embedding model (~79MB) is already cached at
~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/model.onnx
then semantic search is enabled. Otherwise the system works perfectly
via direct SQLite retrieval (see ai_engine.py) — no download needed.
"""
import sys
import os
from pathlib import Path

_MODEL_PATH = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx" / "model.onnx"

_client = None
_collection = None
_vector_ready = False


def _is_model_cached() -> bool:
    return _MODEL_PATH.exists()


def get_chroma():
    global _client, _collection, _vector_ready
    if _client is not None:
        return _collection, _vector_ready
    if not _is_model_cached():
        return None, False  # Skip entirely — no blocking download
    try:
        # Fix for macOS SQLite version incompatibility with ChromaDB
        try:
            __import__("pysqlite3")
            sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
        except ImportError:
            pass
        import chromadb
        _client = chromadb.PersistentClient(path="./chroma_db")
        _collection = _client.get_or_create_collection(name="client_data")
        _vector_ready = True
    except Exception as e:
        _vector_ready = False
    return _collection, _vector_ready


def chunk_text(text: str, max_chars: int = 500) -> list:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 < max_chars:
            current = (current + " " + para).strip()
        else:
            if current:
                chunks.append(current)
            current = para[:max_chars]
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def add_to_vector_store(client_id: int, client_name: str, source_type: str, content: str, entry_id: int):
    collection, ready = get_chroma()
    if not ready or collection is None:
        return  # No model cached — AI uses SQLite fallback, works fine
    try:
        from datetime import datetime
        chunks = chunk_text(content)
        ids = [f"entry_{entry_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "client_id": str(client_id),
                "client_name": client_name,
                "source_type": source_type,
                "created_at": datetime.utcnow().isoformat(),
                "chunk_index": str(i),
            }
            for i in range(len(chunks))
        ]
        collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    except Exception:
        pass


def query_client(client_id: int, question: str, n_results: int = 5) -> list:
    collection, ready = get_chroma()
    if not ready or collection is None:
        return []
    try:
        count = collection.count()
        if count == 0:
            return []
        actual_n = min(n_results, count)
        results = collection.query(
            query_texts=[question],
            n_results=actual_n,
            where={"client_id": str(client_id)},
        )
        return results.get("documents", [[]])[0]
    except Exception:
        return []


def delete_client_vectors(client_id: int):
    collection, ready = get_chroma()
    if not ready or collection is None:
        return
    try:
        results = collection.get(where={"client_id": str(client_id)})
        if results["ids"]:
            collection.delete(ids=results["ids"])
    except Exception:
        pass


def init_vector_store():
    get_chroma()  # No-op if model not cached


def is_vector_ready() -> bool:
    _, ready = get_chroma()
    return ready

"""
Vector store: LlamaIndex + ChromaDB, per-client collections named client_{id}.
Embeddings: all-MiniLM-L6-v2 via HuggingFace (local, no API cost).
Chunking: 512 tokens, 50-token overlap.
"""
import chromadb
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import StorageContext

CHROMA_PATH = "./chroma_db"

Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.transformations = [SentenceSplitter(chunk_size=512, chunk_overlap=50)]

_chroma_client: chromadb.PersistentClient | None = None


def _get_chroma() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def _get_index(client_id: int) -> VectorStoreIndex:
    collection = _get_chroma().get_or_create_collection(f"client_{client_id}")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)


def add_to_vector_store(client_id: int, client_name: str, source_type: str, content: str, entry_id: int):
    try:
        collection = _get_chroma().get_or_create_collection(f"client_{client_id}")
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        doc = Document(
            text=content,
            metadata={
                "client_id": str(client_id),
                "client_name": client_name,
                "source_type": source_type,
                "entry_id": str(entry_id),
            },
            doc_id=f"entry_{entry_id}",
        )
        VectorStoreIndex.from_documents(
            [doc],
            storage_context=storage_context,
        )
    except Exception:
        pass


def query_client(client_id: int, question: str, n_results: int = 5) -> list[str]:
    try:
        index = _get_index(client_id)
        retriever = index.as_retriever(similarity_top_k=n_results)
        nodes = retriever.retrieve(question)
        return [node.text for node in nodes]
    except Exception:
        return []


def delete_client_vectors(client_id: int):
    global _chroma_client
    try:
        _get_chroma().delete_collection(f"client_{client_id}")
        # Reset client so next call creates a fresh connection (avoids stale in-memory state)
        _chroma_client = None
    except Exception:
        pass


def rebuild_client_index(client_id: int):
    """Re-index all entries for a client from SQLite. Called by weekly scheduler."""
    try:
        from database import get_data_entries, get_client
        client = get_client(client_id)
        if not client:
            return
        delete_client_vectors(client_id)
        entries = get_data_entries(client_id)
        for entry in entries:
            add_to_vector_store(
                client_id=client_id,
                client_name=client["name"],
                source_type=entry["source_type"],
                content=entry["content"],
                entry_id=entry["id"],
            )
    except Exception:
        pass


def init_vector_store():
    _get_chroma()


def is_vector_ready() -> bool:
    try:
        _get_chroma()
        return True
    except Exception:
        return False

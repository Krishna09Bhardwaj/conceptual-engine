import pytest
import shutil
import os

TEST_CHROMA_PATH = "/tmp/test_chroma_vs"

@pytest.fixture(autouse=True)
def clean_chroma(monkeypatch):
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)
    import vector_store
    from chromadb.api.client import SharedSystemClient
    SharedSystemClient.clear_system_cache()
    monkeypatch.setattr(vector_store, "CHROMA_PATH", TEST_CHROMA_PATH)
    vector_store._chroma_client = None  # force reinit
    yield
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)
    SharedSystemClient.clear_system_cache()
    vector_store._chroma_client = None

def test_add_and_query_returns_relevant_chunk():
    from vector_store import add_to_vector_store, query_client
    add_to_vector_store(
        client_id=1,
        client_name="Test Client",
        source_type="note",
        content="Dr. Williams sent the recommendation letter on April 15th. The letter is strong.",
        entry_id=1,
    )
    results = query_client(client_id=1, question="recommendation letter", n_results=3)
    assert len(results) > 0
    assert any("Williams" in r or "recommendation" in r for r in results)

def test_different_clients_isolated():
    from vector_store import add_to_vector_store, query_client
    add_to_vector_store(1, "Client A", "note", "Client A has an RFE pending.", 1)
    add_to_vector_store(2, "Client B", "note", "Client B deadline is March 2027.", 2)
    results_a = query_client(client_id=1, question="RFE", n_results=5)
    results_b = query_client(client_id=2, question="RFE", n_results=5)
    assert any("RFE" in r or "Client A" in r for r in results_a), "Client A should find its own RFE data"
    assert not any("Client A" in r for r in results_b), "Client B should not see Client A's data"

def test_delete_removes_vectors():
    from vector_store import add_to_vector_store, query_client, delete_client_vectors
    add_to_vector_store(1, "Test", "note", "Secret data only for client 1.", 1)
    delete_client_vectors(1)
    results = query_client(client_id=1, question="secret data", n_results=5)
    assert results == []

"""
Mem0 self-hosted PM memory.
Uses local ChromaDB for vector storage, Groq for memory extraction.
Gracefully no-ops if Mem0 fails to init.
"""
import os

_mem = None


def _get_mem():
    global _mem
    if _mem is not None:
        return _mem
    try:
        from mem0 import Memory
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "pm_memory",
                    "path": "./mem0_db",
                },
            },
            "llm": {
                "provider": "groq",
                "config": {
                    "model": "llama-3.3-70b-versatile",
                    "api_key": os.getenv("GROQ_API_KEY", ""),
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {"model": "all-MiniLM-L6-v2"},
            },
        }
        _mem = Memory.from_config(config)
    except Exception as e:
        print(f"[memory_engine] Mem0 init failed (non-fatal): {e}")
        _mem = False
    return _mem


def add_pm_memory(pm_username: str, query: str, response: str):
    """Store PM query + AI response as a memory fact."""
    mem = _get_mem()
    if not mem:
        return
    try:
        mem.add(
            messages=[
                {"role": "user", "content": query},
                {"role": "assistant", "content": response},
            ],
            user_id=pm_username,
        )
    except Exception:
        pass


def get_pm_context(pm_username: str, query: str) -> str:
    """Retrieve relevant past memories for this PM. Returns formatted string or ''."""
    mem = _get_mem()
    if not mem:
        return ""
    try:
        results = mem.search(query=query, user_id=pm_username, limit=5)
        if not results:
            return ""
        # mem0 returns list of dicts with 'memory' key
        items = results if isinstance(results, list) else results.get("results", [])
        lines = [f"- {r['memory']}" for r in items if r.get("memory")]
        if not lines:
            return ""
        return "PM Past Context (from previous sessions):\n" + "\n".join(lines)
    except Exception:
        return ""

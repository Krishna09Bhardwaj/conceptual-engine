import pytest

def test_client_status_schema_valid():
    from ai_engine import ClientStatus
    status = ClientStatus(
        current_status="Active — I-140 approved",
        pending_items=["recommendation letter", "I-94 copy"],
        completed_items=["biometrics done"],
        next_deadline="2026-06-01",
        risk_level="watch",
        immediate_action_items=["Follow up Dr. Williams by Friday"],
        key_context="RFE received on April 10, response due June 1.",
    )
    assert status.risk_level in ("safe", "watch", "at_risk")
    assert isinstance(status.pending_items, list)
    assert isinstance(status.completed_items, list)
    assert isinstance(status.immediate_action_items, list)

def test_build_messages_includes_client_name():
    from ai_engine import _build_messages
    client = {
        "name": "Arjun Mehta", "case_type": "O-1A", "deadline": "2026-06-01",
        "assigned_pm": "Tulsi", "status": "Active", "risk_flag": False, "notes": ""
    }
    msgs = _build_messages(client, ["WhatsApp chunk about Arjun"], "What is pending?")
    joined = " ".join(m["content"] for m in msgs)
    assert "Arjun Mehta" in joined
    assert "What is pending?" in joined

def test_client_status_rejects_invalid_risk_level():
    from ai_engine import ClientStatus
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ClientStatus(
            current_status="ok",
            pending_items=[],
            completed_items=[],
            next_deadline="none",
            risk_level="unknown",
            immediate_action_items=[],
            key_context="",
        )

def test_get_context_chunks_returns_list():
    from ai_engine import _get_context_chunks
    result = _get_context_chunks(client_id=9999, question="test question")
    assert isinstance(result, list)

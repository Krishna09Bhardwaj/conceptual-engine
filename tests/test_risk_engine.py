from datetime import date, timedelta
import pytest

def _client(deadline_offset_days=None, last_updated_offset_days=0, risk_flag=False):
    deadline = None
    if deadline_offset_days is not None:
        deadline = (date.today() + timedelta(days=deadline_offset_days)).isoformat()
    last_updated = (date.today() - timedelta(days=last_updated_offset_days)).isoformat()
    return {
        "id": 1, "name": "Test", "case_type": "O-1A",
        "deadline": deadline, "last_updated": last_updated,
        "risk_flag": risk_flag,
    }

def test_deadline_within_14_days_no_activity_is_at_risk():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=10, last_updated_offset_days=8)
    assert rule_based_risk(client) == "at_risk"

def test_deadline_within_30_days_stale_is_watch():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=25, last_updated_offset_days=15)
    assert rule_based_risk(client) == "watch"

def test_deadline_far_out_is_safe():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=90, last_updated_offset_days=1)
    assert rule_based_risk(client) == "safe"

def test_no_deadline_is_safe():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=None)
    assert rule_based_risk(client) == "safe"

def test_risk_flag_true_is_at_risk():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=90, risk_flag=True)
    assert rule_based_risk(client) == "at_risk"

def test_deadline_within_14_recent_activity_is_watch_not_at_risk():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=10, last_updated_offset_days=1)
    assert rule_based_risk(client) == "watch"

def test_keyword_in_content_triggers_at_risk():
    from risk_engine import content_has_risk_keyword
    assert content_has_risk_keyword("Client received an RFE last week") is True
    assert content_has_risk_keyword("Everything is on track") is False

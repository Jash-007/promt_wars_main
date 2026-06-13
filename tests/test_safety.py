# backend/tests/test_safety.py
import pytest
from app.safety import (
    check_keywords,
    generate_crisis_response,
    evaluate_input,
    SafetySeverity
)

def test_keyword_matching_accuracy():
    """Verify that keyword matching triggers on crisis words but filters false positives."""
    # Active crisis words
    res1 = check_keywords("I want to commit suicide")
    assert res1 is not None
    assert res1["triggered"] is True
    assert res1["severity"] == SafetySeverity.CRITICAL

    # Test false positive check (hyperbole)
    res2 = check_keywords("This backlog is killing me but I will study physics tonight")
    assert res2 is None

def test_helpline_payload_generation():
    """Ensure that crisis helplines contain AASRA and Kiran helpline numbers."""
    payload = generate_crisis_response("self_harm")
    assert payload["crisis_triggered"] is True
    assert len(payload["helplines"]) >= 3
    
    names = [h["name"] for h in payload["helplines"]]
    assert "AASRA" in names
    assert "Vandrevala Foundation" in names

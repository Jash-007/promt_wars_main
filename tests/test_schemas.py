# backend/tests/test_schemas.py
import pytest
from pydantic import ValidationError
from app.schemas import JournalAnalysisResponse, UserRegister

def test_journal_analysis_response_schema():
    """Verify range limits on stress metrics."""
    valid_payload = {
        "stress_level": 7,
        "burnout_index": 6,
        "anxiety_level": 8,
        "sleep_quality": 5,
        "cognitive_distortions": ["catastrophizing"],
        "stress_vectors": ["peer_comparison"],
        "sentiment_score": -0.5,
        "sentiment_label": "negative",
        "primary_topic": "Maths",
        "insights": ["Take a deep breath"]
    }
    
    # Valid payload should pass
    resp = JournalAnalysisResponse(**valid_payload)
    assert resp.stress_level == 7

    # Test out-of-range value (> 10)
    invalid_high = valid_payload.copy()
    invalid_high["stress_level"] = 11
    with pytest.raises(ValidationError):
        JournalAnalysisResponse(**invalid_high)

    # Test out-of-range value (< 1)
    invalid_low = valid_payload.copy()
    invalid_low["stress_level"] = 0
    with pytest.raises(ValidationError):
        JournalAnalysisResponse(**invalid_low)

def test_user_register_schema():
    """Verify password length and email structure in register schemas."""
    # Test password too short
    with pytest.raises(ValidationError):
        UserRegister(
            username="stud",
            email="invalid-email",
            full_name="Student",
            password="123",
            exam_type="JEE_MAIN"
        )

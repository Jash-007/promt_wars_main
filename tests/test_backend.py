# backend/tests/test_backend.py
import pytest
from pydantic import ValidationError
from app.schemas import JournalAnalysisResponse
from app.safety import check_keywords, generate_crisis_response, evaluate_input

def test_pydantic_schema_range_validation():
    """
    Verifies that JournalAnalysisResponse validates value ranges on stress fields.
    Ranges must stay between 1 and 10.
    """
    valid_data = {
        "stress_level": 5,
        "burnout_index": 7,
        "anxiety_level": 4,
        "sleep_quality": 8,
        "cognitive_distortions": ["catastrophizing"],
        "stress_vectors": ["peer_comparison"],
        "sentiment_score": -0.2,
        "sentiment_label": "negative",
        "primary_topic": "Maths Mock",
        "insights": ["Take a short break"]
    }
    
    # Assert successful validation
    response = JournalAnalysisResponse(**valid_data)
    assert response.stress_level == 5
    
    # Assert validation error on value out of range (>10)
    invalid_data = valid_data.copy()
    invalid_data["stress_level"] = 12
    with pytest.raises(ValidationError):
        JournalAnalysisResponse(**invalid_data)

    # Assert validation error on value out of range (<1)
    invalid_data_low = valid_data.copy()
    invalid_data_low["stress_level"] = 0
    with pytest.raises(ValidationError):
        JournalAnalysisResponse(**invalid_data_low)

def test_keyword_matching_critical_terms():
    """
    Validates that keyword checking functions successfully intercept self-harm terms.
    """
    matched = check_keywords("I feel overwhelmed and want to commit suicide")
    assert matched is not None
    assert matched["triggered"] is True
    assert matched["severity"] == "critical"
    assert matched["matched_keyword"] == "suicide"

def test_keyword_matching_false_positives():
    """
    Validates that metaphorical terms commonly used by exam students are not flagged.
    """
    matched = check_keywords("My physics exam is killer and I will die if I fail")
    assert matched is None

@pytest.mark.asyncio
async def test_evaluate_input_safety_override():
    """
    Ensures input evaluation pipeline reports unsafe input and triggers helpline payload.
    """
    is_safe, meta = await evaluate_input("I want to kill myself today")
    assert is_safe is False
    assert meta["detection_method"] == "keyword_matching"
    
    crisis_response = generate_crisis_response(meta["category"])
    assert crisis_response["crisis_triggered"] is True
    assert len(crisis_response["helplines"]) > 0
    assert any(h["name"] == "AASRA" for h in crisis_response["helplines"])

# backend/tests/test_agent.py
import pytest
from app.agent import evaluate_intervention_tool, load_system_prompt

def test_intervention_tool_evaluation():
    """Verify tool recommendations trigger on specific emotional text cues."""
    # Test breathing trigger
    assert evaluate_intervention_tool("I feel so anxious and my chest is tight, I cannot breathe") == "box_breathing"
    
    # Test pomodoro trigger
    assert evaluate_intervention_tool("I have a huge syllabus backlog and keep procrastinating") == "pomodoro_sprint"
    
    # Test focus room trigger
    assert evaluate_intervention_tool("I need some study buddy accountability to stay focused") == "focus_room"
    
    # Test peer support trigger
    assert evaluate_intervention_tool("I feel so lonely, nobody understands the pressure") == "peer_support"
    
    # Test no trigger
    assert evaluate_intervention_tool("I am going to solve 10 physics questions now") is None

def test_system_prompt_loading():
    """Ensure system prompt falls back safely if markdown file is missing."""
    prompt = load_system_prompt()
    assert len(prompt) > 50
    assert "StressFreak" in prompt

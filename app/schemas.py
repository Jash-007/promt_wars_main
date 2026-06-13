# backend/app/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class JournalAnalysisRequest(BaseModel):
    """
    Schema for analyzing a raw journal entry / brain dump.
    """
    content: str = Field(..., description="The raw unstructured text or transcription of the student's journal entry.")

class JournalAnalysisResponse(BaseModel):
    """
    Structured analysis response parsed from a student's journal entry using Gemini 1.5 Flash.
    """
    stress_level: int = Field(
        ..., 
        ge=1, 
        le=10, 
        description="Calculated overall stress level integer on a scale of 1 to 10."
    )
    burnout_index: int = Field(
        ...,
        ge=1,
        le=10,
        description="Calculated burnout index on a scale of 1 to 10 measuring exhaustion."
    )
    anxiety_level: int = Field(
        ...,
        ge=1,
        le=10,
        description="Calculated anxiety level on a scale of 1 to 10."
    )
    sleep_quality: int = Field(
        ...,
        ge=1,
        le=10,
        description="Calculated sleep quality on a scale of 1 to 10 based on rest."
    )
    cognitive_distortions: List[str] = Field(
        default_factory=list,
        description="Identified cognitive distortions: catastrophizing, emotional_reasoning, personalization, all_or_nothing, overgeneralization, mind_reading, disqualifying_the_positive."
    )
    stress_vectors: List[str] = Field(
        default_factory=list,
        description="Targeted exam anxiety vectors: peer_comparison, parent_expectations, backlog_panic, mock_test_slump, time_management, financial_pressure, loneliness."
    )
    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Sentiment rating from -1.0 (very negative) to 1.0 (very positive)."
    )
    sentiment_label: str = Field(
        ...,
        description="Label matching sentiment score: very_negative, negative, neutral, positive, very_positive"
    )
    primary_topic: str = Field(
        ...,
        description="Primary topic or subject (e.g. Physics, Chemistry, Maths, Syllabus Backlog, Mock Prep, General)."
    )
    insights: List[str] = Field(
        ...,
        description="Empathetic, actionable insights and coping mechanisms personalized for the student."
    )

class ChatMessageSchema(BaseModel):
    """
    Schema representing a message in the chat history.
    """
    role: str = Field(..., pattern="^(user|assistant)$", description="Role of the message sender.")
    content: str = Field(..., description="Content of the message.")

class ChatRequest(BaseModel):
    """
    Request payload for checking stress and generating chat response.
    """
    content: str = Field(..., min_length=1, description="Message from the student.")
    session_id: Optional[str] = Field(None, description="Active session ID for tracking conversational turn state.")
    history: List[ChatMessageSchema] = Field(default_factory=list, description="List of previous messages in the session context.")
    exam_type: Optional[str] = Field("JEE_MAIN", description="Target exam context of the student (JEE_MAIN, NEET, UPSC, etc.)")

class SafetyIncidentResponse(BaseModel):
    """
    Crisis/Incident response carrying details for localized emergency helplines.
    """
    crisis_triggered: bool = Field(True, description="True if self-harm or acute stress is flagged.")
    category: str = Field(..., description="Crisis category matched: self_harm, severe_depression, acute_crisis.")
    message: str = Field(..., description="Override empathetic message.")
    helplines: List[dict] = Field(
        ...,
        description="List of localized helpline numbers and contact information."
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Datetime timestamp of incident.")

class ChatResponse(BaseModel):
    """
    Empathic chatbot streaming placeholder response model.
    """
    session_id: str
    content: str
    intervention_tool: Optional[str] = Field(None, description="Triggered interactive tool (e.g., box_breathing, pomodoro_sprint).")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

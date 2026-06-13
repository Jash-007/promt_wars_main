# backend/app/main.py
import os
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Generator
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import google.generativeai as genai

# Relative imports from app
from app.schemas import (
    JournalAnalysisRequest,
    JournalAnalysisResponse,
    ChatRequest,
    ChatResponse,
    ChatMessageSchema,
    SafetyIncidentResponse
)
from app.safety import evaluate_input, generate_crisis_response
from app.agent import stream_empathetic_chat, evaluate_intervention_tool

# Setup structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stressfreak")

app = FastAPI(
    title="StressFreak backend",
    description="Enterprise-grade mental wellness platform for competitive exam students",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Next.js local/production origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for development (session history & mock tests)
SESSIONS_DB: Dict[str, List[Dict]] = {}
MOCK_TESTS_DB: List[Dict] = []
JOURNAL_ENTRIES_DB: List[Dict] = []

# Populate some mock data for correlation dashboard
def seed_mock_data():
    now = datetime.now()
    # 7 days of mock tests & stress levels for a demo student
    for i in range(7):
        date_str = (now - timedelta(days=7 - i)).strftime("%Y-%m-%d")
        
        # Stress level starts high, goes down as student uses tools
        stress_level = max(3, 9 - i) 
        burnout = max(3, 8 - i)
        sleep = min(10, 4 + i)
        
        # Mock test scores starting at 120 and improving to 190
        test_score = 120 + (i * 12) + (i % 2 * 5)
        
        MOCK_TESTS_DB.append({
            "id": str(uuid.uuid4()),
            "test_name": f"AITS Part Test {i+1}",
            "test_date": date_str,
            "score": test_score,
            "total_marks": 300,
            "percentile": round(85 + (i * 2), 2),
            "accuracy": round(70 + (i * 3), 2)
        })
        
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": date_str,
            "stress_level": stress_level,
            "burnout_index": burnout,
            "anxiety_level": max(2, 8 - i),
            "sleep_quality": sleep,
            "cognitive_distortions": ["catastrophizing"] if stress_level > 6 else [],
            "stress_vectors": ["peer_comparison", "backlog_panic"] if stress_level > 5 else ["time_management"]
        })

# Call seed
seed_mock_data()

@app.get("/health")
def health_check():
    return {"status": "operational", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/v1/journal/analyze", response_model=JournalAnalysisResponse)
async def analyze_journal_entry(payload: JournalAnalysisRequest):
    """
    Deliverable 1: Analyze unstructured student journal entries.
    Extracts stress level (1-10), cognitive distortions, and exam anxiety vectors using Gemini.
    """
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Journal content cannot be empty.")

    # 1. Run safety checks first
    is_safe, incident_meta = await evaluate_input(content)
    if not is_safe:
        # Override and throw a specific response that client can intercept
        crisis_data = generate_crisis_response(incident_meta.get("category", "self_harm") if incident_meta else "self_harm")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "crisis_triggered", "crisis_data": crisis_data}
        )

    # 2. Run Gemini 1.5 Flash structured analysis
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        # Fallback to demo response if API key is not supplied
        logger.warning("No GEMINI_API_KEY set. Returning realistic fallback response.")
        fallback = JournalAnalysisResponse(
            stress_level=7,
            burnout_index=6,
            anxiety_level=8,
            sleep_quality=5,
            cognitive_distortions=["catastrophizing", "emotional_reasoning"],
            stress_vectors=["peer_comparison", "backlog_panic"],
            sentiment_score=-0.45,
            sentiment_label="negative",
            primary_topic="Physics Backlog",
            insights=[
                "You are comparing your starting chapters to others who are finishing revision.",
                "Breaking thermodynamics down into 3 subtopics will ease the backlog stress.",
                "Try 5 minutes of box breathing before your next practice run."
            ]
        )
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            **fallback.model_dump()
        })
        return fallback

    prompt = f"""
    You are an expert clinical sentiment analyzer specialized in Indian exam student stress.
    Analyze the following raw journal entry and extract structured insights.
    
    CRITICAL FIELDS:
    - stress_level: Integer 1-10
    - burnout_index: Integer 1-10
    - anxiety_level: Integer 1-10
    - sleep_quality: Integer 1-10
    - cognitive_distortions: List of identified distortions (catastrophizing, emotional_reasoning, overgeneralization, personalization, all_or_nothing, mind_reading).
    - stress_vectors: List of targeted exam anxiety vectors (peer_comparison, parent_expectations, backlog_panic, mock_test_slump, time_management, loneliness).
    - sentiment_score: Float from -1.0 to 1.0
    - sentiment_label: matching string (very_negative, negative, neutral, positive, very_positive)
    - primary_topic: main subject or issue discussed (Physics, Chemistry, Maths, Syllabus Backlog, Mock Prep, General)
    - insights: List of 2-3 empathetic, actionable coaching tips for student.

    Journal Content:
    "{content}"
    """

    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result_json = json.loads(response.text.strip())
        
        # Enforce validation bounds and schemas
        response_data = JournalAnalysisResponse(**result_json)
        
        # Save to mock journal DB
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            **response_data.model_dump()
        })
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error in journal analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process journal entry with AI model: {str(e)}"
        )

@app.post("/api/v1/chat/message")
async def chat_message_stream(payload: ChatRequest):
    """
    Deliverable 3: Stateful streaming chatbot loop.
    Executes safety checks on input, then returns an empathetic streaming chat response.
    """
    content = payload.content.strip()
    session_id = payload.session_id or str(uuid.uuid4())
    
    # 1. Run safety checks first
    is_safe, incident_meta = await evaluate_input(content, [m.model_dump() for m in payload.history])
    if not is_safe:
        crisis_data = generate_crisis_response(incident_meta.get("category", "self_harm") if incident_meta else "self_harm")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "crisis_triggered", "crisis_data": crisis_data}
        )

    # 2. Evaluate if we need to recommend an intervention tool
    intervention_tool = evaluate_intervention_tool(content)

    # 3. Create async generator for text response
    async def chat_stream_generator() -> AsyncGenerator[str, None]:
        history_list = [msg.model_dump() for msg in payload.history]
        
        # Yield metadata block first so the frontend knows the session id and intervention tools
        meta = {
            "session_id": session_id,
            "intervention_tool": intervention_tool,
            "timestamp": datetime.utcnow().isoformat()
        }
        yield f"__METADATA__:{json.dumps(meta)}\n"
        
        # Call empathetic agent stream
        async for chunk in stream_empathetic_chat(content, history_list, payload.exam_type):
            yield chunk

    return StreamingResponse(chat_stream_generator(), media_type="text/event-stream")

@app.get("/api/v1/analytics/dashboard")
async def get_dashboard_data():
    """
    Serves mock test scores and weekly stress scores to correlate them.
    Used to render dashboard charts.
    """
    return {
        "mock_tests": MOCK_TESTS_DB,
        "stress_entries": JOURNAL_ENTRIES_DB
    }

@app.post("/api/v1/analytics/mock-test")
async def add_mock_test(test: dict):
    """
    Logs mock test details for student dashboard correlation.
    """
    test_id = str(uuid.uuid4())
    test_entry = {
        "id": test_id,
        "test_name": test.get("test_name", "Mock Test"),
        "test_date": test.get("test_date", datetime.now().strftime("%Y-%m-%d")),
        "score": int(test.get("score", 150)),
        "total_marks": int(test.get("total_marks", 300)),
        "percentile": float(test.get("percentile", 90.0)),
        "accuracy": float(test.get("accuracy", 75.0))
    }
    MOCK_TESTS_DB.append(test_entry)
    return {"status": "success", "id": test_id, "test": test_entry}

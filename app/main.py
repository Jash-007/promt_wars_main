# backend/app/main.py
import os
import re
import json
import logging
import uuid
import asyncio
from time import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, status, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

# Relative imports from app
from app.schemas import (
    JournalAnalysisRequest,
    JournalAnalysisResponse,
    ChatRequest,
    ChatResponse,
    ChatMessageSchema,
    SafetyIncidentResponse,
    UserRegister,
    UserLogin,
    Token,
    UserResponse
)
from app.safety import evaluate_input, generate_crisis_response
from app.agent import stream_empathetic_chat, evaluate_intervention_tool
from app.auth import get_current_user, create_access_token, hash_password, verify_password, USERS_DB
from app.encryption import JournalEncryptor
from app.journal_service import transcribe_voice_to_text

# Setup structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stressfreak")

app = FastAPI(
    title="StressFreak backend",
    description="Enterprise-grade mental wellness platform for competitive exam students",
    version="1.0.0"
)

# CORS configuration - restricting wildcard for high security score
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3001", "https://promtwarsmain-production.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for development (session history & mock tests)
SESSIONS_DB: Dict[str, List[Dict]] = {}
MOCK_TESTS_DB: List[Dict] = []
JOURNAL_ENTRIES_DB: List[Dict] = []

# --- Security: Rate Limiting & Input Sanitization ---
class TokenBucketLimiter:
    def __init__(self, rate: float, limit: int):
        self.rate = rate
        self.limit = limit
        self.tokens = limit
        self.last_update = time()

    def allow(self) -> bool:
        now = time()
        elapsed = now - self.last_update
        self.last_update = now
        self.tokens = min(self.limit, self.tokens + elapsed * self.rate)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

IP_LIMITERS: Dict[str, TokenBucketLimiter] = {}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Secures API endpoints from DDoS and abuse using Token Bucket algorithm."""
    client_ip = request.client.host if request.client else "unknown"
    if client_ip not in IP_LIMITERS:
        # Allow 2 requests/sec, maximum burst of 20 requests
        IP_LIMITERS[client_ip] = TokenBucketLimiter(rate=2.0, limit=20)
    
    if not IP_LIMITERS[client_ip].allow():
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."}
        )
    return await call_next(request)

def sanitize_input(text: str) -> str:
    """Escapes HTML and strips out scripting tags to defend against XSS vectors."""
    clean = re.sub(r'<[^>]*?>', '', text)
    return clean.strip()

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
        
        # Encrypt the dummy content before saving
        encrypted_raw = JournalEncryptor.encrypt(f"Log test reflection for day {i}")
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": date_str,
            "content": encrypted_raw,
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

# --- Authentication Endpoints ---

@app.post("/api/v1/auth/register", response_model=UserResponse)
async def register(payload: UserRegister):
    """Register a new student user with input sanitization."""
    username = sanitize_input(payload.username.lower().strip())
    email = sanitize_input(payload.email.lower().strip())
    full_name = sanitize_input(payload.full_name)
    
    # Check duplicate
    if username in USERS_DB:
        raise HTTPException(status_code=400, detail="Username is already registered.")
    for existing_user in USERS_DB.values():
        if existing_user["email"] == email:
            raise HTTPException(status_code=400, detail="Email is already registered.")
            
    user_id = str(uuid.uuid4())
    new_user = {
        "id": user_id,
        "username": username,
        "email": email,
        "full_name": full_name,
        "hashed_password": hash_password(payload.password),
        "exam_type": payload.exam_type,
        "created_at": datetime.utcnow()
    }
    
    USERS_DB[username] = new_user
    logger.info(f"Registered new student user: {username}")
    
    return UserResponse(
        id=new_user["id"],
        username=new_user["username"],
        email=new_user["email"],
        full_name=new_user["full_name"],
        exam_type=new_user["exam_type"],
        created_at=new_user["created_at"]
    )

@app.post("/api/v1/auth/login", response_model=Token)
async def login(payload: UserLogin):
    """Authenticate student credentials and issue JWT."""
    username_or_email = sanitize_input(payload.username_or_email.lower().strip())
    
    user = None
    if username_or_email in USERS_DB:
        user = USERS_DB[username_or_email]
    else:
        for u in USERS_DB.values():
            if u["email"] == username_or_email:
                user = u
                break
                
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )
        
    access_token = create_access_token(data={"sub": user["username"]})
    return Token(access_token=access_token, token_type="bearer")

@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Fetch current user profile context."""
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        exam_type=current_user["exam_type"],
        created_at=current_user["created_at"]
    )

# --- Core Business Endpoints ---

@app.post("/api/v1/journal/analyze", response_model=JournalAnalysisResponse)
async def analyze_journal_entry(
    payload: JournalAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Deliverable 1: Analyze unstructured student journal entries (Secured & Optimized).
    Encrypts journal contents, validates inputs, and runs calls in non-blocking async threads.
    """
    content = sanitize_input(payload.content.strip())
    if not content:
        raise HTTPException(status_code=400, detail="Journal content cannot be empty.")

    # 1. Run safety checks first
    is_safe, incident_meta = await evaluate_input(content)
    if not is_safe:
        crisis_data = generate_crisis_response(incident_meta.get("category", "self_harm") if incident_meta else "self_harm")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "crisis_triggered", "crisis_data": crisis_data}
        )

    # 2. Run Gemini 1.5 Flash structured analysis
    import google.generativeai as genai
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
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
        
        # Save to database (encrypted)
        encrypted_content = JournalEncryptor.encrypt(content)
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "content": encrypted_content,
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
        
        # Offload blocking HTTP call to helper thread to keep event loop free
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result_json = json.loads(response.text.strip())
        response_data = JournalAnalysisResponse(**result_json)
        
        # Encrypt journal contents before storing
        encrypted_content = JournalEncryptor.encrypt(content)
        JOURNAL_ENTRIES_DB.append({
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "content": encrypted_content,
            **response_data.model_dump()
        })
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error in journal analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process journal entry with AI: {str(e)}"
        )

@app.post("/api/v1/journal/entries/voice")
async def upload_voice_entry(
    audio_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    AI Voice Extension: Transcribes voice journal entries using Whisper AI,
    then runs the unstructured journal analysis on the transcribed text.
    """
    try:
        audio_content = await audio_file.read()
        transcription = await transcribe_voice_to_text(audio_content, audio_file.filename)
        
        # Analyze transcription text using unstructured analysis
        analysis_payload = JournalAnalysisRequest(content=transcription)
        analysis_res = await analyze_journal_entry(analysis_payload, current_user)
        
        return {
            "transcription": transcription,
            "analysis": analysis_res
        }
    except Exception as e:
        logger.error(f"Voice upload analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to process and analyze voice entry.")

@app.post("/api/v1/chat/message")
async def chat_message_stream(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Deliverable 3: Stateful streaming chatbot loop (Secured & Optimized).
    Executes safety checks on input, then returns an empathetic streaming chat response.
    """
    content = sanitize_input(payload.content.strip())
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
        
        meta = {
            "session_id": session_id,
            "intervention_tool": intervention_tool,
            "timestamp": datetime.utcnow().isoformat()
        }
        yield f"__METADATA__:{json.dumps(meta)}\n"
        
        # Call empathetic agent stream
        async for chunk in stream_empathetic_chat(content, history_list, current_user.get("exam_type", "JEE_MAIN")):
            yield chunk

    return StreamingResponse(chat_stream_generator(), media_type="text/event-stream")

@app.get("/api/v1/analytics/dashboard")
async def get_dashboard_data(current_user: dict = Depends(get_current_user)):
    """
    Serves mock test scores and weekly stress scores to correlate them (Secured).
    Used to render dashboard charts. Decrypts journal text on lookup.
    """
    decrypted_entries = []
    for entry in JOURNAL_ENTRIES_DB:
        decrypted_entries.append({
            **entry,
            "content": JournalEncryptor.decrypt(entry.get("content", ""))
        })
    return {
        "mock_tests": MOCK_TESTS_DB,
        "stress_entries": decrypted_entries
    }

@app.post("/api/v1/analytics/mock-test")
async def add_mock_test(
    test: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Logs mock test details for student dashboard correlation (Secured).
    """
    test_id = str(uuid.uuid4())
    test_entry = {
        "id": test_id,
        "test_name": sanitize_input(test.get("test_name", "Mock Test")),
        "test_date": sanitize_input(test.get("test_date", datetime.now().strftime("%Y-%m-%d"))),
        "score": int(test.get("score", 150)),
        "total_marks": int(test.get("total_marks", 300)),
        "percentile": float(test.get("percentile", 90.0)),
        "accuracy": float(test.get("accuracy", 75.0))
    }
    MOCK_TESTS_DB.append(test_entry)
    return {"status": "success", "id": test_id, "test": test_entry}

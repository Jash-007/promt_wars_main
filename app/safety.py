# backend/app/safety.py
import re
import os
import json
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional, List

logger = logging.getLogger(__name__)

class SafetySeverity:
    LOW: str = "low"
    MEDIUM: str = "medium"
    HIGH: str = "high"
    CRITICAL: str = "critical"

# Localized crisis resources for India (default country)
CRISIS_HELPLINES: List[Dict[str, str]] = [
    {
        "name": "Vandrevala Foundation",
        "phone": "+91-9999-666-555",
        "hours": "24/7",
        "website": "https://www.vandrevalafoundation.org"
    },
    {
        "name": "AASRA",
        "phone": "+91-22-2754-6669",
        "hours": "24/7",
        "website": "https://aasra.info"
    },
    {
        "name": "Kiran Helpline",
        "phone": "+91-9141-323-253",
        "hours": "24/7 (Govt of India)",
        "website": "https://www.kiranhelp.org"
    },
    {
        "name": "iCall (TISS)",
        "phone": "+91-9152-987-821",
        "hours": "Monday to Saturday, 8:00 AM - 10:00 PM",
        "website": "https://www.icallhelpline.org"
    }
]

# Critical keywords for fast synchronous matching
CRITICAL_KEYWORDS: List[str] = [
    "suicide", "kill myself", "want to die", "slit wrist", "overdose", 
    "hang myself", "jump off", "end my life", "hurt myself", "self harm", 
    "self-harm", "slash wrist", "poison myself", "commit suicide", 
    "better off dead", "burden to everyone", "no point living", "no point in living"
]

# Compile keywords into a single regex for highly efficient O(N) single-pass search
KEYWORDS_REGEX: re.Pattern = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in CRITICAL_KEYWORDS) + r')\b',
    re.IGNORECASE
)

def check_keywords(content: str) -> Optional[Dict[str, str]]:
    """
    Perform fast single-pass regex keyword matching to identify critical crisis language.
    Executes in <1ms to catch clear threat vectors immediately.
    """
    match = KEYWORDS_REGEX.search(content)
    if match:
        matched_keyword: str = match.group(1).lower()
        logger.warning(f"Safety Trigger: Keyword matched '{matched_keyword}' in input.")
        return {
            "triggered": "true",
            "category": "self_harm",
            "severity": SafetySeverity.CRITICAL,
            "detection_method": "keyword_matching",
            "matched_keyword": matched_keyword,
            "timestamp": datetime.utcnow().isoformat()
        }
    return None

async def check_semantic_safety(content: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, str]]:
    """
    Execute semantic validation using Gemini.
    Compatible with both the deprecated 'google.generativeai' and the newer 'google.genai' SDKs.
    """
    gemini_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.error("GEMINI_API_KEY is not configured. Skipping semantic safety check.")
        return None

    # Construct context from conversation history
    context_str: str = ""
    if history:
        context_str = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history[-3:]])

    prompt: str = f"""
    Analyze the following user input to detect if the student is experiencing a genuine mental health crisis, active self-harm, or suicidal ideation.
    We are a wellness tracker for students preparing for competitive entrance exams in India (JEE, NEET, UPSC, etc.).
    
    CRITICAL DISTINCTION:
    - Exaggeration / Hyperbole: "I will die if I fail my physics exam", "My dad will kill me if I don't get 99 percentile" -> This represents high exam stress, NOT a self-harm crisis. Return is_crisis: false.
    - True Crisis: "I want to end my life", "There is no point in living anymore", "I have bought pills, I'm going to take them tonight" -> Active suicidal planning or intent. Return is_crisis: true.
    
    Respond STRICTLY with a valid JSON block containing:
    {{
        "is_crisis": <bool>,
        "confidence": <float between 0.0 and 1.0>,
        "category": "<self_harm | severe_depression | acute_crisis | none>",
        "reasoning": "<explain the semantic difference in context>"
    }}
    
    Context History:
    {context_str}
    
    Current Statement:
    "{content}"
    """

    try:
        result_text: str = ""
        # 1. Try importing new google-genai SDK first
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            result_text = response.text
        except ImportError:
            # 2. Fall back to deprecated google-generativeai SDK
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            result_text = response.text
            
        result: dict = json.loads(result_text.strip())
        if result.get("is_crisis") is True and result.get("confidence", 0.0) >= 0.70:
            logger.warning(f"Safety Trigger: Semantic check flagged crisis with confidence {result.get('confidence')}")
            return {
                "triggered": "true",
                "category": result.get("category", "self_harm"),
                "severity": SafetySeverity.CRITICAL,
                "detection_method": "semantic_analysis",
                "reasoning": result.get("reasoning", ""),
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Error in semantic safety analysis: {e}", exc_info=True)
        
    return None

async def evaluate_input(content: str, history: Optional[List[Dict[str, str]]] = None) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    Main evaluation pipeline checking both keywords and semantics.
    Returns:
        is_safe (bool), metadata (dict or None)
    """
    # 1. Check O(N) pre-compiled keyword match
    keyword_result: Optional[Dict[str, str]] = check_keywords(content)
    if keyword_result:
        return False, keyword_result
        
    # 2. Check semantic analysis
    semantic_result: Optional[Dict[str, str]] = await check_semantic_safety(content, history)
    if semantic_result:
        return False, semantic_result
        
    return True, None

def generate_crisis_response(category: str = "self_harm") -> Dict[str, object]:
    """
    Generates a structured override payload carrying emergency contact cards.
    This will bypass the AI conversational flow on the client side.
    """
    return {
        "crisis_triggered": True,
        "category": category,
        "message": (
            "I hear how incredibly tough things are right now. You are carrying an immense amount of pressure, "
            "but I want to make sure you get the right support—the real, professional kind. "
            "You are reaching a point where talking to a trained human crisis counselor is the best step. "
            "Please contact one of these free, confidential Indian student and crisis helplines immediately. "
            "They are there to support you without judgment."
        ),
        "helplines": CRISIS_HELPLINES,
        "timestamp": datetime.utcnow().isoformat()
    }

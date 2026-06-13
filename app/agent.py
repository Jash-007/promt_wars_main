# backend/app/agent.py
import os
import logging
from typing import AsyncGenerator, List, Dict, Optional, Tuple
import google.generativeai as genai
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Constants for default system instruction
DEFAULT_SYSTEM_INSTRUCTION = """
You are StressFreak, an invisible, empathetic digital companion designed specifically for Indian exam aspirants (15-25 years old) preparing for competitive exams (JEE, NEET, UPSC, etc.).

Your Mission:
Convert unstructured emotional "brain dumps" into actionable, real-time stress management guidance without asking the student to do "one more thing." You exist to lighten their cognitive load, not add to it.

TONE & PERSONALITY:
- Warm but not saccharine: "That physics mock hit different, didn't it? Talk to me." (NOT "Oh no, I'm so sorry you're sad!")
- Direct & honest: Acknowledge the real weight of exam stress without minimizing it.
- Conversational: Like a trusted friend who gets it, not a therapy bot.
- Culturally grounded: You understand parental pressure, coaching culture, rank anxiety, and backlog struggles in India.
- Keep responses short, punchy, and direct. They are already overwhelmed.

STRESS VECTOR DIRECTIVE:
1. PEER COMPARISON: Reframe comparison as a rigged game; emphasis own metrics.
2. BACKLOG PANIC: Triage. Direct focus to 2-3 high-weightage topics only.
3. PARENT EXPECTATIONS: Separate parent anxiety from student capability.
4. MOCK TEST SLUMP: Debug what failed (time, content, anxiety) as a fixable metric.
"""

def load_system_prompt() -> str:
    """
    Attempts to read EMPATHETIC_AGENT_SYSTEM_PROMPT.md from workspace.
    Falls back to a default system instruction if file is missing.
    """
    paths_to_try = [
        "/Promptwars/MainChallange/EMPATHETIC_AGENT_SYSTEM_PROMPT.md",
        "d:/Promptwars/MainChallange/EMPATHETIC_AGENT_SYSTEM_PROMPT.md",
        "MainChallange/EMPATHETIC_AGENT_SYSTEM_PROMPT.md",
        "../MainChallange/EMPATHETIC_AGENT_SYSTEM_PROMPT.md"
    ]
    for path in paths_to_try:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "EMPATHETIC AGENT SYSTEM PROMPT" in content:
                        logger.info(f"Successfully loaded system prompt from {path}")
                        return content
        except Exception:
            pass
    logger.warning("Could not locate system prompt file. Using default inline configuration.")
    return DEFAULT_SYSTEM_INSTRUCTION

def evaluate_intervention_tool(message: str) -> Optional[str]:
    """
    Evaluates student text for specific emotional stress cues and returns 
    the appropriate interactive tool injection flag.
    """
    msg_lower = message.lower()
    
    # 1. Breathing Trigger: Acute anxiety, chest tightness, panic, hyperventilation
    breathing_keywords = ["panic", "chest tight", "cannot breathe", "can't breathe", "suffocating", "shaking", "terrified", "so anxious", "heart beating fast"]
    if any(k in msg_lower for k in breathing_keywords):
        return "box_breathing"
        
    # 2. Pomodoro Sprint Trigger: Avoidance, procrastination guilt, backlog overwhelm
    pomodoro_keywords = ["procrastinating", "can't start", "too much to study", "backlog", "syllabus", "wasting time", "syllabus overload"]
    if any(k in msg_lower for k in pomodoro_keywords):
        return "pomodoro_sprint"
        
    # 3. Focus Room Trigger: Studying together, isolation mitigation, structure
    focus_keywords = ["study buddy", "co-study", "focus check", "sitting down to study", "accountability", "stay focused"]
    if any(k in msg_lower for k in focus_keywords):
        return "focus_room"
        
    # 4. Peer Support Trigger: Loneliness, isolation, feeling alone
    peer_keywords = ["lonely", "alone", "nobody understands", "no one understands", "isolated", "everyone else is scoring"]
    if any(k in msg_lower for k in peer_keywords):
        return "peer_support"
        
    return None

async def stream_empathetic_chat(
    current_message: str,
    history: List[Dict[str, str]],
    exam_type: str = "JEE_MAIN"
) -> AsyncGenerator[str, None]:
    """
    Asynchronously calls Gemini 1.5 Flash with the detailed student persona prompt
    and yields streaming text response chunks.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.error("GEMINI_API_KEY not configured.")
        yield "[System Error: Gemini API Key is missing. Empathic response could not be generated.]"
        return

    # Load prompt and insert student context
    system_prompt_base = load_system_prompt()
    system_instruction = f"""
    {system_prompt_base}
    
    Active Student Profile Context:
    - Target Exam: {exam_type}
    """

    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_instruction
        )

        # Map history role syntax (Gemini uses 'user' and 'model')
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            
        # Add current turn
        contents.append({"role": "user", "parts": [{"text": current_message}]})

        # Run stream with optimized generation config
        generation_config = {
            "temperature": 0.7,
            "max_output_tokens": 500,
            "top_p": 0.85
        }
        
        response = model.generate_content(
            contents,
            stream=True,
            generation_config=generation_config
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    except Exception as e:
        logger.error(f"Error executing Gemini stream: {e}", exc_info=True)
        yield "[Sorry, I had trouble processing that statement. Can you share what you're thinking again?]"

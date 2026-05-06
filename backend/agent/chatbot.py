"""
chatbot.py
----------
Unified AI chatbot response function.

Routing:
  - If AZURE_FOUNDRY_API_KEY is set → Friday agent (LangGraph / AzureChatOpenAI)
    Text channel, thread_id = username, shared memory with voice.
  - Otherwise → Gemini fallback (existing behaviour, unchanged)

The existing /api/chat endpoint calls _get_response(username, message) — signature preserved.
"""

import os
import sys
from dotenv import load_dotenv

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


load_dotenv()


def _get_response(username: str, user_message: str) -> str:
    """
    Return the assistant's reply for one chat turn.
    Tries Friday (Azure) first; falls back to Gemini if not configured.
    """
    azure_key = os.getenv("AZURE_FOUNDRY_API_KEY", "")

    if azure_key:
        return _friday_response(username, user_message)
    return _gemini_response(username, user_message)


# ── Friday (Azure / LangGraph) ────────────────────────────────────────────────

def _friday_response(username: str, user_message: str) -> str:
    try:
        from backend.agent.graph import invoke_friday
        result = invoke_friday(username, user_message, channel="text")
        return result.get("response") or "I didn't have a response for that."
    except Exception as exc:
        print(f"[Chatbot] Friday error: {exc}")
        return f"AI error: {exc}"


# ── Gemini fallback (original implementation, unchanged) ─────────────────────

def _gemini_response(username: str, user_message: str) -> str:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        return (
            "The AI chatbot is not configured. "
            "Please set GOOGLE_API_KEY or AZURE_FOUNDRY_API_KEY in your .env file."
        )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
        from backend.utils import db

        profile = db.get_user_profile(username) or {}
        history = db.load_chat_history(username)

        target_map = {
            "weight_loss":     "Weight Loss",
            "muscle_gain":     "Muscle Gain",
            "endurance":       "Building Endurance",
            "general_fitness": "General Fitness",
        }

        restrictions = ", ".join(profile.get("dietary_restrictions", [])) or "None"
        system_prompt = (
            "You are a personalized fitness and nutrition AI assistant called ActionBot. "
            "Provide evidence-based dietary and fitness advice tailored to the user's profile.\n\n"
            f"User Profile:\n"
            f"  - Age: {profile.get('age', 'Unknown')}\n"
            f"  - Gender: {profile.get('gender', 'Unknown')}\n"
            f"  - Weight: {profile.get('weight_kg', '?')} kg\n"
            f"  - Height: {profile.get('height_cm', '?')} cm\n"
            f"  - Goal: {target_map.get(profile.get('target', ''), 'General Fitness')}\n"
            f"  - Dietary Restrictions: {restrictions}\n\n"
            "Always respect dietary restrictions strictly. Be concise, friendly, and practical. "
            "When suggesting meal plans, always provide specific quantities and macros."
        )

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.7,
        )

        messages = [SystemMessage(content=system_prompt)]
        for msg in history[-20:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=user_message))

        response = llm.invoke(messages)
        return response.content

    except Exception as exc:
        return f"AI error: {str(exc)}. Please check your API keys."
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from dotenv import load_dotenv
from utils import db

load_dotenv()
    
def _get_response(username: str, user_message: str) -> str:
    """
    Call Gemini via LangChain with user profile as system context.
    Falls back to a placeholder message if GOOGLE_API_KEY is not set.
    """

    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        return (
            "The AI chatbot is not configured. "
            "Please set GOOGLE_API_KEY in your .env file."
        )

    try:
        profile = db.get_user_profile(username) or {}
        history = db.load_chat_history(username)

        # Build system prompt from user profile
        target_map = {
            "weight_loss":      "Weight Loss",
            "muscle_gain":      "Muscle Gain",
            "endurance":        "Building Endurance",
            "general_fitness":  "General Fitness",
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
            model="gemini-2.5-flash",
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

    except Exception as e:
        return f"AI error: {str(e)}. Please check your GOOGLE_API_KEY."
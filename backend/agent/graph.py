"""
friday_graph.py
---------------
Friday AI agent — built with LangGraph.

Primary LLM  : Anthropic Claude (langchain-anthropic)
Fallback LLM : Google Gemini (langchain-google-genai) → original chatbot.py

Graph:
  input → intent_node → [tool_node | clarify_node] → memory_write_node → response_node → END

Both voice (/ws/friday) and text (/api/chat) invoke this graph with
  config = {"configurable": {"thread_id": username}}
so all state — conversation history, diet plans, workout plans, calorie logs — is shared.

Channel-aware output:
  voice → 1-2 sentences, no markdown, speakable prose → piped to Kokoro TTS
  text  → full markdown allowed → returned to chatbot UI
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Annotated, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

load_dotenv()

# ── LLM — Claude primary, Gemini fallback ─────────────────────────────────────
_ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "")   # fill in .env; e.g. claude-3-5-sonnet-20241022
_AGENT_NAME      = os.getenv("AGENT_NAME", "Friday")

_llm         = None
_llm_lock_   = __import__("threading").Lock()


def _get_llm():
    """Return Claude if configured, else fall back to AzureChatOpenAI (legacy), else raise."""
    global _llm
    if _llm is not None:
        return _llm
    with _llm_lock_:
        if _llm is not None:
            return _llm

        if _ANTHROPIC_KEY and _ANTHROPIC_MODEL:
            try:
                from langchain_anthropic import ChatAnthropic  # noqa: PLC0415
                _llm = ChatAnthropic(
                    api_key=_ANTHROPIC_KEY,
                    model=_ANTHROPIC_MODEL,
                    temperature=0.4,
                    max_tokens=2048,
                )
                print(f"[Friday/LLM] ✅ Using Claude: {_ANTHROPIC_MODEL}")
                return _llm
            except Exception as exc:
                print(f"[Friday/LLM] ⚠  Claude init failed ({exc}) — trying Gemini fallback")

        # Gemini fallback
        _GOOGLE_KEY = os.getenv("GOOGLE_API_KEY", "")
        if _GOOGLE_KEY:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415
                _llm = ChatGoogleGenerativeAI(
                    model="gemini-1.5-flash",
                    google_api_key=_GOOGLE_KEY,
                    temperature=0.4,
                )
                print("[Friday/LLM] ✅ Fallback: Gemini 1.5 Flash")
                return _llm
            except Exception as exc:
                print(f"[Friday/LLM] ⚠  Gemini fallback failed: {exc}")

        raise ValueError(
            "No LLM configured. Set ANTHROPIC_API_KEY + ANTHROPIC_MODEL "
            "or GOOGLE_API_KEY in .env"
        )


# ── MongoDB Checkpointer ──────────────────────────────────────────────────────
_MONGO_URI     = os.getenv("MONGODB_URI", "")
_CHECKPOINT_DB = "friday_checkpoints"
_checkpointer  = None


def _get_checkpointer():
    """
    Return a LangGraph-compatible BaseCheckpointSaver.

    MongoDBSaver.from_conn_string() is a context manager — calling it directly
    yields a _GeneratorContextManager, NOT a BaseCheckpointSaver, which LangGraph
    rejects at compile time.  We enter the context manager via __enter__() to get
    the real saver object, and cache it for the lifetime of the process.

    Falls back to MemorySaver (in-process, non-persistent) if MongoDB is
    unavailable so the agent continues to work without crashing.
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    if _MONGO_URI:
        try:
            from langgraph.checkpoint.mongodb import MongoDBSaver  # noqa: PLC0415
            cm = MongoDBSaver.from_conn_string(_MONGO_URI, db_name=_CHECKPOINT_DB)
            # Enter the context manager to obtain the real BaseCheckpointSaver instance
            _checkpointer = cm.__enter__()
            print("[Friday/Checkpointer] ✅ MongoDBSaver connected")
            return _checkpointer
        except Exception as exc:
            print(f"[Friday/Checkpointer] ⚠  MongoDB unavailable ({exc}) — using MemorySaver")

    # Fallback: in-memory (conversation history lost on restart, but functional)
    from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415
    _checkpointer = MemorySaver()
    print("[Friday/Checkpointer] ℹ️  Using MemorySaver (in-process, non-persistent)")
    return _checkpointer


# ── Command Registry ──────────────────────────────────────────────────────────
COMMAND_REGISTRY = [
    {"key": "calorie_scan",         "description": "Capture frame → AI vision → estimate calories → speak result"},
    {"key": "calories_today",       "description": "Sum today's food scan calories and report"},
    {"key": "calorie_history",      "description": "Summarise recent food scan logs"},
    {"key": "who_am_i",             "description": "Read back user profile + today's stats"},
    {"key": "status",               "description": "System health summary"},
    {"key": "overlay_toggle",       "description": "Toggle HUD overlay visibility"},
    {"key": "screenshot",           "description": "Save current camera frame to disk"},
    {"key": "diet_plan",            "description": "Generate + store a personalised diet plan"},
    {"key": "generate_workout_plan","description": (
        "Generate a weekly workout plan tailored to user goals and equipment availability. "
        "Ask the user for: target weekday(s), equipment available, preferred weight and rep range "
        "if not already in their profile. Return structured JSON with exercises per day."
    )},
    {"key": "save_workout_plan",    "description": "Save the workout plan suggested in chat to the user's weekly schedule"},
    {"key": "reset_reps",           "description": "Reset the rep counter for the current set"},
    {"key": "start_camera",         "description": "Start the live webcam / begin exercise session"},
    {"key": "stop_camera",          "description": "Stop the live webcam / end exercise session"},
    {"key": "save_set",             "description": "Save the current completed set of reps"},
    {"key": "next_set",             "description": "Save the current set (if reps > 0) and immediately start the next set"},
    {"key": "shutdown",             "description": "Graceful app shutdown"},
    {"key": "chat",                 "description": "General conversation or question (default)"},
]

_COMMAND_LIST_STR = "\n".join(f"  {c['key']}: {c['description']}" for c in COMMAND_REGISTRY)


# ── State ─────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages:          Annotated[list, add_messages]
    channel:           str            # "text" | "voice"
    username:          str
    intent:            Optional[str]
    intent_params:     Optional[dict]
    intent_confidence: float
    tool_result:       Optional[dict]
    response:          Optional[str]
    latest_frame:      Optional[bytes]


# ── Node: intent_node ─────────────────────────────────────────────────────────
def intent_node(state: AgentState) -> dict:
    """Classify the latest user message into a command key + confidence."""
    last_msg = state["messages"][-1].content if state["messages"] else ""

    system = (
        f"You are an intent classifier for the {_AGENT_NAME} assistant.\n"
        "Given a user message, return ONLY valid JSON — no markdown, no explanation.\n"
        'Schema: {"command": string, "params": {}, "confidence": float}\n\n'
        f"Available commands:\n{_COMMAND_LIST_STR}\n\n"
        "Use command='chat' for general conversation. confidence is 0.0–1.0."
    )

    try:
        resp = _get_llm().invoke([SystemMessage(content=system), HumanMessage(content=last_msg)])
        data = json.loads(resp.content.strip())
        return {
            "intent":            data.get("command", "chat"),
            "intent_params":     data.get("params", {}),
            "intent_confidence": float(data.get("confidence", 0.9)),
        }
    except Exception as exc:
        print(f"[Friday/intent_node] {exc}")
        return {"intent": "chat", "intent_params": {}, "intent_confidence": 0.9}


def _route_after_intent(state: AgentState) -> str:
    return "clarify_node" if state.get("intent_confidence", 1.0) < 0.6 else "tool_node"


# ── Node: tool_node ───────────────────────────────────────────────────────────
def tool_node(state: AgentState) -> dict:
    """Execute the handler for the detected intent."""
    intent   = state.get("intent", "chat")
    username = state["username"]
    result: dict = {}

    try:
        from backend.utils import db  # noqa: PLC0415

        if intent == "calorie_scan":
            frame = state.get("latest_frame")
            if frame is None:
                result = {"error": "no_frame"}
            else:
                import numpy as np   # noqa: PLC0415
                import cv2 as _cv2   # noqa: PLC0415
                arr       = np.frombuffer(frame, dtype=np.uint8)
                frame_bgr = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
                from backend.utils.calorie_tracker import scan_food_from_frame  # noqa: PLC0415
                result = scan_food_from_frame(frame_bgr, username)

        elif intent == "calories_today":
            result = {"calories_today": db.get_calories_today(username)}

        elif intent == "calorie_history":
            result = {"logs": db.get_calorie_logs(username, limit=5)}

        elif intent == "who_am_i":
            profile = db.get_user_profile(username) or {}
            result  = {
                "username":       username,
                "goal":           profile.get("target", "general_fitness"),
                "weight_kg":      profile.get("weight_kg"),
                "calories_today": db.get_calories_today(username),
                "equipment":      profile.get("equipment_availability", []),
            }

        elif intent == "diet_plan":
            result = {"action": "generate_diet_plan"}

        elif intent == "generate_workout_plan":
            profile = db.get_user_profile(username) or {}
            result  = {
                "action":    "generate_workout_plan",
                "goal":      profile.get("target", "general_fitness"),
                "goals_extra": profile.get("goals_extra", ""),
                "equipment": profile.get("equipment_availability", []),
                "params":    state.get("intent_params") or {},
            }

        elif intent == "save_workout_plan":
            # Params expected: {weekday: str, exercises: [{exercise_key, sets, reps, weight_kg}]}
            params = state.get("intent_params") or {}
            weekday   = params.get("weekday")
            exercises = params.get("exercises", [])
            if weekday and exercises:
                saved = db.save_workout_plan(username, weekday, exercises)
                result = {"saved": True, "plan": saved}
            else:
                result = {"error": "missing weekday or exercises in params"}

        elif intent == "status":
            result = {"status": "operational", "time": datetime.now().strftime("%H:%M")}

        elif intent == "shutdown":
            result = {"action": "shutdown"}

        elif intent in ("overlay_toggle", "screenshot", "reset_reps",
                        "start_camera", "stop_camera", "save_set", "next_set"):
            result = {"frontend_command": intent}

    except Exception as exc:
        print(f"[Friday/tool_node] {exc}")
        result = {"error": str(exc)}

    return {"tool_result": result}


# ── Node: clarify_node ────────────────────────────────────────────────────────
def clarify_node(state: AgentState) -> dict:
    return {"tool_result": {"clarify": True}}


# ── Node: memory_write_node ───────────────────────────────────────────────────
def memory_write_node(state: AgentState) -> dict:
    """Write the user's latest message to unified MongoDB conversation history."""
    try:
        from backend.utils import db  # noqa: PLC0415
        last = state["messages"][-1]
        db.append_conversation_turn(
            username=state["username"],
            role="user",
            content=last.content,
            channel=state.get("channel", "text"),
        )
    except Exception as exc:
        print(f"[Friday/memory_write_node] {exc}")
    return {}


# ── Node: response_node ───────────────────────────────────────────────────────
def response_node(state: AgentState) -> dict:
    """Generate Friday's reply, channel-aware."""
    from backend.agent.memory import build_system_prompt  # noqa: PLC0415

    channel     = state.get("channel", "text")
    username    = state["username"]
    intent      = state.get("intent", "chat")
    tool_result = state.get("tool_result") or {}

    if tool_result.get("clarify"):
        text = "I didn't catch that — could you repeat?"
        return {"response": text, "messages": [AIMessage(content=text)]}

    if tool_result.get("error") == "no_frame":
        text = "I can't see anything to scan."
        return {"response": text, "messages": [AIMessage(content=text)]}

    addendum = _build_addendum(intent, tool_result)
    system   = build_system_prompt(username, channel=channel)
    full_sys = f"{system}\n\n{addendum}".strip() if addendum else system

    msgs = [SystemMessage(content=full_sys)] + list(state["messages"][-10:])

    try:
        text = _get_llm().invoke(msgs).content.strip()
    except Exception as exc:
        print(f"[Friday/response_node] LLM error: {exc}")
        text = "Something went wrong on my end."

    # Persist diet plan if generated
    if intent == "diet_plan" and text:
        try:
            from backend.utils import db  # noqa: PLC0415
            plan = db.save_diet_plan(username, "7-Day Diet Plan", text)
            db.log_fulfilled_request(username, "diet_plan",
                                     "Generated a 7-day diet plan", plan["plan_id"])
        except Exception as exc:
            print(f"[Friday/response_node] diet_plan persist error: {exc}")

    return {"response": text, "messages": [AIMessage(content=text)]}


def _build_addendum(intent: str, tool_result: dict) -> str:
    """Convert tool_result into a plain-text context addendum for the LLM."""
    if intent == "calorie_scan" and "foods" in tool_result:
        foods = tool_result.get("foods", [])
        total = tool_result.get("total_calories", 0)
        conf  = tool_result.get("confidence", "medium")
        lines = "; ".join(f"{f['name']} {f['calories']} kcal" for f in foods)
        return (f"Calorie scan: {lines}. Total {total} kcal ({conf} confidence). "
                f"Notes: {tool_result.get('notes','')}. Report this clearly.")

    if intent == "calories_today":
        return f"User consumed {tool_result.get('calories_today', 0)} kcal from food scans today. Report this."

    if intent == "calorie_history":
        logs = tool_result.get("logs", [])
        if not logs:
            return "No food scans on record yet."
        lines = [f"{l['timestamp'][:16]}: {', '.join(f['name'] for f in l.get('foods',[]))} ({l['total_calories']} kcal)"
                 for l in logs]
        return "Recent scans:\n" + "\n".join(lines) + "\nSummarise briefly."

    if intent == "who_am_i":
        r = tool_result
        equip = ", ".join(r.get("equipment", [])) or "none specified"
        return (f"Profile: username={r.get('username')}, goal={r.get('goal')}, "
                f"weight={r.get('weight_kg')} kg, calories today={r.get('calories_today')}, "
                f"equipment={equip}. Report naturally.")

    if intent == "status":
        return "All systems operational. Report briefly."

    if intent == "diet_plan":
        return ("Generate a personalised 7-day diet plan for this user based on their profile. "
                "Be specific with portions and macros.")

    if intent == "generate_workout_plan":
        r       = tool_result
        goal    = r.get("goal", "general_fitness")
        extra   = r.get("goals_extra", "")
        equip   = ", ".join(r.get("equipment", [])) or "bodyweight only"
        params  = r.get("params", {})
        weight_hint = params.get("weight_kg", "as appropriate for user")
        rep_hint    = params.get("rep_range", "8-12")
        return (
            "Generate a detailed weekly workout plan as a JSON object. "
            "Schema: {\"Mon\": [{\"exercise_key\": str, \"sets\": int, \"reps\": int, \"weight_kg\": float}], ...}. "
            f"User goal: {goal}. Additional notes: {extra or 'none'}. "
            f"Available equipment: {equip}. "
            f"Target weight range: {weight_hint} kg. Target rep range: {rep_hint}. "
            "Include only rest days as empty arrays. "
            "Valid exercise_key values: squat, pushup, bicep_curl, pullup, lateral_raise, "
            "overhead_press, situp, crunch, leg_raise, knee_raise, knee_press. "
            "Return ONLY the JSON — no prose, no markdown fences."
        )

    if intent == "save_workout_plan":
        if tool_result.get("saved"):
            day = tool_result.get("plan", {}).get("weekday", "")
            return f"Confirm to the user that their workout plan for {day} has been saved successfully."
        return f"Inform the user there was a problem saving the plan: {tool_result.get('error', 'unknown error')}."

    if intent == "shutdown":
        return "Say a brief goodbye."

    if tool_result.get("frontend_command"):
        cmd_labels = {
            "start_camera":  "starting the camera",
            "stop_camera":   "stopping the camera",
            "save_set":      "saving your set",
            "next_set":      "saving this set and starting the next one",
            "reset_reps":    "resetting the rep counter",
            "overlay_toggle": "toggling the overlay",
        }
        label = cmd_labels.get(tool_result["frontend_command"],
                               tool_result["frontend_command"].replace("_", " "))
        return f"Acknowledge briefly that you are {label}. One sentence, conversational."

    return ""


# ── Compile ───────────────────────────────────────────────────────────────────
_graph = None


def get_friday_graph():
    """Lazily compile and return the Friday LangGraph agent."""
    global _graph
    if _graph is not None:
        return _graph

    b = StateGraph(AgentState)
    b.add_node("intent_node",       intent_node)
    b.add_node("tool_node",         tool_node)
    b.add_node("clarify_node",      clarify_node)
    b.add_node("memory_write_node", memory_write_node)
    b.add_node("response_node",     response_node)

    b.set_entry_point("intent_node")
    b.add_conditional_edges("intent_node", _route_after_intent,
                             {"tool_node": "tool_node", "clarify_node": "clarify_node"})
    b.add_edge("tool_node",         "memory_write_node")
    b.add_edge("clarify_node",      "memory_write_node")
    b.add_edge("memory_write_node", "response_node")
    b.add_edge("response_node",     END)

    _graph = b.compile(checkpointer=_get_checkpointer())
    return _graph


# ── Public helper ─────────────────────────────────────────────────────────────
def invoke_friday(username: str, message: str,
                  channel: str = "text",
                  latest_frame: Optional[bytes] = None) -> dict:
    """
    Invoke the Friday agent for one turn.
    Returns {response: str, intent: str, tool_result: dict | None}
    Falls back to Gemini chatbot if no LLM is configured at all.
    """
    try:
        _get_llm()   # validate at least one LLM is ready
    except ValueError:
        try:
            from backend.agent.chatbot import _get_response as gemini_response  # noqa: PLC0415
            reply = gemini_response(username, message)
        except Exception:
            reply = "AI assistant is not configured."
        return {"response": reply, "intent": "chat", "tool_result": None}

    graph  = get_friday_graph()
    config = {"configurable": {"thread_id": username}}

    state = {
        "messages":          [HumanMessage(content=message)],
        "channel":           channel,
        "username":          username,
        "intent":            None,
        "intent_params":     None,
        "intent_confidence": 1.0,
        "tool_result":       None,
        "response":          None,
        "latest_frame":      latest_frame,
    }

    result = graph.invoke(state, config=config)

    try:
        from backend.utils import db  # noqa: PLC0415
        if result.get("response"):
            attachments = (
                [{"type": "calorie_scan", "ref_id": (result.get("tool_result") or {}).get("log_id")}]
                if result.get("intent") == "calorie_scan" else []
            )
            db.append_conversation_turn(
                username=username, role="assistant",
                content=result["response"], channel=channel,
                attachments=attachments,
            )
    except Exception as exc:
        print(f"[Friday/invoke] memory write error: {exc}")

    return {
        "response":    result.get("response", ""),
        "intent":      result.get("intent", "chat"),
        "tool_result": result.get("tool_result"),
    }

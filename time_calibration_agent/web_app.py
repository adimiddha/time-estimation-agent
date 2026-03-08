"""
Minimal Flask web app for replanning.
"""

import os
import secrets
from datetime import datetime
from typing import Dict, Optional

from flask import Flask, render_template, request, jsonify
from flask import session as flask_session

from time_calibration_agent.replanner import ReplanningAgent
from time_calibration_agent.session_store import DaySessionStore


BASE_SESSIONS_DIR = os.getenv("SESSIONS_DIR", "day_sessions")


def _user_sessions_dir() -> str:
    user_id = flask_session.get("user_id", "anonymous")
    return os.path.join(BASE_SESSIONS_DIR, user_id)


def _resolve_session_id(
    session_store: DaySessionStore,
    session_label: Optional[str],
    date_override: Optional[str],
    use_last: bool,
) -> Optional[str]:
    if session_label or date_override:
        return session_store.build_session_id(date_override, session_label)
    if use_last:
        return session_store.load_last_session_id()
    return None


def _build_plan(
    raw_text: str,
    mode: str,
    session_label: Optional[str],
    date_override: Optional[str],
    session_end_time: Optional[str] = None,
    current_time_override: Optional[str] = None,
) -> Dict:
    replanner = ReplanningAgent()
    session_store = DaySessionStore(root_dir=_user_sessions_dir())

    # Prefer explicit current_time from the client; fall back to text inference then server clock.
    # Inference alone is unreliable for replans because deadline phrases like "before 10pm"
    # are indistinguishable from current-time phrases by the regex.
    inferred_time = replanner._infer_time_from_text(raw_text)
    current_time = current_time_override or inferred_time or datetime.now().strftime("%H:%M")

    overwrite = mode == "new"
    session_id = _resolve_session_id(
        session_store=session_store,
        session_label=session_label,
        date_override=date_override,
        use_last=not overwrite,
    )
    if not session_id:
        if overwrite:
            session_id = session_store.build_session_id(date_override, session_label)
        else:
            return {"error": "No active session. Start a new session first."}

    session = None if overwrite else session_store.load_session(session_id)
    if mode in ("replan", "adjust") and not session:
        return {"error": f"No existing session found for {session_id}."}

    last_plan = None
    last_input = None
    conversation_history = []
    existing_estimates = None
    if session and session.get("replans") and not overwrite:
        last_replan = session["replans"][-1]
        last_plan = last_replan.get("plan_output")
        last_input = last_replan.get("raw_input")
        conversation_history = [r["raw_input"] for r in session["replans"]]
        existing_estimates = last_replan.get("estimated_tasks")

    adjustment_mode = mode in ("adjust", "replan")

    # For replans: load stored session_end_time if not provided; allow override via clarify
    if mode == "replan" and session_end_time is None:
        session_end_time = session_store.get_session_end_time(session_id)
        # Check if replan text mentions a new end time
        clarification = replanner.extract_clarification(raw_text, current_time)
        if clarification.get("session_end_time"):
            session_end_time = clarification["session_end_time"]

    # For adjust: inherit stored session_end_time without calling clarify
    if mode == "adjust" and session_end_time is None:
        session_end_time = session_store.get_session_end_time(session_id)

    plan_output, estimated_tasks, extracted_context = replanner.plan_with_estimates(
        raw_text=raw_text,
        current_time=current_time,
        last_plan=last_plan,
        last_input=last_input,
        session_end_time=session_end_time,
        conversation_history=conversation_history if conversation_history else None,
        estimated_tasks=existing_estimates if (adjustment_mode and existing_estimates is not None) else None,
        adjustment_mode=adjustment_mode,
    )

    session_store.append_replan(
        session_id=session_id,
        raw_input=raw_text,
        plan_output=plan_output,
        current_time=current_time,
        extra={
            "estimated_tasks": estimated_tasks,
            "extracted_context": extracted_context,
        },
        overwrite=overwrite,
        session_end_time=session_end_time,
    )

    session = session_store.load_session(session_id)
    return {
        "session_id": session_id,
        "current_time": current_time,
        "plan_output": plan_output,
        "estimated_tasks": estimated_tasks,
        "extracted_context": extracted_context,
        "session_end_time": session_end_time,
        "phase": session.get("phase", "draft") if session else "draft",
    }


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    @app.before_request
    def ensure_user_id():
        if "user_id" not in flask_session:
            flask_session["user_id"] = secrets.token_urlsafe(16)
            flask_session.permanent = True

    @app.route("/", methods=["GET", "POST"])
    def index():
        return render_template("index.html")

    @app.route("/api/session", methods=["GET"])
    def api_session():
        session_store = DaySessionStore(root_dir=_user_sessions_dir())
        last_id = session_store.load_last_session_id()
        if not last_id:
            return jsonify({})
        session = session_store.load_session(last_id)
        if not session or not session.get("replans"):
            return jsonify({})
        last_replan = session["replans"][-1]
        return jsonify({
            "session_id": last_id,
            "current_time": last_replan.get("current_time", ""),
            "plan_output": last_replan.get("plan_output", {}),
            "estimated_tasks": last_replan.get("estimated_tasks", []),
            "session_end_time": session.get("session_end_time"),
            "replans_count": len(session["replans"]),
            "phase": session.get("phase", "approved"),
        })

    @app.route("/api/approve", methods=["POST"])
    def api_approve():
        data = request.get_json(force=True) or {}
        session_store = DaySessionStore(root_dir=_user_sessions_dir())
        session_id = (data.get("session_id") or "").strip() or session_store.load_last_session_id()
        if not session_id:
            return jsonify({"error": "No session to approve."}), 400
        session = session_store.approve_session(session_id)
        if not session:
            return jsonify({"error": f"Session {session_id} not found."}), 404
        return jsonify({"status": "approved", "session_id": session_id})

    @app.route("/api/clarify", methods=["POST"])
    def api_clarify():
        data = request.get_json(force=True) or {}
        context = (data.get("context") or "").strip()
        current_time = (data.get("current_time") or "").strip()
        if not context:
            return jsonify({"error": "No context provided."}), 400
        if not current_time:
            current_time = datetime.now().strftime("%H:%M")
        try:
            replanner = ReplanningAgent()
            result = replanner.extract_clarification(context, current_time)
            return jsonify(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Server error: {e}"}), 500

    @app.route("/api/health", methods=["GET"])
    def api_health():
        import os
        key = os.getenv("OPENAI_API_KEY")
        return jsonify({
            "status": "ok",
            "openai_key_set": bool(key),
            "openai_key_prefix": key[:8] + "..." if key else None,
        })

    @app.route("/api/plan", methods=["POST"])
    def api_plan():
        data = request.get_json(force=True) or {}
        raw_text = (data.get("context") or "").strip()
        mode = (data.get("mode") or "new").strip()
        session_label = (data.get("session_label") or "").strip() or None
        date_override = (data.get("date_override") or "").strip() or None
        session_end_time = (data.get("session_end_time") or "").strip() or None
        current_time_override = (data.get("current_time") or "").strip() or None
        if not raw_text:
            return jsonify({"error": "No context provided."}), 400
        try:
            result = _build_plan(raw_text, mode, session_label, date_override, session_end_time, current_time_override)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Server error: {e}"}), 500
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

"""
Minimal Flask web app for replanning.
"""

import io
import json
import os
import secrets
from datetime import datetime
from typing import Dict, Optional

import openai
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, redirect
from flask import session as flask_session

load_dotenv()

from time_calibration_agent.replanner import ReplanningAgent
from time_calibration_agent.session_store import DaySessionStore


BASE_SESSIONS_DIR = os.getenv("SESSIONS_DIR", "day_sessions")
STATS_FILE = os.path.join(BASE_SESSIONS_DIR, ".stats.json")


def _read_stats() -> Dict:
    try:
        with open(STATS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"plans_created": 0, "replans": 0}


def _increment_stat(key: str) -> None:
    stats = _read_stats()
    stats[key] = stats.get(key, 0) + 1
    os.makedirs(BASE_SESSIONS_DIR, exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)


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
    @app.route("/welcome", methods=["GET"])
    @app.route("/clarify", methods=["GET"])
    @app.route("/planning", methods=["GET"])
    @app.route("/draft", methods=["GET"])
    @app.route("/planner", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/privacy", methods=["GET"])
    def privacy():
        return render_template("privacy.html")

    @app.route("/about", methods=["GET"])
    def about():
        return render_template("about.html")

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
        if mode == "replan":
            _increment_stat("replans")
        else:
            _increment_stat("plans_created")
        return jsonify(result)

    @app.route("/api/transcribe", methods=["POST"])
    def api_transcribe():
        if "audio" not in request.files:
            return jsonify({"error": "No audio file provided."}), 400
        audio_file = request.files["audio"]
        audio_bytes = audio_file.read()
        if not audio_bytes:
            return jsonify({"error": "Empty audio file."}), 400
        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            audio_obj = io.BytesIO(audio_bytes)
            audio_obj.name = "recording.webm"
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_obj,
            )
            return jsonify({"text": transcript.text})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Transcription failed: {e}"}), 500

    @app.route("/api/export-ics", methods=["GET"])
    def api_export_ics():
        session_id = request.args.get("session_id", "").strip() or None

        # Try the current user's session store first
        session_store = DaySessionStore(root_dir=_user_sessions_dir())
        if session_id:
            session = session_store.load_session(session_id)
        else:
            session_id = session_store.load_last_session_id()
            session = session_store.load_session(session_id) if session_id else None

        # If not found, search all user subdirectories (covers webcal:// / cross-context requests)
        if (not session or not session.get("replans")) and session_id:
            for entry in os.scandir(BASE_SESSIONS_DIR):
                if entry.is_dir():
                    candidate_store = DaySessionStore(root_dir=entry.path)
                    candidate = candidate_store.load_session(session_id)
                    if candidate and candidate.get("replans"):
                        session = candidate
                        break

        if not session_id:
            return jsonify({"error": "No active session."}), 404
        if not session or not session.get("replans"):
            return jsonify({"error": "No plan found."}), 404

        last_replan = session["replans"][-1]
        plan_output = last_replan.get("plan_output", {})
        time_blocks = plan_output.get("time_blocks", [])

        date_str = session_id.split("__")[0]  # e.g. "2026-03-07"
        try:
            year, month, day = [int(x) for x in date_str.split("-")]
        except ValueError:
            return jsonify({"error": "Invalid session date."}), 400

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Untangle//Time Planner//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        for idx, block in enumerate(time_blocks):
            try:
                sh, sm = [int(x) for x in block["start"].split(":")]
                eh, em = [int(x) for x in block["end"].split(":")]
            except (KeyError, ValueError):
                continue
            dtstart = f"{year:04d}{month:02d}{day:02d}T{sh:02d}{sm:02d}00"
            dtend   = f"{year:04d}{month:02d}{day:02d}T{eh:02d}{em:02d}00"
            uid = f"{session_id}-block{idx}@untangle"
            task_name = block.get("task", "Task").replace("\r", "").replace("\n", "\\n")
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:{task_name}",
                "END:VEVENT",
            ]

        lines.append("END:VCALENDAR")
        ics_content = "\r\n".join(lines) + "\r\n"

        return Response(
            ics_content,
            mimetype="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="untangle-{date_str}.ics"'},
        )

    @app.route("/api/stats", methods=["GET"])
    def api_stats():
        return jsonify(_read_stats())

    # ── Google Calendar OAuth ──────────────────────────────────────────────

    def _gcal_tokens_path() -> str:
        return os.path.join(_user_sessions_dir(), ".gcal_tokens.json")

    def _gcal_redirect_uri() -> str:
        # Use https:// in production (Railway proxy reports http but serves https)
        base = request.host_url.rstrip("/").replace("http://", "https://")
        return f"{base}/api/gcal/callback"

    @app.route("/api/gcal/status", methods=["GET"])
    def api_gcal_status():
        from time_calibration_agent import gcal_sync
        creds = gcal_sync.load_credentials(_gcal_tokens_path())
        return jsonify({"connected": creds is not None})

    @app.route("/api/gcal/auth", methods=["GET"])
    def api_gcal_auth():
        if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
            return jsonify({"error": "Google OAuth not configured on this server."}), 503
        from time_calibration_agent import gcal_sync
        state = flask_session.get("user_id", secrets.token_urlsafe(16))
        auth_url, code_verifier = gcal_sync.get_auth_url(_gcal_redirect_uri(), state)
        flask_session["gcal_code_verifier"] = code_verifier
        return redirect(auth_url)

    @app.route("/api/gcal/callback", methods=["GET"])
    def api_gcal_callback():
        from time_calibration_agent import gcal_sync
        state = request.args.get("state", "")
        code = request.args.get("code", "")
        error = request.args.get("error", "")

        if error:
            return redirect("/?gcal=denied")

        if state != flask_session.get("user_id", ""):
            return jsonify({"error": "State mismatch — possible CSRF."}), 400

        code_verifier = flask_session.pop("gcal_code_verifier", None)
        try:
            creds = gcal_sync.exchange_code(_gcal_redirect_uri(), code, code_verifier)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Token exchange failed: {e}"}), 500

        tokens_path = _gcal_tokens_path()
        os.makedirs(os.path.dirname(tokens_path), exist_ok=True)
        with open(tokens_path, "w") as f:
            f.write(creds.to_json())

        return redirect("/?gcal=connected")

    @app.route("/api/gcal/push", methods=["POST"])
    def api_gcal_push():
        from time_calibration_agent import gcal_sync
        creds = gcal_sync.load_credentials(_gcal_tokens_path())
        if not creds:
            return jsonify({"error": "Not connected to Google Calendar."}), 401

        session_store = DaySessionStore(root_dir=_user_sessions_dir())
        session_id = session_store.load_last_session_id()
        if not session_id:
            return jsonify({"error": "No active session."}), 404

        session = session_store.load_session(session_id)
        if not session or not session.get("replans"):
            return jsonify({"error": "No plan found."}), 404

        last_replan = session["replans"][-1]
        time_blocks = last_replan.get("plan_output", {}).get("time_blocks", [])
        date_str = session_id.split("__")[0]

        data = request.get_json(force=True, silent=True) or {}
        timezone = data.get("timezone", "UTC")

        # Filter out events that have already ended (client sends minutes since midnight)
        now_mins = data.get("nowMinutes", -1)
        if isinstance(now_mins, (int, float)) and now_mins >= 0:
            def _end_mins(block):
                try:
                    h, m = block["end"].split(":")
                    return int(h) * 60 + int(m)
                except Exception:
                    return 9999
            future = [b for b in time_blocks if _end_mins(b) > now_mins]
            if future:
                time_blocks = future

        try:
            count = gcal_sync.push_events(creds, time_blocks, date_str, timezone)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to push events: {e}"}), 500

        return jsonify({"pushed": count})

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

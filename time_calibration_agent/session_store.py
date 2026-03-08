"""
Day session storage for replanning.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from time_calibration_agent.day_model import DaySession


class DaySessionStore:
    def __init__(self, root_dir: str = "day_sessions"):
        self.root_dir = Path(root_dir)
        self.last_session_path = self.root_dir / ".last_session"

    def _ensure_root(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def build_session_id(self, date_str: Optional[str] = None, label: Optional[str] = None) -> str:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        if label:
            safe_label = "".join(c for c in label if c.isalnum() or c in ("-", "_"))
            return f"{date_str}__{safe_label}"
        return date_str

    def _path_for_session(self, session_id: str) -> Path:
        return self.root_dir / f"{session_id}.json"

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._path_for_session(session_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_session(self, session: Dict[str, Any]) -> None:
        self._ensure_root()
        path = self._path_for_session(session["session_id"])
        with path.open("w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        self._save_last_session(session["session_id"])

    def _save_last_session(self, session_id: str) -> None:
        self._ensure_root()
        with self.last_session_path.open("w", encoding="utf-8") as f:
            f.write(session_id)

    def load_last_session_id(self) -> Optional[str]:
        if not self.last_session_path.exists():
            return None
        with self.last_session_path.open("r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None

    def get_session_end_time(self, session_id: str) -> Optional[str]:
        session = self.load_session(session_id)
        if not session:
            return None
        return session.get("session_end_time")

    def append_replan(
        self,
        session_id: str,
        raw_input: str,
        plan_output: Dict[str, Any],
        current_time: str,
        extra: Optional[Dict[str, Any]] = None,
        overwrite: bool = False,
        session_end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = None if overwrite else self.load_session(session_id)
        if not session:
            session_obj = DaySession(
                session_id=session_id,
                created_at=datetime.now().isoformat(timespec="seconds"),
            )
            session = session_obj.to_dict()
            if overwrite:
                session["phase"] = "draft"

        # Store/update session_end_time at top-level if provided
        if session_end_time is not None:
            session["session_end_time"] = session_end_time

        session.setdefault("replans", [])
        replan_entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "current_time": current_time,
            "raw_input": raw_input,
            "plan_output": plan_output,
        }
        if extra:
            replan_entry.update(extra)

        session["replans"].append(replan_entry)

        self.save_session(session)
        return session

    def approve_session(self, session_id: str) -> Dict[str, Any]:
        """Set phase='approved', store anchor_plan from last replan."""
        session = self.load_session(session_id)
        if not session:
            return {}
        session["phase"] = "approved"
        if session.get("replans"):
            session["anchor_plan"] = session["replans"][-1]["plan_output"]
        self.save_session(session)
        return session

"""
Replanning agent for building a realistic plan for the rest of the day.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from openai import OpenAI
from dotenv import load_dotenv
from time_calibration_agent.agent import EstimationAgent


# Load .env if present (same behavior as agent.py)
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)


class ReplanningAgent:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.estimator = EstimationAgent(api_key=api_key)

    def plan(
        self,
        raw_text: str,
        current_time: Optional[str] = None,
        last_plan: Optional[Dict[str, Any]] = None,
        last_input: Optional[str] = None,
        estimated_tasks: Optional[list] = None,
    ) -> Dict[str, Any]:
        inferred_time = self._infer_time_from_text(raw_text)
        now = inferred_time or current_time or datetime.now().strftime("%H:%M")
        last_plan_json = json.dumps(last_plan, indent=2) if last_plan else "None"
        last_input_text = last_input or "None"
        if estimated_tasks is None:
            remaining_tasks = self._extract_remaining_tasks(raw_text, now)
            estimated_tasks = self._estimate_tasks(remaining_tasks)
        estimated_tasks_json = json.dumps(estimated_tasks, indent=2)

        prompt = f"""You are an ADHD-friendly replanning assistant.

Current time (authoritative): {now}

User context (latest):
"""
        prompt += raw_text.strip() + "\n\n"
        prompt += "Estimated remaining tasks (use these durations):\n"
        prompt += estimated_tasks_json + "\n\n"
        prompt += "Previous session input (if any):\n" + last_input_text + "\n\n"
        prompt += "Previous plan output (if any):\n" + last_plan_json + "\n\n"
        prompt += """Task: Create a realistic plan for the rest of the day.

Rules:
- Do not schedule anything before the current time.
- Respect hard constraints (meetings, deadlines).
- Soft preferences are used only if they fit.
- If overbooked, drop the lowest priority tasks.
- Output time blocks in chronological order.
- Use 24-hour time format HH:MM for start/end.
- Provide 1-3 immediate next actions.
- Provide a plan-level confidence range with low/high between 0 and 1.

Return ONLY valid JSON with this exact schema:
{
  "time_blocks": [
    {"start": "HH:MM", "end": "HH:MM", "task": "...", "kind": "task|fixed|break"}
  ],
  "next_actions": ["..."],
  "drop_or_defer": ["..."],
  "confidence": {"low": 0.0, "high": 1.0},
  "rationale": "..."
}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful replanning assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            result = json.loads(response.choices[0].message.content)
            normalized = self._normalize_output(result)
            return self._validate_plan(now, normalized)
        except Exception as e:
            print(f"Warning: replanning failed: {e}")
            return self._fallback_plan(now)

    def plan_with_estimates(
        self,
        raw_text: str,
        current_time: Optional[str] = None,
        last_plan: Optional[Dict[str, Any]] = None,
        last_input: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], list]:
        inferred_time = self._infer_time_from_text(raw_text)
        now = inferred_time or current_time or datetime.now().strftime("%H:%M")
        remaining_tasks = self._extract_remaining_tasks(raw_text, now)
        estimated_tasks = self._estimate_tasks(remaining_tasks)
        plan_output = self.plan(
            raw_text=raw_text,
            current_time=now,
            last_plan=last_plan,
            last_input=last_input,
            estimated_tasks=estimated_tasks,
        )
        return plan_output, estimated_tasks

    def _normalize_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        time_blocks = result.get("time_blocks", [])
        next_actions = result.get("next_actions", [])
        drop_or_defer = result.get("drop_or_defer", [])
        confidence = result.get("confidence", {})
        rationale = result.get("rationale", "")

        if not isinstance(time_blocks, list):
            time_blocks = []
        if not isinstance(next_actions, list):
            next_actions = []
        if not isinstance(drop_or_defer, list):
            drop_or_defer = []
        if not isinstance(confidence, dict):
            confidence = {"low": 0.4, "high": 0.7}

        low = confidence.get("low", 0.4)
        high = confidence.get("high", 0.7)
        try:
            low = float(low)
            high = float(high)
        except Exception:
            low, high = 0.4, 0.7

        if low < 0:
            low = 0.0
        if high > 1:
            high = 1.0
        if low > high:
            low, high = high, low

        return {
            "time_blocks": time_blocks,
            "next_actions": next_actions,
            "drop_or_defer": drop_or_defer,
            "confidence": {"low": low, "high": high},
            "rationale": rationale,
        }

    def _validate_plan(self, now: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure plan does not start before current time and is time-ordered."""
        def to_minutes(hhmm: str) -> Optional[int]:
            try:
                parts = hhmm.split(":")
                if len(parts) != 2:
                    return None
                h = int(parts[0])
                m = int(parts[1])
                if h < 0 or h > 23 or m < 0 or m > 59:
                    return None
                return h * 60 + m
            except Exception:
                return None

        def to_hhmm(minutes: int) -> str:
            h = (minutes // 60) % 24
            m = minutes % 60
            return f"{h:02d}:{m:02d}"

        now_min = to_minutes(now)
        if now_min is None:
            return plan

        cleaned = []
        for block in plan.get("time_blocks", []):
            start = block.get("start", "")
            end = block.get("end", "")
            start_min = to_minutes(start)
            end_min = to_minutes(end)
            if start_min is None or end_min is None:
                continue
            if end_min < start_min:
                start_min, end_min = end_min, start_min
            if end_min <= now_min:
                continue
            if start_min < now_min < end_min:
                start_min = now_min
            block["start"] = to_hhmm(start_min)
            block["end"] = to_hhmm(end_min)
            cleaned.append(block)

        cleaned.sort(key=lambda b: to_minutes(b.get("start", "00:00")) or 0)
        plan["time_blocks"] = cleaned
        return plan

    def _fallback_plan(self, now: str) -> Dict[str, Any]:
        return {
            "time_blocks": [
                {"start": now, "end": now, "task": "Unable to generate plan", "kind": "task"}
            ],
            "next_actions": ["Try again with more details"],
            "drop_or_defer": [],
            "confidence": {"low": 0.1, "high": 0.2},
            "rationale": "Fallback plan used due to error.",
        }

    def _infer_time_from_text(self, raw_text: str) -> Optional[str]:
        """
        Infer a time like '2pm' or '3:30 PM' or '14:00' from user input.
        Returns HH:MM in 24-hour format, or None if not found.
        """
        import re

        if not raw_text:
            return None

        # Match 24h time like 14:30 or 09:00
        m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", raw_text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            return f"{hour:02d}:{minute:02d}"

        # Match 12h time like 2pm, 2:15 PM
        m = re.search(r"\b([1-9]|1[0-2])(?::([0-5]\d))?\s*([ap]m)\b", raw_text, re.IGNORECASE)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or "00")
            meridiem = m.group(3).lower()
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"

        return None

    def _extract_remaining_tasks(self, raw_text: str, now: str) -> list:
        """Use the LLM to extract remaining tasks from raw input."""
        prompt = f"""Extract ONLY the remaining tasks the user still needs to do.\n\nCurrent time: {now}\n\nUser input:\n{raw_text}\n\nReturn JSON:\n{{\"remaining_tasks\": [\"...\"]}}"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract remaining tasks. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            tasks = result.get("remaining_tasks", [])
            if isinstance(tasks, list):
                return [str(t).strip() for t in tasks if str(t).strip()]
        except Exception as e:
            print(f"Warning: task extraction failed: {e}")
        return []

    def _estimate_tasks(self, tasks: list) -> list:
        """Estimate durations for each remaining task using the estimator."""
        estimates = []
        for task in tasks:
            est = self.estimator.estimate_task(task_description=task)
            estimates.append(
                {
                    "task": task,
                    "estimated_minutes": est.get("estimated_minutes"),
                    "estimate_range": est.get("estimate_range"),
                    "category": est.get("category"),
                    "ambiguity": est.get("ambiguity"),
                }
            )
        return estimates

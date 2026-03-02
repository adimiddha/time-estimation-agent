"""
Replanning agent for building a realistic plan for the rest of the day.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from openai import OpenAI
from dotenv import load_dotenv
from time_calibration_agent.agent import EstimationAgent


# Load .env if present (same behavior as agent.py)
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)


class ReplanningAgent:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4.1"):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.estimator = EstimationAgent(api_key=api_key)

    def extract_clarification(
        self,
        raw_text: str,
        current_time: str,
    ) -> Dict[str, Any]:
        """
        Lightweight clarification extraction (gpt-4o-mini, ~200 tokens).
        Determines if the user mentioned a session end time and whether a follow-up is needed.
        Returns: {session_end_time: "HH:MM"|None, follow_up_question: str|None, follow_up_type: "end_time"|"ordering"|None}
        """
        prompt = (
            f"You are a minimal time-parsing assistant.\n\n"
            f"Current time: {current_time}\n\n"
            f"User input:\n{raw_text}\n\n"
            f"Your ONLY job: determine if the user has mentioned when they want to be done today "
            f"(a session end time).\n\n"
            f"Examples:\n"
            f'- "done by 7pm" → session_end_time: "19:00"\n'
            f'- "finish by 5:30" → session_end_time: "17:30"\n'
            f'- "wrap up at noon" → session_end_time: "12:00"\n'
            f'- "done by 5" (current time is {current_time}) → if after noon, "5" = 17:00\n'
            f'- "whenever" / "no rush" / "flexible" → no end time, no follow-up needed\n'
            f"- No mention at all → ask the user\n\n"
            f"Return JSON with exactly these fields:\n"
            f'{{"session_end_time": "HH:MM or null", "follow_up_question": "string or null", '
            f'"follow_up_type": "end_time or ordering or null"}}\n\n'
            f"Rules:\n"
            f"- End time found: set session_end_time to HH:MM, follow_up_question to "
            f'"Anything locked to a specific time, or that needs to happen before something else?", '
            f'follow_up_type to "ordering".\n'
            f'- "whenever"/flexible: set all three fields to null (no follow-up).\n'
            f"- No end time mentioned: set session_end_time to null, follow_up_question to "
            f'"When do you want to wrap up today?", follow_up_type to "end_time".\n'
            f"- Ambiguous time (e.g. 'by 5', no AM/PM): infer from current time; if after noon assume PM.\n"
            f"- Respond ONLY with the JSON object. No other text."
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a time-parsing assistant. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=200,
            )
            result = json.loads(response.choices[0].message.content)
            end_time = result.get("session_end_time")
            follow_up = result.get("follow_up_question")
            follow_up_type = result.get("follow_up_type")

            # Validate/normalize end_time
            if end_time and str(end_time) not in ("null", ""):
                parts = str(end_time).split(":")
                if len(parts) == 2:
                    try:
                        h, m = int(parts[0]), int(parts[1])
                        end_time = f"{h:02d}:{m:02d}" if (0 <= h <= 23 and 0 <= m <= 59) else None
                    except ValueError:
                        end_time = None
                else:
                    end_time = None
            else:
                end_time = None

            if follow_up in (None, "null", ""):
                follow_up = None
            if follow_up_type in (None, "null", ""):
                follow_up_type = None

            return {
                "session_end_time": end_time,
                "follow_up_question": follow_up,
                "follow_up_type": follow_up_type,
            }
        except Exception as e:
            print(f"Warning: clarification extraction failed: {e}")
            return {
                "session_end_time": None,
                "follow_up_question": "When do you want to wrap up today?",
                "follow_up_type": "end_time",
            }

    def plan(
        self,
        raw_text: str,
        current_time: Optional[str] = None,
        last_plan: Optional[Dict[str, Any]] = None,
        last_input: Optional[str] = None,
        estimated_tasks: Optional[list] = None,
        extracted_context: Optional[Dict[str, Any]] = None,
        session_end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        inferred_time = self._infer_time_from_text(raw_text)
        now = inferred_time or current_time or datetime.now().strftime("%H:%M")
        last_plan_json = json.dumps(last_plan, indent=2) if last_plan else "None"
        last_input_text = last_input or "None"
        if estimated_tasks is None:
            if not extracted_context:
                extracted_context = self._extract_context(raw_text, now)
            remaining_tasks = extracted_context.get("remaining_tasks", [])
            estimated_tasks = self._estimate_tasks(remaining_tasks)
        estimated_tasks_json = json.dumps(estimated_tasks, indent=2)
        extracted_context_json = json.dumps(extracted_context or {}, indent=2)

        prompt = f"""You are an ADHD-friendly replanning assistant.

Current time (authoritative): {now}

User context (latest):
"""
        prompt += raw_text.strip() + "\n\n"
        prompt += "Structured extraction (remaining tasks, priorities, constraints):\n"
        prompt += extracted_context_json + "\n\n"
        prompt += "Estimated remaining tasks (use these durations):\n"
        prompt += estimated_tasks_json + "\n\n"
        prompt += "Previous session input (if any):\n" + last_input_text + "\n\n"
        prompt += "Previous plan output (if any):\n" + last_plan_json + "\n\n"
        prompt += "Task: Create a realistic plan for the rest of the day.\n\nRules:\n"
        prompt += "- Do not schedule anything before the current time.\n"
        prompt += "- Respect hard constraints (meetings, deadlines).\n"
        prompt += "- Soft preferences are used only if they fit.\n"
        prompt += "- If overbooked, drop the lowest priority tasks.\n"
        prompt += "- Infer natural task dependencies: if tasks clearly must happen in sequence\n"
        prompt += "  (e.g. 'pick up kids' before 'feed kids'), schedule them in that order automatically.\n"
        prompt += "- If tasks finish significantly before the session end time, add reasonable\n"
        prompt += "  sub-steps or prep time (e.g. 'prepare dinner' before 'eat dinner') to use\n"
        prompt += "  the available time naturally — do not leave large unexplained gaps.\n"
        prompt += "- Always use 12-hour time (e.g. '6pm', '2:30pm') in rationale and all text\n"
        prompt += "  fields. Never use 24-hour format in any text output.\n"
        prompt += "- Do not mention ADHD in any output field.\n"
        prompt += "- Output time blocks in chronological order.\n"
        prompt += "- Use 24-hour time format HH:MM for start/end.\n"
        prompt += "- Provide 1-3 immediate next actions.\n"
        prompt += "- Provide a plan-level confidence range with low/high between 0 and 1.\n"
        prompt += "- Explain why each dropped/deferred item was dropped.\n"
        if session_end_time:
            prompt += f"- HARD BOUNDARY: Do not schedule any block ending after {session_end_time}. "
            prompt += "If tasks won't fit, drop the lowest-priority ones.\n"
            prompt += "- If you had to infer AM/PM for this end time, note your interpretation in rationale.\n"
        prompt += """
Return ONLY valid JSON with this exact schema:
{
  "time_blocks": [
    {"start": "HH:MM", "end": "HH:MM", "task": "...", "kind": "task|fixed|break"}
  ],
  "next_actions": ["..."],
  "drop_or_defer": ["..."],
  "drop_reasons": ["..."],
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
        session_end_time: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], list, Dict[str, Any]]:
        inferred_time = self._infer_time_from_text(raw_text)
        now = inferred_time or current_time or datetime.now().strftime("%H:%M")
        # When replanning, combine previous input so previously-mentioned tasks aren't lost
        context_for_extraction = f"{last_input}\n{raw_text}" if last_input else raw_text
        extracted_context = self._extract_context(context_for_extraction, now)
        remaining_tasks = extracted_context.get("remaining_tasks", [])
        estimated_tasks = self._estimate_tasks(remaining_tasks)
        plan_output = self.plan(
            raw_text=raw_text,
            current_time=now,
            last_plan=last_plan,
            last_input=last_input,
            estimated_tasks=estimated_tasks,
            extracted_context=extracted_context,
            session_end_time=session_end_time,
        )
        return plan_output, estimated_tasks, extracted_context

    def _normalize_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        time_blocks = result.get("time_blocks", [])
        next_actions = result.get("next_actions", [])
        drop_or_defer = result.get("drop_or_defer", [])
        drop_reasons = result.get("drop_reasons", [])
        confidence = result.get("confidence", {})
        rationale = result.get("rationale", "")

        if not isinstance(time_blocks, list):
            time_blocks = []
        if not isinstance(next_actions, list):
            next_actions = []
        if not isinstance(drop_or_defer, list):
            drop_or_defer = []
        if not isinstance(drop_reasons, list):
            drop_reasons = []
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
            "drop_reasons": drop_reasons,
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
            "drop_reasons": [],
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

        # Match 24h time like 14:30 or 09:00 (not followed by am/pm or a.m./p.m.)
        m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*[ap]\.?m)", raw_text, re.IGNORECASE)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            return f"{hour:02d}:{minute:02d}"

        # Match 12h time like 2pm, 2:15 PM, 2 p.m.
        m = re.search(r"\b([1-9]|1[0-2])(?::([0-5]\d))?\s*([ap]\.?m)\b", raw_text, re.IGNORECASE)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or "00")
            meridiem = m.group(3).lower().replace('.', '')
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"

        return None

    def _extract_context(self, raw_text: str, now: str) -> Dict[str, Any]:
        """Extract remaining tasks, priorities, and constraints in structured form."""
        prompt = f"""Extract remaining tasks, priorities, and constraints.\n\nCurrent time: {now}\n\nUser input:\n{raw_text}\n\nReturn JSON exactly:\n{{\n  \"remaining_tasks\": [\n    {{\"task\": \"...\", \"priority\": \"high|medium|low\"}}\n  ],\n  \"constraints\": {{\n    \"time_blocks\": [{{\"start\": \"HH:MM\", \"end\": \"HH:MM\", \"label\": \"...\"}}],\n    \"deadlines\": [{{\"time\": \"HH:MM\", \"label\": \"...\"}}]\n  }}\n}}"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Extract remaining tasks and constraints. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            tasks = result.get("remaining_tasks", [])
            if not isinstance(tasks, list):
                tasks = []
            cleaned_tasks = []
            for t in tasks:
                if isinstance(t, dict):
                    task_text = str(t.get("task", "")).strip()
                    priority = str(t.get("priority", "medium")).lower().strip()
                else:
                    task_text = str(t).strip()
                    priority = "medium"
                if not task_text:
                    continue
                if priority not in ("high", "medium", "low"):
                    priority = "medium"
                cleaned_tasks.append({"task": task_text, "priority": priority})

            constraints = result.get("constraints", {})
            if not isinstance(constraints, dict):
                constraints = {}
            time_blocks = constraints.get("time_blocks", [])
            deadlines = constraints.get("deadlines", [])
            if not isinstance(time_blocks, list):
                time_blocks = []
            if not isinstance(deadlines, list):
                deadlines = []

            return {
                "remaining_tasks": cleaned_tasks,
                "constraints": {
                    "time_blocks": time_blocks,
                    "deadlines": deadlines,
                },
            }
        except Exception as e:
            print(f"Warning: task extraction failed: {e}")
        return {"remaining_tasks": [], "constraints": {"time_blocks": [], "deadlines": []}}

    def _estimate_tasks(self, tasks: List[Dict[str, Any]]) -> list:
        """Estimate durations for each remaining task using the estimator."""
        estimates = []
        for task in tasks:
            task_text = task.get("task", "")
            priority = task.get("priority", "medium")
            est = self.estimator.estimate_task(task_description=task_text)
            estimates.append(
                {
                    "task": task_text,
                    "priority": priority,
                    "estimated_minutes": est.get("estimated_minutes"),
                    "estimate_range": est.get("estimate_range"),
                    "category": est.get("category"),
                    "ambiguity": est.get("ambiguity"),
                }
            )
        return estimates

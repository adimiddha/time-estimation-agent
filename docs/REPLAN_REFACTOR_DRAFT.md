# Replanning MVP Refactor Draft

## Goals
- MVP focuses on a single capability: **“replan the rest of my day when I’m behind.”**
- Keep input friction low: **raw text** only (voice later).
- Output is **structured JSON** so we can plug into a UI later.
- Defer calibration, bias multipliers, and long-term learning until after MVP.

## Recommendation: Session Identity
**Default:** session per day, with an optional session label override.
- Most users will use it once per day; a day-based default is simplest.
- Allow `--session` to create multiple sessions in a day when needed.

**MVP approach**
- Session ID format: `YYYY-MM-DD` by default.
- Optional: `YYYY-MM-DD::<label>` if user passes `--session label`.
- Storage path: `day_sessions/2026-02-22.json` or `day_sessions/2026-02-22__label.json`.

This is easy to implement and flexible enough for rare multi-session use.

## Confidence Range (MVP)
Use a **plan-level confidence range**, not per-task.
- Meaning: “confidence the plan is feasible if followed.”
- Output example: `{ "confidence": { "p50": "likely", "p80": "tight" } }` or `{ "confidence": { "low": 0.4, "high": 0.7 } }`.

Per-task confidence can be added later once duration estimation is robust.

## Input Contract (Raw Text)
For MVP, accept a single text block:
- “It’s 2pm. I already did X. I still need A, B, C. Constraints: dinner at 7, meeting 4-5.”

The LLM parses:
- current time
- done list
- remaining tasks
- constraints (hard/soft)
- priorities (infer importance × urgency when explicit priorities are absent)

## Output Contract (Structured JSON)
Minimum output fields:
- `time_blocks`: ordered list of blocks with start/end + task
- `next_actions`: 1–3 concrete steps
- `drop_or_defer`: tasks to drop or push later
- `confidence`: plan-level confidence range
- `rationale`: short justification

Example:
```json
{
  "time_blocks": [
    {"start": "15:15", "end": "16:00", "task": "Draft client email"},
    {"start": "16:00", "end": "17:00", "task": "Meeting (fixed)"},
    {"start": "17:15", "end": "18:30", "task": "Finalize slide deck"}
  ],
  "next_actions": [
    "Open the slide deck and outline the 3 key points",
    "Draft the client email with bullet points",
    "Prep meeting notes"
  ],
  "drop_or_defer": ["Research new tools", "Inbox zero"],
  "confidence": {"low": 0.45, "high": 0.7},
  "rationale": "This plan fits the available time if you skip low-priority items."
}
```

## MVP Behavior Rules
1. **Respect hard constraints** (meetings, deadlines).
2. **Soft preferences** are used only when feasible.
3. **Drop lowest priority** tasks when the schedule overflows.
4. Keep blocks simple: no need for advanced scheduling or optimization.

## Proposed Refactor Plan (MVP)

### New/Changed Modules
- `time_calibration_agent/day_model.py`
  - Data classes for `DayContext`, `Task`, `Constraint`, `PlanOutput`.
- `time_calibration_agent/replanner.py`
  - Orchestrates parsing, estimates rough durations, fills time blocks, drops tasks.
- `time_calibration_agent/session_store.py`
  - Reads/writes day session JSON files, appends replans.
- `time_calibration_agent/cli.py`
  - New command: `plan` (create/replan a session)
  - New command: `update` (log actuals + replan)
  - New command: `status` (show current plan)

### Storage
- New folder `day_sessions/`
- Each session file contains:
  - raw user inputs
  - parsed context
  - plan outputs
  - timestamps for each replan

## MVP Scope (Explicitly Deferred)
- Calibration or bias multipliers
- Long-term user history across days
- Per-task confidence ranges
- Full scheduler optimization
- Web UI
- Voice input

## Evaluation (Simple and Cheap)
- Use small synthetic day scenarios in JSON to test:
  - respects constraints
  - drops lowest priority
  - outputs valid JSON
  - outputs next actions
- Manual QA by running `plan` on 5–10 real scenarios.

## Next Steps
1. Implement session ID scheme and storage layout.
2. Define schemas in `day_model.py`.
3. Implement `replanner.py` with a greedy schedule + drop logic.
4. Update CLI to support `plan`, `update`, and `status`.
5. Add 3–5 sample day scenarios for eval.

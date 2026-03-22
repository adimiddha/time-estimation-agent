# Feature Plan: Batch Estimation Refactor

**Status:** Ready to implement
**Goal:** Replace N serial gpt-4.1 estimation calls with a single gpt-4o-mini batch call
**Expected latency improvement:** ~12-15s (5 tasks) → ~1-2s

---

## Background

The current `_estimate_tasks()` loop in `replanner.py` calls `estimate_task()` once per task serially. Each call is a full gpt-4.1 round trip (~2-3s). A 5-task day = ~12-15s just for estimation. This is the primary latency bottleneck.

Key finding: the replanning path already passes **no** historical context to `estimate_task()` — so the batch refactor introduces zero regression on context quality.

---

## Changes Required

### File 1: `time_calibration_agent/agent.py`

Add a new method `estimate_tasks_batch()` to `EstimationAgent`. **Do not modify `estimate_task()`** — it is used by the CLI path and must remain intact.

**Method signature:**
```python
def estimate_tasks_batch(
    self,
    tasks: List[Dict[str, Any]],
    calibration_context: Optional[Dict] = None,
    historical_tasks: Optional[List[Dict]] = None,
) -> List[Dict[str, Any]]:
```

**Logic:**
1. If `tasks` is empty, return `[]`
2. Build a minimal shared context string from `calibration_context` if provided (use `_build_minimal_context()` or equivalent)
3. Build the batch prompt (see below)
4. Call `client.chat.completions.create()` with:
   - model: `"gpt-4o-mini"`
   - `response_format={"type": "json_object"}`
   - `temperature=0.3`
   - no `max_tokens` cap
5. Parse response, match items by `id` field (not position)
6. Call `validate_and_normalize_category()` on each returned `category`
7. Return list of dicts with keys: `task`, `priority`, `estimated_minutes`, `estimate_range`, `category`, `ambiguity`
8. On any exception, fall back to calling `estimate_task()` per task serially (zero-regression fallback)
9. After parsing, verify `len(estimates) == len(tasks)` — fall back to serial for any missing `id`

**Batch prompt:**
```
System: "You are a time estimation expert. Estimate durations for ALL tasks in the list below.
Respond ONLY with valid JSON matching the schema provided."

User:
SHARED CONTEXT:
{shared_calibration_summary}  ← optional, include if calibration_context provided

TASKS TO ESTIMATE:
[
  {"id": 0, "task": "...", "priority": "high"},
  {"id": 1, "task": "...", "priority": "medium"},
  ...
]

Return JSON with exactly this schema:
{
  "estimates": [
    {
      "id": 0,
      "estimated_minutes": <int>,
      "estimate_range": {"optimistic": <int>, "realistic": <int>, "pessimistic": <int>},
      "category": "<deep work|admin|social|errands|coding|writing|meetings|learning|general>",
      "ambiguity": "<clear|moderate|fuzzy>"
    },
    ...
  ]
}

Rules:
- One entry per task, in the same order as the input.
- "estimated_minutes" must equal "estimate_range.realistic".
- Category must be one of the exact values listed.
- Do not include explanations in the response.
```

**Fallback (inside except block):**
```python
results = []
for task in tasks:
    task_text = task.get("task", "")
    priority = task.get("priority", "medium")
    est = self.estimate_task(task_description=task_text)
    results.append({
        "task": task_text,
        "priority": priority,
        "estimated_minutes": est.get("estimated_minutes"),
        "estimate_range": est.get("estimate_range"),
        "category": est.get("category"),
        "ambiguity": est.get("ambiguity"),
    })
return results
```

---

### File 2: `time_calibration_agent/replanner.py`

Replace the body of `_estimate_tasks()` (currently lines ~459-476) with a one-line delegation:

```python
def _estimate_tasks(self, tasks: List[Dict[str, Any]]) -> list:
    """Estimate durations for all remaining tasks in a single batched API call."""
    if not tasks:
        return []
    return self.estimator.estimate_tasks_batch(tasks)
```

No other changes to this file.

---

## Files NOT changed

- `cli.py` — uses `estimate_task()` directly, unaffected
- `web_app.py` — no changes needed; `existing_estimates` reuse in replan mode is already handled upstream of `_estimate_tasks()`
- `session_store.py`, `day_model.py` — unaffected

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Model returns estimates out of order | Match by `id` field, not list position |
| JSON parse error | Full serial fallback in except block |
| Partial results (model drops tasks) | Check `len(estimates) == len(tasks)`; fall back to serial for missing ids |
| Quality regression (gpt-4o-mini vs gpt-4.1) | Low risk — duration estimation is structured output, not deep reasoning. Also: current path already uses no historical context. |

---

## Future: Option C (merge clarify + context extraction)

After this ships, consider merging `extract_clarification()` and `_extract_context()` into a single call. Both parse the same raw user text. A merged call would save ~2s and potentially hit the 2-3s total target.

That refactor is more complex (the clarify call happens at a different API endpoint than context extraction) and should be a separate plan/PR.

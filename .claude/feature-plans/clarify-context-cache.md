# Feature Plan: Clarify + Context Cache (Scoped)

**Status:** Approved (scoped down from original proposal)
**Goal:** Front-load _extract_context() work during the clarify screen so /api/plan wall clock time shrinks by ~1.5s. Target: total planning time <5s after the batch estimation and model benchmark changes.

---

## Problem

After the batch estimation refactor, the remaining wall-clock latency at /api/plan time is:
- `_extract_context()` — ~2s, gpt-4.1
- `plan()` — 3-5s, gpt-4.1 (addressed by the model benchmark plan separately)

`_extract_context()` runs on the brain dump text, which the server already has at /api/clarify time. The user is reading a follow-up question for ~5-10s before submitting. This is dead latency that could be used to run extraction in the background.

---

## Why the naive "cache and reuse" approach is rejected

The follow-up answer often contains structured information that `_extract_context()` needs:
- Hard fixed times ("call at 4pm", "dentist can't move")
- Ordering constraints ("email before the call")
- Deadlines ("invoice by 3pm")

If extraction runs only on the brain dump, these are invisible to the structured task list passed to batch estimation and plan(). They are present in raw_text when plan() runs, but the plan() prompt trusts extracted_context_json as the authoritative task list. Missing a constraint here produces an incorrect plan, violating "trustworthy output."

A full re-extraction at /api/plan time with the combined text would eliminate the latency benefit.

---

## Proposed Solution: Eager extraction + lightweight constraint patch

**At /api/clarify time:**
1. Run `_extract_context()` on the raw brain dump (existing behavior moved earlier, same cost).
2. Cache the result as `initial_context` in the Flask session.
3. Return the clarification response as normal.

**At /api/plan time:**
1. Retrieve `initial_context` from session cache.
2. Run a new lightweight `_patch_constraints()` call (gpt-4o-mini, ~150 tokens) on just the follow-up answer text.
3. Merge: append any new tasks, time_blocks, or deadlines from the patch into `initial_context`.
4. Use the merged context as `extracted_context` — skip the full `_extract_context()` call.

**Net change:** `_extract_context()` moves from /api/plan to /api/clarify (no time saved in compute, but it runs in parallel with the user reading). `_patch_constraints()` at plan time is a much cheaper call (~0.3s) than the full extraction (~2s). Net /api/plan savings: ~1.5s.

---

## Scope

### In

- New method `_patch_constraints(follow_up_answer: str, current_context: Dict) -> Dict` in `replanner.py`
  - Uses `gpt-4o-mini`, max_tokens=200, temperature=0.1
  - Prompt: given the follow-up answer text and the already-extracted task list, return only new constraints or task amendments (new time_blocks, new deadlines, priority changes)
  - Falls back to returning `current_context` unchanged on any exception
- `/api/clarify` endpoint in `web_app.py`: after extracting clarification, also call `_extract_context()` and store result in `session["initial_context"]`
- `/api/plan` endpoint in `web_app.py`: read `session["initial_context"]` if available; call `_patch_constraints(follow_up_answer, initial_context)`; pass merged result as `extracted_context` to `plan_with_estimates()`
- `plan_with_estimates()` in `replanner.py`: accept optional `extracted_context` parameter (already accepts this via `plan()` — verify the pass-through works)
- Cache invalidation: clear `session["initial_context"]` after it is consumed by /api/plan, so replans don't use stale extraction

### Out of scope

- Changing the clarification question logic in `extract_clarification()` — that method stays as-is
- Changing the batch estimation flow
- Prefetching or streaming plan() output
- Replan path (adjustment_mode=True) — this path already has estimated_tasks passed in; leave it unchanged

---

## Acceptance Criteria

1. /api/plan wall clock time decreases by ≥1s in manual testing on a 4-task brain dump with a follow-up answer that adds no new constraints (baseline case).
2. A brain dump with a follow-up answer containing a hard fixed time (e.g., "call at 4pm") produces a plan where that fixed time appears in the schedule. This is the regression test for the quality risk.
3. A brain dump with a follow-up answer containing no new structured information (e.g., "wrapping up by 7pm, no other fixed stuff") produces an identical plan to the pre-change behavior.
4. If `/api/clarify` fails or `initial_context` is missing from the session, `/api/plan` falls back silently to calling `_extract_context()` on the full combined text (zero-regression fallback).
5. No change to the CLI path (`plan_with_estimates()` called from `cli.py`) — the cache logic is in `web_app.py` only.

---

## Sequencing

Implement after the model benchmark plan. Reason: the model benchmark may reduce plan() from 3-5s to 1.5-2.5s. If that alone hits the <5s target, the engineering cost of this plan may not be justified. Run the benchmark first, measure total latency after a model switch, then decide whether this plan is still needed.

---

## Notes for Engineer

`plan_with_estimates()` already accepts `estimated_tasks` to skip re-estimation on replan. You need to add the same pass-through for `extracted_context`. Check line 255 in `replanner.py` — `_extract_context()` is called unconditionally there. Add a guard: `if extracted_context is None: extracted_context = self._extract_context(...)`.

The Flask session is cookie-backed by default. `initial_context` is a small dict (task list + constraints). Size should be well within the 4KB session cookie limit for typical days (≤10 tasks). Verify this does not grow beyond that for edge cases.

`_patch_constraints()` should have a narrow prompt that explicitly says "return only NEW items not already in the current context." If it returns everything, the merge step will produce duplicates.

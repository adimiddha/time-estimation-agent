# Feature Plan: Constraint Enforcement Prompt Fix

**Status:** Shipped 2026-03-22
**Goal:** Fix silent dropping/ignoring of user-stated time constraints (appointments, fixed meetings)

---

## Problem

User-reported: plans often ignore stated time constraints like "my appointment is at 3pm" or "I need to do X at this time."

Two root causes identified by code inspection:

### Root cause 1: `_extract_context()` prompt is too thin
The extraction prompt is a single line with no examples and no rules for classifying constraints. The model guesses what counts as a `time_block` vs `deadline` vs flexible task from the schema alone. Constraints get silently dropped or misclassified.

### Root cause 2: `plan()` constraint enforcement is a single vague line
The only rule is: `"- Respect hard constraints (meetings, deadlines)."` No instruction to use `kind: "fixed"`, no instruction to schedule fixed blocks first, no explicit prohibition on overlapping a fixed block.

---

## Fix

### 1. `_extract_context()` — add explicit rules + few-shot examples

Add before the JSON schema:
- Definition of what counts as a fixed time block vs deadline vs flexible task
- 3-4 inline examples covering common phrasings
- Explicit rule that fixed blocks must have accurate start+end times

### 2. `plan()` — expand constraint enforcement rule

Replace the single vague line with:
- Instruction to schedule fixed blocks first, at their exact stated time, with `kind: "fixed"`
- Explicit prohibition on placing any block overlapping a fixed time block
- Instruction that fixed blocks should not be dropped even if overbooked — drop flexible tasks instead

---

## Files Changed

- `time_calibration_agent/replanner.py` — `_extract_context()` prompt and `plan()` constraint rule

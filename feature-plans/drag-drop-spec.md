# Feature Spec: Drag-to-Reorder Time Blocks (Phase 1)

**Status:** Approved 2026-03-19
**Scope:** Phase 1 only. Phase 2 (edge-drag to resize) is explicitly out of scope and remains rejected.

---

## Problem

After approving a draft schedule, users frequently want to swap the order of two tasks — "I'd rather do X before Y" — without changing any block's duration or triggering a full AI replan. The current path for this micro-adjustment is the voice/text replan panel, which introduces AI round-trip latency for an operation that requires zero AI judgment. For an ADHD-primary user already mid-day, that unnecessary latency is a friction point that discourages the replanning habit the product depends on.

---

## Proposed Solution

Allow users to drag calendar blocks to reorder them in **approved mode only**. Block durations are fixed throughout. When a block is dropped into a new position, adjacent blocks shift up or down to close the gap or make room. Start times update automatically. No user time-math is required at any point.

This is a deterministic sort operation — the same total time is redistributed, just in a different sequence. It is positioned as post-approval fine-tuning, downstream of the AI loop, not a replacement for it.

---

## Scope

**In scope:**
- Drag-to-reorder on the calendar in approved mode
- Adjacent blocks shift automatically to fill gaps; start times recalculate
- Works for `task` and `break` block types
- Touch support (mobile) — drag handle or long-press to initiate
- Visual drag state: dragged block renders at reduced opacity with a drop-zone indicator showing where it will land
- Fixed-event blocks (`fixed` kind) are **not draggable** and act as hard boundaries — a dragged block cannot be dropped to overlap a fixed event
- After a drag, the "Right Now" panel updates to reflect the new current block

**Out of scope (Phase 1):**
- Draft mode — drag is disabled before the user approves the plan
- Resizing blocks by dragging edges (Phase 2, not approved)
- Dragging across day boundaries
- Undo / redo (a voice/text replan achieves this)
- Persisting the reordered state to the server without a subsequent replan (the reordered state lives in frontend memory; a new replan from this state is the save path)

---

## Acceptance Criteria

1. A user can drag a task block to a new position on the calendar in approved mode; it lands, adjacent blocks shift, and start times update — all without a network call.
2. Fixed-event blocks do not move and act as hard stops; dragging a task block into a fixed event's slot is rejected (block snaps back).
3. On mobile (touch), a long-press or visible drag handle initiates the drag without conflicting with scroll.
4. The "Right Now" panel reflects the post-drag order within 300ms of drop.
5. The feature is invisible in draft mode — no drag handles, no drag behavior.
6. The existing calendar rendering constants (PIXELS_PER_HOUR, MIN_BLOCK_HEIGHT) are not changed as a result of this feature.

---

## Why Phase 2 Remains Rejected

Edge-dragging to resize a block changes its duration. Duration change requires the user to decide how much time to add or remove — that is time math, which VISION.md's ADHD-primary user should not have to perform under mid-day stress. Phase 2 also risks breaking the "realistic over optimistic" principle: a user who extends one block without AI judgment may end up with a plan that silently drops a task, with no draft review and no rationale shown. That is exactly the trust problem the draft screen exists to prevent.

Phase 2 can be re-evaluated if VISION.md's target user is broadened or if a design is proposed that makes duration changes honest (e.g., showing what gets dropped immediately when a block is resized).

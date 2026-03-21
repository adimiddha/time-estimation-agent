---
# Stale Plan Recovery

**Status:** Approved (reduced scope)
**Date:** 2026-03-21

---

## Problem

When a user plans their day and then returns to the app hours later (or the next day), the "Right Now" panel shows past blocks as if they are current. For an ADHD user experiencing time blindness, this is an active harm: the app's one job — answering "what do I do next?" — gives a confidently wrong answer. The replanning loop breaks down silently rather than recovering.

---

## Proposed solution

Detect when all planned blocks are in the past and replace the "Right Now" section content with a stale-state prompt. The prompt must immediately surface the existing replan slide-up panel — the same flow as the FAB replan panel — rather than redirecting the user or displaying a passive notification.

The Right Now panel goes from showing micro-steps → to showing: a one-line acknowledgment ("Looks like your day plan has passed") and a single primary CTA that opens the slide-up replan panel. The mic is available inside that panel as usual; it is not auto-activated.

No auto-redirect. No new screen. No separate notification layer.

---

## Scope

**In:**
- Frontend detection: compare all block end times against current time; if all are in the past, the plan is stale
- Replace Right Now panel content with stale-state prompt when condition is true
- Stale prompt contains a single CTA that triggers the existing replan voice/text entry (same as FAB panel)
- Detection runs on page load and on the existing `drawNowLine()` / `updateRightNow()` update tick (every minute)
- If the plan has zero blocks (new session, no plan yet), this condition does not trigger — stale detection only applies to approved plans with at least one block

**Out of scope (this feature):**
- Auto-redirect to the welcome/brain-dump screen for same-day stale plans (see new-day reset, below)
- Push notifications or OS-level reminders
- Persisting a "stale" flag server-side
- Any change to the calendar panel — blocks remain visible
- Any change to the replan API or backend — this is entirely frontend state

**Related behavior (approved, to be implemented alongside):**

| State | Condition | Behavior |
|---|---|---|
| New day | Date of last session != today | Reset to welcome screen |
| Same day, unapproved draft with expired first block | Draft first block start < now | Reset to welcome screen |
| Same day, unapproved draft, first block still ahead | Draft first block start > now | Restore to draft screen |
| Same day, approved, last block ended > 1 hour ago but not all blocks past | Last block end + 60 min < now | Nudge banner in Right Now panel (does not replace content) |
| Same day, approved, all blocks in past | All block end times < now | Full stale-state prompt (replaces Right Now content) |

---

## Acceptance criteria

1. Given an approved plan where all blocks end before the current time, the Right Now panel shows the stale prompt instead of micro-steps.
2. Tapping the stale prompt's CTA opens the slide-up replan panel within two taps/touches from the planner screen — consistent with the vision's stated ceiling. The mic is not auto-activated; it is available inside the panel as usual.
3. The calendar panel is unaffected — past blocks remain visible.
4. If the user replans from the stale prompt and approves a new plan, the Right Now panel returns to normal micro-step display.
5. Detection re-evaluates every minute (on the existing update tick); if a user leaves the tab open overnight and returns in the morning, the stale state is shown without requiring a page reload.
6. A plan with no blocks (empty session) does not trigger the stale state prompt.

---

## Risks and mitigations

**Risk: user's device clock is wrong or in a different timezone.**
The app already uses client-side `new Date()` for the now-line. This feature uses the same clock, so it is consistent — any existing clock-mismatch issues are inherited, not introduced.

**Risk: user has a plan that runs past midnight.**
The stale check should use the last block's end time, not the calendar day. A plan ending at 01:00 is not stale until after 01:00.

**Risk: stale prompt feels like an error state.**
Copy and visual treatment must be calm, not alarming. Consistent with VISION.md's "calm visual design" principle — warm neutral, not red/warning. Suggested copy: "Your plan wrapped up. Ready to map out what's next?"

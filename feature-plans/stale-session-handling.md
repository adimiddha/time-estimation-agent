# Stale Session Handling — Decision Record

**Status:** Approved 2026-03-22

---

## Problem

When a user returns to an unapproved draft later the same day, the current logic resets to the welcome screen if the first block's start time has already passed. This is too aggressive: a draft made at 9am is wiped at 9:10am even though 90% of the plan is still in the future.

This creates two compounding problems:
1. It destroys recoverable work at exactly the moment the user has the least executive bandwidth to start over.
2. The copy on the welcome screen ("You had a plan from earlier — it's a bit out of date. Start fresh or adjust it?") implied an adjust path that did not exist, violating user trust.

---

## Proposed Solution

Replace the single-condition reset trigger with a last-block-end check. Restore to draft unless the entire plan has already passed.

| Draft state | Condition | Behavior |
|---|---|---|
| Fully expired | Last block end < now | Reset to welcome |
| Partially past | First block start < now AND last block end > now | Restore to draft screen |
| Still valid | First block start > now | Restore to draft screen |

The "partially past" and "still valid" cases collapse to one rule: **restore to draft if any block is still in the future.**

---

## Scope

- Change the stale-detection condition in the session-restore logic from `firstBlockStart < now` to `lastBlockEnd < now`
- Update welcome-screen reset copy to remove the "adjust it" option entirely when the plan is fully expired: "Your earlier plan has fully passed. What's on for today?"
- No new UI surfaces, screens, or states

---

## Acceptance Criteria

- A draft made at 9:00am is restored to the draft screen at 9:10am, 10:00am, and any time before the last block ends
- A draft whose last block ended before the current time resets to the welcome screen
- The welcome-screen copy shown on full expiry contains no reference to adjusting or recovering the old plan
- The draft screen behavior after restoration is unchanged — user can still approve or trigger a replan from there

---

## Out of Scope

- Any changes to how approved sessions are handled
- Auto-advancing the "Right Now" panel based on how much time has passed
- Showing the user which blocks have already passed within the draft view
- Multi-day session recovery

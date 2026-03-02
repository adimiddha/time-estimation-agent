---
name: debug-ui
description: Diagnose and fix UI bugs in the time-calibration-agent web app. Invoke when the user describes any visual or layout issue — scroll, positioning, rendering, responsive breakage, time display, calendar blocks, or sticky header.
---

You are debugging a UI issue in the time-calibration-agent web app.

The UI consists of exactly four files:
- `time_calibration_agent/templates/index.html` — HTML structure: welcome screen, planner layout, sidebar, calendar container
- `time_calibration_agent/static/style.css` — all styling: CSS variables, layout, scroll behavior, responsive breakpoints (`@media (max-width: 768px)`)
- `time_calibration_agent/static/app.js` — all interactivity: calendar rendering (`renderCalendar`), block positioning, `fmt12()` time display, resize handling, replan API calls
- `time_calibration_agent/web_app.py` — Flask routes and JSON responses that feed the frontend

## Step 1: Assess what's already known

Read the user's message carefully. For each question below, mark it as answered or missing:

| Question | Answered if the user has... |
|---|---|
| **Component** | Named a specific element (calendar, sidebar, block, header, etc.) |
| **Existing behavior** | Described what it currently does (precise: "block extends past 8pm", "hidden under another block") |
| **Expected behavior** | Described what it should do instead |
| **Constraints** | Stated hard requirements ("must never overlap", "must work at all zoom levels", "works on mobile") |
| **Acceptance criteria** | Described how they'll know it's fixed ("every block should have its own visible space") |

Ask **only** for what is genuinely unanswered or too vague to act on. Ask all missing questions together in one message — never one at a time. Good prompting is specific: push for concrete descriptions, not just "it looks wrong."

Only ask about **goal/why** if the fix could reasonably go in multiple directions — for a clear bug, skip it.

If the user's message answers everything, skip this step entirely and go to Step 2.

## Step 2: Map symptom to files

Read ONLY the files relevant to the reported symptom:

| Symptom area | File(s) to read |
|---|---|
| Block positioning, overlap, stacking, pixel scaling | `app.js` — `renderCalendar`, `stickyBottom`, `MIN_BLOCK_HEIGHT` |
| Time display ("9am", "Noon", "2:30pm") | `app.js` — `fmt12()` |
| Scroll, overflow, height, sticky positioning | `style.css` — search for the component's CSS class |
| Responsive / stacked layout | `style.css` `@media` block + `app.js` resize logic |
| HTML structure, element nesting | `index.html` |
| API data driving the UI (wrong blocks, missing fields) | `web_app.py` |

## Step 3: Diagnose

Quote the specific lines responsible for the bug. Explain in 2–3 sentences why they cause the reported behavior. Reference the constraints and acceptance criteria the user gave you.

## Step 4: Fix

Apply a minimal, targeted fix. After applying it, confirm explicitly how it satisfies each constraint and acceptance criterion the user stated. Do not refactor surrounding code.

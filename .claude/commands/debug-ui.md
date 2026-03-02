You are debugging a UI issue in the time-calibration-agent web app.

The UI consists of exactly four files:
- `time_calibration_agent/templates/index.html` — HTML structure: welcome screen, planner layout, sidebar, calendar container
- `time_calibration_agent/static/style.css` — all styling: CSS variables, layout, scroll behavior, responsive breakpoints (`@media (max-width: 768px)`)
- `time_calibration_agent/static/app.js` — all interactivity: calendar rendering (`renderCalendar`), adaptive pixel-per-minute scaling, `fmt12()` time display, resize handling, replan API calls
- `time_calibration_agent/web_app.py` — Flask routes and JSON responses that feed the frontend

## Step 1: Interview

Ask the user ALL of these questions at once (do not ask one at a time):

1. **Which component or area is broken?**
   Examples: sidebar, calendar, sticky header, welcome screen, block layout, responsive/stacked view, time labels, re-plan button

2. **What is the symptom?**
   Examples: won't scroll, elements overlap, not visible, wrong size, clipped text, misaligned, wrong time format

3. **When does it happen?**
   Examples: always, only at high zoom, only on narrow viewport, after replanning, on first load, only in stacked layout

Wait for the user's answers before reading any files.

## Step 2: Map symptom to files

Read ONLY the files relevant to the reported symptom. Do not read files that are not implicated.

| Symptom area | File(s) to read |
|---|---|
| Scroll, overflow, height, sticky positioning | `style.css` — search for the component's CSS class |
| Calendar block positioning, pixel scaling, tick labels | `app.js` — focus on `renderCalendar`, `pixelsPerMinute`, tick logic |
| Time display ("9am", "Noon", "2:30pm") | `app.js` — focus on `fmt12()` |
| Responsive / stacked layout | `style.css` — focus on `@media` block; `app.js` — focus on resize logic |
| HTML structure, element nesting, missing containers | `index.html` |
| API data driving the UI (wrong blocks, missing fields, bad JSON) | `web_app.py` |

## Step 3: Diagnose

Quote the specific lines responsible for the bug. Explain in 2–3 sentences why those lines cause the reported symptom.

## Step 4: Fix

Apply a targeted, minimal fix to only the affected lines. Do not refactor surrounding code. After applying the fix, explain what changed and why it resolves the symptom.

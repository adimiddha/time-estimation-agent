# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Requires `OPENAI_API_KEY` in a `.env` file at the project root.

```bash
pip install -r requirements.txt
# or install as editable package:
pip install -e .
```

No formatter or linter is configured; run manual checks before committing.

### Web app environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for all LLM calls |
| `SECRET_KEY` | random token | Flask session signing (set for stable deploys) |
| `SESSIONS_DIR` | `day_sessions` | Root directory for per-user session files |
| `PORT` | `5000` | Listening port |

### Deployment

A `Procfile` is included for Railway/Heroku:
```
web: gunicorn "time_calibration_agent.web_app:app" --workers 2 --timeout 120 --bind 0.0.0.0:$PORT
```

## Commands

```bash
# Core estimation + logging
python -m time_calibration_agent.cli estimate "Write blog post about time estimation"
python -m time_calibration_agent.cli log <task_id> <actual_minutes>
python -m time_calibration_agent.cli status
python -m time_calibration_agent.cli history [limit]
python -m time_calibration_agent.cli clear          # clear pending tasks

# Day planning / replanning
python -m time_calibration_agent.cli new-session "It's 2pm. I still need A, B. Dinner at 7." [--session label] [--date YYYY-MM-DD]
python -m time_calibration_agent.cli replan "It's 3pm. I finished A." [--session label] [--date YYYY-MM-DD]
python -m time_calibration_agent.cli session [--session label] [--date YYYY-MM-DD]

# Web app (replanning UI)
python -m time_calibration_agent.web_app           # open http://127.0.0.1:5000

# Evaluation
python -m time_calibration_agent.cli eval [--export results.json]
python -m time_calibration_agent.cli experiment [--output path.json]
python -m time_calibration_agent.cli test-dataset generate --n 50 --output test_dataset.json
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json [--strategy name] [--evaluator ai|human|both] [--output path.json]
python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json
python -m time_calibration_agent.cli analyze-quality --file quality_eval_debug.json
python -m time_calibration_agent.cli compare-scoring --old old_debug.json --new new_debug.json

# Top-level analysis scripts (run from project root)
python collect_human_evaluations.py
python analyze_human_ai_comparison.py
```

There are no automated tests; validation is via CLI workflows and evaluation scripts.

## Architecture

All persistent state lives in `calibration_data.json`. The CLI is the only stateful orchestrator; `Agent` and `CalibrationLearner` are stateless (data in → data out).

```
CLI (cli.py)
  ├── Storage (storage.py)              ← JSON persistence, single source of truth
  ├── Agent (agent.py)                  ← Stateless OpenAI calls for estimation (gpt-4.1)
  ├── CalibrationLearner (learning.py)  ← Stateless heuristic calibration
  ├── ReplanningAgent (replanner.py)    ← Day scheduling via OpenAI (gpt-4.1)
  └── DaySessionStore (session_store.py) ← Reads/writes day_sessions/*.json
        └── day_model.py               ← PlanBlock / PlanOutput / DaySession dataclasses

Web app (web_app.py)
  ├── ReplanningAgent                  ← same as CLI path
  └── DaySessionStore                  ← per-user: day_sessions/<user_id>/ (Flask session cookie)
```

### Estimation flow

CLI fetches calibration + history from Storage → Agent calls OpenAI for initial estimate → CalibrationLearner applies multiplicative adjustments (`adjusted = base × category_factor × ambiguity_factor × bias_factor`) → result saved to Storage.

After logging actual time, CLI recomputes calibration from all completed tasks using exponential moving average (alpha ~0.3).

### Replanning flow

`new-session` / `replan` → `ReplanningAgent.plan_with_estimates()` → calls `_extract_context()` (LLM parse of raw text), then `_estimate_tasks()` (calls `EstimationAgent` per task), then `plan()` (LLM schedules time blocks) → output saved to `day_sessions/<session_id>.json`.

Session IDs default to `YYYY-MM-DD`; optional label produces `YYYY-MM-DD__<label>`. `DaySessionStore` tracks `day_sessions/.last_session` as a pointer to the most recently used session.

### Key design choices

- **Category normalization**: `VALID_CATEGORIES` and `CATEGORY_NORMALIZATION` in `agent.py` normalize AI-returned categories through `validate_and_normalize_category()` before any storage.
- **Context strategies** (`ContextStrategy` enum in `agent.py`): `RECENT_N` (default), `MINIMAL`, `SUMMARIZED`, `CATEGORY_FILTERED`, `SIMILARITY_BASED` — control what historical tasks are included in the estimation prompt.
- **Calibration adjustment** is applied as a geometric-mean composite of three multiplicative factors (category, ambiguity, bias), capped at [0.5×, 2.0×].
- **Similar-task shortcut**: if a high-confidence match is found in completed tasks, the CLI uses that actual time directly, skipping the LLM call entirely.

### Model usage

| Component | Model |
|---|---|
| `EstimationAgent` | `gpt-4.1` |
| `QualityEvaluator` | `gpt-4o` |
| `ReplanningAgent` | `gpt-4.1` |

### Research / evaluation layer

- **`evaluation.py`** (`EvaluationMetrics`): MAE, MAPE, within-threshold %, calibration drift for tasks with actuals.
- **`quality_evaluation.py`** (`QualityEvaluator`): GPT-4o scoring in `binary` (0/1) or `five_point` (1–5) modes; `HumanEvaluator` for human ratings.
- **`test_dataset.py`** (`TestDatasetGenerator`): AI-generates diverse test prompts across categories, ambiguity, and complexity.
- **`experiments.py`** (`ContextExperiment`): A/B comparisons across context strategies via leave-one-out cross-validation.
- **`quality_analysis.py`**: Analysis utilities for evaluation result files.

### Data files

- `calibration_data.json` — live task + calibration data (created on first run)
- `day_sessions/` — one JSON per planning session; web app writes to `day_sessions/<user_id>/`
- `human_evaluations.json` / `human_ai_comparison.json` — human rating results
- `eval/` — evaluation output artifacts

## Web UI

The web app is a SPA branded **"Untangle"** — a day-planning interface built with vanilla HTML/CSS/JS and Flask (no build step).

### UI files
- `time_calibration_agent/templates/index.html` — single HTML template
- `time_calibration_agent/static/app.js` — all frontend logic
- `time_calibration_agent/static/style.css` — CSS variables-driven theme
- `time_calibration_agent/static/manifest.json` — PWA manifest

### Screen flow
**Welcome overlay (3 screens, shown on first load):**
1. `#brain-dump-screen` — live clock, mic hero button (voice-first CTA), textarea fallback, "Untangle my day →" submit
2. `#followup-clarify-screen` — follow-up question from LLM; drum picker for time inputs, textarea for others
3. `#loading-screen` — canvas knot-untangle animation with 3-stage progress text

**Planner screen (after draft approval):**
- Sticky header (app title + session date/time)
- Calendar panel — time blocks with now-line, adaptive scaling (`getLayoutMetrics()`)
- `#right-now-section` — current/next block with micro-steps (hidden in draft mode)
- Draft mode sidebar — dropped tasks, rationale, Approve button, Adjust controls (mic + textarea)
- FAB (approved mode only) — slide-up replan panel with mic + textarea

### API endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/session` | GET | Load last saved session |
| `/api/clarify` | POST | Extract follow-up question from raw text |
| `/api/plan` | POST | Generate or replan the day schedule |
| `/api/approve` | POST | Approve draft → transition to planner screen |
| `/api/transcribe` | POST | Whisper audio → text |
| `/api/export-ics` | GET | Export plan as `.ics` calendar file |
| `/api/stats` | GET | Return aggregate `plans_created` / `replans` counts |
| `/api/health` | GET | Check API key + server status |

### Key JS functions
- `showScreen(id)` / `hideOverlay()` — screen transitions
- `enterDraftMode()` / `exitDraftMode()` — toggles sidebar + FAB visibility
- `renderCalendar(timeBlocks)` — main calendar rendering engine
- `getLayoutMetrics()` — computes adaptive `pixelsPerMinute` from container height
- `drawNowLine()` — red "now" indicator, updates every minute
- `updateRightNow()` — populates micro-steps for current/next block
- `recordAudio()` → POST `/api/transcribe` — voice input via Web Audio API
- `trackPageView(path, name)` — GA4 virtual page views for SPA screen transitions

### Design system
- CSS variables in `:root`; accent `#7b68ee` (slate blue), bg `#fdf8f0` (warm white)
- Block gradients: `task` (blue-purple), `fixed` (amber/honey), `break` (mint)
- Micro-blocks ≤8 min render as 26px compact pills instead of full-height blocks
- Responsive breakpoint: ≤768px stacks to single-column, page scrolls

### Additional features
- **Voice input**: Web Audio API captures audio → POST to `/api/transcribe` (Whisper)
- **Calendar export**: `.ics` download via `/api/export-ics`
- **PWA**: installable to home screen; 192px + 512px icons; `standalone` display mode
- **GA4 analytics**: virtual page views (`/welcome`, `/clarify`, `/planning`, `/draft`, `/planner`) + events (`plan_created`, `plan_approved`, `replan_triggered`, `voice_used`, `export_ics`, `error_occurred`); tracking ID `G-6HRL53D8E1`
- **Server-side stats**: `.stats.json` in sessions dir tracks aggregate usage counts

## Skills

- **`/debug-ui`** — diagnose and fix web UI bugs. Defined in `.claude/skills/debug-ui/SKILL.md`. Auto-invoked when a UI issue is described.

## Conventions

- Python, PEP 8, 4-space indentation. Modules/functions `snake_case`; classes `CamelCase`; constants `UPPER_SNAKE_CASE`.
- Commit messages: concise imperative summaries (e.g., `add quality-eval strategy comparison`).
- Keep CLI output format stable; prefer additive changes over breaking output formats.

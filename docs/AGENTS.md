# Repository Guidelines

## Project Structure & Module Organization
- `time_calibration_agent/` holds the core package (CLI, agent, learning, storage, evaluation, experiments, quality evaluation, replanner, session store, day model).
- Top-level scripts such as `run_all_evaluations.py`, `analyze_human_ai_comparison.py`, `collect_human_evaluations.py`, `generate_final_summary.py`, and `show_disagreements.py` are analysis utilities.
- Data and outputs live at the repo root and `eval/` (e.g., `calibration_data.json`, `test_*_dataset.json`, `quality_eval_debug_*.json`, `human_evaluations.json`, `human_ai_comparison.json`, `day_sessions/`).
- Reference docs: `README.md`, `QUICKSTART.md`, `EVALUATION_GUIDE.md`, and `CODEBASE_OVERVIEW.md`.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` installs runtime dependencies.
- `python -m time_calibration_agent.cli estimate "Task"` generates time estimates.
- `python -m time_calibration_agent.cli log <task_id_or_query> <minutes>` logs actuals.
- `python -m time_calibration_agent.cli status` and `history [limit]` inspect calibration state.
- `python -m time_calibration_agent.cli eval [--export path.json]` prints accuracy metrics on completed tasks.
- `python -m time_calibration_agent.cli experiment [--output path.json]` runs context experiments using completed tasks.
- `python -m time_calibration_agent.cli test-dataset generate --n 50 --output my_test_dataset.json` creates test prompts.
- `python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json [--strategy name] [--evaluator ai|human|both] [--output path.json]` runs quality scoring.
- `python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json` compares context strategies.
- `python -m time_calibration_agent.cli analyze-quality --file quality_eval_debug.json` analyzes quality evaluation results.
- `python -m time_calibration_agent.cli compare-scoring --old old_debug.json --new new_debug.json` compares scoring methodologies.
- `python -m time_calibration_agent.cli new-session "context text" [--session label] [--date YYYY-MM-DD]` starts a planning session.
- `python -m time_calibration_agent.cli replan "context text" [--session label] [--date YYYY-MM-DD]` updates a planning session.
- `python -m time_calibration_agent.cli session [--session label] [--date YYYY-MM-DD]` shows a stored session.
- `python -m time_calibration_agent.cli clear` clears pending tasks.

## Coding Style & Naming Conventions
- Python, PEP 8 style with 4-space indentation.
- Modules and functions use `snake_case`; classes use `CamelCase`; constants use `UPPER_SNAKE_CASE`.
- Keep CLI output stable for downstream analysis; prefer additive changes over breaking output formats.
- No formatter or linter is configured; run manual checks before committing.

## Testing Guidelines
- No unit test framework is wired in. Validation is primarily via CLI workflows and evaluation scripts.
- If adding tests, follow `test_*.py` naming and keep datasets in JSON for reproducibility.

## Commit & Pull Request Guidelines
- Git history shows descriptive, sentence-style commit messages rather than a strict convention. Use concise, imperative summaries (e.g., “add quality-eval strategy comparison”).
- PRs should include: purpose, key changes, and sample CLI output or JSON artifacts when relevant.
- Link issues if applicable and note any data files added or regenerated.

## Security & Configuration Tips
- Set `OPENAI_API_KEY` via `.env` or environment variables. Avoid committing secrets.
- `calibration_data.json`, session logs, and evaluation outputs can contain user task details; treat as local artifacts.

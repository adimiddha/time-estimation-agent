# Feature Plan: plan() Model Benchmark

**Status:** Approved
**Goal:** Determine whether plan() can be switched to a faster model without quality regression, in service of hitting the <5s total planning latency target.

---

## Problem

`plan()` currently takes 3-5s using `gpt-4.1`. It is the largest remaining latency contributor after the batch estimation refactor. Switching to a faster/cheaper model could cut 1-3s, but the plan is the most user-visible output and incorrect plans (missed fixed times, bad micro-steps, wrong priority dropping) violate the "trustworthy output" principle directly.

A model swap must not be a guess. This plan specifies a benchmark script that measures latency and quality before any production change is made.

---

## Proposed Solution

Build a standalone benchmark script `scripts/benchmark_plan_models.py` that runs a fixed set of representative planning prompts through each candidate model, measures wall-clock latency per call, and uses the existing `QualityEvaluator` to score plan quality.

---

## Scope

### In

- A benchmark script that accepts a list of test cases (raw_text + current_time + expected constraints)
- Candidate models (OpenAI only — do not add Anthropic SDK for this benchmark):
  - `gpt-4.1` — current baseline
  - `gpt-4.1-mini` — faster/cheaper 4.1 variant
  - `gpt-4o-mini` — established fast option
  - `gpt-5-mini` — GPT-5 family, newer architecture
  - `gpt-5-nano` — fastest/cheapest GPT-5 variant
  - `gpt-5.4-mini` — latest mini model (March 2026)
  - `gpt-5.4-nano` — latest nano, best speed/quality tradeoff candidate
  - `gpt-5.4` — latest flagship, sets quality ceiling
- Per-model metrics: p50 latency, p95 latency, mean quality score, cost estimate per call
- Quality scoring via the existing `QualityEvaluator` in `quality_evaluation.py` using `five_point` mode
- At least 3 quality dimensions explicitly tested: constraint adherence, micro-step concreteness, overbooking/drop logic
- A test case set covering: ≥1 case with a hard fixed time, ≥1 case with overbooking (more tasks than time), ≥1 case with a dependency (task A must precede task B), ≥1 minimal case (3 tasks, no constraints)
- Console output: a table of model × metric results that can be read and acted on immediately
- Optional `--output path.json` flag for saving raw results

### Out of scope

- Anthropic SDK integration (claude-* models) — add Anthropic dependency only if OpenAI benchmarks fail to meet the target
- Modifying `replanner.py` or `web_app.py` — this is measurement only
- Automated model selection or dynamic routing
- CI integration

---

## Acceptance Criteria

1. Script runs end-to-end with `python3 scripts/benchmark_plan_models.py` and produces a results table without error.
2. Results include wall-clock latency (p50, p95) and quality score for each model.
3. Quality scoring specifically tests constraint adherence: a plan that places a task after a stated hard end time must score lower than one that does not.
4. After reviewing results, an engineer can make a model-switch decision in `replanner.py` in one line: `self.model = "gpt-4o-mini"` (or equivalent).
5. The recommended switch is the fastest model that scores within 10% of `gpt-4.1` on quality and is ≥1.5s faster at p50. Document this threshold explicitly in the script's output, and flag `gpt-5.4-nano` and `gpt-5.4-mini` as primary candidates given their recency.

---

## Out of Scope (explicitly)

- Changing any production code before benchmark results are reviewed
- Adding claude-* models to production (separate decision, requires new dependency)
- Benchmarking `_extract_context()` or `extract_clarification()` — those are covered by the separate clarify-context-merge plan
- Using human evaluators for this benchmark — AI scoring is sufficient for a model-selection decision

---

## Notes for Engineer

The benchmark script should instantiate `ReplanningAgent` with the target model passed via constructor (`ReplanningAgent(model="gpt-4o-mini")`), then call `plan()` directly with pre-built inputs (skip `plan_with_estimates()` to isolate `plan()` latency from estimation latency). Use `time.perf_counter()` around the `plan()` call only.

The `QualityEvaluator` in `quality_evaluation.py` already supports `five_point` scoring mode. Pass the plan JSON and the original prompt as context. Add a custom scoring dimension for "constraint adherence" if the existing evaluator dimensions do not cover it — check `QualityEvaluator` before adding new ones.

Cost estimate: use tiktoken to count prompt tokens per call × published $/1M token rates. Hardcode the rates as constants in the script with a comment noting they should be updated if pricing changes.

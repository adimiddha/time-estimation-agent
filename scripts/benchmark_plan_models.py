"""
Benchmark script: measure plan() latency and quality across candidate models.

Goal: determine whether plan() can be switched to a faster model without quality
regression, in service of hitting the <5s total planning latency target.

Usage:
    python3 scripts/benchmark_plan_models.py
    python3 scripts/benchmark_plan_models.py --output results.json

Dependencies:
    tiktoken  -- used for token counting / cost estimates.
    IMPORTANT: tiktoken is NOT in requirements.txt yet.
    Add it before running:  pip install tiktoken
    or add `tiktoken>=0.7.0` to requirements.txt and re-run `pip install -r requirements.txt`.

Decision threshold (from spec):
    Recommended switch = fastest model that scores within 10% of gpt-4.1 quality
    AND is >=1.5s faster at p50 latency.
    Primary candidates to watch: gpt-5.4-nano, gpt-5.4-mini.
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Path setup — allow running from any directory
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from time_calibration_agent.replanner import ReplanningAgent  # noqa: E402

# ---------------------------------------------------------------------------
# Candidate models
# ---------------------------------------------------------------------------
CANDIDATE_MODELS = [
    "gpt-4.1",          # current baseline
    "gpt-4.1-mini",     # faster/cheaper 4.1 variant
    "gpt-4o-mini",      # established fast option
    "gpt-5-mini",       # GPT-5 family, newer architecture
    "gpt-5-nano",       # fastest/cheapest GPT-5 variant
    "gpt-5.4-mini",     # latest mini model (March 2026) — primary candidate
    "gpt-5.4-nano",     # latest nano, best speed/quality tradeoff candidate — primary candidate
    "gpt-5.4",          # latest flagship, sets quality ceiling
]

# ---------------------------------------------------------------------------
# Token pricing — $/1M tokens (input / output).
# UPDATE THESE if OpenAI changes pricing:
# Last verified: March 2026 from https://openai.com/api/pricing
# ---------------------------------------------------------------------------
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4.1":       {"input": 2.00,  "output": 8.00},
    "gpt-4.1-mini":  {"input": 0.40,  "output": 1.60},
    "gpt-4o-mini":   {"input": 0.15,  "output": 0.60},
    "gpt-5-mini":    {"input": 1.10,  "output": 4.40},   # placeholder — update when published
    "gpt-5-nano":    {"input": 0.30,  "output": 1.20},   # placeholder — update when published
    "gpt-5.4-mini":  {"input": 0.80,  "output": 3.20},   # placeholder — update when published
    "gpt-5.4-nano":  {"input": 0.20,  "output": 0.80},   # placeholder — update when published
    "gpt-5.4":       {"input": 3.00,  "output": 12.00},  # placeholder — update when published
}

FALLBACK_PRICING = {"input": 2.00, "output": 8.00}  # conservative fallback for unknown models

# ---------------------------------------------------------------------------
# Test cases
# Each case provides pre-built estimated_tasks and extracted_context so that
# plan() makes exactly one LLM call (the scheduling step). This isolates
# plan() latency from estimation latency.
# ---------------------------------------------------------------------------
TEST_CASES = [
    # -----------------------------------------------------------------------
    # Case 1: Hard fixed time constraint
    # Tests: does the model respect a hard meeting at 15:00 and not schedule
    # tasks that overlap it?
    # -----------------------------------------------------------------------
    {
        "id": "fixed_time",
        "label": "Hard fixed time — team meeting at 3pm",
        "raw_text": "It's 1pm. I need to finish the quarterly report, respond to emails, and prep slides. Team meeting is locked at 3pm for 1 hour.",
        "current_time": "13:00",
        "session_end_time": "18:00",
        "expected_constraints": "Meeting block 15:00-16:00 must appear. No task should overlap 15:00-16:00.",
        "estimated_tasks": [
            {"task": "Finish quarterly report", "priority": "high",
             "estimated_minutes": 60, "estimate_range": {"optimistic": 45, "realistic": 60, "pessimistic": 90},
             "category": "deep work", "ambiguity": "low"},
            {"task": "Respond to emails", "priority": "medium",
             "estimated_minutes": 30, "estimate_range": {"optimistic": 20, "realistic": 30, "pessimistic": 45},
             "category": "admin", "ambiguity": "low"},
            {"task": "Prep slides", "priority": "high",
             "estimated_minutes": 45, "estimate_range": {"optimistic": 30, "realistic": 45, "pessimistic": 60},
             "category": "deep work", "ambiguity": "low"},
        ],
        "extracted_context": {
            "remaining_tasks": [
                {"task": "Finish quarterly report", "priority": "high"},
                {"task": "Respond to emails", "priority": "medium"},
                {"task": "Prep slides", "priority": "high"},
            ],
            "constraints": {
                "time_blocks": [{"start": "15:00", "end": "16:00", "label": "Team meeting"}],
                "deadlines": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # Case 2: Overbooking — more work than available time
    # Tests: model must drop lowest-priority tasks and provide drop_reasons.
    # -----------------------------------------------------------------------
    {
        "id": "overbooking",
        "label": "Overbooking — 5h of tasks in 2h window",
        "raw_text": "It's 4pm. I need to write a blog post (2h), refactor the auth module (90min), review 3 PRs (60min), update Notion docs (45min), and answer Slack. Session ends at 6pm.",
        "current_time": "16:00",
        "session_end_time": "18:00",
        "expected_constraints": "Only ~2h available. Low/medium tasks should be dropped. drop_or_defer must be non-empty with drop_reasons.",
        "estimated_tasks": [
            {"task": "Write blog post", "priority": "high",
             "estimated_minutes": 120, "estimate_range": {"optimistic": 90, "realistic": 120, "pessimistic": 150},
             "category": "writing", "ambiguity": "low"},
            {"task": "Refactor auth module", "priority": "high",
             "estimated_minutes": 90, "estimate_range": {"optimistic": 60, "realistic": 90, "pessimistic": 120},
             "category": "coding", "ambiguity": "medium"},
            {"task": "Review 3 PRs", "priority": "medium",
             "estimated_minutes": 60, "estimate_range": {"optimistic": 45, "realistic": 60, "pessimistic": 75},
             "category": "coding", "ambiguity": "low"},
            {"task": "Update Notion docs", "priority": "low",
             "estimated_minutes": 45, "estimate_range": {"optimistic": 30, "realistic": 45, "pessimistic": 60},
             "category": "admin", "ambiguity": "low"},
            {"task": "Answer Slack", "priority": "low",
             "estimated_minutes": 30, "estimate_range": {"optimistic": 15, "realistic": 30, "pessimistic": 45},
             "category": "admin", "ambiguity": "low"},
        ],
        "extracted_context": {
            "remaining_tasks": [
                {"task": "Write blog post", "priority": "high"},
                {"task": "Refactor auth module", "priority": "high"},
                {"task": "Review 3 PRs", "priority": "medium"},
                {"task": "Update Notion docs", "priority": "low"},
                {"task": "Answer Slack", "priority": "low"},
            ],
            "constraints": {
                "time_blocks": [],
                "deadlines": [{"time": "18:00", "label": "Session end"}],
            },
        },
    },

    # -----------------------------------------------------------------------
    # Case 3: Task dependency — pick up kids before feed kids
    # Tests: model must infer and respect the natural ordering dependency.
    # -----------------------------------------------------------------------
    {
        "id": "dependency",
        "label": "Task dependency — pick up kids before feed kids",
        "raw_text": "It's 3pm. I need to pick up the kids from school, feed them dinner, help with homework, and put them to bed. Also need to do a grocery run so we have food for dinner.",
        "current_time": "15:00",
        "session_end_time": "21:00",
        "expected_constraints": "grocery run before feed kids. pick up kids before feed kids. Logical dependency chain must be preserved.",
        "estimated_tasks": [
            {"task": "Grocery run", "priority": "high",
             "estimated_minutes": 45, "estimate_range": {"optimistic": 30, "realistic": 45, "pessimistic": 60},
             "category": "errands", "ambiguity": "low"},
            {"task": "Pick up kids from school", "priority": "high",
             "estimated_minutes": 30, "estimate_range": {"optimistic": 20, "realistic": 30, "pessimistic": 45},
             "category": "errands", "ambiguity": "low"},
            {"task": "Feed kids dinner", "priority": "high",
             "estimated_minutes": 45, "estimate_range": {"optimistic": 30, "realistic": 45, "pessimistic": 60},
             "category": "general", "ambiguity": "low"},
            {"task": "Help with homework", "priority": "medium",
             "estimated_minutes": 60, "estimate_range": {"optimistic": 30, "realistic": 60, "pessimistic": 90},
             "category": "general", "ambiguity": "medium"},
            {"task": "Put kids to bed", "priority": "high",
             "estimated_minutes": 30, "estimate_range": {"optimistic": 20, "realistic": 30, "pessimistic": 45},
             "category": "general", "ambiguity": "low"},
        ],
        "extracted_context": {
            "remaining_tasks": [
                {"task": "Grocery run", "priority": "high"},
                {"task": "Pick up kids from school", "priority": "high"},
                {"task": "Feed kids dinner", "priority": "high"},
                {"task": "Help with homework", "priority": "medium"},
                {"task": "Put kids to bed", "priority": "high"},
            ],
            "constraints": {
                "time_blocks": [],
                "deadlines": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # Case 4: Minimal — 3 tasks, no constraints
    # Tests: basic scheduling, micro-step quality on a simple scenario.
    # -----------------------------------------------------------------------
    {
        "id": "minimal",
        "label": "Minimal — 3 tasks, no hard constraints",
        "raw_text": "It's 10am. I want to meditate, write in my journal, and do a 30-minute workout.",
        "current_time": "10:00",
        "session_end_time": None,
        "expected_constraints": "All three tasks fit easily. Micro-steps must be concrete physical actions.",
        "estimated_tasks": [
            {"task": "Meditate", "priority": "medium",
             "estimated_minutes": 15, "estimate_range": {"optimistic": 10, "realistic": 15, "pessimistic": 20},
             "category": "general", "ambiguity": "low"},
            {"task": "Write in journal", "priority": "medium",
             "estimated_minutes": 20, "estimate_range": {"optimistic": 15, "realistic": 20, "pessimistic": 30},
             "category": "writing", "ambiguity": "low"},
            {"task": "30-minute workout", "priority": "high",
             "estimated_minutes": 35, "estimate_range": {"optimistic": 30, "realistic": 35, "pessimistic": 45},
             "category": "general", "ambiguity": "low"},
        ],
        "extracted_context": {
            "remaining_tasks": [
                {"task": "Meditate", "priority": "medium"},
                {"task": "Write in journal", "priority": "medium"},
                {"task": "30-minute workout", "priority": "high"},
            ],
            "constraints": {
                "time_blocks": [],
                "deadlines": [],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Plan quality evaluator
# ---------------------------------------------------------------------------

PLAN_EVAL_SYSTEM = (
    "You are an expert evaluator of AI-generated day plans. "
    "Score objectively on a 1-5 scale. Always respond with valid JSON."
)

PLAN_EVAL_PROMPT_TEMPLATE = """\
Evaluate the quality of this AI-generated day plan. Score each dimension 1-5.

SCALE:
5 = Excellent  4 = Good  3 = Acceptable  2 = Poor  1 = Very Poor

ORIGINAL PROMPT:
{raw_text}

EXPECTED CONSTRAINTS:
{expected_constraints}

PLAN OUTPUT:
{plan_json}

SCORING DIMENSIONS:

1. Constraint Adherence (1-5)
   - 5: All hard constraints met (fixed times, ordering dependencies, session end boundary)
   - 4: Nearly all constraints met; at most one minor slip
   - 3: Most constraints met but one notable violation
   - 2: Multiple constraint violations
   - 1: Constraint(s) completely ignored

2. Micro-step Concreteness (1-5)
   - 5: Every block has 2-3 concrete physical actions ("Open Notion", "Set a 25-min timer") — no vague steps
   - 4: Most steps are concrete; one or two are slightly vague
   - 3: Mix of concrete and vague steps
   - 2: Most steps are vague ("work on X", "continue X")
   - 1: No meaningful micro-steps provided

3. Overbooking / Drop Logic (1-5)
   - If the scenario is NOT overbooked: score 5 if all tasks are scheduled, 3 if any are dropped unnecessarily
   - If the scenario IS overbooked: 5 = lowest-priority tasks dropped with clear reasons; 1 = wrong tasks dropped or no drop_reasons

Respond in JSON:
{{
    "constraint_adherence": <1-5>,
    "microstep_concreteness": <1-5>,
    "drop_logic": <1-5>,
    "overall": <1-5>,
    "reasoning": "<1-2 sentences explaining the scores>"
}}
"""


class PlanQualityEvaluator:
    """Evaluate a day plan output across constraint adherence, micro-step concreteness,
    and overbooking/drop logic. Returns 1-5 scores per dimension and an overall score."""

    def __init__(self, api_key: Optional[str] = None, evaluator_model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.evaluator_model = evaluator_model

    def evaluate(self, test_case: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a plan against a test case.

        Returns dict with keys: constraint_adherence, microstep_concreteness,
        drop_logic, overall, reasoning. On evaluator failure returns zeroes and
        sets evaluator_error.
        """
        plan_json = json.dumps(plan, indent=2)
        prompt = PLAN_EVAL_PROMPT_TEMPLATE.format(
            raw_text=test_case["raw_text"],
            expected_constraints=test_case["expected_constraints"],
            plan_json=plan_json,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.evaluator_model,
                messages=[
                    {"role": "system", "content": PLAN_EVAL_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            return {
                "constraint_adherence": float(result.get("constraint_adherence", 0)),
                "microstep_concreteness": float(result.get("microstep_concreteness", 0)),
                "drop_logic": float(result.get("drop_logic", 0)),
                "overall": float(result.get("overall", 0)),
                "reasoning": result.get("reasoning", ""),
                "evaluator_error": None,
            }
        except Exception as exc:
            return {
                "constraint_adherence": 0.0,
                "microstep_concreteness": 0.0,
                "drop_logic": 0.0,
                "overall": 0.0,
                "reasoning": "",
                "evaluator_error": str(exc),
            }


# ---------------------------------------------------------------------------
# Token counting + cost estimation
# ---------------------------------------------------------------------------

def _get_encoder():
    """Return a tiktoken encoder, or None if tiktoken is not installed."""
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except ImportError:
        return None


def estimate_cost(prompt_text: str, completion_text: str, model: str, encoder) -> float:
    """
    Estimate USD cost for one API call.

    Uses cl100k_base token counts as a proxy for all models (GPT-4.1 and newer
    all use the same tokenizer family). Returns 0.0 if tiktoken is unavailable.
    """
    if encoder is None:
        return 0.0

    pricing = MODEL_PRICING.get(model, FALLBACK_PRICING)
    input_tokens = len(encoder.encode(prompt_text))
    output_tokens = len(encoder.encode(completion_text))
    cost = (input_tokens / 1_000_000) * pricing["input"] + \
           (output_tokens / 1_000_000) * pricing["output"]
    return cost


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(models: List[str], cases: List[Dict], runs_per_case: int = 3) -> Dict[str, Any]:
    """
    For each model, run every test case `runs_per_case` times.
    Returns a dict keyed by model name containing per-case and aggregate results.
    """
    encoder = _get_encoder()
    if encoder is None:
        print("WARNING: tiktoken not installed. Cost estimates will be 0.0.")
        print("         Run: pip install tiktoken\n")

    evaluator = PlanQualityEvaluator()
    all_results: Dict[str, Any] = {}

    total_calls = len(models) * len(cases) * runs_per_case
    call_idx = 0

    for model in models:
        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"{'='*60}")

        model_results = {
            "model": model,
            "cases": {},
            "latencies_all": [],   # flat list of all latencies for percentile calc
            "costs_all": [],
            "quality_scores_all": [],
            "error_count": 0,
            "skip_reason": None,
        }

        agent = ReplanningAgent(model=model)

        for case in cases:
            case_id = case["id"]
            case_results = {
                "label": case["label"],
                "runs": [],
                "latencies": [],
                "quality_scores": [],
                "costs": [],
                "error_count": 0,
            }

            for run_i in range(runs_per_case):
                call_idx += 1
                print(f"  [{call_idx}/{total_calls}] {case_id} run {run_i + 1}/{runs_per_case} ... ", end="", flush=True)

                # ------------------------------------------------------------------
                # Timed section: ONLY plan() — not estimation, not context extraction
                # pre-built estimated_tasks and extracted_context are injected so
                # no extra LLM calls happen inside plan().
                # ------------------------------------------------------------------
                t_start = time.perf_counter()
                try:
                    plan_output = agent.plan(
                        raw_text=case["raw_text"],
                        current_time=case["current_time"],
                        estimated_tasks=case["estimated_tasks"],
                        extracted_context=case["extracted_context"],
                        session_end_time=case.get("session_end_time"),
                    )
                    t_elapsed = time.perf_counter() - t_start
                    plan_error = None
                except Exception as exc:
                    t_elapsed = time.perf_counter() - t_start
                    plan_output = None
                    plan_error = str(exc)
                    # Detect JSON-mode / model-not-found errors specifically
                    err_lower = plan_error.lower()
                    if any(kw in err_lower for kw in ("model", "not found", "does not exist", "invalid model")):
                        print(f"SKIPPED (model not available: {plan_error})")
                        model_results["skip_reason"] = plan_error
                        model_results["error_count"] += 1
                        break  # skip remaining cases for this model
                    elif "json" in err_lower or "response_format" in err_lower:
                        print(f"ERROR (JSON mode unsupported: {plan_error})")
                        model_results["skip_reason"] = f"JSON mode unsupported: {plan_error}"
                        model_results["error_count"] += 1
                        break
                    else:
                        print(f"ERROR ({plan_error})")
                        model_results["error_count"] += 1
                        case_results["error_count"] += 1
                        case_results["runs"].append({"run": run_i + 1, "error": plan_error, "latency_s": t_elapsed})
                        continue

                # If model was skipped mid-case-loop, break outer loop too
                if model_results["skip_reason"]:
                    break

                # Cost estimate using the prompt we can reconstruct from run metadata
                # Approximate: use raw_text + estimated_tasks JSON as a proxy for prompt length
                prompt_proxy = case["raw_text"] + json.dumps(case["estimated_tasks"])
                completion_proxy = json.dumps(plan_output) if plan_output else ""
                cost = estimate_cost(prompt_proxy, completion_proxy, model, encoder)

                # Quality evaluation (only if plan was produced successfully)
                if plan_output and not plan_error:
                    quality = evaluator.evaluate(case, plan_output)
                    q_score = quality["overall"]
                    q_detail = quality
                else:
                    q_score = 0.0
                    q_detail = {"overall": 0.0, "evaluator_error": plan_error or "no plan"}

                print(f"latency={t_elapsed:.2f}s  quality={q_score:.1f}/5  cost=${cost:.5f}")

                case_results["runs"].append({
                    "run": run_i + 1,
                    "latency_s": round(t_elapsed, 3),
                    "quality": q_detail,
                    "cost_usd": round(cost, 6),
                    "plan_error": plan_error,
                })
                case_results["latencies"].append(t_elapsed)
                case_results["quality_scores"].append(q_score)
                case_results["costs"].append(cost)

                model_results["latencies_all"].append(t_elapsed)
                model_results["quality_scores_all"].append(q_score)
                model_results["costs_all"].append(cost)

            model_results["cases"][case_id] = case_results

            if model_results["skip_reason"]:
                break  # skip remaining cases for this model

        all_results[model] = model_results

    return all_results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (pct / 100) * (len(sorted_data) - 1)
    lo = int(idx)
    hi = lo + 1
    frac = idx - lo
    if hi >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


def _mean(data: List[float]) -> float:
    return statistics.mean(data) if data else 0.0


def print_results_table(all_results: Dict[str, Any], baseline_model: str = "gpt-4.1") -> None:
    """Print a formatted results table to stdout."""
    QUALITY_THRESHOLD_PCT = 0.10   # within 10% of baseline quality = acceptable
    LATENCY_THRESHOLD_S = 1.5      # must be >=1.5s faster at p50

    print("\n")
    print("=" * 90)
    print("PLAN() MODEL BENCHMARK RESULTS")
    print("=" * 90)
    print(
        f"{'Model':<18} {'p50 (s)':>8} {'p95 (s)':>8} {'Quality':>9} "
        f"{'Cost/call':>11} {'Errors':>7} {'Verdict':>10}"
    )
    print("-" * 90)

    baseline_p50 = 0.0
    baseline_quality = 0.0
    if baseline_model in all_results:
        bm = all_results[baseline_model]
        baseline_p50 = _percentile(bm["latencies_all"], 50)
        baseline_quality = _mean(bm["quality_scores_all"])

    for model in CANDIDATE_MODELS:
        if model not in all_results:
            continue
        r = all_results[model]

        if r["skip_reason"]:
            print(f"  {model:<18} {'—':>8} {'—':>8} {'—':>9} {'—':>11} {'—':>7}  SKIPPED")
            print(f"    Reason: {r['skip_reason'][:70]}")
            continue

        lats = r["latencies_all"]
        scores = r["quality_scores_all"]
        costs = r["costs_all"]

        p50 = _percentile(lats, 50)
        p95 = _percentile(lats, 95)
        mean_q = _mean(scores)
        mean_cost = _mean(costs)
        errors = r["error_count"]

        # Verdict
        if model == baseline_model:
            verdict = "BASELINE"
        elif not lats:
            verdict = "NO DATA"
        else:
            quality_ok = (baseline_quality == 0) or (mean_q >= baseline_quality * (1 - QUALITY_THRESHOLD_PCT))
            latency_ok = (p50 <= baseline_p50 - LATENCY_THRESHOLD_S)
            if quality_ok and latency_ok:
                verdict = "CANDIDATE"
            elif quality_ok:
                verdict = "qual-ok"
            elif latency_ok:
                verdict = "fast-only"
            else:
                verdict = "—"

        print(
            f"  {model:<18} {p50:>8.2f} {p95:>8.2f} {mean_q:>8.2f}/5 "
            f"  ${mean_cost:>8.5f} {errors:>7}  {verdict}"
        )

    print("-" * 90)
    print(f"Baseline: {baseline_model}  |  Quality threshold: within {QUALITY_THRESHOLD_PCT*100:.0f}% of baseline")
    print(f"Latency threshold: p50 must be >= {LATENCY_THRESHOLD_S}s faster than baseline to be flagged CANDIDATE")
    print("Primary candidates to watch: gpt-5.4-nano, gpt-5.4-mini")
    print("=" * 90)

    # Per-case breakdown
    print("\nPER-CASE QUALITY BREAKDOWN (mean quality score, 1-5 scale)")
    print("-" * 90)
    case_ids = [c["id"] for c in TEST_CASES]
    header = f"  {'Model':<18}" + "".join(f"  {cid:>14}" for cid in case_ids)
    print(header)
    print("-" * 90)
    for model in CANDIDATE_MODELS:
        if model not in all_results:
            continue
        r = all_results[model]
        if r["skip_reason"]:
            row = f"  {model:<18}" + "".join(f"  {'SKIPPED':>14}" for _ in case_ids)
        else:
            row = f"  {model:<18}"
            for cid in case_ids:
                case_data = r["cases"].get(cid, {})
                scores = case_data.get("quality_scores", [])
                if scores:
                    row += f"  {_mean(scores):>13.2f}"
                else:
                    row += f"  {'—':>14}"
        print(row)
    print("=" * 90)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark plan() latency and quality across candidate models."
    )
    parser.add_argument(
        "--output", metavar="PATH", default=None,
        help="Optional path to save raw results as JSON (e.g. results.json)"
    )
    parser.add_argument(
        "--runs", type=int, default=3, metavar="N",
        help="Number of runs per test case per model (default: 3)"
    )
    parser.add_argument(
        "--models", nargs="+", default=None, metavar="MODEL",
        help="Subset of models to run (default: all candidates)"
    )
    args = parser.parse_args()

    models = args.models if args.models else CANDIDATE_MODELS

    print(f"Benchmarking {len(models)} models × {len(TEST_CASES)} cases × {args.runs} runs")
    print(f"Total API calls (plan): {len(models) * len(TEST_CASES) * args.runs}  (+ quality eval calls)")
    print("Using gpt-4o as quality evaluator (not counted in latency).\n")

    results = run_benchmark(models=models, cases=TEST_CASES, runs_per_case=args.runs)
    print_results_table(results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nRaw results saved to: {output_path}")


if __name__ == "__main__":
    main()

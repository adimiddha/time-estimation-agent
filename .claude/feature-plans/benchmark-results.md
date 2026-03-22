# Benchmark Results: plan() Model Selection

**Date:** 2026-03-21
**Decision:** Switch `plan()` default model from `gpt-4.1` → `gpt-5.4-mini`

---

## Setup

- 8 candidate models × 4 test cases × 3 runs = 96 plan() calls
- Quality scored by `gpt-4o` via `QualityEvaluator` in five_point mode
- Latency measured with `time.perf_counter()` around `plan()` only (estimation excluded)
- Raw results saved to `results.json` in project root

## Test Cases

| ID | Scenario |
|---|---|
| fixed_time | "It's 1pm. Quarterly report, emails, slides. Team meeting locked at 3pm for 1 hour." |
| overbooking | "It's 4pm. 5+ hours of tasks in a 2-hour window ending at 6pm." |
| dependency | "It's 3pm. Pick up kids, grocery run (must happen before dinner), feed kids, homework, bedtime." |
| minimal | "It's 10am. Meditate, journal, 30-min workout. No constraints." |

## Results

| Model | p50 (s) | p95 (s) | Quality | Cost/call | Verdict |
|---|---|---|---|---|---|
| gpt-4.1 *(baseline)* | 6.06 | 8.92 | 5.0/5 | $0.0046 | BASELINE |
| **gpt-5.4-mini** | **2.35** | **3.05** | **5.0/5** | $0.0018 | **CANDIDATE ✓** |
| gpt-5.4-nano | 3.28 | 4.49 | 5.0/5 | $0.0005 | CANDIDATE |
| gpt-4.1-mini | 6.96 | 15.86 | 5.0/5 | $0.0008 | qual-ok (not faster) |
| gpt-4o-mini | 6.80 | 9.13 | 4.92/5 | $0.0002 | qual-ok (not faster) |
| gpt-5.4 | 8.86 | 13.34 | 5.0/5 | $0.0085 | slower + expensive |
| gpt-5-mini | ~0.17 | — | 1.0/5 | — | FAIL (temperature error) |
| gpt-5-nano | ~0.16 | — | 1.0/5 | — | FAIL (temperature error) |

## Key Findings

- **gpt-5.4-mini**: 3.7s faster than baseline at p50, perfect quality across all cases, 60% cheaper. Clear winner.
- **gpt-5.4-nano**: Also valid — 2.8s faster, perfect quality, 88% cheaper. Good fallback if cost becomes a priority.
- **gpt-5-mini / gpt-5-nano**: Failed entirely — these models reject custom `temperature` values. Not usable without removing temperature from the plan() call.
- **gpt-4o-mini**: No meaningful latency improvement over gpt-4.1 despite being cheaper.
- **gpt-5.4**: Slower and ~2× more expensive than baseline. Not worth it.

## Decision

Switched `ReplanningAgent` default model to `gpt-5.4-mini` (one-line change in `replanner.py`).

Expected end-to-end improvement (combined with batch estimation refactor already shipped):
- Before: ~18-22s
- After batch estimation: ~10-12s
- After model switch: ~6-8s total
- Next: clarify-context-cache plan (Option C) targets further ~1.5s reduction → <5s

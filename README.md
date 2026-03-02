# Time Calibration Agent

An AI-powered day planner for people who get overwhelmed when their day stops going according to plan.

**Try it live:** [time-estimation-agent-production.up.railway.app](https://time-estimation-agent-production.up.railway.app/)

---

## The Problem

Most productivity tools assume your day goes as planned. They don't. A meeting runs long, a task takes twice as expected, something urgent lands in your inbox — and suddenly the plan you made at 9am is useless by noon. For people with ADHD, this is especially painful: time blindness and executive function difficulties make it hard to re-orient mid-day, re-assess what's realistic, and decide what to actually do next.

The common advice is "just re-prioritize." That's not nothing — but doing it well requires holding your whole day in your head, estimating how long everything remaining will take, and making trade-offs quickly under stress. Most people don't do this well, and most tools don't help them do it at all.

---

## How It Started (and Where It Went)

This project started as a **time calibration agent**: a CLI tool that tried to answer "how long will this vague task take?" You'd describe a task, get an estimate with a confidence range and reasoning, then log the actual time afterward. The agent would learn your personal bias — "you consistently underestimate writing tasks by 25%" — and adjust future estimates accordingly.

That was a real problem worth solving. But through using it and talking about it, a bigger and more urgent problem kept surfacing: *I don't just need to estimate one task — I need help planning my whole day, and especially recovering when it all falls apart.*

So the project pivoted. The time estimation engine stayed (it's now embedded inside the planner), but the primary product became a **replanning assistant**: describe your day and constraints in plain language, get a visual block schedule, and return to it throughout the day with updates. The calendar adjusts. The plan stays alive.

---

## The Solution

**Two modes, one workflow:**

**1. Plan your day**

Open the web app, type everything on your plate in plain language — tasks, meetings, hard stops, energy levels, whatever context is relevant. Set the current time. The assistant figures out what's realistic, estimates durations, prioritizes, and generates a visual time-block calendar fitted to your available hours.

**2. Replan when things change**

When the day breaks down, you don't start over. Type what happened ("the standup ran 45 minutes, I didn't get to the report") and hit Replan. The assistant re-reads your original constraints, incorporates the new context, and regenerates the calendar from the current time forward — surfacing what got dropped, what can still fit, and what to do next.

The design is intentionally ADHD-friendly: a clean two-screen flow (input → calendar), rounded Nunito font to reduce visual noise, spring animations to make state changes trackable, and time blocks color-coded by type (tasks, fixed events, breaks).

---

## Quick Start

```bash
git clone https://github.com/adimiddha/time-estimation-agent.git
cd time-estimation-agent
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env

# Run the web app
PORT=5001 python3 -m time_calibration_agent.web_app
# Open http://127.0.0.1:5001
```

> macOS note: port 5000 is reserved by AirPlay Receiver. Use `PORT=5001`.

**Or use the CLI directly:**

```bash
python3 -m time_calibration_agent.cli estimate "Write API documentation"
python3 -m time_calibration_agent.cli log <task_id> 120   # log actual minutes
python3 -m time_calibration_agent.cli status              # see your calibration
```

---

## Key Decisions

### Pivoting from time calibration to day replanning

The original agent was technically interesting: learn user-specific estimation bias, apply multiplicative adjustments, get more accurate over time. But the feedback was consistent — the felt need wasn't "help me estimate one task better," it was "help me survive a day that's gone sideways."

Competitive alternatives exist (Todoist, Reclaim, Motion) but they all share the same limitation: they help you *plan*, not *recover*. The replanning loop — "here's what happened, what do I do now?" — was the gap worth filling. The time estimation engine didn't go away; it now runs under the hood to estimate each task when building the schedule.

### Binary (0/1) vs 5-point (1–5) scoring for AI evaluation

Before the pivot, significant time went into evaluating how good the time estimation agent actually was — without ground-truth actuals to measure against, which is the hard case. The solution was an LLM-as-judge evaluator, with parallel human evaluations for validation.

The first instinct was a 1–5 scale: more granularity should mean richer signal. In practice, neither the LLM nor human raters could agree with themselves across runs at that resolution. What was a 3 vs a 4? The distinction was too soft to be consistent. Human raters also found the 5-point form slower and more cognitively taxing.

Switching to binary (0 = poor, 1 = good) with an explicit quality threshold changed things. Disagreements became legible: when the human said 1 and the model said 0, there was a clear, investigable failure. We ran both scoring methods on the same dataset and found binary AI scores tracked human judgment more reliably than 5-point AI scores did.

**The lesson:** LLM-as-judge works better with fewer score levels. Granularity implies precision the model doesn't actually have.

### gpt-4o-mini for estimation, gpt-4.1 for replanning

Estimation is structured and narrow: produce a JSON object with a number, a category, and a rationale. gpt-4o-mini handles it reliably and cheaply. Replanning is a different kind of task — it requires reading an unstructured brain dump, inferring implicit constraints ("dinner at 7" means hard stop at ~6:30), performing time arithmetic across a full day, and producing a coherent schedule. We upgraded the replanning model to gpt-4.1 and kept the estimator on gpt-4o-mini. The cost delta is worth it at the replanning step; it's not worth it for estimation.

---

## What We Learned

**AI evals: fewer levels, more signal.** The 1–5 scoring experiment was genuinely useful even though we dropped it — running it in parallel with binary on the same dataset made the instability visible. The 5-point scores had higher variance across runs and showed less agreement with human raters. If we'd only tried binary, we'd have assumed it was the obvious choice; running the comparison made the *why* concrete.

**The original product was a solution looking for a sharper problem.** Time calibration as a concept is real — people are genuinely miscalibrated — but the pain wasn't acute enough to drive repeat use. "I need to re-estimate all my tasks after a meeting blew up my afternoon" is a problem people feel viscerally and repeatedly. The pivot came from sitting with the question: what problem would make someone open this app without being reminded to?

**Estimation context matters more than model quality.** The biggest source of estimation errors wasn't the model being wrong — it was missing scope. "Write a blog post" can be 30 minutes or 3 hours depending on whether research is in scope, who's reviewing, and whether you're blocked waiting on someone. Structured prompting (asking for category, ambiguity level, and explicit assumptions) had more impact on accuracy than model selection or calibration tuning.

---

## Architecture

```
CLI (cli.py)
  ├── EstimationAgent (agent.py)      ← gpt-4o-mini, structured JSON estimates
  ├── CalibrationLearner (learning.py) ← EMA multiplicative bias correction
  ├── Storage (storage.py)            ← JSON persistence
  └── ReplanningAgent (replanner.py)  ← gpt-4.1 day scheduling
        └── DaySessionStore           ← per-user session files

Web app (web_app.py)
  └── Same ReplanningAgent + DaySessionStore, per-user via Flask session cookie
```

Calibration applies three multiplicative factors updated via exponential moving average (α ≈ 0.3):

```
adjusted = base × category_factor × ambiguity_factor × bias_factor
```

This is intentionally simple — with 10–50 tasks, any regression model overfits. EMA has one hyperparameter, is inspectable, and works with as few as 3 data points.

---

## License

MIT

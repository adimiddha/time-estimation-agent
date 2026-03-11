# Untangle

AI that helps you untangle your day when it all falls apart.

**Try it live:** [Untangel Web App](https://time-estimation-agent-production.up.railway.app/)

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

Open the app and tap the mic — or type — everything on your plate in plain language: tasks, meetings, hard stops, energy levels, whatever context is relevant. The assistant figures out what's realistic, estimates durations, prioritizes, and presents a draft schedule. You see what got dropped and why before approving anything. Once you approve, a visual time-block calendar fills the screen.

**2. Replan when things change**

When the day breaks down, tap the floating Replan button. Speak or type what happened ("the standup ran 45 minutes, I skipped lunch") and the assistant regenerates the calendar from the current moment forward — without losing your original constraints.

Above the calendar is a **Right Now** panel: not your whole schedule, but the 2–3 concrete actions you should be doing in the next block. "Open the doc. Pull up last draft. Set a 25-minute timer." — not "work on report."

The design is intentionally ADHD-friendly: voice-first input, a draft-before-commit review step, rounded Nunito font to reduce visual noise, spring animations to make state changes feel trackable, and time blocks color-coded by type (tasks, fixed events, breaks).

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

### Matching model to task complexity

Replanning involves three distinct LLM calls with different complexity profiles. The context extraction step — "does this raw text contain a hard end time?" — is a narrow classification task with a 200-token budget. gpt-4o-mini handles it reliably and cheaply. The estimation step (structured JSON: a number, a category, a rationale) and the full scheduling step (time arithmetic across a whole day, implicit constraint inference, priority trade-offs) both use gpt-4.1. The cost delta on extraction isn't worth it; on scheduling it is.

### Voice as the primary input

The original UI had a textarea as the entry point. The problem: typing a full brain dump — tasks, meetings, energy, constraints — while you're already stressed and behind is a high-friction ask. Especially for the ADHD use case. We moved the mic button to the center of the welcome screen as the primary CTA, with typing as the fallback. This wasn't about "AI voice features" — it was about removing the cost of getting started when your day is already off the rails. Speaking is lower effort than composing. The transcript gets cleaned up by Whisper; the user doesn't need to structure their input at all.

### A draft step before showing the calendar

The first version generated a schedule and showed it immediately. Users weren't sure whether to trust it — they didn't know what got dropped, why a task was placed where it was, or what the model had decided to punt. Adding a **draft screen** before approval changed the interaction: you see the plan, the dropped/deferred tasks, and the model's rationale before committing. The Approve button becomes a deliberate act rather than something that just happened to you. This also surfaced a practical problem — the draft review revealed bugs and edge cases (like the model incorrectly treating "work until 8pm" as a session hard boundary when activities were mentioned after it) that wouldn't have been visible in an immediate-show flow.

### Designing the "Right Now" section around a single question

Early user feedback on the calendar was consistent: people would open it, scan the schedule for a moment, and then not know what to actually do next. The schedule answered "what's on my list" but not "what do I do *right now*." The Right Now panel is the fix: it shows the current active block with 2–3 micro-steps — concrete, physical actions rather than task labels. Not "write report" but "open the doc, pull up last draft, set a 25-minute timer." These steps are generated by the model alongside the schedule. Break blocks get rest-specific steps ("step away from your desk, get water"). The panel updates automatically as blocks change. This turned out to matter more for actual use than any calendar density tweak — people didn't need a better schedule view, they needed an answer to a different question.

---

## What We Learned

**AI evals: fewer levels, more signal.** The 1–5 scoring experiment was genuinely useful even though we dropped it — running it in parallel with binary on the same dataset made the instability visible. The 5-point scores had higher variance across runs and showed less agreement with human raters. If we'd only tried binary, we'd have assumed it was the obvious choice; running the comparison made the *why* concrete.

**The original product was a solution looking for a sharper problem.** Time calibration as a concept is real — people are genuinely miscalibrated — but the pain wasn't acute enough to drive repeat use. "I need to re-estimate all my tasks after a meeting blew up my afternoon" is a problem people feel viscerally and repeatedly. The pivot came from sitting with the question: what problem would make someone open this app without being reminded to?

**Estimation context matters more than model quality.** The biggest source of estimation errors wasn't the model being wrong — it was missing scope. "Write a blog post" can be 30 minutes or 3 hours depending on whether research is in scope, who's reviewing, and whether you're blocked waiting on someone. Structured prompting (asking for category, ambiguity level, and explicit assumptions) had more impact on accuracy than model selection or calibration tuning. The similar-task shortcut — reusing the actual time from a closely matched completed task, skipping the LLM call entirely — turned out to be more accurate than re-estimating from scratch for recurring tasks.

**LLMs return inconsistent category labels without normalization.** When the estimation agent was asked to categorize tasks, it would return "software dev," "engineering," "coding," and "programming" for the same kind of task across different sessions. This broke calibration — each category was tracking its own bias factor, so the "coding" multiplier learned from 10 tasks had no connection to the "programming" multiplier learned from 5 others. The fix was a normalization layer (`CATEGORY_NORMALIZATION` dict + `validate_and_normalize_category()`) that maps all variants to a canonical set. This is a general problem with using LLM outputs as dictionary keys: you need to treat the output as fuzzy and normalize before storing.

**The replanning loop needs to be frictionless to actually be used.** Early iterations had replanning buried at the bottom of a sidebar. The insight was that mid-day replanning — the core use case — happens when users are already stressed, behind, and decision-fatigued. Any friction at the replan entry point is a reason not to do it. Moving replan to a floating action button that's always visible, with a slide-up panel pre-focused on voice input, cut the interaction down to two taps. The design principle: the more stressed the user, the lower the friction has to be.

**A replanning UI needs to show the whole day without scrolling.** Early calendar implementations used a fixed pixel-per-hour density. The problem: a day that ends at 10pm and a day that ends at 6pm looked completely different — one required scrolling to see whether the evening was even feasible, which defeated the point of at-a-glance orientation. The fix was computing pixels-per-minute dynamically from the container height, so the full remaining schedule always fits on screen regardless of how long the day is. The tradeoff: on long days, individual blocks get smaller. That led to a second problem — blocks under 8 minutes would collapse to unreadable slivers. The fix there was rendering micro-blocks as compact 26px pills instead of proportional rectangles. Neither of these decisions was obvious upfront; they only became clear once real schedules were rendered at different lengths.

**Session end time parsing is harder than it looks.** "Work until 8pm, then F1 race at 8pm" should produce a schedule that ends at 8pm with the race as a fixed block. Early versions treated "work until Xpm" as a hard session boundary and dropped everything after it — including the fixed event the user explicitly mentioned. The fix required checking whether activities exist after the stated end time before deciding whether it's a boundary. This class of bug — where an LLM extracts a rule that's locally correct but misses context — is hard to catch without a draft review step that makes dropped items visible.

---

## Architecture

```
CLI (cli.py)
  ├── EstimationAgent (agent.py)        ← gpt-4.1, structured JSON estimates
  ├── CalibrationLearner (learning.py)  ← EMA multiplicative bias correction
  ├── Storage (storage.py)              ← JSON persistence
  └── ReplanningAgent (replanner.py)    ← day scheduling
        ├── extract_clarification()     ← gpt-4o-mini, lightweight time parsing
        ├── plan_with_estimates()       ← gpt-4.1, full scheduling
        └── DaySessionStore             ← reads/writes day_sessions/*.json

Web app (web_app.py)
  ├── ReplanningAgent + DaySessionStore ← same as CLI path, per-user via Flask session
  ├── Whisper (openai)                  ← audio transcription for voice input
  └── SPA frontend
        ├── templates/index.html        ← single HTML template (welcome + planner screens)
        ├── static/app.js               ← all screen transitions, calendar rendering, voice
        ├── static/style.css            ← CSS variables-driven theme
        └── static/manifest.json        ← PWA manifest (installable, standalone display)
```

Calibration applies three multiplicative factors updated via exponential moving average (α ≈ 0.3):

```
adjusted = base × category_factor × ambiguity_factor × bias_factor
```

This is intentionally simple — with 10–50 tasks, any regression model overfits. EMA has one hyperparameter, is inspectable, and works with as few as 3 data points.

---

## License

MIT

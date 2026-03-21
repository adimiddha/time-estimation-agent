# Untangle — Vision

## What It Is

Untangle is an AI-powered day replanning assistant. You tell it what's on your plate — in plain language, by voice or text — and it builds a realistic time-block schedule. When your day breaks down (a meeting runs long, a task balloons, something urgent drops in), you tell it what happened and it regenerates the plan from the current moment forward.

The core loop: **describe → schedule → replan → repeat.**

## Who It's For

Untangle is built for people whose days don't go as planned — which is most people, but especially:

- **People with ADHD**, who experience time blindness and executive dysfunction that make mid-day reorientation genuinely hard. "Just reprioritize" is not useful advice when you can't hold the whole day in your head under stress.
- **Anyone who over-commits**, underestimates task duration, or finds themselves at 4pm with a plan that stopped being relevant at noon.
- **Knowledge workers** whose work is hard to scope in advance — writing, coding, research, design — where duration variance is high and unexpected interruptions are the norm.

The design is explicitly ADHD-friendly: voice-first input (speaking is lower friction than typing when you're already behind), draft-before-commit review (you see what got dropped before anything is locked in), concrete micro-steps in the "Right Now" panel (not "work on report" but "open the doc, pull up last draft, set a 25-minute timer"), and a calm visual design that avoids overwhelming the user with information.

## What It Values

**1. Recovery over planning.**
Most productivity tools help you plan. Untangle's reason for existing is *recovery* — what do you do when the plan fails? That's the moment of highest stress and lowest executive function. Every design decision should ask: does this reduce friction at that moment?

**2. Realistic over optimistic.**
A schedule that drops tasks is more honest than one that pretends everything fits. Dropped tasks are shown explicitly, with rationale, before the user approves anything. The goal is a plan the user can trust, not one that looks good on screen.

**3. Right Now over full picture.**
Users don't primarily need a better calendar view. They need an answer to one question: *what do I do next?* The "Right Now" panel — 2–3 concrete physical actions for the current block — is more important than any calendar density or layout improvement.

**4. Voice first.**
The primary input is speaking, not typing. Typing a structured brain dump while already stressed and behind is a high-friction ask. The mic is the hero CTA. Text is the fallback. Whisper handles transcription; the user doesn't need to format their input.

**5. Friction as the enemy.**
The replanning loop only works if users actually use it mid-day. Mid-day is when friction is highest — stress, decision fatigue, time pressure. The replan entry point must be impossible to miss and require minimal steps. Two taps to get to a voice input should be the ceiling.

**6. Show your work.**
The draft screen exists because users need to trust the plan before committing to it. Showing dropped tasks, rationale, and the model's reasoning before approval is not a UX nicety — it's how the product earns trust.

## What It Is Not

- Not a to-do list app. Untangle doesn't track tasks over time or manage a backlog.
- Not a calendar replacement. It generates schedules for a single day; it doesn't sync with Google Calendar or manage recurring events.
- Not a general AI assistant. Every feature exists in service of the replanning loop.

## Design Principles in Practice

| Principle | How it shows up |
|---|---|
| Voice first | Mic is centered hero on welcome screen; text is secondary |
| Low friction | FAB always visible; slide-up replan panel pre-focused on voice |
| Honest scheduling | Draft mode shows dropped tasks + rationale before approval |
| Right Now focus | "Right Now" panel shows micro-steps, not task labels |
| ADHD-friendly | Nunito font, spring animations, warm color palette, no dense UI |
| Calm visual design | Warm white bg (`#fdf8f0`), slate blue accent (`#7b68ee`), muted block gradients |

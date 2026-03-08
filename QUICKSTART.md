# Quick Start Guide

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your OpenAI API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

   Or export it:
   ```bash
   export OPENAI_API_KEY=your_key_here
   ```

## Basic Usage

### 1. Estimate a task

```bash
python -m time_calibration_agent.cli estimate "Write a blog post about AI"
```

Output:
```
============================================================
TIME ESTIMATION
============================================================

Task 1: Write a blog post about AI
------------------------------------------------------------
📊 Estimate: 90 minutes
   Range: 60 - 120 minutes
   Category: writing
   Ambiguity: moderate
   Explanation: Writing a blog post typically involves research, drafting, and editing...
   Task ID: task_1_1704110400
```

### 2. Log actual time

After completing the task, log how long it actually took:

```bash
python -m time_calibration_agent.cli log task_1_1704110400 120
```

Output:
```
✅ Time logged for task: Write a blog post about AI
   Estimated: 90 minutes
   Actual: 120 minutes
   Error: +33.3%

📈 Calibration updated based on this outcome.
```

### 3. Check your calibration status

```bash
python -m time_calibration_agent.cli status
```

Output:
```
============================================================
CALIBRATION STATUS
============================================================

Total tasks: 5
Pending: 2
Completed: 3

📊 Overall pattern: You tend to UNDERESTIMATE by ~15.2%

Category patterns:
  - writing: +18.5% adjustment
  - coding: -5.0% adjustment
```

### 4. View history

```bash
python -m time_calibration_agent.cli history
```

### 5. Run the web app (Replanning MVP)

```bash
python -m time_calibration_agent.web_app
```

Then open `http://127.0.0.1:5000` in your browser and use the replanning form.

### 6. Start a planning session (optional)

```bash
python -m time_calibration_agent.cli new-session "It's 2pm. I finished X. Need A, B. Dinner at 7."
python -m time_calibration_agent.cli session
```

### 7. Replan a session (optional)

```bash
python -m time_calibration_agent.cli replan "It's 3pm. I finished A. Need B."
```

## Evaluation & Testing

### Evaluate accuracy on completed tasks

```bash
python -m time_calibration_agent.cli eval
python -m time_calibration_agent.cli eval --export results.json
```

### Generate a test dataset

```bash
python -m time_calibration_agent.cli test-dataset generate --n 50 --output test_dataset.json
```

### Run quality evaluation

```bash
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --strategy summarized
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --evaluator human
```

### Compare strategies

```bash
python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json
```

## How It Learns

1. **First few tasks**: The agent uses general knowledge to estimate
2. **After logging time**: The system learns your patterns
3. **Future estimates**: Automatically adjusted based on your history

The more tasks you complete and log, the better the estimates become!

## Tips

- **Be consistent**: Log actual time for all tasks to improve learning
- **Use descriptive task names**: Helps the agent understand context
- **Check status regularly**: See how your calibration is improving
- **Review history**: Understand patterns in your estimation accuracy

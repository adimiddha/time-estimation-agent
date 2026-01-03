# Time Calibration Agent

An AI agent that helps users become better calibrated at estimating how long tasks take. The agent predicts task durations, learns from actual time logged, and improves its estimates over time using user-specific context.

## Product Goal

This is **not a todo list**. It's a **prediction + learning system** that:
- Predicts how long tasks will take before execution
- Learns from actual time logged
- Improves estimates over time using user-specific context

## Core User Flow (V1)

1. **User describes tasks** in natural language
2. **Agent outputs**:
   - Estimated duration per task
   - A range (optimistic / realistic / pessimistic)
   - A brief explanation of assumptions
   - Task category and ambiguity level
3. **User logs actual time** spent later
4. **Agent updates** its understanding:
   - User's personal estimation bias
   - Task-type-specific patterns
   - Ambiguity effects

## Architecture

### Components

1. **Storage Layer** (`storage.py`)
   - JSON-based persistence (simple for V1)
   - Stores tasks, estimates, actuals, and calibration data
   - No database required

2. **Estimation Agent** (`agent.py`)
   - Uses OpenAI API to generate initial estimates
   - Considers historical patterns and similar tasks
   - Returns structured estimates with explanations

3. **Learning System** (`learning.py`)
   - Heuristic-based calibration (V1 approach)
   - Tracks overall user bias
   - Learns category-specific patterns
   - Learns ambiguity effects
   - Applies adjustments to future estimates

4. **CLI Interface** (`cli.py`)
   - Simple command-line interface
   - Estimate tasks
   - Log actual time
   - View status and history

### Data Schema

```json
{
  "tasks": [
    {
      "id": "task_1_1234567890",
      "description": "Write blog post",
      "estimated_minutes": 60,
      "estimate_range": {
        "optimistic": 45,
        "realistic": 60,
        "pessimistic": 90
      },
      "explanation": "...",
      "category": "writing",
      "ambiguity": "moderate",
      "actual_minutes": 75,
      "created_at": "2024-01-01T10:00:00",
      "completed_at": "2024-01-01T11:15:00"
    }
  ],
  "calibration": {
    "user_bias": 0.15,
    "category_patterns": {
      "writing": 1.25,
      "coding": 0.9
    },
    "ambiguity_patterns": {
      "fuzzy": 1.3,
      "clear": 0.95
    },
    "total_tasks": 10,
    "total_discrepancy": 150.0
  }
}
```

## How Learning Happens

### 1. Initial Estimation

When a user describes a task, the agent:
- Analyzes the task description
- Considers historical patterns (if available)
- Looks at similar past tasks
- Generates an estimate with range and explanation

### 2. Calibration Application

Before returning the estimate, the learning system applies adjustments:
- **User bias**: If user consistently over/underestimates, adjust baseline
- **Category patterns**: If "coding" tasks always take 20% longer, apply that
- **Ambiguity effects**: If "fuzzy" tasks are underestimated, adjust upward

### 3. Learning from Outcomes

When actual time is logged:
- Calculate error percentage
- Update overall user bias (exponential moving average)
- Update category-specific patterns
- Update ambiguity patterns
- Store insights for future estimates

### Learning Strategy (V1)

The V1 learning system uses **heuristics** rather than complex ML:

1. **Bias Calculation**: Weighted average of estimation errors
2. **Pattern Detection**: Track errors by category and ambiguity
3. **Smoothing**: Exponential moving average to avoid overreacting to outliers
4. **Adjustment Application**: Multiplicative factors applied to future estimates

This approach is:
- ✅ Simple and inspectable
- ✅ Fast and doesn't require training
- ✅ Works with small datasets
- ✅ Easy to debug and improve

## Installation

1. **Clone or download** this repository

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up OpenAI API key**:
   Create a `.env` file:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```
   Or export it:
   ```bash
   export OPENAI_API_KEY=your_api_key_here
   ```

## Usage

### Estimate Tasks

```bash
python -m time_calibration_agent.cli estimate "Write blog post about time estimation"
python -m time_calibration_agent.cli estimate "Code review PR #123" "Update documentation"
```

### Log Actual Time

```bash
python -m time_calibration_agent.cli log task_1_1234567890 45
```

### View Status

```bash
python -m time_calibration_agent.cli status
```

### View History

```bash
python -m time_calibration_agent.cli history
python -m time_calibration_agent.cli history 20  # Show last 20 tasks
```

## Example Session

```bash
# Estimate some tasks
$ python -m time_calibration_agent.cli estimate "Write API documentation" "Fix bug in auth system"

Task 1: Write API documentation
------------------------------------------------------------
📊 Estimate: 90 minutes
   Range: 60 - 120 minutes
   Category: writing
   Ambiguity: moderate
   Explanation: Documentation typically requires research, writing, and review...
   Task ID: task_1_1704110400

Task 2: Fix bug in auth system
------------------------------------------------------------
📊 Estimate: 45 minutes
   Range: 30 - 60 minutes
   Category: coding
   Ambiguity: clear
   Explanation: Bug fixes can vary, but auth issues are usually straightforward...
   Task ID: task_2_1704110401

# Later, log actual time
$ python -m time_calibration_agent.cli log task_1_1704110400 120
✅ Time logged for task: Write API documentation
   Estimated: 90 minutes
   Actual: 120 minutes
   Error: +33.3%

📈 Calibration updated based on this outcome.

# Check status
$ python -m time_calibration_agent.cli status
============================================================
CALIBRATION STATUS
============================================================

Total tasks: 5
Pending: 1
Completed: 4

📊 Overall pattern: You tend to UNDERESTIMATE by ~12.5%

Category patterns:
  - writing: +18.2% adjustment
  - coding: -5.0% adjustment
```

## Key Concepts Tracked

- **Task Category**: e.g., deep work, admin, social, errands, coding, writing
- **Task Ambiguity**: clear, moderate, or fuzzy
- **User Bias**: Overall tendency to over/underestimate
- **Contextual Patterns**: Category and ambiguity-specific adjustments

## Known Limitations (V1)

1. **No user authentication**: Single-user only, data stored locally
2. **Simple learning**: Heuristic-based, not ML-powered
3. **No context awareness**: Doesn't consider time of day, energy levels, etc. (mentioned but not implemented)
4. **No task dependencies**: Doesn't account for task ordering or dependencies
5. **Limited pattern detection**: Only tracks category and ambiguity, not more nuanced patterns
6. **No confidence intervals**: Range is provided but not used in learning
7. **JSON storage**: Not suitable for large datasets or concurrent access

## What Would Be Improved in V2

### Learning Improvements
- **ML-based calibration**: Use regression models or simple neural networks
- **Feature engineering**: Extract more features from task descriptions
- **Confidence tracking**: Learn when estimates are more/less reliable
- **Temporal patterns**: Learn from time of day, day of week effects
- **Context awareness**: Consider energy levels, interruptions, etc.

### Product Improvements
- **Web interface**: Better UX than CLI
- **Voice input**: Natural language task entry
- **Task templates**: Recurring task patterns
- **Visualizations**: Charts showing calibration improvement over time
- **Export/import**: Backup and share calibration data
- **Multi-user support**: Auth and user-specific models

### Technical Improvements
- **Database**: SQLite or PostgreSQL for better data management
- **API**: REST API for integration with other tools
- **Caching**: Reduce API calls for similar tasks
- **Batch processing**: Learn from multiple outcomes at once
- **A/B testing**: Test different learning strategies

## Design Decisions

1. **Heuristics over ML (V1)**: Faster to implement, easier to debug, works with small data
2. **JSON storage**: No setup required, easy to inspect and modify
3. **CLI first**: Fastest way to validate the core learning loop
4. **Exponential moving average**: Smooth learning that doesn't overreact
5. **Multiplicative adjustments**: Preserves relative differences between tasks
6. **Category + Ambiguity**: Two key dimensions that affect estimation accuracy

## License

MIT


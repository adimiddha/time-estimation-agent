🚀 Built an AI-powered time calibration agent that learns from your work patterns

The problem: Most people are terrible at estimating how long tasks take. This leads to missed deadlines, overcommitment, and stress.

The solution: An AI agent that predicts task duration, learns from actual time logged, and improves estimates over time using user-specific context.

Here's what I built:

📐 Architecture
• 4-layer system: Storage, Agent, Learning, CLI
• Clean separation of concerns
• Stateless components with centralized data persistence

🤖 AI-Powered Estimation
• OpenAI GPT-4o-mini for cost-efficient predictions
• Historical context integration
• Structured JSON responses with ranges and explanations

📊 Learning System
• Tracks overall user bias (over/underestimation tendency)
• Learns category-specific patterns (e.g., "writing" tasks take 20% longer)
• Detects ambiguity effects (fuzzy tasks vs. clear tasks)
• Uses exponential moving averages for smooth learning

💻 User Experience
• Simple CLI: estimate → log → learn
• Natural language task matching
• Status and history views
• Zero setup required (just needs OpenAI API key)

Key design decisions:
✅ Heuristics over ML (V1) - faster to implement, easier to debug
✅ JSON storage - no database setup required
✅ CLI first - fastest way to validate the learning loop
✅ Exponential smoothing - avoids overreacting to outliers

The system gets better with each task you complete. After logging just a few tasks, it starts learning your personal patterns and adjusting future estimates accordingly.

Built with Python, OpenAI API, and a focus on simplicity and effectiveness.

#AI #ProductDevelopment #TimeManagement #Python #OpenAI# Time Calibration Agent - Codebase Overview

## Architecture Overview

The codebase follows a clean separation of concerns with four main components that work together:

```
┌─────────────┐
│     CLI     │  ← User Interface Layer
└──────┬──────┘
       │
       ├──► Storage  ← Data Persistence Layer
       ├──► Agent    ← AI Estimation Layer  
       └──► Learner  ← Calibration/Learning Layer
```

---

## Component Breakdown

### 1. **`storage.py`** - Data Persistence Layer
**Purpose**: Manages all data persistence using JSON files.

**Key Responsibilities**:
- Stores tasks, estimates, and calibration data in `calibration_data.json`
- Provides CRUD operations for tasks
- Manages calibration/learning data

**Key Classes & Methods**:
- `TaskStorage` - Main storage class
  - `add_task()` - Creates new task with estimate
  - `log_actual_time()` - Records actual time spent
  - `get_task()` - Retrieves a specific task
  - `get_pending_tasks()` - Gets incomplete tasks
  - `get_completed_tasks()` - Gets tasks with actual time logged
  - `get_calibration_data()` - Gets current learning data
  - `update_calibration()` - Saves updated learning data

**Data Structure**:
```json
{
  "tasks": [
    {
      "id": "task_1_1234567890",
      "description": "Write blog post",
      "estimated_minutes": 60,
      "estimate_range": {...},
      "actual_minutes": 75,
      "category": "writing",
      "ambiguity": "moderate",
      "created_at": "...",
      "completed_at": "..."
    }
  ],
  "calibration": {
    "user_bias": 0.15,
    "category_patterns": {"writing": 1.25},
    "ambiguity_patterns": {"fuzzy": 1.3},
    "total_tasks": 10
  }
}
```

---

### 2. **`agent.py`** - AI Estimation Layer
**Purpose**: Uses OpenAI API to generate initial time estimates.

**Key Responsibilities**:
- Calls OpenAI API to estimate task durations
- Incorporates historical context into prompts
- Returns structured estimates with explanations

**Key Classes & Methods**:
- `EstimationAgent` - Main agent class
  - `estimate_task()` - Generates estimate for a task
    - Takes: task description, calibration context, historical tasks
    - Returns: estimate with range, explanation, category, ambiguity
  - `reflect_on_outcome()` - (Optional) Uses AI to reflect on completed tasks

**How It Works**:
1. Builds context from user's historical patterns (bias, category patterns)
2. Includes recent similar tasks as examples
3. Sends prompt to OpenAI with all context
4. Parses JSON response and validates fields
5. Returns structured estimate

**Key Features**:
- Uses `gpt-4o-mini` for cost efficiency
- Temperature 0.3 for consistency
- JSON response format for structured output
- Fallback to default estimate if API fails

---

### 3. **`learning.py`** - Calibration/Learning Layer
**Purpose**: Learns from actual vs estimated time to improve future estimates.

**Key Responsibilities**:
- Calculates user bias (over/underestimation tendency)
- Tracks category-specific patterns
- Tracks ambiguity effects
- Applies learned adjustments to new estimates

**Key Classes & Methods**:
- `CalibrationLearner` - Main learning class
  - `update_calibration()` - Updates learning data from completed tasks
    - Calculates overall bias (weighted average of errors)
    - Builds category patterns (e.g., "writing" tasks take 20% longer)
    - Builds ambiguity patterns (e.g., "fuzzy" tasks underestimated)
    - Uses exponential moving average for smoothing
  - `apply_calibration_to_estimate()` - Adjusts new estimates
    - Applies category adjustment factor
    - Applies ambiguity adjustment factor
    - Applies overall bias factor
    - Returns calibrated estimate

**Learning Algorithm**:
- **Bias Calculation**: Weighted average of estimation errors
- **Pattern Detection**: Tracks errors by category and ambiguity
- **Smoothing**: Exponential moving average (alpha ~0.3) to avoid overreacting
- **Adjustment**: Multiplicative factors applied to future estimates

**Example**:
- If "writing" tasks consistently take 25% longer than estimated
- Future "writing" task estimates are multiplied by 1.25

---

### 4. **`cli.py`** - User Interface Layer
**Purpose**: Command-line interface that orchestrates all components.

**Key Responsibilities**:
- Parses command-line arguments
- Coordinates between Storage, Agent, and Learner
- Formats and displays output to user

**Key Classes & Methods**:
- `TimeCalibrationCLI` - Main CLI class
  - `estimate_tasks()` - Estimates one or more tasks
  - `log_time()` - Logs actual time for a task
  - `show_status()` - Shows calibration status
  - `show_history()` - Shows recent task history
  - `_update_calibration()` - Internal method to update learning

**Commands**:
- `estimate "task description"` - Get estimate for task(s)
- `log <task_id> <minutes>` - Log actual time
- `status` - Show calibration status
- `history [limit]` - Show recent history

---

## Data Flow

### Estimating a Task

```
User: estimate "Write blog post"
  │
  ├─► CLI.estimate_tasks()
  │     │
  │     ├─► Storage.get_calibration_data()  ← Get learning data
  │     ├─► Storage.get_completed_tasks()    ← Get historical context
  │     │
  │     ├─► Agent.estimate_task()           ← Get AI estimate
  │     │     │
  │     │     └─► OpenAI API call           ← Generate estimate
  │     │
  │     ├─► Learner.apply_calibration_to_estimate()  ← Adjust estimate
  │     │
  │     └─► Storage.add_task()              ← Save task
  │
  └─► Display estimate to user
```

### Logging Actual Time

```
User: log task_1_1234567890 45
  │
  ├─► CLI.log_time()
  │     │
  │     ├─► Storage.log_actual_time()       ← Save actual time
  │     │
  │     ├─► CLI._update_calibration()
  │     │     │
  │     │     ├─► Storage.get_completed_tasks()  ← Get all completed
  │     │     ├─► Storage.get_calibration_data()  ← Get current learning
  │     │     │
  │     │     ├─► Learner.update_calibration()  ← Recalculate patterns
  │     │     │
  │     │     └─► Storage.update_calibration()  ← Save updated learning
  │     │
  │     └─► Display result
  │
  └─► Learning data updated for future estimates
```

---

## Key Interactions

### 1. **Storage ↔ CLI**
- CLI reads/writes all data through Storage
- Storage is the single source of truth

### 2. **Agent ↔ CLI**
- CLI calls Agent to get estimates
- Agent is stateless (no internal memory)
- Agent receives context from Storage via CLI

### 3. **Learner ↔ CLI**
- CLI uses Learner to:
  - Update calibration after logging time
  - Apply calibration to new estimates
- Learner is stateless (operates on data passed in)

### 4. **Storage ↔ Learner**
- Learner reads completed tasks from Storage (via CLI)
- Learner writes updated calibration to Storage (via CLI)

---

## Design Patterns

1. **Separation of Concerns**: Each module has a single, clear responsibility
2. **Stateless Components**: Agent and Learner are stateless - all state in Storage
3. **Dependency Injection**: CLI creates and coordinates all components
4. **JSON Storage**: Simple file-based storage (no database needed for V1)

---

## File Structure

```
time_calibration_agent/
├── __init__.py          # Package initialization, version info
├── agent.py            # AI estimation (OpenAI integration)
├── storage.py          # Data persistence (JSON file management)
├── learning.py         # Calibration/learning algorithms
└── cli.py              # Command-line interface (orchestration)
```

---

## Extension Points

To extend the system:

1. **Better Learning**: Modify `learning.py` to use ML models instead of heuristics
2. **Different Storage**: Replace `storage.py` with database backend
3. **Web Interface**: Create new `web.py` that uses same Agent/Storage/Learner
4. **More Context**: Add features to `agent.py` prompts (time of day, energy levels, etc.)
5. **Better Estimates**: Use different models or fine-tuning in `agent.py`

---

## Key Concepts

- **User Bias**: Overall tendency to over/underestimate (e.g., +15% = overestimate by 15%)
- **Category Patterns**: Task-type-specific adjustments (e.g., "coding" tasks take 10% longer)
- **Ambiguity Effects**: How task clarity affects accuracy (e.g., "fuzzy" tasks underestimated)
- **Calibration**: The process of adjusting estimates based on learned patterns
- **Exponential Moving Average**: Smoothing technique to avoid overreacting to outliers


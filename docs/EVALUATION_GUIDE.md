# Evaluation and Testing Guide

This guide covers the evaluation framework, test dataset generation, and quality evaluation features added to the Time Calibration Agent.

## Table of Contents

1. [Overview](#overview)
2. [Evaluation Framework](#evaluation-framework)
3. [Test Dataset Generation](#test-dataset-generation)
4. [Quality Evaluation](#quality-evaluation)
5. [Context Engineering Experiments](#context-engineering-experiments)
6. [Usage Examples](#usage-examples)

---

## Overview

The evaluation system supports two types of evaluation:

1. **Personalized Evaluation** (with actuals): Measures accuracy against logged actual times
   - Uses metrics like MAE, MAPE, % within ±20%
   - Tracks calibration drift over time
   - Per-user calibration and learning

2. **General Quality Evaluation** (without actuals): Measures estimate quality using AI/human evaluators
   - Tests base model performance before personalization
   - Determines best default context strategy for new users
   - Uses AI evaluators to assess reasonableness, consistency, and appropriateness

---

## Evaluation Framework

### Metrics Available

- **MAE (Mean Absolute Error)**: Average absolute difference between estimated and actual time (in minutes)
- **MAPE (Mean Absolute Percentage Error)**: Average percentage error
- **% Within Threshold**: Percentage of tasks within ±20% or ±10% of actual
- **Calibration Drift**: How accuracy changes over time (early vs recent performance)
- **By Category**: Metrics broken down by task category
- **By Ambiguity**: Metrics broken down by ambiguity level

### Usage

```bash
# View evaluation metrics for completed tasks
python -m time_calibration_agent.cli eval

# Export results to JSON
python -m time_calibration_agent.cli eval --export results.json
```

### Output

The evaluation displays:
- Overall performance metrics (MAE, MAPE, % within thresholds)
- Calibration drift over time
- Performance breakdown by category
- Performance breakdown by ambiguity level

---

## Test Dataset Generation

### Features

Generates diverse test prompts covering:
- **Categories**: All 9 categories (deep work, admin, social, errands, coding, writing, meetings, learning, general)
- **Ambiguity**: clear (30%), moderate (50%), fuzzy (20%)
- **Length**: short (20%), medium (50%), long (30%)
- **Task Types**: cooking, cleaning, work, personal care, errands, creative, technical, social, learning
- **Complexity**: simple (40%), multi-step (40%), task breakdowns (20%)
- **Interruption Likelihood**: low (33%), medium (34%), high (33%)

### Usage

```bash
# Generate default dataset (50 prompts)
python -m time_calibration_agent.cli test-dataset generate

# Generate custom number of prompts
python -m time_calibration_agent.cli test-dataset generate --n 100

# Specify output file
python -m time_calibration_agent.cli test-dataset generate --n 50 --output my_test_dataset.json
```

### Output Format

```json
{
  "test_prompts": [
    {
      "id": "test_1",
      "prompt": "Write a blog post about time estimation",
      "metadata": {
        "category": "writing",
        "ambiguity": "moderate",
        "length": "medium",
        "task_type": "creative",
        "complexity": "simple",
        "interruption_likelihood": "low"
      }
    }
  ],
  "total_count": 50,
  "metadata": {
    "categories": ["writing", "coding", ...],
    "ambiguities": ["clear", "moderate", "fuzzy"],
    "lengths": ["short", "medium", "long"]
  }
}
```

---

## Quality Evaluation

### Evaluation Criteria

The AI evaluator assesses estimates on:

1. **Reasonableness** (1-5 scale):
   - Is the estimate number reasonable for the task?
   - Does the explanation provide sound reasoning?
   - Are there logical flaws in the explanation?

2. **Consistency** (1-5 scale):
   - **Explanation-Number Alignment**: Does explanation justify the estimate number?
   - **Range Alignment**: Does explanation account for optimistic/realistic/pessimistic range?
   - **Internal Consistency**: Is explanation internally consistent (no contradictions)?

3. **Range Appropriateness** (1-5 scale):
   - Are optimistic < realistic < pessimistic?
   - Is the range reasonable (not too narrow/wide)?

4. **Category Appropriateness** (1-5 scale):
   - Does category match the task description?

5. **Overall Quality** (1-5 scale):
   - Composite score considering all factors

### Usage

#### AI Evaluation

```bash
# Evaluate with default strategy (recent_n)
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json

# Evaluate with specific strategy
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --strategy minimal
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --strategy summarized
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --strategy category_filtered
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --strategy similarity_based
```

#### Human Evaluation

```bash
# Run human evaluation (interactive)
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --evaluator human

# Run both AI and human evaluation
python -m time_calibration_agent.cli quality-eval --dataset test_dataset.json --evaluator both
```

#### Compare All Strategies

```bash
# Compare all context strategies on quality metrics
python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json
```

### Available Strategies

- `minimal`: No historical context, just system prompt
- `recent_n`: Last N tasks (default: 10)
- `summarized`: AI-generated summary of history
- `category_filtered`: Only similar category tasks
- `similarity_based`: Semantic similarity to current task

### Output

Quality evaluation displays:
- Average quality score (1-5)
- Score distribution
- Individual evaluation results with detailed checks
- Comparison table when comparing strategies

---

## Context Engineering Experiments

### Personalized Experiments (with actuals)

Tests context strategies on your completed tasks to find the best per-user strategy.

```bash
# Run experiments on your completed tasks
python -m time_calibration_agent.cli experiment

# Save results
python -m time_calibration_agent.cli experiment --output experiment_results.json
```

### General Quality Experiments (without actuals)

Tests context strategies on generated test dataset to find best default strategy.

```bash
# Generate dataset first
python -m time_calibration_agent.cli test-dataset generate --n 50 --output test_dataset.json

# Compare all strategies
python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json
```

---

## Usage Examples

### Complete Workflow: Finding Best Default Strategy

```bash
# Step 1: Generate test dataset
python -m time_calibration_agent.cli test-dataset generate --n 50 --output test_dataset.json

# Step 2: Compare all strategies on quality
python -m time_calibration_agent.cli quality-compare --dataset test_dataset.json

# Step 3: Review results to determine best default strategy
# (Results show which strategy has highest average quality score)
```

### Complete Workflow: Evaluating Your Personal Performance

```bash
# Step 1: Estimate some tasks
python -m time_calibration_agent.cli estimate "Write blog post" "Fix bug"

# Step 2: Log actual time
python -m time_calibration_agent.cli log "the writing task" 45

# Step 3: View evaluation metrics
python -m time_calibration_agent.cli eval

# Step 4: Run personalized experiments
python -m time_calibration_agent.cli experiment
```

### Testing a Specific Strategy

```bash
# Generate test dataset
python -m time_calibration_agent.cli test-dataset generate --n 20 --output small_test.json

# Test minimal strategy
python -m time_calibration_agent.cli quality-eval --dataset small_test.json --strategy minimal

# Test summarized strategy
python -m time_calibration_agent.cli quality-eval --dataset small_test.json --strategy summarized
```

### Human Evaluation Workflow

```bash
# Generate dataset
python -m time_calibration_agent.cli test-dataset generate --n 10 --output human_test.json

# Run human evaluation (interactive)
python -m time_calibration_agent.cli quality-eval --dataset human_test.json --evaluator human

# Results saved to human_evaluations.json
```

---

## Understanding the Results

### Evaluation Metrics (with actuals)

- **MAE < 10 minutes**: Excellent accuracy
- **MAPE < 15%**: Very good
- **% Within ±20% > 70%**: Well calibrated
- **Calibration Drift negative**: Improving over time

### Quality Scores (without actuals)

- **Average Score > 4.0**: Excellent quality
- **Average Score 3.5-4.0**: Good quality
- **Average Score 3.0-3.5**: Acceptable quality
- **Average Score < 3.0**: Needs improvement

### Strategy Selection

- **Personalized**: Use `experiment` command results - best strategy for YOUR data
- **General/Default**: Use `quality-compare` results - best strategy for NEW users

---

## Key Files

- `time_calibration_agent/evaluation.py`: Metrics calculation (MAE, MAPE, etc.)
- `time_calibration_agent/test_dataset.py`: Test dataset generation
- `time_calibration_agent/quality_evaluation.py`: Quality evaluation (AI/human)
- `time_calibration_agent/experiments.py`: Experiment framework
- `time_calibration_agent/agent.py`: Context strategies implementation

---

## Tips

1. **Start with a small test dataset** (n=10-20) to test workflows before generating large datasets
2. **Use human evaluation** for edge cases or when you want ground truth
3. **Compare strategies regularly** as your data grows to see if best strategy changes
4. **Export results** to JSON for deeper analysis or tracking over time
5. **Test dataset is reproducible** - use seeds for consistent testing

---

## Troubleshooting

**"Not enough completed tasks"**: 
- Need at least 3 completed tasks for experiments
- Log actual time for some tasks first

**"Error loading dataset"**:
- Check file path is correct
- Ensure JSON file is valid

**Low quality scores**:
- Review individual evaluations to see what's failing
- Check if explanation quality is the issue
- Consider adjusting system prompt or context strategy


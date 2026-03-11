#!/usr/bin/env python3
"""Display test_4 disagreements side by side."""

import json
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

# Get dataset from command line or default to test4
import sys
dataset_arg = sys.argv[1] if len(sys.argv) > 1 else 'test4'
# Handle both test1 and test_1 formats
if '_' in dataset_arg:
    dataset = dataset_arg
    dataset_name = dataset.replace('_', '')
else:
    dataset_name = dataset_arg
    dataset = f"test_{dataset_name[-1]}" if dataset_name.startswith('test') and len(dataset_name) == 5 else dataset_arg

def extract_estimate_from_reasoning(reasoning):
    """Extract estimate details from reasoning text."""
    estimate_info = {
        'estimated_minutes': None,
        'range': None,
        'category': None
    }
    
    # Extract estimated minutes (look for patterns like "30 minutes", "estimate of 30 minutes", etc.)
    minute_patterns = [
        r'estimate[d]?\s+(?:of|is|of\s+)?\s*(\d+)\s+minutes?',
        r'(\d+)\s+minutes?\s+(?:is|for|estimate)',
        r'time\s+(?:of|estimate[d]?\s+of)?\s*(\d+)\s+minutes?',
        r'(\d+)\s+minutes?\s+(?:is\s+reasonable|estimate)'
    ]
    
    for pattern in minute_patterns:
        match = re.search(pattern, reasoning, re.IGNORECASE)
        if match:
            estimate_info['estimated_minutes'] = int(match.group(1))
            break
    
    # Extract range (look for patterns like "20-30-45 minutes", "15-30 minutes", etc.)
    range_patterns = [
        r'range\s+(?:of|provided|is)?\s*\(?(\d+)[-\s]+(\d+)[-\s]+(\d+)\s+minutes?',
        r'(\d+)[-\s]+(\d+)[-\s]+(\d+)\s+minutes?\s+(?:range|estimate)',
        r'range\s+(?:of|provided|is)?\s*(\d+)[-\s]+(\d+)\s+minutes?',
        r'(\d+)[-\s]+(\d+)\s+minutes?\s+(?:range|account)'
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, reasoning, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                estimate_info['range'] = f"{groups[0]}-{groups[1]}-{groups[2]}"
            elif len(groups) == 2:
                estimate_info['range'] = f"{groups[0]}-{groups[1]}"
            break
    
    # Extract category
    category_patterns = [
        r"category\s+(?:of|is)?\s*['\"]?(\w+)['\"]?",
        r"category\s+['\"](\w+)['\"]"
    ]
    
    for pattern in category_patterns:
        match = re.search(pattern, reasoning, re.IGNORECASE)
        if match:
            estimate_info['category'] = match.group(1)
            break
    
    return estimate_info

# Load actual evaluation files to get task and estimate details
old_file = f'eval/results/quality_eval_debug_1-5_{dataset_name}.json'
new_file = f'eval/results/quality_eval_debug_0-1_{dataset_name}.json'

with open(old_file, 'r') as f:
    old_data = json.load(f)
    
with open(new_file, 'r') as f:
    new_data = json.load(f)

old_samples = old_data.get('samples', [])
new_samples = new_data.get('samples', [])

# Generate disagreements from evaluation files
from time_calibration_agent.quality_analysis import find_disagreements

# Get all evaluations
old_all_evals = old_data.get('all_evaluations', [])
new_all_evals = new_data.get('all_evaluations', [])

# Generate disagreements
disagreements_data = find_disagreements(old_all_evals, new_all_evals, old_samples, new_samples)

# Get disagreements (already generated above)
all_disagreements = disagreements_data.get('all_disagreements', [])

# Separate by type - the field is called 'type' in find_disagreements output
old_stricter = [d for d in all_disagreements if d.get('type') == 'old_poor_new_good']
new_stricter = [d for d in all_disagreements if d.get('type') == 'old_good_new_poor']

# Load full dataset to get all tasks
# Try both naming conventions
test_dataset_file = f'eval/datasets/{dataset}_dataset.json'
if not Path(test_dataset_file).exists():
    test_dataset_file = f'eval/datasets/{dataset_name}_dataset.json'
with open(test_dataset_file, 'r') as f:
    test_dataset = json.load(f)
    test_prompts = test_dataset.get('test_prompts', [])

console.print(Panel.fit(f'[bold cyan]📊 {dataset.upper()} Disagreements Analysis[/bold cyan]', border_style='cyan'))
console.print()

# Display old stricter cases
console.print('[bold yellow]Cases Where Old System Was Stricter (Old Poor → New Good):[/bold yellow]')
console.print()

for i, d in enumerate(old_stricter, 1):
    idx = d.get('index', 0)
    
    # Get task from dataset
    if idx < len(test_prompts):
        task_data = test_prompts[idx]
        task = task_data.get('prompt', 'Unknown task')
    else:
        task = 'Unknown task'
    
    # Try to get estimate from samples first
    old_sample = old_samples[idx] if idx < len(old_samples) else {}
    new_sample = new_samples[idx] if idx < len(new_samples) else {}
    
    estimate = old_sample.get('estimate', new_sample.get('estimate', {}))
    
    # If estimate is empty, try to find it by matching task in samples
    if not estimate or estimate == {}:
        # Search through all samples to find matching task
        for sample in old_samples + new_samples:
            if sample.get('task', '') == task:
                estimate = sample.get('estimate', {})
                break
        else:
            estimate = {'estimated_minutes': 'N/A', 'estimate_range': {}, 'explanation': 'Estimate not in debug samples', 'category': 'N/A'}
    
    old_eval = d.get('old_evaluation', {})
    new_eval = d.get('new_evaluation', {})
    
    console.print(f'[bold]Case {i}: Old Score {d.get("old_score")}/5 → New Score {d.get("new_score")}[/bold]')
    console.print()
    
    # Task and estimate
    task_display = task[:200] + "..." if len(task) > 200 else task
    console.print(f'[cyan]Task:[/cyan] {task_display}')
    console.print()
    
    # Try to get estimate from the estimate dict first
    est_min = estimate.get('estimated_minutes', None)
    est_range = estimate.get('estimate_range', {})
    opt = est_range.get('optimistic', None)
    real = est_range.get('realistic', est_min)
    pess = est_range.get('pessimistic', None)
    explanation = estimate.get('explanation', 'N/A')
    category = estimate.get('category', None)
    
    # If estimate not found, extract from reasoning
    if est_min is None or est_min == 'N/A':
        old_reasoning = old_eval.get('reasoning', '')
        new_reasoning = new_eval.get('reasoning', '')
        
        # Try to extract from both reasonings
        old_info = extract_estimate_from_reasoning(old_reasoning)
        new_info = extract_estimate_from_reasoning(new_reasoning)
        
        # Prefer new info, fall back to old
        est_min = new_info.get('estimated_minutes') or old_info.get('estimated_minutes') or 'N/A'
        if est_min != 'N/A':
            range_str = new_info.get('range') or old_info.get('range')
            if range_str:
                console.print(f'[cyan]Estimate:[/cyan] {est_min} min [dim](extracted from reasoning)[/dim]')
                console.print(f'[cyan]Range:[/cyan] {range_str} min [dim](extracted from reasoning)[/dim]')
            else:
                console.print(f'[cyan]Estimate:[/cyan] {est_min} min [dim](extracted from reasoning)[/dim]')
                console.print(f'[cyan]Range:[/cyan] Not specified in reasoning')
        else:
            console.print(f'[cyan]Estimate:[/cyan] Not found in reasoning')
            console.print(f'[cyan]Range:[/cyan] Not found in reasoning')
        
        category = new_info.get('category') or old_info.get('category') or category or 'N/A'
        console.print(f'[cyan]Category:[/cyan] {category}')
    else:
        console.print(f'[cyan]Estimate:[/cyan] {est_min} min')
        if opt and pess:
            console.print(f'[cyan]Range:[/cyan] {opt}-{real}-{pess} min')
        elif opt:
            console.print(f'[cyan]Range:[/cyan] {opt}-{real} min')
        else:
            console.print(f'[cyan]Range:[/cyan] Not specified')
        console.print(f'[cyan]Category:[/cyan] {category or "N/A"}')
    
    if explanation and explanation != 'N/A' and explanation != 'Estimate not in debug samples':
        expl_display = explanation[:300] + "..." if len(explanation) > 300 else explanation
        console.print(f'[cyan]Explanation:[/cyan] {expl_display}')
    console.print()
    
    # Side by side comparison
    comp_table = Table(box=box.ROUNDED, show_header=True)
    comp_table.add_column('Aspect', style='cyan', width=20)
    comp_table.add_column('Old System (1-5)', style='yellow', width=40)
    comp_table.add_column('New System (0-1)', style='green', width=40)
    
    comp_table.add_row('Score', f"{d.get('old_score')}/5", f"{d.get('new_score')}/1")
    comp_table.add_row('Reasonableness', f"{old_eval.get('reasonableness_score', 'N/A')}/5", f"{new_eval.get('reasonableness_score', 'N/A')}/1")
    comp_table.add_row('Consistency', f"{old_eval.get('consistency_score', 'N/A')}/5", f"{new_eval.get('consistency_score', 'N/A')}/1")
    comp_table.add_row('Range', f"{old_eval.get('range_score', 'N/A')}/5", f"{new_eval.get('range_score', 'N/A')}/1")
    comp_table.add_row('Category', f"{old_eval.get('category_score', 'N/A')}/5", f"{new_eval.get('category_score', 'N/A')}/1")
    
    console.print(comp_table)
    console.print()
    
    # Reasoning side by side
    console.print('[bold]Reasoning Comparison:[/bold]')
    console.print()
    
    old_reasoning = old_eval.get('reasoning', 'N/A')
    new_reasoning = new_eval.get('reasoning', 'N/A')
    
    # Display full reasoning in panels
    console.print(Panel(
        f'[bold yellow]Old System Reasoning (Score {d.get("old_score")}/5):[/bold yellow]\n\n{old_reasoning}',
        border_style='yellow',
        title='Old Evaluation'
    ))
    console.print()
    
    console.print(Panel(
        f'[bold green]New System Reasoning (Score {d.get("new_score")}/1):[/bold green]\n\n{new_reasoning}',
        border_style='green',
        title='New Evaluation'
    ))
    console.print()
    console.print('[dim]' + '='*100 + '[/dim]')
    console.print()

# Display new stricter cases
console.print('[bold yellow]Cases Where New System Is Stricter (Old Good → New Poor):[/bold yellow]')
console.print()

for i, d in enumerate(new_stricter, 1):
    idx = d.get('index', 0)
    
    # Get task from dataset
    if idx < len(test_prompts):
        task_data = test_prompts[idx]
        task = task_data.get('prompt', 'Unknown task')
    else:
        task = 'Unknown task'
    
    # Try to get estimate from samples first
    old_sample = old_samples[idx] if idx < len(old_samples) else {}
    new_sample = new_samples[idx] if idx < len(new_samples) else {}
    
    estimate = old_sample.get('estimate', new_sample.get('estimate', {}))
    
    # If estimate is empty, try to find it by matching task in samples
    if not estimate or estimate == {}:
        # Search through all samples to find matching task
        for sample in old_samples + new_samples:
            if sample.get('task', '') == task:
                estimate = sample.get('estimate', {})
                break
        else:
            estimate = {'estimated_minutes': 'N/A', 'estimate_range': {}, 'explanation': 'Estimate not in debug samples', 'category': 'N/A'}
    
    old_eval = d.get('old_evaluation', {})
    new_eval = d.get('new_evaluation', {})
    
    console.print(f'[bold]Case {i}: Old Score {d.get("old_score")}/5 → New Score {d.get("new_score")}[/bold]')
    console.print()
    
    # Task and estimate
    task_display = task[:200] + "..." if len(task) > 200 else task
    console.print(f'[cyan]Task:[/cyan] {task_display}')
    console.print()
    
    # Try to get estimate from the estimate dict first
    est_min = estimate.get('estimated_minutes', None)
    est_range = estimate.get('estimate_range', {})
    opt = est_range.get('optimistic', None)
    real = est_range.get('realistic', est_min)
    pess = est_range.get('pessimistic', None)
    explanation = estimate.get('explanation', 'N/A')
    category = estimate.get('category', None)
    
    # If estimate not found, extract from reasoning
    if est_min is None or est_min == 'N/A':
        old_reasoning = old_eval.get('reasoning', '')
        new_reasoning = new_eval.get('reasoning', '')
        
        # Try to extract from both reasonings
        old_info = extract_estimate_from_reasoning(old_reasoning)
        new_info = extract_estimate_from_reasoning(new_reasoning)
        
        # Prefer new info, fall back to old
        est_min = new_info.get('estimated_minutes') or old_info.get('estimated_minutes') or 'N/A'
        if est_min != 'N/A':
            range_str = new_info.get('range') or old_info.get('range')
            if range_str:
                console.print(f'[cyan]Estimate:[/cyan] {est_min} min [dim](extracted from reasoning)[/dim]')
                console.print(f'[cyan]Range:[/cyan] {range_str} min [dim](extracted from reasoning)[/dim]')
            else:
                console.print(f'[cyan]Estimate:[/cyan] {est_min} min [dim](extracted from reasoning)[/dim]')
                console.print(f'[cyan]Range:[/cyan] Not specified in reasoning')
        else:
            console.print(f'[cyan]Estimate:[/cyan] Not found in reasoning')
            console.print(f'[cyan]Range:[/cyan] Not found in reasoning')
        
        category = new_info.get('category') or old_info.get('category') or category or 'N/A'
        console.print(f'[cyan]Category:[/cyan] {category}')
    else:
        console.print(f'[cyan]Estimate:[/cyan] {est_min} min')
        if opt and pess:
            console.print(f'[cyan]Range:[/cyan] {opt}-{real}-{pess} min')
        elif opt:
            console.print(f'[cyan]Range:[/cyan] {opt}-{real} min')
        else:
            console.print(f'[cyan]Range:[/cyan] Not specified')
        console.print(f'[cyan]Category:[/cyan] {category or "N/A"}')
    
    if explanation and explanation != 'N/A' and explanation != 'Estimate not in debug samples':
        expl_display = explanation[:300] + "..." if len(explanation) > 300 else explanation
        console.print(f'[cyan]Explanation:[/cyan] {expl_display}')
    console.print()
    
    # Side by side comparison
    comp_table = Table(box=box.ROUNDED, show_header=True)
    comp_table.add_column('Aspect', style='cyan', width=20)
    comp_table.add_column('Old System (1-5)', style='yellow', width=40)
    comp_table.add_column('New System (0-1)', style='red', width=40)
    
    comp_table.add_row('Score', f"{d.get('old_score')}/5", f"{d.get('new_score')}/1")
    comp_table.add_row('Reasonableness', f"{old_eval.get('reasonableness_score', 'N/A')}/5", f"{new_eval.get('reasonableness_score', 'N/A')}/1")
    comp_table.add_row('Consistency', f"{old_eval.get('consistency_score', 'N/A')}/5", f"{new_eval.get('consistency_score', 'N/A')}/1")
    comp_table.add_row('Range', f"{old_eval.get('range_score', 'N/A')}/5", f"{new_eval.get('range_score', 'N/A')}/1")
    comp_table.add_row('Category', f"{old_eval.get('category_score', 'N/A')}/5", f"{new_eval.get('category_score', 'N/A')}/1")
    
    console.print(comp_table)
    console.print()
    
    # Reasoning side by side
    console.print('[bold]Reasoning Comparison:[/bold]')
    console.print()
    
    old_reasoning = old_eval.get('reasoning', 'N/A')
    new_reasoning = new_eval.get('reasoning', 'N/A')
    
    # Display full reasoning in panels
    console.print(Panel(
        f'[bold yellow]Old System Reasoning (Score {d.get("old_score")}/5):[/bold yellow]\n\n{old_reasoning}',
        border_style='yellow',
        title='Old Evaluation'
    ))
    console.print()
    
    console.print(Panel(
        f'[bold red]New System Reasoning (Score {d.get("new_score")}/1):[/bold red]\n\n{new_reasoning}',
        border_style='red',
        title='New Evaluation'
    ))
    console.print()
    console.print('[dim]' + '='*100 + '[/dim]')
    console.print()


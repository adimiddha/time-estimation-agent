#!/usr/bin/env python3
"""
Analyze existing human evaluations and compare to AI binary scores.
Use this if you've already collected human evaluations.
"""

import json
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# Import Cohen's kappa calculation
from time_calibration_agent.quality_analysis import calculate_cohens_kappa


def load_human_evaluations(human_file: str) -> list:
    """Load human evaluations from JSON file."""
    with open(human_file, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "evaluations" in data:
        return data["evaluations"]
    else:
        raise ValueError("Unexpected format in human evaluations file")


def load_ai_evaluations(ai_file: str) -> dict:
    """Load AI evaluations and create a lookup by task."""
    with open(ai_file, 'r') as f:
        data = json.load(f)
    
    samples = data.get('samples', [])
    
    # Create lookup by task description
    lookup = {}
    for sample in samples:
        task = sample.get('task', '')
        eval_data = sample.get('evaluation', {})
        lookup[task] = {
            'ai_score': eval_data.get('score', None),
            'ai_reasoning': eval_data.get('reasoning', ''),
            'estimate': sample.get('estimate', {})
        }
    
    return lookup


def match_human_to_ai(human_evals: list, ai_lookup: dict) -> list:
    """Match human evaluations to AI scores by task description."""
    matched = []
    
    for human_eval in human_evals:
        task = human_eval.get('task', human_eval.get('task_description', ''))
        
        if task in ai_lookup:
            matched.append({
                'task': task,
                'human_score': human_eval.get('rating', human_eval.get('human_score')),
                'ai_score': ai_lookup[task]['ai_score'],
                'ai_reasoning': ai_lookup[task]['ai_reasoning'],
                'estimate': ai_lookup[task]['estimate'],
                'notes': human_eval.get('notes')
            })
        else:
            console.print(f"[yellow]Warning: Could not find AI evaluation for task: {task[:50]}...[/yellow]")
    
    return matched


def compare_human_ai(matched: list) -> dict:
    """Compare human and AI scores."""
    if not matched:
        return {"error": "No matched evaluations"}
    
    human_scores = [m['human_score'] for m in matched]
    ai_scores = [m['ai_score'] for m in matched]
    
    # Filter out None values
    valid_pairs = [(h, a) for h, a in zip(human_scores, ai_scores) if h is not None and a is not None]
    
    if not valid_pairs:
        return {"error": "No valid score pairs found"}
    
    human_scores_valid = [h for h, a in valid_pairs]
    ai_scores_valid = [a for h, a in valid_pairs]
    
    # Calculate agreement
    agreements = sum(1 for h, a in valid_pairs if h == a)
    agreement_pct = (agreements / len(valid_pairs)) * 100
    
    # Calculate Cohen's kappa
    kappa = calculate_cohens_kappa(human_scores_valid, ai_scores_valid)
    
    # Confusion matrix
    both_0 = sum(1 for h, a in valid_pairs if h == 0 and a == 0)
    both_1 = sum(1 for h, a in valid_pairs if h == 1 and a == 1)
    human_0_ai_1 = sum(1 for h, a in valid_pairs if h == 0 and a == 1)
    human_1_ai_0 = sum(1 for h, a in valid_pairs if h == 1 and a == 0)
    
    # Score distributions
    human_good = sum(1 for s in human_scores_valid if s == 1)
    ai_good = sum(1 for s in ai_scores_valid if s == 1)
    
    return {
        "total_comparisons": len(valid_pairs),
        "agreement_count": agreements,
        "agreement_percentage": agreement_pct,
        "cohens_kappa": kappa,
        "confusion_matrix": {
            "both_0": both_0,
            "both_1": both_1,
            "human_0_ai_1": human_0_ai_1,
            "human_1_ai_0": human_1_ai_0
        },
        "score_distributions": {
            "human_good": human_good,
            "human_poor": len(valid_pairs) - human_good,
            "ai_good": ai_good,
            "ai_poor": len(valid_pairs) - ai_good
        }
    }


def display_comparison_results(comparison: dict):
    """Display comparison results."""
    if "error" in comparison:
        console.print(f"[red]Error: {comparison['error']}[/red]")
        return
    
    console.print(Panel.fit(
        '[bold cyan]📊 Human-AI Comparison Results[/bold cyan]',
        border_style='cyan'
    ))
    console.print()
    
    # Main metrics table
    metrics_table = Table(box=box.ROUNDED, show_header=True, title='Agreement Metrics')
    metrics_table.add_column('Metric', style='cyan', width=30)
    metrics_table.add_column('Value', justify='right')
    
    metrics_table.add_row('Total Comparisons', str(comparison['total_comparisons']))
    metrics_table.add_row('Agreements', f"{comparison['agreement_count']}")
    metrics_table.add_row('Agreement Percentage', f"[bold]{comparison['agreement_percentage']:.1f}%[/bold]")
    metrics_table.add_row("Cohen's Kappa", f"[bold]{comparison['cohens_kappa']:.3f}[/bold]")
    
    # Kappa interpretation
    kappa = comparison['cohens_kappa']
    kappa_interpretation = {
        (0.81, 1.0): "Almost perfect agreement",
        (0.61, 0.80): "Substantial agreement",
        (0.41, 0.60): "Moderate agreement",
        (0.21, 0.40): "Fair agreement",
        (0.0, 0.20): "Slight agreement",
        (-1.0, 0.0): "Poor agreement"
    }
    
    interpretation = "Unknown"
    for (low, high), desc in kappa_interpretation.items():
        if low <= kappa <= high:
            interpretation = desc
            break
    
    metrics_table.add_row('Kappa Interpretation', interpretation)
    comparison['kappa_interpretation'] = interpretation
    
    console.print(metrics_table)
    console.print()
    
    # Confusion matrix
    cm = comparison['confusion_matrix']
    cm_table = Table(box=box.ROUNDED, show_header=True, title='Confusion Matrix')
    cm_table.add_column('', style='dim', width=20)
    cm_table.add_column('AI: Poor (0)', justify='right', width=15)
    cm_table.add_column('AI: Good (1)', justify='right', width=15)
    
    cm_table.add_row('Human: Poor (0)', str(cm['both_0']), str(cm['human_0_ai_1']))
    cm_table.add_row('Human: Good (1)', str(cm['human_1_ai_0']), str(cm['both_1']))
    
    console.print(cm_table)
    console.print()
    
    # Score distributions
    dist = comparison['score_distributions']
    dist_table = Table(box=box.ROUNDED, show_header=True, title='Score Distributions')
    dist_table.add_column('Evaluator', style='cyan', width=20)
    dist_table.add_column('Good (1)', justify='right', style='green')
    dist_table.add_column('Poor (0)', justify='right', style='red')
    dist_table.add_column('Good %', justify='right')
    
    human_good_pct = (dist['human_good'] / comparison['total_comparisons']) * 100
    ai_good_pct = (dist['ai_good'] / comparison['total_comparisons']) * 100
    
    dist_table.add_row('Human', str(dist['human_good']), str(dist['human_poor']), f"{human_good_pct:.1f}%")
    dist_table.add_row('AI', str(dist['ai_good']), str(dist['ai_poor']), f"{ai_good_pct:.1f}%")
    
    console.print(dist_table)
    console.print()
    
    return comparison


def main():
    """Main function."""
    if len(sys.argv) < 3:
        console.print("[red]Usage: python analyze_human_ai_comparison.py <human_eval_file> <ai_eval_file>[/red]")
        console.print("[dim]Example: python analyze_human_ai_comparison.py human_evaluations.json quality_eval_debug_0-1_strict_test1.json[/dim]")
        sys.exit(1)
    
    human_file = sys.argv[1]
    ai_file = sys.argv[2]
    
    # Load files
    console.print(f"[cyan]Loading human evaluations from: {human_file}[/cyan]")
    try:
        human_evals = load_human_evaluations(human_file)
        console.print(f"[green]✅ Loaded {len(human_evals)} human evaluations[/green]\n")
    except Exception as e:
        console.print(f"[red]Error loading human evaluations: {e}[/red]")
        sys.exit(1)
    
    console.print(f"[cyan]Loading AI evaluations from: {ai_file}[/cyan]")
    try:
        ai_lookup = load_ai_evaluations(ai_file)
        console.print(f"[green]✅ Loaded {len(ai_lookup)} AI evaluations[/green]\n")
    except Exception as e:
        console.print(f"[red]Error loading AI evaluations: {e}[/red]")
        sys.exit(1)
    
    # Match human to AI
    matched = match_human_to_ai(human_evals, ai_lookup)
    console.print(f"[cyan]Matched {len(matched)} evaluations[/cyan]\n")
    
    if not matched:
        console.print("[red]No matched evaluations found. Exiting.[/red]")
        sys.exit(1)
    
    # Compare
    comparison = compare_human_ai(matched)
    display_comparison_results(comparison)
    
    # Save results
    output_file = "eval/results/human_ai_comparison.json"
    with open(output_file, 'w') as f:
        json.dump(comparison, f, indent=2)

    console.print(f"[green]✅ Comparison results saved to {output_file}[/green]\n")
    
    # Summary for resume
    kappa_interp = comparison.get('kappa_interpretation', 'N/A')
    console.print(Panel(
        f"[bold]📝 Resume Metric Summary:[/bold]\n\n"
        f"Human-AI Agreement: [bold]{comparison['agreement_percentage']:.1f}%[/bold]\n"
        f"Cohen's Kappa: [bold]{comparison['cohens_kappa']:.3f}[/bold] ({kappa_interp})\n"
        f"Total Evaluations: {comparison['total_comparisons']}",
        border_style='green',
        title='[bold]For Your Resume[/bold]'
    ))


if __name__ == "__main__":
    main()



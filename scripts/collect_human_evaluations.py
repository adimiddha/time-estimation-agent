#!/usr/bin/env python3
"""
Collect human evaluations on a subset of tasks and compare to AI binary scores.
"""

import json
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from typing import List, Dict, Optional
import random

console = Console()

# Import Cohen's kappa calculation
from time_calibration_agent.quality_analysis import calculate_cohens_kappa


def load_ai_evaluations(file_path: str) -> List[Dict]:
    """Load AI binary evaluations from JSON file."""
    with open(file_path, 'r') as f:
        data = json.load(f)

    samples = data.get('samples', [])
    return samples


def select_subset(samples: List[Dict], n: int = 25, seed: Optional[int] = None) -> List[Dict]:
    """
    Select a random subset of samples for human evaluation.
    
    Args:
        samples: All samples
        n: Number of samples to select
        seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)
    
    if len(samples) <= n:
        return samples
    
    return random.sample(samples, n)


def format_estimate_display(estimate: Dict) -> str:
    """Format estimate for display."""
    est_min = estimate.get('estimated_minutes', 'N/A')
    est_range = estimate.get('estimate_range', {})
    opt = est_range.get('optimistic', None)
    real = est_range.get('realistic', est_min)
    pess = est_range.get('pessimistic', None)
    explanation = estimate.get('explanation', 'N/A')
    category = estimate.get('category', 'N/A')
    ambiguity = estimate.get('ambiguity', 'N/A')
    
    lines = [
        f"[cyan]Estimated Time:[/cyan] {est_min} minutes",
    ]
    
    if opt and pess:
        lines.append(f"[cyan]Range:[/cyan] {opt} (optimistic) - {real} (realistic) - {pess} (pessimistic) minutes")
    elif opt:
        lines.append(f"[cyan]Range:[/cyan] {opt} - {real} minutes")
    
    lines.append(f"[cyan]Category:[/cyan] {category}")
    lines.append(f"[cyan]Ambiguity:[/cyan] {ambiguity}")
    lines.append(f"[cyan]Explanation:[/cyan] {explanation}")
    
    return "\n".join(lines)


def get_evaluation_criteria() -> str:
    """Get the AI evaluation criteria to display to human evaluators."""
    return """
[bold cyan]BINARY SCORING CRITERIA (0 = Poor, 1 = Good):[/bold cyan]

[bold]Score 1 (Good Quality) - ALL of the following must be STRICTLY true:[/bold]
  ✓ The number is reasonable AND well-justified with specific reasoning
  ✓ The explanation is THOROUGH (not brief or superficial) - addresses MULTIPLE relevant factors
  ✓ The explanation demonstrates DEEP understanding - not just surface-level acknowledgment
  ✓ The range is appropriate AND the explanation clearly justifies why the range is what it is
  ✓ The category is correct
  ✓ Everything is consistent and aligned
  ✓ The estimate adequately addresses task ambiguity/complexity with sufficient detail

[bold yellow]CRITICAL:[/bold yellow] If the explanation is brief, lacks detail, doesn't address multiple 
factors, or feels superficial → score 0. If you find yourself saying "could be more thorough" 
or "lacks depth" → score 0. Only score 1 if the explanation is genuinely thorough and 
demonstrates deep understanding.

[bold]Score 0 (Poor Quality) - Score 0 if ANY of the following:[/bold]
  ✗ The number is unreasonable or poorly justified
  ✗ The explanation is brief, superficial, or lacks sufficient detail
  ✗ The explanation doesn't address multiple relevant factors
  ✗ The explanation doesn't demonstrate deep understanding of the task
  ✗ The range is inappropriate (too narrow/wide) or not well-explained
  ✗ The category is wrong
  ✗ There are inconsistencies or misalignments
  ✗ The estimate doesn't adequately acknowledge task ambiguity/complexity
  ✗ The explanation could be described as "lacking depth" or "could be more thorough"
  ✗ There are noticeable problems that affect reliability

[bold]Evaluation Dimensions:[/bold]
1. [bold]Reasonableness:[/bold] Is the number reasonable? Is the explanation thorough and detailed?
2. [bold]Consistency:[/bold] Does explanation justify the number? Does it account for the range? Is it internally consistent?
3. [bold]Range:[/bold] Is the range appropriate? (Not too narrow/wide for the task type)
4. [bold]Category:[/bold] Does the category match the task?
5. [bold]Overall:[/bold] Score 1 ONLY if ALL dimensions are GOOD. Score 0 if ANY dimension has problems.

[dim]Key Question: Is this GOOD quality (1) or does it have noticeable problems (0)?[/dim]
[dim]Remember: "Acceptable but has noticeable problems" = Score 0. Only "Good quality" = Score 1.[/dim]
"""


def collect_human_evaluation(sample: Dict, index: int, total: int, show_criteria: bool = True) -> Optional[Dict]:
    """
    Collect a single human evaluation.
    
    Returns:
        Dict with evaluation or None if skipped
    """
    task = sample.get('task', 'Unknown task')
    estimate = sample.get('estimate', {})
    ai_eval = sample.get('evaluation', {})
    ai_score = ai_eval.get('score', 'N/A')
    
    console.print(Panel.fit(
        f'[bold cyan]Task {index + 1} of {total}[/bold cyan]',
        border_style='cyan'
    ))
    console.print()
    
    # Show evaluation criteria (first time or if requested)
    if show_criteria and index == 0:
        console.print(Panel(
            get_evaluation_criteria(),
            border_style='yellow',
            title='[bold]Evaluation Criteria[/bold]'
        ))
        console.print()
    
    # Show task
    console.print('[bold]Task Description:[/bold]')
    console.print(Panel(task, border_style='blue'))
    console.print()
    
    # Show estimate
    console.print('[bold]Estimate:[/bold]')
    console.print(Panel(format_estimate_display(estimate), border_style='yellow'))
    console.print()
    
    # Get human rating
    while True:
        try:
            rating_input = console.input(
                "[yellow]Your Rating (0 = Poor Quality, 1 = Good Quality, 'skip' to skip, 'criteria' to see criteria again): [/yellow]"
            ).strip().lower()
            
            if rating_input == 'skip':
                console.print("[dim]Skipped[/dim]\n")
                return None
            
            if rating_input == 'criteria':
                console.print()
                console.print(Panel(
                    get_evaluation_criteria(),
                    border_style='yellow',
                    title='[bold]Evaluation Criteria[/bold]'
                ))
                console.print()
                continue
            
            rating = int(rating_input)
            if rating == 0 or rating == 1:
                notes = console.input(
                    "[dim]Optional notes (press Enter to skip): [/dim]"
                ).strip()
                
                rating_label = "Good Quality" if rating == 1 else "Poor Quality"
                console.print(f"[green]✅ Rated {rating} ({rating_label})[/green]\n")
                console.print('[dim]' + '='*80 + '[/dim]\n')
                
                return {
                    "task": task,
                    "estimate": estimate,
                    "human_score": rating,
                    "ai_score": ai_score,
                    "notes": notes if notes else None,
                    "sample_index": index
                }
            else:
                console.print("[red]Please enter 0 (poor quality) or 1 (good quality)[/red]")
        except ValueError:
            console.print("[red]Please enter a valid number (0 or 1), 'skip', or 'criteria'[/red]")


def save_human_evaluations(evaluations: List[Dict], output_path: str, source_file: str):
    """Save human evaluations to file."""
    data = {
        "source_ai_file": source_file,
        "total_evaluations": len(evaluations),
        "evaluations": evaluations,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    console.print(f"[green]✅ Saved {len(evaluations)} evaluation(s) to {output_path}[/green]\n")


def compare_human_ai(evaluations: List[Dict]) -> Dict:
    """
    Compare human evaluations to AI scores.
    
    Returns:
        Dict with comparison metrics
    """
    if not evaluations:
        return {"error": "No evaluations to compare"}
    
    human_scores = [e['human_score'] for e in evaluations]
    ai_scores = [e['ai_score'] for e in evaluations]
    
    # Calculate agreement
    agreements = sum(1 for h, a in zip(human_scores, ai_scores) if h == a)
    agreement_pct = (agreements / len(evaluations)) * 100
    
    # Calculate Cohen's kappa
    kappa = calculate_cohens_kappa(human_scores, ai_scores)
    
    # Confusion matrix
    both_0 = sum(1 for h, a in zip(human_scores, ai_scores) if h == 0 and a == 0)
    both_1 = sum(1 for h, a in zip(human_scores, ai_scores) if h == 1 and a == 1)
    human_0_ai_1 = sum(1 for h, a in zip(human_scores, ai_scores) if h == 0 and a == 1)
    human_1_ai_0 = sum(1 for h, a in zip(human_scores, ai_scores) if h == 1 and a == 0)
    
    # Score distributions
    human_good = sum(1 for s in human_scores if s == 1)
    ai_good = sum(1 for s in ai_scores if s == 1)
    
    return {
        "total_comparisons": len(evaluations),
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
            "human_poor": len(evaluations) - human_good,
            "ai_good": ai_good,
            "ai_poor": len(evaluations) - ai_good
        }
    }


def display_comparison_results(comparison: Dict):
    """Display comparison results in a nice format."""
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
    comparison['kappa_interpretation'] = interpretation  # Store for later use
    
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


def main():
    """Main function to collect human evaluations and compare to AI."""
    # Get command line arguments
    if len(sys.argv) < 2:
        console.print("[red]Usage: python collect_human_evaluations.py <ai_eval_file> [--subset N] [--seed SEED][/red]")
        console.print("[dim]Example: python collect_human_evaluations.py quality_eval_debug_0-1_strict_test1.json --subset 25[/dim]")
        sys.exit(1)
    
    ai_file = sys.argv[1]
    subset_size = 25
    seed = None
    
    # Parse optional arguments
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--subset' and i + 1 < len(sys.argv):
            subset_size = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--seed' and i + 1 < len(sys.argv):
            seed = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1
    
    # Load AI evaluations
    console.print(f"[cyan]Loading AI evaluations from: {ai_file}[/cyan]")
    try:
        samples = load_ai_evaluations(ai_file)
        console.print(f"[green]✅ Loaded {len(samples)} samples[/green]\n")
    except Exception as e:
        console.print(f"[red]Error loading file: {e}[/red]")
        sys.exit(1)
    
    # Select subset
    subset = select_subset(samples, n=subset_size, seed=seed)
    console.print(f"[cyan]Selected {len(subset)} samples for evaluation[/cyan]\n")
    
    # Collect human evaluations
    console.print(Panel.fit(
        '[bold yellow]👤 HUMAN EVALUATION[/bold yellow]\n'
        '[dim]Rate each estimate as 0 (Poor Quality) or 1 (Good Quality)[/dim]\n'
        '[dim]Evaluation criteria will be shown before the first task[/dim]',
        border_style='yellow'
    ))
    console.print()
    
    evaluations = []
    for i, sample in enumerate(subset):
        eval_result = collect_human_evaluation(sample, i, len(subset), show_criteria=(i == 0))
        if eval_result is not None:
            evaluations.append(eval_result)
    
    if not evaluations:
        console.print("[yellow]No evaluations collected. Exiting.[/yellow]")
        sys.exit(0)
    
    # Save evaluations
    output_file = "eval/results/human_evaluations.json"
    save_human_evaluations(evaluations, output_file, ai_file)

    # Compare human vs AI
    console.print()
    comparison = compare_human_ai(evaluations)
    display_comparison_results(comparison)

    # Save comparison results
    comparison_file = "eval/results/human_ai_comparison.json"
    with open(comparison_file, 'w') as f:
        json.dump(comparison, f, indent=2)
    
    console.print(f"[green]✅ Comparison results saved to {comparison_file}[/green]\n")
    
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


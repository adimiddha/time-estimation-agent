#!/usr/bin/env python3
"""Generate final comprehensive summary of all evaluations and comparisons."""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

datasets = ['test_1', 'test_2', 'test_3', 'test_4']

console.print(Panel.fit('[bold cyan]📊 COMPREHENSIVE EVALUATION SUMMARY[/bold cyan]', border_style='cyan'))
console.print()

# Main summary table
main_table = Table(box=box.ROUNDED, show_header=True, title='All Datasets - Evaluation Results')
main_table.add_column('Dataset', style='cyan', width=10)
main_table.add_column('Binary (0-1)', justify='center', width=25)
main_table.add_column('Five-Point (1-5)', justify='center', width=25)
main_table.add_column('Agreement', justify='right', width=12)
main_table.add_column('Kappa', justify='right', width=10)
main_table.add_column('Disagreements', justify='right', width=12)

all_results = []

for dataset in datasets:
    # Handle test_1 vs test1 naming
    dataset_name = dataset.replace('_', '')
    bin_file = f'quality_eval_debug_0-1_{dataset_name}.json'
    fp_file = f'quality_eval_debug_1-5_{dataset_name}.json'
    comp_file = f'scoring_comparison_{dataset_name}.json'
    
    # Check if files exist, try alternative naming
    if not Path(bin_file).exists():
        bin_file = f'quality_eval_debug_0-1_{dataset}.json'
    if not Path(fp_file).exists():
        fp_file = f'quality_eval_debug_1-5_{dataset}.json'
    if not Path(comp_file).exists():
        comp_file = f'scoring_comparison_{dataset}.json'
    
    # Load binary results
    with open(bin_file) as f:
        bin_data = json.load(f)
    bin_evals = bin_data.get('all_evaluations', [])
    bin_scores = [e.get('score', 0) for e in bin_evals]
    bin_avg = sum(bin_scores) / len(bin_scores) if bin_scores else 0
    bin_good = sum(1 for s in bin_scores if s == 1)
    bin_pct = (bin_good / len(bin_scores)) * 100 if bin_scores else 0
    
    # Load five-point results
    with open(fp_file) as f:
        fp_data = json.load(f)
    fp_evals = fp_data.get('all_evaluations', [])
    fp_scores = [e.get('score', 0) for e in fp_evals]
    fp_avg = sum(fp_scores) / len(fp_scores) if fp_scores else 0
    fp_good = sum(1 for s in fp_scores if s >= 4)
    fp_pct = (fp_good / len(fp_scores)) * 100 if fp_scores else 0
    
    # Load comparison results
    agreement = 0
    kappa = 0
    disagreements = 0
    
    # Try both naming conventions
    comp_files = [comp_file, f'scoring_comparison_{dataset}.json']
    for cf in comp_files:
        if Path(cf).exists():
            try:
                with open(cf) as f:
                    comp_data = json.load(f)
                agreement = comp_data.get('agreement_between_systems', 0)
                kappa = comp_data.get('cohens_kappa', 0)
                # Try different paths for disagreements
                if 'summary' in comp_data:
                    disagreements = comp_data['summary'].get('total_disagreements', 0)
                elif 'total_disagreements' in comp_data:
                    disagreements = comp_data['total_disagreements']
                break
            except:
                continue
    
    main_table.add_row(
        dataset,
        f'{bin_avg:.2f} ({bin_good}/{len(bin_scores)} = {bin_pct:.1f}%)',
        f'{fp_avg:.2f}/5 ({fp_good}/{len(fp_scores)} = {fp_pct:.1f}%)',
        f'{agreement:.1f}%' if agreement > 0 else 'N/A',
        f'{kappa:.3f}' if kappa != 0 else 'N/A',
        str(disagreements) if disagreements > 0 else 'N/A'
    )
    
    all_results.append({
        'dataset': dataset,
        'binary': {'avg': bin_avg, 'good': bin_good, 'total': len(bin_scores), 'pct': bin_pct},
        'five_point': {'avg': fp_avg, 'good': fp_good, 'total': len(fp_scores), 'pct': fp_pct},
        'agreement': agreement,
        'kappa': kappa,
        'disagreements': disagreements
    })

console.print(main_table)
console.print()

# Overall statistics
console.print('[bold]Overall Statistics Across All Datasets:[/bold]')
console.print()

total_bin = sum(r['binary']['total'] for r in all_results)
total_fp = sum(r['five_point']['total'] for r in all_results)
total_bin_good = sum(r['binary']['good'] for r in all_results)
total_fp_good = sum(r['five_point']['good'] for r in all_results)
overall_bin_avg = sum(r['binary']['avg'] * r['binary']['total'] for r in all_results) / total_bin if total_bin > 0 else 0
overall_fp_avg = sum(r['five_point']['avg'] * r['five_point']['total'] for r in all_results) / total_fp if total_fp > 0 else 0

stats_table = Table.grid(padding=(0, 2))
stats_table.add_column(style='dim', width=30)
stats_table.add_column()

stats_table.add_row('Total Tasks Evaluated:', f'{total_bin} (binary) / {total_fp} (five-point)')
stats_table.add_row('Overall Binary Average:', f'{overall_bin_avg:.2f}')
stats_table.add_row('Overall Five-Point Average:', f'{overall_fp_avg:.2f}/5')
stats_table.add_row('Overall Good Quality (Binary):', f'{total_bin_good}/{total_bin} ({total_bin_good/total_bin*100:.1f}%)')
stats_table.add_row('Overall Good Quality (Five-Point):', f'{total_fp_good}/{total_fp} ({total_fp_good/total_fp*100:.1f}%)')

console.print(Panel(stats_table, title='[bold]Summary[/bold]', border_style='blue'))
console.print()

# Show comparison details
console.print('[bold]Comparison Details by Dataset:[/bold]')
console.print()

for result in all_results:
    if result['agreement'] > 0:
        console.print(f"[bold]{result['dataset']}:[/bold]")
        console.print(f"  Agreement: {result['agreement']:.1f}%")
        console.print(f"  Cohen's Kappa: {result['kappa']:.3f}")
        console.print(f"  Disagreements: {result['disagreements']}")
        console.print()

console.print('[bold]✅ All evaluations and comparisons complete![/bold]')
console.print()
console.print('[bold]Files generated:[/bold]')
console.print('  • quality_eval_debug_0-1_test*.json (binary evaluations)')
console.print('  • quality_eval_debug_1-5_test*.json (five-point evaluations)')
console.print('  • scoring_comparison_test*.json (comparison results)')
console.print('  • scoring_disagreements_analysis.json (latest disagreement analysis)')
console.print()
console.print('[bold]To view disagreements for a specific dataset:[/bold]')
console.print('  python show_disagreements.py  # (modify script to use different dataset)')


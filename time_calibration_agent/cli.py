"""
Command-line interface for the Time Calibration Agent.
"""

import sys
import json
from datetime import datetime
from typing import List, Optional, Dict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich.markdown import Markdown
from rich import box
from time_calibration_agent.storage import TaskStorage
from time_calibration_agent.agent import EstimationAgent, validate_and_normalize_category
from time_calibration_agent.learning import CalibrationLearner
from time_calibration_agent.evaluation import EvaluationMetrics
from time_calibration_agent.experiments import ContextExperiment
from time_calibration_agent.quality_evaluation import QualityEvaluator, HumanEvaluator
from time_calibration_agent.test_dataset import TestDatasetGenerator
from time_calibration_agent.quality_analysis import (
    analyze_score_patterns,
    identify_common_issues,
    analyze_by_dimension,
    correlate_estimate_features,
    generate_recommendations
)
from time_calibration_agent.replanner import ReplanningAgent
from time_calibration_agent.session_store import DaySessionStore


class TimeCalibrationCLI:
    """CLI interface for interacting with the calibration agent."""
    
    def __init__(self, data_file: str = "calibration_data.json"):
        self.storage = TaskStorage(data_file)
        self.agent = EstimationAgent()
        self.learner = CalibrationLearner()
        self.console = Console()
        self.replanner = ReplanningAgent()
        self.session_store = DaySessionStore()
    
    def estimate_tasks(self, task_descriptions: List[str]):
        """Estimate durations for one or more tasks."""
        calibration = self.storage.get_calibration_data()
        completed_tasks = self.storage.get_completed_tasks()
        all_tasks = self.storage.get_all_tasks()  # Get all tasks for category consistency
        
        # Get recent similar tasks for context
        historical_context = completed_tasks[-10:] if completed_tasks else []
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]⏱️  TIME ESTIMATION[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        task_ids = []
        
        for i, description in enumerate(task_descriptions, 1):
            # Check for similar completed tasks first
            similar_task_match = self.agent.find_similar_completed_task(
                description, completed_tasks
            )
            
            if similar_task_match and similar_task_match.get('confidence') == 'high':
                # Use actual time from similar task as the estimate
                matched_task = similar_task_match['task']
                actual_time = matched_task['actual_minutes']
                
                # Create estimate based on previous actual time
                # Use the actual time as the realistic estimate, with a small range
                # Normalize category to ensure consistency
                matched_category = matched_task.get('category', 'general')
                normalized_category = validate_and_normalize_category(matched_category)
                
                estimate = {
                    "estimated_minutes": actual_time,
                    "estimate_range": {
                        "optimistic": max(1, int(actual_time * 0.8)),
                        "realistic": actual_time,
                        "pessimistic": int(actual_time * 1.2)
                    },
                    "explanation": f"Based on previous completion: '{matched_task['description'][:50]}' took {actual_time} minutes. Using that as the estimate.",
                    "category": normalized_category,
                    "ambiguity": matched_task.get('ambiguity', 'clear'),
                    "from_similar_task": True
                }
                calibrated_estimate = estimate
            else:
                # Show progress
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=self.console,
                    transient=True
                ) as progress:
                    task_progress = progress.add_task(
                        f"[cyan]Analyzing task {i}/{len(task_descriptions)}...",
                        total=None
                    )
                    
                    # Check for category from similar tasks for consistency
                    suggested_category = self.agent.find_category_for_task(description, all_tasks)
                    
                    # Get initial estimate from agent
                    estimate = self.agent.estimate_task(
                        description,
                        calibration_context=calibration,
                        historical_tasks=historical_context,
                        suggested_category=suggested_category
                    )
                    
                    # Check if agent cannot estimate due to vague task
                    if estimate.get('cannot_estimate', False):
                        # Display refusal message
                        self.console.print()
                        self.console.print(Panel(
                            f"[bold yellow]⚠️  Cannot Estimate[/bold yellow]\n\n"
                            f"[dim]Task:[/dim] {description}\n\n"
                            f"[yellow]{estimate.get('explanation', 'The task description is too vague to provide a reliable time estimate.')}[/yellow]",
                            border_style="yellow",
                            title=f"[bold]Task {i}/{len(task_descriptions)}[/bold]"
                        ))
                        self.console.print()
                        # Skip storing this task - it's not a valid estimate
                        continue
                    
                    # Apply calibration adjustments
                    calibrated_estimate = self.learner.apply_calibration_to_estimate(
                        estimate, calibration
                    )
            
            # Store task with category and ambiguity
            task_id = self.storage.add_task(
                description,
                calibrated_estimate['estimated_minutes'],
                calibrated_estimate['estimate_range'],
                calibrated_estimate['explanation'],
                category=calibrated_estimate['category'],
                ambiguity=calibrated_estimate['ambiguity']
            )
            
            task_ids.append(task_id)
            
            # Create estimate table
            estimate_table = Table.grid(padding=(0, 2))
            estimate_table.add_column(style="dim", width=12)
            estimate_table.add_column()
            
            # Format time estimate
            minutes = calibrated_estimate['estimated_minutes']
            hours = minutes / 60
            if hours >= 1:
                time_str = f"[bold green]{minutes}[/bold green] min ([bold]{hours:.1f} hrs[/bold])"
            else:
                time_str = f"[bold green]{minutes}[/bold green] min"
            
            estimate_table.add_row("📊 Estimate:", time_str)
            
            # Format range
            opt = calibrated_estimate['estimate_range']['optimistic']
            pess = calibrated_estimate['estimate_range']['pessimistic']
            estimate_table.add_row("📈 Range:", f"[dim]{opt}[/dim] - [dim]{pess}[/dim] minutes")
            
            # Category with color
            category = calibrated_estimate['category']
            category_colors = {
                'coding': 'blue',
                'writing': 'magenta',
                'admin': 'yellow',
                'deep work': 'cyan',
                'social': 'green',
                'errands': 'yellow',
                'meetings': 'blue',
                'learning': 'cyan',
                'fitness': 'green',
                'general': 'white'
            }
            cat_color = category_colors.get(category, 'white')
            estimate_table.add_row("🏷️  Category:", f"[{cat_color}]{category}[/{cat_color}]")
            
            # Ambiguity
            ambiguity = calibrated_estimate['ambiguity']
            amb_colors = {'clear': 'green', 'moderate': 'yellow', 'fuzzy': 'red'}
            amb_color = amb_colors.get(ambiguity, 'white')
            estimate_table.add_row("🔍 Ambiguity:", f"[{amb_color}]{ambiguity}[/{amb_color}]")
            
            # Explanation
            explanation = calibrated_estimate['explanation']
            estimate_table.add_row("💡 Explanation:", f"[dim]{explanation}[/dim]")
            
            if calibrated_estimate.get('from_similar_task'):
                estimate_table.add_row("", "[dim italic]🔄 Using time from previous identical task[/dim italic]")
            elif calibrated_estimate.get('calibration_applied'):
                estimate_table.add_row("", "[dim italic]✨ Calibrated based on your history[/dim italic]")
            
            # Task ID
            estimate_table.add_row("", "")
            estimate_table.add_row("🆔 Task ID:", f"[dim]{task_id}[/dim]")
            
            # Display in panel
            self.console.print(Panel(
                estimate_table,
                title=f"[bold]Task {i}: {description[:50]}{'...' if len(description) > 50 else ''}[/bold]",
                border_style="blue",
                padding=(1, 2)
            ))
            self.console.print()
        
        # Summary
        self.console.print(Panel(
            f"[bold green]✅ {len(task_ids)} task(s) added[/bold green]\n"
            "[dim]Use the task IDs to log actual time later.[/dim]",
            border_style="green"
        ))
        self.console.print()
        
        return task_ids
    
    def find_task_by_query(self, query: str) -> Optional[str]:
        """
        Find a task using a natural language query.
        Returns task_id if found and confirmed, None otherwise.
        """
        # Get pending tasks (most likely what user wants to log)
        pending_tasks = self.storage.get_pending_tasks()
        
        if not pending_tasks:
            self.console.print("\n[red]❌ No pending tasks found.[/red]\n")
            return None
        
        # Try to match the query
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            progress.add_task("[cyan]Searching for matching task...", total=None)
            match_result = self.agent.match_task_query(query, pending_tasks)
        
        if not match_result:
            self.console.print(f"\n[red]❌ Could not match your query: '{query}'[/red]\n")
            
            # Show available tasks in a table
            task_table = Table(title="Available Pending Tasks", box=box.ROUNDED)
            task_table.add_column("ID", style="dim")
            task_table.add_column("Description")
            task_table.add_column("Estimate", justify="right")
            
            for task in pending_tasks:
                task_table.add_row(
                    task['id'],
                    task['description'][:50],
                    f"{task['estimated_minutes']} min"
                )
            
            self.console.print(task_table)
            self.console.print()
            return None
        
        matched_task = match_result['task']
        confidence = match_result['confidence']
        reasoning = match_result['reasoning']
        
        # Show the match in a panel
        match_table = Table.grid(padding=(0, 2))
        match_table.add_column(style="dim", width=12)
        match_table.add_column()
        
        match_table.add_row("🔍 Query:", f"[cyan]{query}[/cyan]")
        match_table.add_row("✅ Matched:", matched_task['description'])
        match_table.add_row("🏷️  Category:", matched_task.get('category', 'N/A'))
        match_table.add_row("⏱️  Estimated:", f"{matched_task['estimated_minutes']} minutes")
        
        # Confidence with color
        conf_colors = {'high': 'green', 'medium': 'yellow', 'low': 'red'}
        conf_color = conf_colors.get(confidence, 'white')
        match_table.add_row("🎯 Confidence:", f"[{conf_color}]{confidence}[/{conf_color}]")
        match_table.add_row("💭 Reasoning:", f"[dim]{reasoning}[/dim]")
        
        self.console.print()
        self.console.print(Panel(
            match_table,
            title="[bold]TASK MATCH[/bold]",
            border_style="cyan"
        ))
        self.console.print()
        
        # For high confidence, auto-confirm; otherwise ask
        if confidence == "high":
            self.console.print("[green]✅ High confidence match - proceeding...[/green]\n")
            return matched_task['id']
        else:
            response = self.console.input("[yellow]Is this the correct task?[/yellow] [dim](yes/no):[/dim] ").strip().lower()
            if response in ['yes', 'y', '']:
                return matched_task['id']
            else:
                self.console.print("[red]Match rejected. Please try a more specific query or use the task ID.[/red]\n")
                return None
    
    def log_time(self, task_identifier: str, actual_minutes: int):
        """
        Log actual time spent on a task.
        
        Args:
            task_identifier: Either a task_id or a natural language query
            actual_minutes: Actual time spent in minutes
        """
        try:
            # Check if it looks like a task_id (starts with "task_")
            if task_identifier.startswith("task_"):
                # Try to use it as a task_id first
                task = self.storage.get_task(task_identifier)
                if task:
                    task_id = task_identifier
                else:
                    # Task ID not found, try treating it as a query
                    self.console.print(f"[yellow]Task ID '{task_identifier}' not found. Trying as natural language query...[/yellow]")
                    task_id = self.find_task_by_query(task_identifier)
                    if not task_id:
                        return
            else:
                # It's a natural language query - try to match it
                task_id = self.find_task_by_query(task_identifier)
                if not task_id:
                    return
            
            self.storage.log_actual_time(task_id, actual_minutes)
            
            task = self.storage.get_task(task_id)
            if not task:
                self.console.print(f"[red]Error: Task {task_id} not found[/red]")
                return
            
            # Calculate error
            estimated = task['estimated_minutes']
            error_pct = ((actual_minutes - estimated) / estimated) * 100
            
            # Create comparison table
            comparison_table = Table.grid(padding=(0, 2))
            comparison_table.add_column(style="dim", width=12)
            comparison_table.add_column()
            
            comparison_table.add_row("📝 Task:", task['description'][:60])
            comparison_table.add_row("⏱️  Estimated:", f"[cyan]{estimated}[/cyan] minutes")
            comparison_table.add_row("✅ Actual:", f"[green]{actual_minutes}[/green] minutes")
            
            # Error with color
            if abs(error_pct) < 10:
                error_color = "green"
                error_emoji = "🎯"
            elif error_pct > 0:
                error_color = "red"
                error_emoji = "📈"
            else:
                error_color = "blue"
                error_emoji = "📉"
            
            comparison_table.add_row(
                f"{error_emoji} Error:",
                f"[{error_color}]{error_pct:+.1f}%[/{error_color}]"
            )
            
            self.console.print()
            self.console.print(Panel(
                comparison_table,
                title="[bold green]✅ Time Logged[/bold green]",
                border_style="green"
            ))
            
            # Update calibration
            self._update_calibration()
            
            self.console.print("\n[cyan]📈 Calibration updated based on this outcome.[/cyan]\n")
            
        except ValueError as e:
            self.console.print(f"[red]Error: {e}[/red]\n")
    
    def _update_calibration(self):
        """Update calibration based on all completed tasks."""
        completed_tasks = self.storage.get_completed_tasks()
        current_calibration = self.storage.get_calibration_data()
        
        updated_calibration = self.learner.update_calibration(
            completed_tasks,
            current_calibration
        )
        
        self.storage.update_calibration(updated_calibration)
    
    def show_status(self):
        """Show current calibration status and pending tasks."""
        calibration = self.storage.get_calibration_data()
        pending = self.storage.get_pending_tasks()
        completed = self.storage.get_completed_tasks()
        
        self.console.print()
        
        # Overview stats
        stats_table = Table.grid(padding=(0, 2))
        stats_table.add_column(style="bold", width=20)
        stats_table.add_column()
        
        total_tasks = len(pending) + len(completed)
        stats_table.add_row("📊 Total tasks:", f"[bold]{total_tasks}[/bold]")
        stats_table.add_row("⏳ Pending:", f"[yellow]{len(pending)}[/yellow]")
        stats_table.add_row("✅ Completed:", f"[green]{len(completed)}[/green]")
        
        # Bias analysis
        bias = calibration.get('user_bias', 0.0)
        if abs(bias) > 0.01:
            if bias > 0:
                bias_text = Text(f"You tend to OVERESTIMATE by ~{bias:.1%}", style="red")
            else:
                bias_text = Text(f"You tend to UNDERESTIMATE by ~{abs(bias):.1%}", style="blue")
        else:
            bias_text = Text("Well calibrated! 🎯", style="green")
        
        stats_table.add_row("", "")
        stats_table.add_row("📈 Overall pattern:", bias_text)
        
        self.console.print(Panel(
            stats_table,
            title="[bold cyan]CALIBRATION STATUS[/bold cyan]",
            border_style="cyan"
        ))
        
        # Category patterns
        category_patterns = calibration.get('category_patterns', {})
        if category_patterns:
            cat_table = Table(title="Category Patterns", box=box.ROUNDED, show_header=True)
            cat_table.add_column("Category", style="cyan")
            cat_table.add_column("Adjustment", justify="right")
            cat_table.add_column("Trend", justify="center")
            
            for category, factor in sorted(category_patterns.items(), 
                                         key=lambda x: abs(x[1] - 1.0), 
                                         reverse=True)[:5]:
                adj_pct = (factor - 1.0) * 100
                if adj_pct > 0:
                    trend = "📈"
                    style = "red"
                elif adj_pct < 0:
                    trend = "📉"
                    style = "blue"
                else:
                    trend = "➡️"
                    style = "green"
                
                cat_table.add_row(
                    category,
                    f"[{style}]{adj_pct:+.1f}%[/{style}]",
                    trend
                )
            
            self.console.print()
            self.console.print(cat_table)
        
        # Pending tasks
        if pending:
            pending_table = Table(title="📋 Pending Tasks", box=box.ROUNDED, show_header=True)
            pending_table.add_column("ID", style="dim", width=20)
            pending_table.add_column("Description")
            pending_table.add_column("Estimate", justify="right", style="cyan")
            
            for task in pending:
                pending_table.add_row(
                    task['id'],
                    task['description'][:50],
                    f"{task['estimated_minutes']} min"
                )
            
            self.console.print()
            self.console.print(pending_table)
        
        self.console.print()
    
    def show_history(self, limit: int = 10):
        """Show recent task history."""
        completed = self.storage.get_completed_tasks()
        
        self.console.print()
        
        if not completed:
            self.console.print(Panel(
                "[dim]No completed tasks yet.[/dim]",
                border_style="dim"
            ))
            self.console.print()
            return
        
        history_table = Table(title=f"📜 Recent History (Last {min(limit, len(completed))} tasks)", 
                             box=box.ROUNDED, show_header=True)
        history_table.add_column("Task", width=35)
        history_table.add_column("Category", width=12)
        history_table.add_column("Estimated", justify="right", style="cyan")
        history_table.add_column("Actual", justify="right", style="green")
        history_table.add_column("Error", justify="right")
        
        # Category color mapping (same as in estimate_tasks)
        category_colors = {
            'coding': 'blue',
            'writing': 'magenta',
            'admin': 'yellow',
            'deep work': 'cyan',
            'social': 'green',
            'errands': 'yellow',
            'meetings': 'blue',
            'learning': 'cyan',
            'fitness': 'green',
            'general': 'white'
        }
        
        for task in completed[-limit:]:
            error_pct = ((task['actual_minutes'] - task['estimated_minutes']) / 
                        task['estimated_minutes']) * 100
            
            # Color code error
            if abs(error_pct) < 10:
                error_style = "green"
            elif error_pct > 0:
                error_style = "red"
            else:
                error_style = "blue"
            
            # Get category with color
            category = task.get('category', 'general')
            cat_color = category_colors.get(category, 'white')
            category_display = f"[{cat_color}]{category}[/{cat_color}]"
            
            history_table.add_row(
                task['description'][:35] + ("..." if len(task['description']) > 35 else ""),
                category_display,
                f"{task['estimated_minutes']} min",
                f"{task['actual_minutes']} min",
                f"[{error_style}]{error_pct:+.1f}%[/{error_style}]"
            )
        
        self.console.print(history_table)
        self.console.print()
    
    def run_experiments(self, output_path: Optional[str] = None):
        """Run context engineering experiments."""
        completed_tasks = self.storage.get_completed_tasks()
        
        if len(completed_tasks) < 3:
            self.console.print(Panel(
                "[yellow]Not enough completed tasks for experiments.[/yellow]\n"
                "[dim]Need at least 3 completed tasks to run experiments.[/dim]",
                border_style="yellow"
            ))
            self.console.print()
            return
        
        calibration = self.storage.get_calibration_data()
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]🧪 CONTEXT ENGINEERING EXPERIMENTS[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        self.console.print(f"[dim]Running experiments on {len(completed_tasks)} completed tasks...[/dim]\n")
        
        # Run experiments
        experiment = ContextExperiment(self.agent, self.learner)
        results = experiment.run_all_experiments(completed_tasks, calibration)
        
        # Display comparison
        comparison = results.get('comparison', {})
        comparisons = comparison.get('comparisons', {})
        
        if comparisons:
            comp_table = Table(title="Strategy Comparison", box=box.ROUNDED, show_header=True)
            comp_table.add_column("Strategy", style="cyan")
            comp_table.add_column("MAE", justify="right")
            comp_table.add_column("MAPE", justify="right")
            comp_table.add_column("Within ±20%", justify="right")
            
            # Sort by MAPE (lower is better)
            sorted_strategies = sorted(comparisons.items(), key=lambda x: x[1]['mape'])
            
            for strategy_name, metrics in sorted_strategies:
                # Highlight best
                if strategy_name == comparison.get('best_mape', {}).get('strategy'):
                    style = "bold green"
                else:
                    style = None
                
                comp_table.add_row(
                    f"[{style}]{strategy_name}[/{style}]" if style else strategy_name,
                    f"{metrics['mae']:.1f} min",
                    f"{metrics['mape']:.1f}%",
                    f"{metrics['within_20pct']:.1f}%"
                )
            
            self.console.print(comp_table)
            self.console.print()
            
            # Show best strategies
            best_table = Table.grid(padding=(0, 2))
            best_table.add_column(style="dim", width=20)
            best_table.add_column()
            
            best_mae = comparison.get('best_mae', {})
            best_mape = comparison.get('best_mape', {})
            best_within_20 = comparison.get('best_within_20pct', {})
            
            if best_mae:
                best_table.add_row("🏆 Best MAE:", f"[green]{best_mae['strategy']}[/green] ({best_mae['value']:.1f} min)")
            if best_mape:
                best_table.add_row("🏆 Best MAPE:", f"[green]{best_mape['strategy']}[/green] ({best_mape['value']:.1f}%)")
            if best_within_20:
                best_table.add_row("🏆 Best ±20%:", f"[green]{best_within_20['strategy']}[/green] ({best_within_20['value']:.1f}%)")
            
            self.console.print(Panel(
                best_table,
                title="[bold]Best Strategies[/bold]",
                border_style="green"
            ))
            self.console.print()
        
        # Save if requested
        if output_path:
            experiment.save_results(results, output_path)
            self.console.print(Panel(
                f"[green]✅ Experiment results saved to: {output_path}[/green]",
                border_style="green"
            ))
            self.console.print()
    
    def collect_human_evaluations(self, estimates: List[Dict], task_descriptions: List[str],
                                  output_path: str = "human_evaluations.json"):
        """
        Interactive interface for human evaluation of estimates.
        
        Args:
            estimates: List of estimate dicts
            task_descriptions: List of corresponding task descriptions
            output_path: Path to save evaluations
        """
        human_evaluator = HumanEvaluator(output_path)
        evaluations = []
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]👤 HUMAN EVALUATION[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        self.console.print("[dim]Rate each estimate: 1 = good quality, 0 = poor quality[/dim]\n")
        
        for i, (task_desc, estimate) in enumerate(zip(task_descriptions, estimates), 1):
            estimated = estimate.get('estimated_minutes', 0)
            range_data = estimate.get('estimate_range', {})
            explanation = estimate.get('explanation', '')
            category = estimate.get('category', 'unknown')
            
            # Display estimate
            eval_table = Table.grid(padding=(0, 2))
            eval_table.add_column(style="dim", width=15)
            eval_table.add_column()
            
            eval_table.add_row("📝 Task:", task_desc)
            eval_table.add_row("⏱️  Estimate:", f"{estimated} minutes")
            eval_table.add_row("📊 Range:", 
                             f"{range_data.get('optimistic', 0)} - {range_data.get('realistic', estimated)} - {range_data.get('pessimistic', 0)} min")
            eval_table.add_row("🏷️  Category:", category)
            eval_table.add_row("💡 Explanation:", explanation[:100] + ("..." if len(explanation) > 100 else ""))
            
            self.console.print(Panel(
                eval_table,
                title=f"[bold]Estimate {i}/{len(estimates)}[/bold]",
                border_style="blue"
            ))
            self.console.print()
            
            # Get rating
            while True:
                try:
                    rating_input = self.console.input("[yellow]Rating (0 or 1, or 'skip'):[/yellow] ").strip().lower()
                    if rating_input == 'skip':
                        self.console.print("[dim]Skipped[/dim]\n")
                        break
                    rating = int(rating_input)
                    if rating == 0 or rating == 1:
                        notes = self.console.input("[dim]Optional notes (press Enter to skip):[/dim] ").strip()
                        
                        rating_label = "Good Quality" if rating == 1 else "Poor Quality"
                        evaluations.append({
                            "task_description": task_desc,
                            "estimate": estimate,
                            "rating": rating,
                            "notes": notes if notes else None,
                            "evaluator": "human"
                        })
                        self.console.print(f"[green]✅ Rated {rating} ({rating_label})[/green]\n")
                        break
                    else:
                        self.console.print("[red]Please enter 0 (poor quality) or 1 (good quality)[/red]")
                except ValueError:
                    self.console.print("[red]Please enter a valid number or 'skip'[/red]")
        
        # Save evaluations
        if evaluations:
            human_evaluator.save_evaluations(evaluations)
            self.console.print(Panel(
                f"[green]✅ Saved {len(evaluations)} evaluation(s) to {output_path}[/green]",
                border_style="green"
            ))
            self.console.print()
    
    def clear_pending(self):
        """Clear all pending tasks."""
        pending_count = len(self.storage.get_pending_tasks())
        if pending_count == 0:
            self.console.print(Panel(
                "[yellow]No pending tasks to clear.[/yellow]",
                border_style="yellow"
            ))
            self.console.print()
            return
        
        deleted = self.storage.delete_pending_tasks()
        self.console.print(Panel(
            f"[bold red]🗑️  Deleted {deleted} pending task(s)[/bold red]\n"
            "[dim]Completed tasks were preserved.[/dim]",
            border_style="red"
        ))
        self.console.print()

    def _resolve_session_id(
        self,
        session_label: Optional[str] = None,
        date_override: Optional[str] = None,
        use_last: bool = True,
    ) -> Optional[str]:
        if session_label or date_override:
            return self.session_store.build_session_id(date_override, session_label)
        if use_last:
            last_id = self.session_store.load_last_session_id()
            if last_id:
                return last_id
        return None

    def plan_day(
        self,
        raw_text: str,
        session_label: Optional[str] = None,
        date_override: Optional[str] = None,
        require_existing: bool = False,
        overwrite: bool = False,
        debug: bool = False,
    ):
        """Create or update a replanning session from raw text input."""
        if not raw_text.strip():
            self.console.print("[red]Error: Please provide context text to plan your day[/red]")
            return

        session_id = self._resolve_session_id(
            session_label=session_label,
            date_override=date_override,
            use_last=not overwrite,
        )
        if not session_id:
            if overwrite:
                session_id = self.session_store.build_session_id(date_override, session_label)
            else:
                self.console.print("[red]Error: No active session. Start with new-session.[/red]")
                return

        session = None if overwrite else self.session_store.load_session(session_id)
        if require_existing and not session:
            self.console.print(f"[red]Error: No existing session found for {session_id}[/red]")
            return

        last_plan = None
        last_input = None
        if session and session.get("replans") and not overwrite:
            last_replan = session["replans"][-1]
            last_plan = last_replan.get("plan_output")
            last_input = last_replan.get("raw_input")

        current_time = datetime.now().strftime("%H:%M")
        plan_output, estimated_tasks, extracted_context = self.replanner.plan_with_estimates(
            raw_text=raw_text,
            current_time=current_time,
            last_plan=last_plan,
            last_input=last_input,
        )

        if debug:
            plan_output = dict(plan_output)
            plan_output["estimated_tasks"] = estimated_tasks
            plan_output["extracted_context"] = extracted_context

        self.session_store.append_replan(
            session_id=session_id,
            raw_input=raw_text,
            plan_output=plan_output,
            current_time=current_time,
            extra={
                "estimated_tasks": estimated_tasks,
                "extracted_context": extracted_context,
            },
            overwrite=overwrite,
        )

        self.console.print_json(json.dumps(plan_output))

    def show_session(
        self,
        session_label: Optional[str] = None,
        date_override: Optional[str] = None,
        debug: bool = False,
    ):
        """Show the latest plan for a session."""
        session_id = self._resolve_session_id(
            session_label=session_label,
            date_override=date_override,
            use_last=True,
        )
        if not session_id:
            self.console.print("[yellow]No session found. Start with new-session.[/yellow]")
            return
        session = self.session_store.load_session(session_id)
        if not session or not session.get("replans"):
            self.console.print(f"[yellow]No session found for {session_id}[/yellow]")
            return

        last_replan = session["replans"][-1]
        plan_output = last_replan.get("plan_output", {})
        if debug:
            plan_output = dict(plan_output)
            if "estimated_tasks" not in plan_output:
                plan_output["estimated_tasks"] = last_replan.get("estimated_tasks", [])
            if "extracted_context" not in plan_output:
                plan_output["extracted_context"] = last_replan.get("extracted_context", {})
        self.console.print_json(json.dumps(plan_output))
    
    def generate_test_dataset(self, n: int = 50, output_path: Optional[str] = None):
        """Generate a test dataset with diverse prompts."""
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]📝 TEST DATASET GENERATION[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        self.console.print(f"[dim]Generating {n} diverse test prompts...[/dim]\n")
        
        generator = TestDatasetGenerator()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            progress.add_task("[cyan]Generating prompts...", total=None)
            prompts = generator.generate_test_dataset(n)
        
        if output_path:
            generator.save_dataset(prompts, output_path)
        else:
            default_path = "test_dataset.json"
            generator.save_dataset(prompts, default_path)
            output_path = default_path
        
        # Show summary
        summary_table = Table.grid(padding=(0, 2))
        summary_table.add_column(style="dim", width=20)
        summary_table.add_column()
        
        categories = {}
        ambiguities = {}
        lengths = {}
        
        for prompt in prompts:
            meta = prompt.get('metadata', {})
            cat = meta.get('category', 'unknown')
            amb = meta.get('ambiguity', 'unknown')
            length = meta.get('length', 'unknown')
            
            categories[cat] = categories.get(cat, 0) + 1
            ambiguities[amb] = ambiguities.get(amb, 0) + 1
            lengths[length] = lengths.get(length, 0) + 1
        
        summary_table.add_row("📊 Total prompts:", str(n))
        summary_table.add_row("📁 Saved to:", output_path)
        summary_table.add_row("", "")
        summary_table.add_row("🏷️  Categories:", ", ".join(f"{k}({v})" for k, v in sorted(categories.items())))
        summary_table.add_row("🔍 Ambiguities:", ", ".join(f"{k}({v})" for k, v in sorted(ambiguities.items())))
        summary_table.add_row("📏 Lengths:", ", ".join(f"{k}({v})" for k, v in sorted(lengths.items())))
        
        self.console.print(Panel(
            summary_table,
            title="[bold]Dataset Summary[/bold]",
            border_style="green"
        ))
        self.console.print()
    
    def run_quality_evaluation(self, dataset_path: str, strategy_name: str = "recent_n", 
                              evaluator: str = "ai", debug: bool = False, output_path: Optional[str] = None,
                              scoring_mode: str = "binary"):
        """Run quality evaluation on a test dataset."""
        from time_calibration_agent.agent import ContextStrategy
        
        # Load dataset
        generator = TestDatasetGenerator()
        try:
            test_prompts = generator.load_dataset(dataset_path)
        except Exception as e:
            self.console.print(f"[red]Error loading dataset: {e}[/red]\n")
            return
        
        # Map strategy name to enum
        strategy_map = {
            "minimal": ContextStrategy.MINIMAL,
            "recent_n": ContextStrategy.RECENT_N,
            "summarized": ContextStrategy.SUMMARIZED,
            "category_filtered": ContextStrategy.CATEGORY_FILTERED,
            "similarity_based": ContextStrategy.SIMILARITY_BASED
        }
        
        strategy = strategy_map.get(strategy_name.lower(), ContextStrategy.RECENT_N)
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]🔍 QUALITY EVALUATION[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        self.console.print(f"[dim]Evaluating {len(test_prompts)} prompts with strategy: {strategy_name}[/dim]")
        self.console.print(f"[dim]Scoring mode: {scoring_mode}[/dim]\n")
        
        # Generate estimates
        quality_evaluator = QualityEvaluator(scoring_mode=scoring_mode)
        estimates = []
        task_descriptions = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Generating estimates...", total=len(test_prompts))
            
            for prompt_data in test_prompts:
                prompt_text = prompt_data.get('prompt', '') if isinstance(prompt_data, dict) else prompt_data
                if not prompt_text:
                    continue
                
                # Get prompt quality metadata
                prompt_quality = prompt_data.get('metadata', {}).get('prompt_quality', 'unknown') if isinstance(prompt_data, dict) else 'unknown'
                
                estimate = self.agent.estimate_task(
                    prompt_text,
                    context_strategy=strategy
                )
                estimates.append(estimate)
                task_descriptions.append(prompt_text)
                
                # #region agent log
                import json
                with open('/Users/adimiddha/Github/time-calibration-agent/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B",
                        "location": "cli.py:run_quality_evaluation",
                        "message": "Estimate generated for prompt",
                        "data": {
                            "prompt_quality": prompt_quality,
                            "estimated_minutes": estimate.get('estimated_minutes', 0),
                            "explanation_length": len(estimate.get('explanation', '')),
                            "category": estimate.get('category', 'unknown')
                        },
                        "timestamp": int(__import__('time').time() * 1000)
                    }) + '\n')
                # #endregion
                
                progress.update(task, advance=1)
        
        # Evaluate quality
        if evaluator in ["ai", "both"]:
            self.console.print("[dim]Running AI evaluation...[/dim]\n")
            eval_results = []
            for i, (task_desc, estimate) in enumerate(zip(task_descriptions, estimates)):
                # Get prompt quality from original data
                prompt_quality = "unknown"
                if i < len(test_prompts):
                    prompt_data = test_prompts[i]
                    if isinstance(prompt_data, dict):
                        prompt_quality = prompt_data.get('metadata', {}).get('prompt_quality', 'unknown')
                
                eval_result = quality_evaluator.evaluate_estimate_quality(task_desc, estimate, prompt_quality=prompt_quality)
                # Ensure result has a score key
                if "score" not in eval_result:
                    self.console.print(f"[yellow]Warning: Evaluation result missing 'score' key for task {len(eval_results)+1}[/yellow]")
                    eval_result["score"] = 0  # Default to 0 if missing
                eval_results.append(eval_result)
                
                # #region agent log
                import json
                with open('/Users/adimiddha/Github/time-calibration-agent/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C,D,E",
                        "location": "cli.py:run_quality_evaluation",
                        "message": "Evaluation completed",
                        "data": {
                            "prompt_quality": prompt_quality,
                            "score": eval_result.get('score', 0),
                            "reasonableness_score": eval_result.get('reasonableness_score', 0),
                            "consistency_score": eval_result.get('consistency_score', 0),
                            "estimated_minutes": estimate.get('estimated_minutes', 0)
                        },
                        "timestamp": int(__import__('time').time() * 1000)
                    }) + '\n')
                # #endregion
            
            # Display results
            # Filter out any results without scores and ensure all have scores
            valid_eval_results = []
            for e in eval_results:
                if "score" not in e:
                    self.console.print(f"[yellow]Warning: Evaluation result missing 'score' key, defaulting to 0[/yellow]")
                    e["score"] = 0
                valid_eval_results.append(e)
            eval_results = valid_eval_results
            
            avg_score = sum(e.get("score", 0) for e in eval_results) / len(eval_results) if eval_results else 0
            is_five_point = scoring_mode == "five_point"
            
            if is_five_point:
                good_count = sum(1 for e in eval_results if e.get("score", 0) >= 4)
                poor_count = sum(1 for e in eval_results if e.get("score", 0) < 4)
                score_label = f"(1-5 scale: 5=excellent, 4=good, 3=acceptable, 2=poor, 1=very poor)"
            else:
                good_count = sum(1 for e in eval_results if e.get("score", 0) == 1)
                poor_count = sum(1 for e in eval_results if e.get("score", 0) == 0)
                score_label = "(binary: 0=poor, 1=good)"
            
            results_table = Table.grid(padding=(0, 2))
            results_table.add_column(style="dim", width=20)
            results_table.add_column()
            
            results_table.add_row("📊 Average Score:", f"[bold]{avg_score:.2f}[/bold] {score_label}")
            results_table.add_row("✅ Good Quality:", f"[green]{good_count}[/green] ({good_count/len(eval_results)*100:.1f}%)")
            results_table.add_row("❌ Poor Quality:", f"[red]{poor_count}[/red] ({poor_count/len(eval_results)*100:.1f}%)")
            results_table.add_row("📈 Total Evaluated:", str(len(eval_results)))
            
            score_dist = {}
            for result in eval_results:
                score = result["score"]
                score_dist[score] = score_dist.get(score, 0) + 1
            
            dist_text = ", ".join(f"{k}: {v}" for k, v in sorted(score_dist.items(), reverse=True))
            results_table.add_row("📊 Score Distribution:", dist_text)
            
            self.console.print(Panel(
                results_table,
                title="[bold]AI Evaluation Results[/bold]",
                border_style="green"
            ))
            self.console.print()
            
            # Debug mode: Show sample estimates with scores and reasoning
            if debug:
                self._show_debug_samples(task_descriptions, estimates, eval_results, output_path=output_path, scoring_mode=scoring_mode)
        
        if evaluator in ["human", "both"]:
            self.console.print("[yellow]Starting human evaluation...[/yellow]\n")
            self.collect_human_evaluations(estimates, task_descriptions)
    
    def _show_debug_samples(self, task_descriptions: List[str], estimates: List[Dict], 
                           eval_results: List[Dict], num_samples: int = 10, output_path: Optional[str] = None,
                           scoring_mode: str = "binary"):
        """Show debug samples of estimates with scores and reasoning."""
        import random
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold yellow]🐛 DEBUG MODE[/bold yellow]",
            border_style="yellow"
        ))
        self.console.print()
        
        # Group by score to show variety
        score_groups = {}
        for i, (task_desc, estimate, eval_result) in enumerate(zip(task_descriptions, estimates, eval_results)):
            score = eval_result["score"]
            if score not in score_groups:
                score_groups[score] = []
            score_groups[score].append((i, task_desc, estimate, eval_result))
        
        # Show samples from each score group
        self.console.print("[bold]Sample Estimates by Score:[/bold]\n")
        
        for score in sorted(score_groups.keys(), reverse=True):
            samples = score_groups[score][:3]  # Show up to 3 examples per score
            
            for idx, task_desc, estimate, eval_result in samples:
                debug_table = Table.grid(padding=(0, 2))
                debug_table.add_column(style="dim", width=18)
                debug_table.add_column()
                
                debug_table.add_row("📝 Task:", task_desc[:80] + ("..." if len(task_desc) > 80 else ""))
                debug_table.add_row("⏱️  Estimate:", f"{estimate.get('estimated_minutes', 'N/A')} min")
                est_range = estimate.get('estimate_range', {}) or {}
                if est_range:
                    debug_table.add_row("📊 Range:", 
                                       f"{est_range.get('optimistic', 'N/A')}-{est_range.get('realistic', estimate.get('estimated_minutes', 'N/A'))}-{est_range.get('pessimistic', 'N/A')} min")
                else:
                    debug_table.add_row("📊 Range:", "N/A")
                debug_table.add_row("🏷️  Category:", estimate.get('category', 'unknown'))
                debug_table.add_row("💡 Explanation:", estimate.get('explanation', '')[:120] + ("..." if len(estimate.get('explanation', '')) > 120 else ""))
                debug_table.add_row("", "")
                score_val = eval_result['score']
                is_five_point = scoring_mode == "five_point"
                if is_five_point:
                    score_label = f"{score_val}/5"
                    score_color = "green" if score_val >= 4 else "yellow" if score_val == 3 else "red"
                    dim_label = "(1-5 scale)"
                else:
                    score_label = "Good (1)" if score_val == 1 else "Poor (0)"
                    score_color = "green" if score_val == 1 else "red"
                    dim_label = "(1=good, 0=poor)"
                debug_table.add_row("⭐ Score:", f"[bold {score_color}]{score_val} ({score_label})[/bold {score_color}]")
                debug_table.add_row("📊 Reasonableness:", f"{eval_result.get('reasonableness_score', 'N/A')} {dim_label}")
                debug_table.add_row("🔄 Consistency:", f"{eval_result.get('consistency_score', 'N/A')} {dim_label}")
                debug_table.add_row("📈 Range Score:", f"{eval_result.get('range_score', 'N/A')} {dim_label}")
                debug_table.add_row("🏷️  Category Score:", f"{eval_result.get('category_score', 'N/A')} {dim_label}")
                debug_table.add_row("", "")
                debug_table.add_row("💭 Reasoning:", eval_result.get('reasoning', 'No reasoning')[:200] + ("..." if len(eval_result.get('reasoning', '')) > 200 else ""))
                
                checks = eval_result.get('checks', {})
                if checks:
                    debug_table.add_row("", "")
                    debug_table.add_row("✅ Checks:", 
                                       f"Reasonable: {checks.get('reasonable_number', 'N/A')}, "
                                       f"Aligned: {checks.get('explanation_number_aligned', 'N/A')}, "
                                       f"Range Valid: {checks.get('range_valid', 'N/A')}")
                
                is_five_point = scoring_mode == "five_point"
                if is_five_point:
                    score_color = "green" if score >= 4 else "yellow" if score == 3 else "red"
                    score_labels = {5: "Excellent", 4: "Good", 3: "Acceptable", 2: "Poor", 1: "Very Poor"}
                    score_label = score_labels.get(score, f"Score {score}")
                else:
                    score_color = "green" if score == 1 else "red"
                    score_label = "Good Quality" if score == 1 else "Poor Quality"
                
                self.console.print(Panel(
                    debug_table,
                    title=f"[bold {score_color}]Score {score} ({score_label}) - Example[/bold {score_color}]",
                    border_style=score_color
                ))
                self.console.print()
        
        # Show summary statistics
        self.console.print("[bold]Score Breakdown:[/bold]\n")
        breakdown_table = Table(box=box.ROUNDED, show_header=True)
        breakdown_table.add_column("Score", style="cyan", justify="center")
        breakdown_table.add_column("Label", justify="left")
        breakdown_table.add_column("Count", justify="right")
        breakdown_table.add_column("Avg Reasonableness", justify="right")
        breakdown_table.add_column("Avg Consistency", justify="right")
        breakdown_table.add_column("Avg Range", justify="right")
        
        for score in sorted(score_groups.keys(), reverse=True):
            group = score_groups[score]
            avg_reasonableness = sum(e[3].get('reasonableness_score', 0) for e in group) / len(group)
            avg_consistency = sum(e[3].get('consistency_score', 0) for e in group) / len(group)
            avg_range = sum(e[3].get('range_score', 0) for e in group) / len(group)
            is_five_point = scoring_mode == "five_point"
            if is_five_point:
                score_labels = {5: "Excellent", 4: "Good", 3: "Acceptable", 2: "Poor", 1: "Very Poor"}
                label = score_labels.get(score, f"Score {score}")
            else:
                label = "Good Quality" if score == 1 else "Poor Quality"
            
            breakdown_table.add_row(
                str(score),
                label,
                str(len(group)),
                f"{avg_reasonableness:.2f}",
                f"{avg_consistency:.2f}",
                f"{avg_range:.2f}"
            )
        
        self.console.print(breakdown_table)
        self.console.print()
        
        # Save debug data to JSON
        debug_data = {
            "samples": [
                {
                    "task": task_desc,
                    "estimate": estimate,
                    "evaluation": eval_result
                }
                for task_desc, estimate, eval_result in zip(task_descriptions,
                                                          estimates,
                                                          eval_results)
            ],
            "score_distribution": {str(k): len(v) for k, v in score_groups.items()},
            "all_evaluations": eval_results
        }
        
        import json
        from pathlib import Path
        from datetime import datetime
        
        # Determine output path
        if output_path:
            debug_path = output_path
        else:
            debug_path = "quality_eval_debug.json"
        
        # Backup existing file if it exists and we're using default name
        if not output_path:
            existing_file = Path(debug_path)
            if existing_file.exists():
                # Create backup with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"quality_eval_debug_backup_{timestamp}.json"
                try:
                    import shutil
                    shutil.copy2(existing_file, backup_path)
                    self.console.print(f"[yellow]⚠️  Backed up existing file to: {backup_path}[/yellow]\n")
                except Exception as e:
                    self.console.print(f"[yellow]⚠️  Could not backup existing file: {e}[/yellow]\n")
        
        # Save debug data
        with open(debug_path, 'w') as f:
            json.dump(debug_data, f, indent=2, default=str)
        
        self.console.print(Panel(
            f"[green]✅ Debug data saved to: {debug_path}[/green]\n"
            "[dim]Contains sample estimates, evaluations, and full reasoning.[/dim]",
            border_style="green"
        ))
        self.console.print()
    
    def analyze_quality_results(self, debug_path: str = "quality_eval_debug.json"):
        """Analyze quality evaluation results to identify patterns."""
        import json
        from pathlib import Path
        
        # Load debug data
        debug_file = Path(debug_path)
        if not debug_file.exists():
            self.console.print(f"[red]Error: Debug file not found: {debug_path}[/red]")
            return
        
        try:
            with open(debug_file, 'r') as f:
                debug_data = json.load(f)
        except Exception as e:
            self.console.print(f"[red]Error loading debug data: {e}[/red]")
            return
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]📊 QUALITY EVALUATION ANALYSIS[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Run all analyses
        all_evaluations = debug_data.get("all_evaluations", [])
        samples = debug_data.get("samples", [])
        
        if not all_evaluations:
            self.console.print("[yellow]No evaluation data found in debug file.[/yellow]")
            return
        
        # Try to find test dataset path (look for common names)
        test_dataset_path = None
        for test_file in ["test_2_dataset.json", "test_1_dataset.json", "test_dataset.json"]:
            test_path = Path(test_file)
            if test_path.exists():
                test_dataset_path = str(test_path)
                break
        
        # 1. Score Patterns Analysis
        self.console.print("[bold]1. Score Distribution Analysis[/bold]")
        score_patterns = analyze_score_patterns(debug_data, test_dataset_path)
        
        patterns_table = Table(box=box.ROUNDED, show_header=True)
        patterns_table.add_column("Metric", style="cyan")
        patterns_table.add_column("Value", justify="right")
        
        patterns_table.add_row("Total Evaluations", str(score_patterns.get("total_evaluations", 0)))
        patterns_table.add_row("Average Score", f"{score_patterns.get('average_score', 0):.2f}")
        
        # Score distribution
        dist = score_patterns.get("overall_distribution", {})
        dist_str = ", ".join(f"Score {k}: {v}" for k, v in sorted(dist.items()))
        patterns_table.add_row("Distribution", dist_str)
        
        self.console.print(patterns_table)
        self.console.print()
        
        # By quality
        by_quality = score_patterns.get("by_quality", {})
        if by_quality:
            quality_table = Table(title="Average Score by Prompt Quality", box=box.ROUNDED, show_header=True)
            quality_table.add_column("Quality", style="cyan")
            quality_table.add_column("Avg Score", justify="right")
            quality_table.add_column("Count", justify="right", style="dim")
            
            for quality, avg_score in sorted(by_quality.items(), key=lambda x: x[1], reverse=True):
                count = len([s for s in samples if quality in str(s).lower()])
                quality_table.add_row(quality.capitalize(), f"{avg_score:.2f}", str(count))
            
            self.console.print(quality_table)
            self.console.print()
        
        # By category
        by_category = score_patterns.get("by_category", {})
        if by_category:
            category_table = Table(title="Average Score by Category", box=box.ROUNDED, show_header=True)
            category_table.add_column("Category", style="cyan")
            category_table.add_column("Avg Score", justify="right")
            
            for category, avg_score in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
                category_table.add_row(category.capitalize(), f"{avg_score:.2f}")
            
            self.console.print(category_table)
            self.console.print()
        
        # 2. Common Issues Analysis
        self.console.print("[bold]2. Common Issues & Success Patterns[/bold]")
        common_issues = identify_common_issues(all_evaluations)
        
        issues_table = Table(box=box.ROUNDED, show_header=True)
        issues_table.add_column("Metric", style="cyan")
        issues_table.add_column("Value", justify="right")
        
        issues_table.add_row("Low Scores (≤2)", str(common_issues.get("low_score_count", 0)))
        issues_table.add_row("High Scores (≥4)", str(common_issues.get("high_score_count", 0)))
        
        self.console.print(issues_table)
        self.console.print()
        
        # Top issues
        low_issues = common_issues.get("low_score_issues", {})
        if low_issues:
            issues_list = Table(title="Most Common Issues in Low Scores", box=box.ROUNDED, show_header=True)
            issues_list.add_column("Issue", style="cyan")
            issues_list.add_column("Count", justify="right")
            
            for issue, count in sorted(low_issues.items(), key=lambda x: x[1], reverse=True)[:5]:
                issues_list.add_row(issue.replace("_", " ").title(), str(count))
            
            self.console.print(issues_list)
            self.console.print()
        
        # Success patterns
        high_patterns = common_issues.get("high_score_patterns", {})
        if high_patterns:
            patterns_list = Table(title="Success Patterns in High Scores", box=box.ROUNDED, show_header=True)
            patterns_list.add_column("Pattern", style="cyan")
            patterns_list.add_column("Count", justify="right")
            
            for pattern, count in sorted(high_patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
                patterns_list.add_row(pattern.replace("_", " ").title(), str(count))
            
            self.console.print(patterns_list)
            self.console.print()
        
        # 3. Dimension Analysis
        self.console.print("[bold]3. Dimension Analysis[/bold]")
        dimension_analysis = analyze_by_dimension(all_evaluations)
        
        dim_table = Table(title="Average Scores by Dimension", box=box.ROUNDED, show_header=True)
        dim_table.add_column("Dimension", style="cyan")
        dim_table.add_column("Avg Score", justify="right")
        
        avg_dims = dimension_analysis.get("average_dimensions", {})
        for dim, score in sorted(avg_dims.items(), key=lambda x: x[1], reverse=True):
            dim_table.add_row(dim.capitalize(), f"{score:.2f}")
        
        self.console.print(dim_table)
        self.console.print()
        
        weakest = dimension_analysis.get("weakest_dimension")
        strongest = dimension_analysis.get("strongest_dimension")
        if weakest:
            self.console.print(f"[yellow]Weakest dimension: {weakest} ({dimension_analysis.get('weakest_score', 0):.2f})[/yellow]")
        if strongest:
            self.console.print(f"[green]Strongest dimension: {strongest} ({dimension_analysis.get('strongest_score', 0):.2f})[/green]")
        self.console.print()
        
        # 4. Correlation Analysis
        self.console.print("[bold]4. Feature Correlations[/bold]")
        correlations = correlate_estimate_features(samples)
        
        corr_insights = correlations.get("insights", [])
        if corr_insights:
            for insight in corr_insights:
                self.console.print(f"  • {insight}")
        else:
            self.console.print("[dim]No significant correlations found.[/dim]")
        self.console.print()
        
        # 5. Recommendations
        self.console.print("[bold]5. Recommendations[/bold]")
        analysis_results = {
            "score_patterns": score_patterns,
            "common_issues": common_issues,
            "dimension_analysis": dimension_analysis,
            "correlations": correlations
        }
        recommendations = generate_recommendations(analysis_results)
        
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                self.console.print(f"  {i}. {rec}")
        else:
            self.console.print("[dim]No specific recommendations at this time.[/dim]")
        self.console.print()
        
        # Show examples
        self.console.print("[bold]6. Example Estimates[/bold]")
        
        # High score example
        high_score_samples = [s for s in samples if s.get("evaluation", {}).get("score", 0) >= 4]
        if high_score_samples:
            example = high_score_samples[0]
            self.console.print(Panel(
                f"[green]High Score Example (Score {example['evaluation']['score']})[/green]\n\n"
                f"[bold]Task:[/bold] {example['task'][:100]}...\n"
                f"[bold]Estimate:[/bold] {example['estimate']['estimated_minutes']} min\n"
                f"[bold]Explanation:[/bold] {example['estimate']['explanation'][:150]}...",
                title="✓ Good Estimate",
                border_style="green"
            ))
            self.console.print()
        
        # Low score example
        low_score_samples = [s for s in samples if s.get("evaluation", {}).get("score", 0) <= 2]
        if low_score_samples:
            example = low_score_samples[0]
            self.console.print(Panel(
                f"[red]Low Score Example (Score {example['evaluation']['score']})[/red]\n\n"
                f"[bold]Task:[/bold] {example['task'][:100]}...\n"
                f"[bold]Estimate:[/bold] {example['estimate']['estimated_minutes']} min\n"
                f"[bold]Issue:[/bold] {example['evaluation']['reasoning'][:150]}...",
                title="✗ Poor Estimate",
                border_style="red"
            ))
            self.console.print()
    
    def compare_scoring_methodologies(self, old_debug_path: str = "quality_eval_debug.json",
                                     new_debug_path: Optional[str] = None):
        """
        Compare old 1-5 scoring vs new 0-1 binary scoring methodologies.
        
        Args:
            old_debug_path: Path to old evaluation results (1-5 scoring)
            new_debug_path: Path to new evaluation results (0-1 scoring). If None, will prompt to run new evaluation.
        """
        from time_calibration_agent.quality_analysis import (
            compare_scoring_methodologies, load_old_evaluations,
            measure_evaluation_consistency, measure_discrimination_ability
        )
        import json
        from pathlib import Path
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]📊 SCORING METHODOLOGY COMPARISON[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Load old evaluations
        self.console.print("[dim]Loading old 1-5 scoring results...[/dim]")
        old_data = load_old_evaluations(old_debug_path)
        
        if not old_data or "error" in old_data:
            self.console.print(f"[red]Error: Could not load old evaluations from {old_debug_path}[/red]")
            if old_data and "error" in old_data:
                self.console.print(f"[red]Details: {old_data['error']}[/red]")
            return
        
        old_evaluations = old_data.get("all_evaluations", [])
        old_samples = old_data.get("samples", [])
        
        if not old_evaluations:
            self.console.print("[yellow]No old evaluations found in file.[/yellow]")
            return
        
        self.console.print(f"[green]✅ Loaded {len(old_evaluations)} old evaluations (1-5 scoring)[/green]\n")
        
        # Load or generate new evaluations
        if new_debug_path and Path(new_debug_path).exists():
            self.console.print(f"[dim]Loading new 0-1 scoring results from {new_debug_path}...[/dim]")
            try:
                with open(new_debug_path, 'r') as f:
                    new_data = json.load(f)
                new_evaluations = new_data.get("all_evaluations", [])
                new_samples = new_data.get("samples", [])
                self.console.print(f"[green]✅ Loaded {len(new_evaluations)} new evaluations (0-1 scoring)[/green]\n")
            except Exception as e:
                self.console.print(f"[red]Error loading new evaluations: {e}[/red]")
                return
        else:
            self.console.print("[yellow]⚠️  New evaluation results not provided.[/yellow]")
            self.console.print("[dim]To compare methodologies, you need to run a new evaluation with binary scoring.[/dim]")
            self.console.print("[dim]Recommended: Save old results first, then run new evaluation:[/dim]")
            self.console.print("[dim]  1. Rename current file: mv quality_eval_debug.json quality_eval_debug_1-5.json[/dim]")
            self.console.print("[dim]  2. Run new eval: python -m time_calibration_agent.cli quality-eval --dataset <dataset> --debug --output quality_eval_debug_0-1.json[/dim]")
            self.console.print("[dim]  3. Compare: python -m time_calibration_agent.cli compare-scoring --old quality_eval_debug_1-5.json --new quality_eval_debug_0-1.json[/dim]\n")
            return
        
        if len(old_evaluations) != len(new_evaluations):
            min_len = min(len(old_evaluations), len(new_evaluations))
            self.console.print(f"[yellow]⚠️  Warning: Different number of evaluations (old: {len(old_evaluations)}, new: {len(new_evaluations)})[/yellow]")
            self.console.print(f"[dim]Comparing first {min_len} evaluations...[/dim]\n")
            old_evaluations = old_evaluations[:min_len]
            new_evaluations = new_evaluations[:min_len]
        
        # Run comparison
        self.console.print("[bold]Running comparison analysis...[/bold]\n")
        comparison = compare_scoring_methodologies(
            old_evaluations, new_evaluations, old_samples, new_samples
        )
        
        if "error" in comparison:
            self.console.print(f"[red]Error in comparison: {comparison['error']}[/red]")
            return
        
        # Display results
        self.console.print("[bold]📊 Comparison Results[/bold]\n")
        
        # Agreement metrics
        agreement_table = Table.grid(padding=(0, 2))
        agreement_table.add_column(style="dim", width=30)
        agreement_table.add_column()
        
        agreement_table.add_row("Agreement Percentage:", f"[bold]{comparison['agreement_between_systems']:.1f}%[/bold]")
        agreement_table.add_row("Cohen's Kappa:", f"[bold]{comparison['cohens_kappa']:.3f}[/bold]")
        
        kappa_interpretation = {
            (0.81, 1.0): "Almost perfect agreement",
            (0.61, 0.80): "Substantial agreement",
            (0.41, 0.60): "Moderate agreement",
            (0.21, 0.40): "Fair agreement",
            (0.0, 0.20): "Slight agreement",
            (-1.0, 0.0): "Poor agreement"
        }
        
        kappa_val = comparison['cohens_kappa']
        interpretation = "Unknown"
        for (low, high), desc in kappa_interpretation.items():
            if low <= kappa_val <= high:
                interpretation = desc
                break
        
        agreement_table.add_row("Kappa Interpretation:", interpretation)
        
        self.console.print(Panel(
            agreement_table,
            title="[bold]Agreement Metrics[/bold]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Score distributions
        dist_table = Table(title="Score Distributions", box=box.ROUNDED, show_header=True)
        dist_table.add_column("System", style="cyan")
        dist_table.add_column("Average Score", justify="right")
        dist_table.add_column("Binary Equivalent", justify="right")
        dist_table.add_column("Good % (1)", justify="right", style="green")
        dist_table.add_column("Poor % (0)", justify="right", style="red")
        
        old_sys = comparison['old_system']
        new_sys = comparison['new_system']
        
        old_good_pct = old_sys['discrimination'].get('good_percentage', 0)
        new_good_pct = new_sys['discrimination'].get('good_percentage', 0)
        
        dist_table.add_row(
            "Old (1-5)",
            f"{old_sys['average_score']:.2f}",
            f"{old_sys['average_binary_equivalent']:.2f}",
            f"{old_good_pct:.1f}%",
            f"{100 - old_good_pct:.1f}%"
        )
        dist_table.add_row(
            "New (0-1)",
            f"{new_sys['average_score']:.2f}",
            "N/A",
            f"{new_good_pct:.1f}%",
            f"{100 - new_good_pct:.1f}%"
        )
        
        self.console.print(dist_table)
        self.console.print()
        
        # Variance improvements
        improvements = comparison.get('improvements', {})
        variance_reduction = improvements.get('variance_reduction', {})
        
        if variance_reduction:
            var_table = Table(title="Variance Reduction by Dimension", box=box.ROUNDED, show_header=True)
            var_table.add_column("Dimension", style="cyan")
            var_table.add_column("Old Variance", justify="right")
            var_table.add_column("New Variance", justify="right")
            var_table.add_column("Reduction", justify="right", style="green")
            
            old_vars = old_sys.get('dimension_variances', {})
            new_vars = new_sys.get('dimension_variances', {})
            
            for dim in ["reasonableness", "consistency", "range", "category"]:
                old_var = old_vars.get(dim, 0)
                new_var = new_vars.get(dim, 0)
                reduction = variance_reduction.get(dim, 0)
                
                var_table.add_row(
                    dim.capitalize(),
                    f"{old_var:.4f}",
                    f"{new_var:.4f}",
                    f"{reduction:.4f}" if reduction > 0 else f"{reduction:.4f}"
                )
            
            self.console.print(var_table)
            self.console.print()
        
        # Overall clarity improvement
        clarity = improvements.get('clarity_improvement', {})
        if clarity:
            clarity_table = Table.grid(padding=(0, 2))
            clarity_table.add_column(style="dim", width=30)
            clarity_table.add_column()
            
            old_avg_var = clarity.get('old_avg_dimension_variance', 0)
            new_avg_var = clarity.get('new_avg_dimension_variance', 0)
            improvement = old_avg_var - new_avg_var
            
            clarity_table.add_row("Old Avg Dimension Variance:", f"{old_avg_var:.4f}")
            clarity_table.add_row("New Avg Dimension Variance:", f"{new_avg_var:.4f}")
            clarity_table.add_row("Variance Reduction:", f"[green]{improvement:.4f}[/green]" if improvement > 0 else f"[red]{improvement:.4f}[/red]")
            
            self.console.print(Panel(
                clarity_table,
                title="[bold]Overall Clarity Improvement[/bold]",
                border_style="green" if improvement > 0 else "yellow"
            ))
            self.console.print()
        
        # Summary
        summary_panel = Panel(
            f"[bold]Summary:[/bold]\n\n"
            f"• Agreement: {comparison['agreement_between_systems']:.1f}% ({interpretation})\n"
            f"• Binary scoring shows {'improved' if improvement > 0 else 'similar'} consistency "
            f"({'reduced' if improvement > 0 else 'maintained'} variance by {abs(improvement):.4f})\n"
            f"• Good quality rate: Old {old_good_pct:.1f}% → New {new_good_pct:.1f}%",
            title="[bold]Key Findings[/bold]",
            border_style="cyan"
        )
        self.console.print(summary_panel)
        self.console.print()
        
        # Show disagreements
        from time_calibration_agent.quality_analysis import find_disagreements
        self.console.print("[bold]🔍 Analyzing Disagreements...[/bold]\n")
        disagreements = find_disagreements(old_evaluations, new_evaluations, old_samples, new_samples)
        
        if "error" not in disagreements:
            self._display_disagreements(disagreements)
            
            # Export detailed disagreements to file
            self._export_disagreements(disagreements, old_samples, new_samples)
    
    def _display_disagreements(self, disagreements: Dict):
        """Display disagreement analysis between old and new scoring systems."""
        total_disagreements = disagreements.get("total_disagreements", 0)
        total_agreements = disagreements.get("total_agreements", 0)
        agreement_rate = disagreements.get("agreement_rate", 0)
        
        # Summary table
        summary_table = Table.grid(padding=(0, 2))
        summary_table.add_column(style="dim", width=30)
        summary_table.add_column()
        
        summary_table.add_row("Total Disagreements:", f"[bold]{total_disagreements}[/bold]")
        summary_table.add_row("Total Agreements:", f"[bold]{total_agreements}[/bold]")
        summary_table.add_row("Agreement Rate:", f"{agreement_rate:.1f}%")
        
        breakdown = disagreements.get("disagreement_breakdown", {})
        summary_table.add_row("", "")
        summary_table.add_row("Old Poor → New Good:", f"[yellow]{breakdown.get('old_poor_new_good', 0)}[/yellow]")
        summary_table.add_row("Old Good → New Poor:", f"[yellow]{breakdown.get('old_good_new_poor', 0)}[/yellow]")
        
        self.console.print(Panel(
            summary_table,
            title="[bold]Disagreement Summary[/bold]",
            border_style="yellow"
        ))
        self.console.print()
        
        # Show breakdown by old score range
        by_range = disagreements.get("by_old_score_range", {})
        if by_range:
            range_table = Table(title="Disagreements by Old Score Range", box=box.ROUNDED, show_header=True)
            range_table.add_column("Old Score Range", style="cyan")
            range_table.add_column("Count", justify="right")
            
            for score_range, count in sorted(by_range.items()):
                range_table.add_row(score_range, str(count))
            
            self.console.print(range_table)
            self.console.print()
        
        # Show borderline cases (old score = 3)
        borderline = disagreements.get("borderline_cases", [])
        if borderline:
            self.console.print(f"[bold]📊 Borderline Cases (Old Score = 3): {len(borderline)}[/bold]\n")
            
            examples = disagreements.get("disagreement_examples", {}).get("borderline", [])[:5]
            for i, example in enumerate(examples, 1):
                task = example.get("task", "Unknown task")[:100] + ("..." if len(example.get("task", "")) > 100 else "")
                old_score = example.get("old_score", 0)
                new_score = example.get("new_score", 0)
                old_reasoning = example.get("old_evaluation", {}).get("reasoning", "")[:200]
                new_reasoning = example.get("new_evaluation", {}).get("reasoning", "")[:200]
                
                example_table = Table.grid(padding=(0, 2))
                example_table.add_column(style="dim", width=20)
                example_table.add_column()
                
                example_table.add_row("Task:", task)
                example_table.add_row("Old Score (1-5):", f"[yellow]{old_score}/5[/yellow]")
                example_table.add_row("New Score (0-1):", f"[yellow]{new_score}[/yellow]")
                example_table.add_row("", "")
                example_table.add_row("Old Reasoning:", old_reasoning + ("..." if len(example.get("old_evaluation", {}).get("reasoning", "")) > 200 else ""))
                example_table.add_row("New Reasoning:", new_reasoning + ("..." if len(example.get("new_evaluation", {}).get("reasoning", "")) > 200 else ""))
                
                self.console.print(Panel(
                    example_table,
                    title=f"[bold]Borderline Case {i}[/bold]",
                    border_style="yellow"
                ))
                self.console.print()
        
        # Show examples where old said poor but new says good
        old_poor_new_good = disagreements.get("disagreement_examples", {}).get("old_poor_new_good", [])
        if old_poor_new_good:
            self.console.print(f"[bold]⚠️  Cases: Old Poor (≤3) → New Good (1): {len(old_poor_new_good)}[/bold]\n")
            self.console.print("[dim]These are cases where the old system was stricter.[/dim]\n")
            
            for i, example in enumerate(old_poor_new_good[:3], 1):  # Show top 3
                task = example.get("task", "Unknown task")[:80] + ("..." if len(example.get("task", "")) > 80 else "")
                old_score = example.get("old_score", 0)
                new_score = example.get("new_score", 0)
                
                self.console.print(f"[dim]{i}.[/dim] Old: {old_score}/5 → New: {new_score} | {task}")
            self.console.print()
        
        # Show examples where old said good but new says poor
        old_good_new_poor = disagreements.get("disagreement_examples", {}).get("old_good_new_poor", [])
        if old_good_new_poor:
            self.console.print(f"[bold]⚠️  Cases: Old Good (≥4) → New Poor (0): {len(old_good_new_poor)}[/bold]\n")
            self.console.print("[dim]These are cases where the new system is stricter.[/dim]\n")
            
            for i, example in enumerate(old_good_new_poor[:3], 1):  # Show top 3
                task = example.get("task", "Unknown task")[:80] + ("..." if len(example.get("task", "")) > 80 else "")
                old_score = example.get("old_score", 0)
                new_score = example.get("new_score", 0)
                
                self.console.print(f"[dim]{i}.[/dim] Old: {old_score}/5 → New: {new_score} | {task}")
            self.console.print()
        
        # Note about conversion
        note_panel = Panel(
            "[bold]Note on Score Conversion:[/bold]\n\n"
            "For comparison purposes, old 1-5 scores are converted to binary:\n"
            "• 4-5 → 1 (good)\n"
            "• 1-3 → 0 (poor)\n\n"
            "However, each system calculates scores independently. The conversion\n"
            "is only used to compare agreement between the two systems.",
            title="[dim]Understanding the Comparison[/dim]",
            border_style="dim"
        )
        self.console.print(note_panel)
        self.console.print()
    
    def _export_disagreements(self, disagreements: Dict, old_samples: Optional[List[Dict]] = None,
                             new_samples: Optional[List[Dict]] = None):
        """Export detailed disagreement analysis to JSON file."""
        import json
        from pathlib import Path
        from datetime import datetime
        
        # Prepare detailed export data
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "summary": {
                "total_disagreements": disagreements.get("total_disagreements", 0),
                "total_agreements": disagreements.get("total_agreements", 0),
                "agreement_rate": disagreements.get("agreement_rate", 0),
                "disagreement_breakdown": disagreements.get("disagreement_breakdown", {}),
                "by_old_score_range": disagreements.get("by_old_score_range", {})
            },
            "borderline_cases": [],
            "all_disagreements": []
        }
        
        # Export all borderline cases with full details
        borderline = disagreements.get("borderline_cases", [])
        for case in borderline:
            idx = case.get("index", 0)
            case_data = {
                "index": idx,
                "old_score": case.get("old_score", 0),
                "old_binary": case.get("old_binary", 0),
                "new_score": case.get("new_score", 0),
                "task": case.get("task", ""),
                "estimate": case.get("estimate", {}),
                "old_evaluation": {
                    "score": case.get("old_evaluation", {}).get("score", 0),
                    "reasonableness_score": case.get("old_evaluation", {}).get("reasonableness_score", 0),
                    "consistency_score": case.get("old_evaluation", {}).get("consistency_score", 0),
                    "range_score": case.get("old_evaluation", {}).get("range_score", 0),
                    "category_score": case.get("old_evaluation", {}).get("category_score", 0),
                    "reasoning": case.get("old_evaluation", {}).get("reasoning", ""),
                    "checks": case.get("old_evaluation", {}).get("checks", {})
                },
                "new_evaluation": {
                    "score": case.get("new_evaluation", {}).get("score", 0),
                    "reasonableness_score": case.get("new_evaluation", {}).get("reasonableness_score", 0),
                    "consistency_score": case.get("new_evaluation", {}).get("consistency_score", 0),
                    "range_score": case.get("new_evaluation", {}).get("range_score", 0),
                    "category_score": case.get("new_evaluation", {}).get("category_score", 0),
                    "reasoning": case.get("new_evaluation", {}).get("reasoning", ""),
                    "checks": case.get("new_evaluation", {}).get("checks", {})
                }
            }
            export_data["borderline_cases"].append(case_data)
        
        # Export all disagreements with full details
        all_disagreements = disagreements.get("all_disagreements", [])
        for case in all_disagreements:
            idx = case.get("index", 0)
            case_data = {
                "index": idx,
                "old_score": case.get("old_score", 0),
                "old_binary": case.get("old_binary", 0),
                "new_score": case.get("new_score", 0),
                "disagreement_type": case.get("type", ""),
                "task": case.get("task", ""),
                "estimate": case.get("estimate", {}),
                "old_evaluation": {
                    "score": case.get("old_evaluation", {}).get("score", 0),
                    "reasonableness_score": case.get("old_evaluation", {}).get("reasonableness_score", 0),
                    "consistency_score": case.get("old_evaluation", {}).get("consistency_score", 0),
                    "range_score": case.get("old_evaluation", {}).get("range_score", 0),
                    "category_score": case.get("old_evaluation", {}).get("category_score", 0),
                    "reasoning": case.get("old_evaluation", {}).get("reasoning", ""),
                    "checks": case.get("old_evaluation", {}).get("checks", {})
                },
                "new_evaluation": {
                    "score": case.get("new_evaluation", {}).get("score", 0),
                    "reasonableness_score": case.get("new_evaluation", {}).get("reasonableness_score", 0),
                    "consistency_score": case.get("new_evaluation", {}).get("consistency_score", 0),
                    "range_score": case.get("new_evaluation", {}).get("range_score", 0),
                    "category_score": case.get("new_evaluation", {}).get("category_score", 0),
                    "reasoning": case.get("new_evaluation", {}).get("reasoning", ""),
                    "checks": case.get("new_evaluation", {}).get("checks", {})
                }
            }
            export_data["all_disagreements"].append(case_data)
        
        # Save to file
        output_path = "scoring_disagreements_analysis.json"
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        self.console.print(Panel(
            f"[green]✅ Detailed disagreement analysis exported to: {output_path}[/green]\n"
            f"[dim]Contains {len(borderline)} borderline cases and {len(all_disagreements)} total disagreements[/dim]\n"
            "[dim]Includes full task descriptions, estimates, scores, and reasoning from both systems.[/dim]",
            border_style="green"
        ))
        self.console.print()
    
    def compare_quality_strategies(self, dataset_path: str):
        """Compare all context strategies on quality metrics."""
        from time_calibration_agent.agent import ContextStrategy
        
        # Load dataset
        generator = TestDatasetGenerator()
        try:
            test_prompts = generator.load_dataset(dataset_path)
        except Exception as e:
            self.console.print(f"[red]Error loading dataset: {e}[/red]\n")
            return
        
        strategies = [
            ContextStrategy.MINIMAL,
            ContextStrategy.RECENT_N,
            ContextStrategy.SUMMARIZED,
            ContextStrategy.CATEGORY_FILTERED,
            ContextStrategy.SIMILARITY_BASED
        ]
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]⚖️  QUALITY STRATEGY COMPARISON[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        quality_evaluator = QualityEvaluator()
        strategy_results = {}
        
        for strategy in strategies:
            strategy_name = strategy.value
            self.console.print(f"[dim]Testing strategy: {strategy_name}...[/dim]")
            
            estimates = []
            task_descriptions = []
            
            for prompt_data in test_prompts:
                prompt_text = prompt_data.get('prompt', '') if isinstance(prompt_data, dict) else prompt_data
                if not prompt_text:
                    continue
                
                estimate = self.agent.estimate_task(
                    prompt_text,
                    context_strategy=strategy
                )
                estimates.append(estimate)
                task_descriptions.append(prompt_text)
            
            # Evaluate quality
            eval_results = []
            for task_desc, estimate in zip(task_descriptions, estimates):
                eval_result = quality_evaluator.evaluate_estimate_quality(task_desc, estimate)
                eval_results.append(eval_result)
            
            avg_score = sum(e["score"] for e in eval_results) / len(eval_results) if eval_results else 0
            
            strategy_results[strategy_name] = {
                "average_score": avg_score,
                "total": len(eval_results),
                "results": eval_results
            }
        
        # Display comparison
        comp_table = Table(title="Strategy Quality Comparison", box=box.ROUNDED, show_header=True)
        comp_table.add_column("Strategy", style="cyan")
        comp_table.add_column("Avg Score", justify="right")
        comp_table.add_column("Count", justify="right", style="dim")
        
        sorted_strategies = sorted(strategy_results.items(), key=lambda x: x[1]["average_score"], reverse=True)
        
        for strategy_name, results in sorted_strategies:
            score = results["average_score"]
            style = "bold green" if strategy_name == sorted_strategies[0][0] else None
            comp_table.add_row(
                f"[{style}]{strategy_name}[/{style}]" if style else strategy_name,
                f"{score:.2f}",
                str(results["total"])
            )
        
        self.console.print(comp_table)
        self.console.print()
        
        best_strategy = sorted_strategies[0][0]
        self.console.print(Panel(
            f"[green]🏆 Best Strategy: {best_strategy} (Score: {sorted_strategies[0][1]['average_score']:.2f}, binary: 0=poor, 1=good)[/green]",
            border_style="green"
        ))
        self.console.print()
    
    def show_evaluation(self, export_path: Optional[str] = None):
        """Show evaluation metrics for completed tasks."""
        completed_tasks = self.storage.get_completed_tasks()
        
        if not completed_tasks:
            self.console.print(Panel(
                "[yellow]No completed tasks available for evaluation.[/yellow]\n"
                "[dim]Complete some tasks first by logging actual time.[/dim]",
                border_style="yellow"
            ))
            self.console.print()
            return
        
        # Run evaluation
        metrics = EvaluationMetrics(completed_tasks)
        results = metrics.evaluate_all()
        
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]📊 EVALUATION METRICS[/bold cyan]",
            border_style="cyan"
        ))
        self.console.print()
        
        # Overall metrics
        overall = results['overall']
        overall_table = Table.grid(padding=(0, 2))
        overall_table.add_column(style="dim", width=20)
        overall_table.add_column()
        
        overall_table.add_row("📈 Mean Absolute Error:", f"[bold]{overall['mae']:.1f}[/bold] minutes")
        overall_table.add_row("📊 Mean Absolute % Error:", f"[bold]{overall['mape']:.1f}%[/bold]")
        
        within_20 = overall['within_20pct']
        within_20_color = "green" if within_20['percentage'] >= 50 else "yellow" if within_20['percentage'] >= 30 else "red"
        overall_table.add_row("✅ Within ±20%:", 
                             f"[{within_20_color}]{within_20['percentage']:.1f}%[/{within_20_color}] "
                             f"({within_20['count']}/{within_20['total']} tasks)")
        
        within_10 = overall['within_10pct']
        within_10_color = "green" if within_10['percentage'] >= 50 else "yellow" if within_10['percentage'] >= 30 else "red"
        overall_table.add_row("🎯 Within ±10%:", 
                             f"[{within_10_color}]{within_10['percentage']:.1f}%[/{within_10_color}] "
                             f"({within_10['count']}/{within_10['total']} tasks)")
        
        overall_table.add_row("", "")
        overall_table.add_row("📋 Total Tasks:", f"[bold]{overall['total_tasks']}[/bold]")
        
        self.console.print(Panel(
            overall_table,
            title="[bold]Overall Performance[/bold]",
            border_style="blue"
        ))
        self.console.print()
        
        # Calibration drift
        drift = results['calibration_drift']
        if drift['early_count'] > 0 and drift['recent_count'] > 0:
            drift_table = Table.grid(padding=(0, 2))
            drift_table.add_column(style="dim", width=20)
            drift_table.add_column()
            
            drift_table.add_row("📉 Early MAPE:", f"{drift['early_mape']:.1f}%")
            drift_table.add_row("📈 Recent MAPE:", f"{drift['recent_mape']:.1f}%")
            
            drift_value = drift['drift']
            drift_color = "green" if drift['improving'] else "red"
            drift_arrow = "⬇️" if drift['improving'] else "⬆️"
            drift_table.add_row("🔄 Calibration Drift:", 
                              f"[{drift_color}]{drift_value:+.1f}%[/{drift_color}] {drift_arrow}")
            
            trend_text = "Improving" if drift['improving'] else "Getting worse"
            drift_table.add_row("📊 Trend:", f"[{drift_color}]{trend_text}[/{drift_color}]")
            
            self.console.print(Panel(
                drift_table,
                title="[bold]Calibration Over Time[/bold]",
                border_style="cyan"
            ))
            self.console.print()
        
        # By category
        by_category = results.get('by_category', {})
        if by_category:
            cat_table = Table(title="Performance by Category", box=box.ROUNDED, show_header=True)
            cat_table.add_column("Category", style="cyan")
            cat_table.add_column("MAE", justify="right")
            cat_table.add_column("MAPE", justify="right")
            cat_table.add_column("±20%", justify="right")
            cat_table.add_column("Count", justify="right", style="dim")
            
            for category, cat_metrics in sorted(by_category.items(), 
                                                key=lambda x: x[1]['count'], 
                                                reverse=True):
                cat_table.add_row(
                    category,
                    f"{cat_metrics['mae']:.1f} min",
                    f"{cat_metrics['mape']:.1f}%",
                    f"{cat_metrics['within_20pct']['percentage']:.1f}%",
                    str(cat_metrics['count'])
                )
            
            self.console.print(cat_table)
            self.console.print()
        
        # By ambiguity
        by_ambiguity = results.get('by_ambiguity', {})
        if by_ambiguity:
            amb_table = Table(title="Performance by Ambiguity", box=box.ROUNDED, show_header=True)
            amb_table.add_column("Ambiguity", style="cyan")
            amb_table.add_column("MAE", justify="right")
            amb_table.add_column("MAPE", justify="right")
            amb_table.add_column("±20%", justify="right")
            amb_table.add_column("Count", justify="right", style="dim")
            
            for ambiguity, amb_metrics in sorted(by_ambiguity.items(), 
                                                 key=lambda x: x[1]['count'], 
                                                 reverse=True):
                amb_table.add_row(
                    ambiguity,
                    f"{amb_metrics['mae']:.1f} min",
                    f"{amb_metrics['mape']:.1f}%",
                    f"{amb_metrics['within_20pct']['percentage']:.1f}%",
                    str(amb_metrics['count'])
                )
            
            self.console.print(amb_table)
            self.console.print()
        
        # Export if requested
        if export_path:
            import json
            with open(export_path, 'w') as f:
                json.dump(results, f, indent=2)
            self.console.print(Panel(
                f"[green]✅ Evaluation results exported to: {export_path}[/green]",
                border_style="green"
            ))
            self.console.print()


def main():
    """Main CLI entry point."""
    cli = TimeCalibrationCLI()
    console = Console()
    
    if len(sys.argv) < 2:
        console.print(Panel(
            "[bold cyan]Time Calibration Agent[/bold cyan]\n\n"
            "[bold]Usage:[/bold]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]estimate[/yellow] \"task description\"\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]estimate[/yellow] \"task 1\" \"task 2\" ...\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]log[/yellow] <task_id_or_query> <minutes>\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]replan[/yellow] \"context text\" [--session label] [--date YYYY-MM-DD]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]new-session[/yellow] \"context text\" [--session label] [--date YYYY-MM-DD]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]session[/yellow] [--session label] [--date YYYY-MM-DD]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]status[/yellow]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]history[/yellow] [limit]\n"
            "  [dim]Flags: --debug to show extracted tasks/estimates[/dim]\n"
            "  [dim]If --session is omitted, the last active session is used.[/dim]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]eval[/yellow] [--export path.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]experiment[/yellow] [--output path.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]test-dataset[/yellow] generate [--n 50] [--output path.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]quality-eval[/yellow] [--dataset path.json] [--strategy recent_n] [--evaluator ai|human|both] [--output path.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]quality-compare[/yellow] [--dataset path.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]analyze-quality[/yellow] [--file quality_eval_debug.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]compare-scoring[/yellow] [--old old_debug.json] [--new new_debug.json]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]clear[/yellow]\n\n"
            "[bold]Examples:[/bold]\n"
            "  [dim]python -m time_calibration_agent.cli estimate \"Write blog post about time estimation\"[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli log task_1_1234567890 45[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli new-session \"It's 2pm. I did X. I still need A, B. Dinner at 7.\"[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli replan \"It's 3pm. I finished A. Need B.\"[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli log \"the writing task\" 45[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli status[/dim]",
            border_style="cyan",
            title="[bold]Help[/bold]"
        ))
        return
    
    command = sys.argv[1].lower()
    
    if command == "estimate":
        if len(sys.argv) < 3:
            console.print("[red]Error: Please provide at least one task description[/red]")
            return
        tasks = sys.argv[2:]
        cli.estimate_tasks(tasks)
    
    elif command == "log":
        if len(sys.argv) < 4:
            console.print("[red]Error: Usage: log <task_id_or_query> <minutes>[/red]")
            console.print("\n[yellow]Examples:[/yellow]")
            console.print("  [dim]log task_1_1234567890 45[/dim]")
            console.print("  [dim]log \"the writing task\" 45[/dim]")
            console.print("  [dim]log \"the task I just did\" 30[/dim]")
            console.print("  [dim]log the writing task 45  (quotes optional)[/dim]")
            return
        try:
            # The last argument should be minutes (a number)
            # Everything before that is the task identifier/query
            minutes = int(sys.argv[-1])
            task_identifier = " ".join(sys.argv[2:-1])
            
            # If task_identifier is empty (shouldn't happen with len check above, but just in case)
            if not task_identifier:
                console.print("[red]Error: Please provide a task ID or query[/red]")
                return
                
            cli.log_time(task_identifier, minutes)
        except ValueError:
            console.print("[red]Error: Minutes must be a number[/red]")

    elif command == "replan":
        if len(sys.argv) < 3:
            console.print("[red]Error: Please provide context text for replanning[/red]")
            return
        session_label = None
        date_override = None
        debug = False
        raw_parts = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session" and i + 1 < len(sys.argv):
                session_label = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--date" and i + 1 < len(sys.argv):
                date_override = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--debug":
                debug = True
                i += 1
            else:
                raw_parts.append(sys.argv[i])
                i += 1
        raw_text = " ".join(raw_parts)
        cli.plan_day(
            raw_text,
            session_label=session_label,
            date_override=date_override,
            require_existing=True,
            debug=debug,
        )

    elif command == "new-session" or command == "newsession":
        if len(sys.argv) < 3:
            console.print("[red]Error: Please provide context text for a new session[/red]")
            return
        session_label = None
        date_override = None
        debug = False
        raw_parts = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session" and i + 1 < len(sys.argv):
                session_label = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--date" and i + 1 < len(sys.argv):
                date_override = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--debug":
                debug = True
                i += 1
            else:
                raw_parts.append(sys.argv[i])
                i += 1
        raw_text = " ".join(raw_parts)
        cli.plan_day(
            raw_text,
            session_label=session_label,
            date_override=date_override,
            overwrite=True,
            debug=debug,
        )

    elif command == "session":
        session_label = None
        date_override = None
        debug = False
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session" and i + 1 < len(sys.argv):
                session_label = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--date" and i + 1 < len(sys.argv):
                date_override = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--debug":
                debug = True
                i += 1
            else:
                i += 1
        cli.show_session(session_label=session_label, date_override=date_override, debug=debug)
    
    elif command == "status":
        cli.show_status()
    
    elif command == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cli.show_history(limit)
    
    elif command == "eval" or command == "evaluation":
        # Check for --export flag
        export_path = None
        if len(sys.argv) > 2:
            if sys.argv[2] == "--export" and len(sys.argv) > 3:
                export_path = sys.argv[3]
        cli.show_evaluation(export_path=export_path)
    
    elif command == "experiment" or command == "exp":
        # Check for --output flag
        output_path = None
        if len(sys.argv) > 2:
            if sys.argv[2] == "--output" and len(sys.argv) > 3:
                output_path = sys.argv[3]
            elif sys.argv[2].endswith(".json"):
                output_path = sys.argv[2]
        
        cli.run_experiments(output_path=output_path)
    
    elif command == "test-dataset" or command == "testdataset":
        if len(sys.argv) > 2 and sys.argv[2] == "generate":
            n = 50
            output_path = None
            
            # Parse arguments
            i = 3
            while i < len(sys.argv):
                if sys.argv[i] == "--n" and i + 1 < len(sys.argv):
                    n = int(sys.argv[i + 1])
                    i += 2
                elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                    output_path = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i].endswith(".json"):
                    output_path = sys.argv[i]
                    i += 1
                else:
                    i += 1
            
            cli.generate_test_dataset(n=n, output_path=output_path)
        else:
            console.print("[red]Usage: test-dataset generate [--n 50] [--output path.json][/red]")
    
    elif command == "quality-eval" or command == "qualityeval":
        dataset_path = None
        strategy_name = "recent_n"
        evaluator = "ai"
        debug = False
        output_path = None
        scoring_mode = "binary"
        
        # Parse arguments
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--dataset" and i + 1 < len(sys.argv):
                dataset_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--strategy" and i + 1 < len(sys.argv):
                strategy_name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--evaluator" and i + 1 < len(sys.argv):
                evaluator = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--scoring-mode" and i + 1 < len(sys.argv):
                scoring_mode = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--debug":
                debug = True
                i += 1
            elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i].endswith(".json") and not dataset_path:
                dataset_path = sys.argv[i]
                i += 1
            else:
                i += 1
        
        if not dataset_path:
            console.print("[red]Error: Please provide a dataset file with --dataset[/red]")
            return
        
        cli.run_quality_evaluation(dataset_path, strategy_name, evaluator, debug, output_path, scoring_mode)
    
    elif command == "quality-compare" or command == "qualitycompare":
        dataset_path = None
        
        # Parse arguments
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--dataset" and i + 1 < len(sys.argv):
                dataset_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i].endswith(".json") and not dataset_path:
                dataset_path = sys.argv[i]
                i += 1
            else:
                i += 1
        
        if not dataset_path:
            console.print("[red]Error: Please provide a dataset file with --dataset[/red]")
            return
        
        cli.compare_quality_strategies(dataset_path)
    
    elif command == "analyze-quality" or command == "analyzequality":
        debug_path = "quality_eval_debug.json"
        
        # Parse arguments
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--file" and i + 1 < len(sys.argv):
                debug_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i].endswith(".json") and debug_path == "quality_eval_debug.json":
                debug_path = sys.argv[i]
                i += 1
            else:
                i += 1
        
        cli.analyze_quality_results(debug_path)
    
    elif command == "compare-scoring" or command == "comparescoring":
        old_debug_path = "quality_eval_debug.json"
        new_debug_path = None
        
        # Parse arguments
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--old" and i + 1 < len(sys.argv):
                old_debug_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--new" and i + 1 < len(sys.argv):
                new_debug_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i].endswith(".json") and old_debug_path == "quality_eval_debug.json":
                old_debug_path = sys.argv[i]
                i += 1
            else:
                i += 1
        
        cli.compare_scoring_methodologies(old_debug_path, new_debug_path)
    
    elif command == "clear":
        cli.clear_pending()
    
    else:
        console.print(f"[red]Unknown command: {command}[/red]")


if __name__ == "__main__":
    main()

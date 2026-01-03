"""
Command-line interface for the Time Calibration Agent.
"""

import sys
from typing import List, Optional
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


class TimeCalibrationCLI:
    """CLI interface for interacting with the calibration agent."""
    
    def __init__(self, data_file: str = "calibration_data.json"):
        self.storage = TaskStorage(data_file)
        self.agent = EstimationAgent()
        self.learner = CalibrationLearner()
        self.console = Console()
    
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
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]status[/yellow]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]history[/yellow] [limit]\n"
            "  [cyan]python -m time_calibration_agent.cli[/cyan] [yellow]clear[/yellow]\n\n"
            "[bold]Examples:[/bold]\n"
            "  [dim]python -m time_calibration_agent.cli estimate \"Write blog post about time estimation\"[/dim]\n"
            "  [dim]python -m time_calibration_agent.cli log task_1_1234567890 45[/dim]\n"
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
    
    elif command == "status":
        cli.show_status()
    
    elif command == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cli.show_history(limit)
    
    elif command == "clear":
        cli.clear_pending()
    
    else:
        console.print(f"[red]Unknown command: {command}[/red]")


if __name__ == "__main__":
    main()

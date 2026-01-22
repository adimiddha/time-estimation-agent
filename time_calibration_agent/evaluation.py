"""
Evaluation framework for measuring estimation accuracy and calibration.
Provides metrics like MAE, MAPE, % within threshold, and calibration drift.
"""

from typing import Dict, List, Optional
from enum import Enum
import statistics


class EvaluationMetrics:
    """Computes evaluation metrics for time estimation accuracy."""
    
    def __init__(self, completed_tasks: List[Dict]):
        """
        Initialize with completed tasks.
        
        Args:
            completed_tasks: List of task dicts with 'estimated_minutes' and 'actual_minutes'
        """
        self.completed_tasks = [
            task for task in completed_tasks 
            if task.get('actual_minutes') is not None and task.get('estimated_minutes') is not None
        ]
    
    def calculate_mae(self) -> float:
        """
        Calculate Mean Absolute Error (MAE) in minutes.
        
        Returns:
            Mean absolute error in minutes
        """
        if not self.completed_tasks:
            return 0.0
        
        errors = [
            abs(task['actual_minutes'] - task['estimated_minutes'])
            for task in self.completed_tasks
        ]
        return statistics.mean(errors)
    
    def calculate_mape(self) -> float:
        """
        Calculate Mean Absolute Percentage Error (MAPE).
        
        Returns:
            MAPE as a percentage (e.g., 15.5 means 15.5%)
        """
        if not self.completed_tasks:
            return 0.0
        
        percentage_errors = []
        for task in self.completed_tasks:
            estimated = task['estimated_minutes']
            if estimated > 0:
                error_pct = abs((task['actual_minutes'] - estimated) / estimated) * 100
                percentage_errors.append(error_pct)
        
        if not percentage_errors:
            return 0.0
        
        return statistics.mean(percentage_errors)
    
    def calculate_within_threshold(self, threshold: float = 0.2) -> Dict[str, float]:
        """
        Calculate percentage of tasks within ±threshold (e.g., ±20%).
        
        Args:
            threshold: Threshold as a decimal (0.2 = 20%)
            
        Returns:
            Dict with 'percentage' and 'count' keys
        """
        if not self.completed_tasks:
            return {"percentage": 0.0, "count": 0, "total": 0}
        
        within_count = 0
        for task in self.completed_tasks:
            estimated = task['estimated_minutes']
            if estimated > 0:
                error_ratio = abs((task['actual_minutes'] - estimated) / estimated)
                if error_ratio <= threshold:
                    within_count += 1
        
        percentage = (within_count / len(self.completed_tasks)) * 100
        return {
            "percentage": percentage,
            "count": within_count,
            "total": len(self.completed_tasks)
        }
    
    def calculate_calibration_drift(self) -> Dict[str, float]:
        """
        Calculate how accuracy changes over time (calibration drift).
        
        Returns:
            Dict with metrics about drift over time
        """
        if len(self.completed_tasks) < 3:
            return {
                "early_mape": 0.0,
                "recent_mape": 0.0,
                "drift": 0.0,
                "improving": False
            }
        
        # Split into early and recent halves
        mid_point = len(self.completed_tasks) // 2
        early_tasks = self.completed_tasks[:mid_point]
        recent_tasks = self.completed_tasks[mid_point:]
        
        # Calculate MAPE for each half
        early_metrics = EvaluationMetrics(early_tasks)
        recent_metrics = EvaluationMetrics(recent_tasks)
        
        early_mape = early_metrics.calculate_mape()
        recent_mape = recent_metrics.calculate_mape()
        
        drift = recent_mape - early_mape  # Positive = getting worse, negative = improving
        improving = drift < 0
        
        return {
            "early_mape": early_mape,
            "recent_mape": recent_mape,
            "drift": drift,
            "improving": improving,
            "early_count": len(early_tasks),
            "recent_count": len(recent_tasks)
        }
    
    def calculate_by_category(self) -> Dict[str, Dict]:
        """
        Calculate metrics broken down by task category.
        
        Returns:
            Dict mapping category to metrics dict
        """
        category_tasks = {}
        for task in self.completed_tasks:
            category = task.get('category', 'general')
            if category not in category_tasks:
                category_tasks[category] = []
            category_tasks[category].append(task)
        
        category_metrics = {}
        for category, tasks in category_tasks.items():
            if len(tasks) >= 1:  # Need at least 1 task
                metrics = EvaluationMetrics(tasks)
                category_metrics[category] = {
                    "mae": metrics.calculate_mae(),
                    "mape": metrics.calculate_mape(),
                    "within_20pct": metrics.calculate_within_threshold(0.2),
                    "count": len(tasks)
                }
        
        return category_metrics
    
    def calculate_by_ambiguity(self) -> Dict[str, Dict]:
        """
        Calculate metrics broken down by task ambiguity level.
        
        Returns:
            Dict mapping ambiguity to metrics dict
        """
        ambiguity_tasks = {}
        for task in self.completed_tasks:
            ambiguity = task.get('ambiguity', 'moderate')
            if ambiguity not in ambiguity_tasks:
                ambiguity_tasks[ambiguity] = []
            ambiguity_tasks[ambiguity].append(task)
        
        ambiguity_metrics = {}
        for ambiguity, tasks in ambiguity_tasks.items():
            if len(tasks) >= 1:
                metrics = EvaluationMetrics(tasks)
                ambiguity_metrics[ambiguity] = {
                    "mae": metrics.calculate_mae(),
                    "mape": metrics.calculate_mape(),
                    "within_20pct": metrics.calculate_within_threshold(0.2),
                    "count": len(tasks)
                }
        
        return ambiguity_metrics
    
    def evaluate_all(self) -> Dict:
        """
        Run full evaluation suite and return all metrics.
        
        Returns:
            Dict with all evaluation metrics
        """
        return {
            "overall": {
                "mae": self.calculate_mae(),
                "mape": self.calculate_mape(),
                "within_20pct": self.calculate_within_threshold(0.2),
                "within_10pct": self.calculate_within_threshold(0.1),
                "total_tasks": len(self.completed_tasks)
            },
            "calibration_drift": self.calculate_calibration_drift(),
            "by_category": self.calculate_by_category(),
            "by_ambiguity": self.calculate_by_ambiguity()
        }


def compare_strategies(strategy_results: Dict[str, Dict]) -> Dict:
    """
    Compare results from different context strategies.
    
    Args:
        strategy_results: Dict mapping strategy name to evaluation results
        
    Returns:
        Comparison dict with rankings and differences
    """
    if not strategy_results:
        return {}
    
    # Extract key metrics for comparison
    comparisons = {}
    for strategy, results in strategy_results.items():
        overall = results.get("overall", {})
        comparisons[strategy] = {
            "mae": overall.get("mae", 0.0),
            "mape": overall.get("mape", 0.0),
            "within_20pct": overall.get("within_20pct", {}).get("percentage", 0.0)
        }
    
    # Find best strategy for each metric
    best_mae = min(comparisons.items(), key=lambda x: x[1]["mae"])
    best_mape = min(comparisons.items(), key=lambda x: x[1]["mape"])
    best_within_20pct = max(comparisons.items(), key=lambda x: x[1]["within_20pct"])
    
    return {
        "comparisons": comparisons,
        "best_mae": {"strategy": best_mae[0], "value": best_mae[1]["mae"]},
        "best_mape": {"strategy": best_mape[0], "value": best_mape[1]["mape"]},
        "best_within_20pct": {"strategy": best_within_20pct[0], "value": best_within_20pct[1]["within_20pct"]}
    }




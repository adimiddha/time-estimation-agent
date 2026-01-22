"""
Experiment framework for testing different context engineering strategies.
Runs experiments comparing context strategies and saves results for analysis.
"""

import json
from typing import Dict, List, Optional
from pathlib import Path
from time_calibration_agent.agent import EstimationAgent, ContextStrategy
from time_calibration_agent.evaluation import EvaluationMetrics, compare_strategies
from time_calibration_agent.learning import CalibrationLearner
from time_calibration_agent.quality_evaluation import QualityEvaluator
from time_calibration_agent.test_dataset import TestDatasetGenerator


class ContextExperiment:
    """Runs experiments comparing different context strategies."""
    
    def __init__(self, agent: Optional[EstimationAgent] = None, learner: Optional[CalibrationLearner] = None):
        """
        Initialize experiment runner.
        
        Args:
            agent: EstimationAgent instance (creates new one if None)
            learner: CalibrationLearner instance (creates new one if None)
        """
        self.agent = agent or EstimationAgent()
        self.learner = learner or CalibrationLearner()
    
    def run_context_experiment(self, strategy: ContextStrategy, test_tasks: List[Dict],
                               calibration_context: Optional[Dict] = None,
                               context_n: int = 10) -> Dict:
        """
        Run estimation experiment with a specific context strategy.
        
        Args:
            strategy: Context strategy to test
            test_tasks: List of completed tasks to re-estimate
            calibration_context: Calibration data (optional, will be computed if None)
            context_n: Number of tasks for RECENT_N strategy
            
        Returns:
            Dict with estimates and evaluation metrics
        """
        if not test_tasks:
            return {"error": "No test tasks provided"}
        
        # Get historical tasks (all completed tasks except the one being tested)
        all_completed = [t for t in test_tasks if t.get('actual_minutes')]
        
        estimates = []
        errors = []
        
        for i, task in enumerate(all_completed):
            # Use all other tasks as historical context
            historical_context = [t for j, t in enumerate(all_completed) if j != i]
            
            # Get calibration context at the time this task would have been estimated
            # For simplicity, use current calibration_context or compute from historical_context
            task_calibration = calibration_context
            if task_calibration is None and historical_context:
                # Compute calibration from historical tasks up to this point
                temp_learner = CalibrationLearner()
                task_calibration = temp_learner.update_calibration(
                    historical_context,
                    {"user_bias": 0.0, "category_patterns": {}, "ambiguity_patterns": {}, "total_tasks": 0, "total_discrepancy": 0.0}
                )
            
            # Estimate with the specified strategy
            try:
                estimate = self.agent.estimate_task(
                    task_description=task['description'],
                    calibration_context=task_calibration,
                    historical_tasks=historical_context,
                    suggested_category=task.get('category'),
                    context_strategy=strategy,
                    context_n=context_n
                )
                
                # Apply calibration if available
                if task_calibration:
                    estimate = self.learner.apply_calibration_to_estimate(estimate, task_calibration)
                
                estimated_minutes = estimate['estimated_minutes']
                actual_minutes = task['actual_minutes']
                
                error = abs(actual_minutes - estimated_minutes)
                error_pct = abs((actual_minutes - estimated_minutes) / estimated_minutes * 100) if estimated_minutes > 0 else 0
                
                estimates.append({
                    "task_id": task.get('id'),
                    "description": task['description'],
                    "estimated_minutes": estimated_minutes,
                    "actual_minutes": actual_minutes,
                    "error": error,
                    "error_pct": error_pct,
                    "category": task.get('category'),
                    "ambiguity": task.get('ambiguity')
                })
                
            except Exception as e:
                print(f"Warning: Failed to estimate task {task.get('id')}: {e}")
                continue
        
        # Evaluate results
        if estimates:
            # Convert to format expected by EvaluationMetrics
            completed_with_estimates = []
            for est in estimates:
                completed_with_estimates.append({
                    "estimated_minutes": est["estimated_minutes"],
                    "actual_minutes": est["actual_minutes"],
                    "category": est.get("category"),
                    "ambiguity": est.get("ambiguity")
                })
            
            metrics = EvaluationMetrics(completed_with_estimates)
            evaluation_results = metrics.evaluate_all()
            
            return {
                "strategy": strategy.value,
                "estimates": estimates,
                "evaluation": evaluation_results,
                "total_tasks": len(estimates)
            }
        else:
            return {
                "strategy": strategy.value,
                "error": "No successful estimates",
                "total_tasks": 0
            }
    
    def run_all_experiments(self, test_tasks: List[Dict],
                            calibration_context: Optional[Dict] = None,
                            strategies: Optional[List[ContextStrategy]] = None,
                            context_n_values: Optional[List[int]] = None) -> Dict:
        """
        Run experiments with all context strategies and compare results.
        
        Args:
            test_tasks: List of completed tasks to test on
            calibration_context: Calibration data
            strategies: List of strategies to test (default: all strategies)
            context_n_values: List of N values to test for RECENT_N (default: [5, 10, 20])
            
        Returns:
            Dict with results for each strategy and comparison
        """
        if strategies is None:
            strategies = [
                ContextStrategy.MINIMAL,
                ContextStrategy.RECENT_N,
                ContextStrategy.SUMMARIZED,
                ContextStrategy.CATEGORY_FILTERED,
                ContextStrategy.SIMILARITY_BASED
            ]
        
        if context_n_values is None:
            context_n_values = [5, 10, 20]
        
        results = {}
        
        # Run experiments for each strategy
        for strategy in strategies:
            if strategy == ContextStrategy.RECENT_N:
                # Test different N values for RECENT_N
                for n in context_n_values:
                    strategy_name = f"{strategy.value}_n{n}"
                    print(f"Running experiment: {strategy_name}")
                    result = self.run_context_experiment(
                        strategy, test_tasks, calibration_context, context_n=n
                    )
                    results[strategy_name] = result
            else:
                strategy_name = strategy.value
                print(f"Running experiment: {strategy_name}")
                result = self.run_context_experiment(
                    strategy, test_tasks, calibration_context
                )
                results[strategy_name] = result
        
        # Compare strategies
        evaluation_results = {}
        for strategy_name, result in results.items():
            if "evaluation" in result:
                evaluation_results[strategy_name] = result["evaluation"]
        
        comparison = compare_strategies(evaluation_results)
        
        return {
            "results": results,
            "comparison": comparison,
            "test_tasks_count": len([t for t in test_tasks if t.get('actual_minutes')])
        }
    
    def save_results(self, results: Dict, output_path: str):
        """
        Save experiment results to JSON file.
        
        Args:
            results: Experiment results dict
            output_path: Path to save JSON file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"Results saved to: {output_path}")
    
    def test_general_quality(self, test_dataset: List[Dict], context_strategy: ContextStrategy,
                            evaluator: str = "ai", context_n: int = 10) -> Dict:
        """
        Test general quality of estimates on a test dataset (without actuals).
        
        Args:
            test_dataset: List of test prompts (dicts with 'prompt' key or just strings)
            context_strategy: Context strategy to test
            evaluator: Evaluation method ("ai", "heuristic", or "both")
            context_n: Number of tasks for RECENT_N strategy
            
        Returns:
            Dict with quality evaluation results
        """
        quality_evaluator = QualityEvaluator()
        estimates = []
        task_descriptions = []
        evaluations = []
        
        for prompt_data in test_dataset:
            # Handle both dict format and string format
            if isinstance(prompt_data, dict):
                prompt_text = prompt_data.get('prompt', '')
            else:
                prompt_text = str(prompt_data)
            
            if not prompt_text:
                continue
            
            # Generate estimate
            estimate = self.agent.estimate_task(
                prompt_text,
                context_strategy=context_strategy,
                context_n=context_n
            )
            
            estimates.append(estimate)
            task_descriptions.append(prompt_text)
            
            # Evaluate quality
            if evaluator in ["ai", "both"]:
                eval_result = quality_evaluator.evaluate_estimate_quality(prompt_text, estimate)
                evaluations.append(eval_result)
            elif evaluator == "heuristic":
                eval_result = quality_evaluator._heuristic_evaluation(prompt_text, estimate)
                evaluations.append(eval_result)
        
        # Calculate metrics
        if evaluations:
            avg_score = sum(e["score"] for e in evaluations) / len(evaluations)
            avg_reasonableness = sum(e.get("reasonableness_score", 0) for e in evaluations) / len(evaluations)
            avg_consistency = sum(e.get("consistency_score", 0) for e in evaluations) / len(evaluations)
            avg_range = sum(e.get("range_score", 0) for e in evaluations) / len(evaluations)
            avg_category = sum(e.get("category_score", 0) for e in evaluations) / len(evaluations)
            
            # Score distribution
            score_dist = {}
            for eval_result in evaluations:
                score = eval_result["score"]
                score_dist[score] = score_dist.get(score, 0) + 1
        else:
            avg_score = 0
            avg_reasonableness = 0
            avg_consistency = 0
            avg_range = 0
            avg_category = 0
            score_dist = {}
        
        # Run heuristic checks
        heuristic_results = quality_evaluator.run_heuristic_checks(estimates)
        
        return {
            "strategy": context_strategy.value,
            "total_tasks": len(estimates),
            "average_score": avg_score,
            "average_reasonableness": avg_reasonableness,
            "average_consistency": avg_consistency,
            "average_range": avg_range,
            "average_category": avg_category,
            "score_distribution": score_dist,
            "heuristic_checks": heuristic_results,
            "evaluations": evaluations
        }
    
    def compare_general_quality(self, test_dataset: List[Dict],
                               strategies: Optional[List[ContextStrategy]] = None,
                               evaluator: str = "ai",
                               context_n_values: Optional[List[int]] = None) -> Dict:
        """
        Compare all context strategies on general quality metrics.
        
        Args:
            test_dataset: List of test prompts
            strategies: List of strategies to test (default: all strategies)
            evaluator: Evaluation method
            context_n_values: List of N values for RECENT_N (default: [10])
            
        Returns:
            Dict with comparison results
        """
        if strategies is None:
            strategies = [
                ContextStrategy.MINIMAL,
                ContextStrategy.RECENT_N,
                ContextStrategy.SUMMARIZED,
                ContextStrategy.CATEGORY_FILTERED,
                ContextStrategy.SIMILARITY_BASED
            ]
        
        if context_n_values is None:
            context_n_values = [10]
        
        results = {}
        
        for strategy in strategies:
            if strategy == ContextStrategy.RECENT_N:
                # Test different N values
                for n in context_n_values:
                    strategy_name = f"{strategy.value}_n{n}"
                    print(f"Testing general quality: {strategy_name}")
                    result = self.test_general_quality(
                        test_dataset, strategy, evaluator, context_n=n
                    )
                    results[strategy_name] = result
            else:
                strategy_name = strategy.value
                print(f"Testing general quality: {strategy_name}")
                result = self.test_general_quality(
                    test_dataset, strategy, evaluator
                )
                results[strategy_name] = result
        
        # Find best strategy
        best_strategy = max(results.items(), key=lambda x: x[1].get("average_score", 0))
        
        return {
            "results": results,
            "best_strategy": {
                "name": best_strategy[0],
                "average_score": best_strategy[1].get("average_score", 0)
            },
            "test_dataset_size": len(test_dataset)
        }


def run_experiment_suite(test_tasks: List[Dict],
                        calibration_context: Optional[Dict] = None,
                        output_path: Optional[str] = None) -> Dict:
    """
    Convenience function to run full experiment suite.
    
    Args:
        test_tasks: List of completed tasks to test on
        calibration_context: Calibration data
        output_path: Optional path to save results
        
    Returns:
        Experiment results dict
    """
    experiment = ContextExperiment()
    results = experiment.run_all_experiments(test_tasks, calibration_context)
    
    if output_path:
        experiment.save_results(results, output_path)
    
    return results




"""
Quality evaluation analysis module.
Extracts insights and patterns from quality evaluation results.
"""

from typing import Dict, List, Optional
from collections import defaultdict
import json
import statistics


def analyze_score_patterns(debug_data: Dict, test_dataset_path: Optional[str] = None) -> Dict:
    """
    Analyze score distribution by various dimensions.
    
    Args:
        debug_data: Debug data from quality evaluation
        test_dataset_path: Optional path to test dataset to get prompt quality metadata
        
    Returns:
        Dict with analysis results
    """
    all_evaluations = debug_data.get("all_evaluations", [])
    samples = debug_data.get("samples", [])
    
    if not all_evaluations:
        return {}
    
    # Score distribution overall
    score_dist = defaultdict(int)
    for eval_result in all_evaluations:
        score = eval_result.get("score", 0)
        score_dist[score] += 1
    
    # Score distribution by prompt quality
    # Try to load test dataset to get actual prompt quality
    task_to_quality = {}
    if test_dataset_path:
        try:
            import json
            from pathlib import Path
            dataset_file = Path(test_dataset_path)
            if dataset_file.exists():
                with open(dataset_file, 'r') as f:
                    test_data = json.load(f)
                test_prompts = test_data.get("test_prompts", [])
                for prompt_data in test_prompts:
                    task_text = prompt_data.get("prompt", "")
                    quality = prompt_data.get("metadata", {}).get("prompt_quality", "unknown")
                    if task_text:
                        task_to_quality[task_text] = quality
        except Exception:
            pass  # Fall back to inference
    
    scores_by_quality = defaultdict(list)
    for sample in samples:
        task = sample.get("task", "")
        eval_result = sample.get("evaluation", {})
        score = eval_result.get("score", 0)
        
        # Get quality from test dataset if available, otherwise infer
        quality = task_to_quality.get(task, "unknown")
        if quality == "unknown":
            # Infer from task characteristics
            if len(task) < 20 or task.strip() in ["Work stuff", "Something"]:
                quality = "poor"
            elif len(task) > 200 and any(word in task.lower() for word in ["specific", "detailed", "ensure", "located"]):
                quality = "excellent"
            else:
                quality = "good"
        
        scores_by_quality[quality].append(score)
    
    # Calculate averages
    avg_by_quality = {}
    for quality, scores in scores_by_quality.items():
        if scores:
            avg_by_quality[quality] = sum(scores) / len(scores)
    
    # Score distribution by category (from samples)
    scores_by_category = defaultdict(list)
    for sample in samples:
        estimate = sample.get("estimate", {})
        eval_result = sample.get("evaluation", {})
        category = estimate.get("category", "unknown")
        score = eval_result.get("score", 0)
        scores_by_category[category].append(score)
    
    avg_by_category = {}
    for category, scores in scores_by_category.items():
        if scores:
            avg_by_category[category] = sum(scores) / len(scores)
    
    # Score distribution by task length
    scores_by_length = defaultdict(list)
    for sample in samples:
        task = sample.get("task", "")
        eval_result = sample.get("evaluation", {})
        score = eval_result.get("score", 0)
        length = len(task)
        
        if length < 50:
            length_bucket = "short"
        elif length < 200:
            length_bucket = "medium"
        else:
            length_bucket = "long"
        
        scores_by_length[length_bucket].append(score)
    
    avg_by_length = {}
    for length_bucket, scores in scores_by_length.items():
        if scores:
            avg_by_length[length_bucket] = sum(scores) / len(scores)
    
    return {
        "overall_distribution": dict(score_dist),
        "average_score": sum(e.get("score", 0) for e in all_evaluations) / len(all_evaluations) if all_evaluations else 0,
        "by_quality": avg_by_quality,
        "by_category": avg_by_category,
        "by_length": avg_by_length,
        "total_evaluations": len(all_evaluations)
    }


def identify_common_issues(evaluations: List[Dict]) -> Dict:
    """
    Identify common patterns in low-scoring and high-scoring estimates.
    
    Args:
        evaluations: List of evaluation results
        
    Returns:
        Dict with common issues and success patterns
    """
    # Handle both binary (0-1) and 1-5 scoring
    # For binary: 0 = low, 1 = high
    # For 1-5: <= 2 = low, >= 4 = high
    low_scores = [e for e in evaluations if e.get("score", 0) == 0 or (e.get("score", 0) <= 2 and e.get("score", 0) > 1)]
    high_scores = [e for e in evaluations if e.get("score", 0) == 1 or e.get("score", 0) >= 4]
    
    # Analyze low scores
    low_score_issues = defaultdict(int)
    low_score_reasoning_themes = defaultdict(int)
    
    for eval_result in low_scores:
        checks = eval_result.get("checks", {})
        reasoning = eval_result.get("reasoning", "").lower()
        
        # Check for common failure modes
        if not checks.get("reasonable_number", True):
            low_score_issues["unreasonable_number"] += 1
        if not checks.get("reasonable_explanation", True):
            low_score_issues["poor_explanation"] += 1
        if not checks.get("explanation_number_aligned", True):
            low_score_issues["misaligned"] += 1
        if not checks.get("range_aligned", True):
            low_score_issues["range_misaligned"] += 1
        
        # Extract themes from reasoning
        if "vague" in reasoning or "ambiguous" in reasoning:
            low_score_reasoning_themes["vague_estimate"] += 1
        if "precise" in reasoning and ("too" in reasoning or "overly" in reasoning):
            low_score_reasoning_themes["overly_precise"] += 1
        if "range" in reasoning and ("narrow" in reasoning or "too small" in reasoning):
            low_score_reasoning_themes["narrow_range"] += 1
        if "explanation" in reasoning and ("lacks" in reasoning or "missing" in reasoning):
            low_score_reasoning_themes["insufficient_explanation"] += 1
    
    # Analyze high scores
    high_score_patterns = defaultdict(int)
    high_score_reasoning_themes = defaultdict(int)
    
    for eval_result in high_scores:
        checks = eval_result.get("checks", {})
        reasoning = eval_result.get("reasoning", "").lower()
        
        # Check for success patterns
        if checks.get("reasonable_number", False):
            high_score_patterns["reasonable_number"] += 1
        if checks.get("reasonable_explanation", False):
            high_score_patterns["good_explanation"] += 1
        if checks.get("explanation_number_aligned", False):
            high_score_patterns["well_aligned"] += 1
        
        # Extract themes from reasoning
        if "thorough" in reasoning or "detailed" in reasoning:
            high_score_reasoning_themes["thorough"] += 1
        if "appropriate" in reasoning and "range" in reasoning:
            high_score_reasoning_themes["good_range"] += 1
        if "logical" in reasoning or "sound" in reasoning:
            high_score_reasoning_themes["logical"] += 1
    
    return {
        "low_score_count": len(low_scores),
        "high_score_count": len(high_scores),
        "low_score_issues": dict(low_score_issues),
        "low_score_themes": dict(low_score_reasoning_themes),
        "high_score_patterns": dict(high_score_patterns),
        "high_score_themes": dict(high_score_reasoning_themes)
    }


def analyze_by_dimension(evaluations: List[Dict]) -> Dict:
    """
    Analyze performance by evaluation dimension.
    
    Args:
        evaluations: List of evaluation results
        
    Returns:
        Dict with dimension analysis
    """
    if not evaluations:
        return {}
    
    dimensions = {
        "reasonableness": [],
        "consistency": [],
        "range": [],
        "category": []
    }
    
    dimension_mismatches = []
    
    for eval_result in evaluations:
        reasonableness = eval_result.get("reasonableness_score", 0)
        consistency = eval_result.get("consistency_score", 0)
        range_score = eval_result.get("range_score", 0)
        category_score = eval_result.get("category_score", 0)
        overall = eval_result.get("score", 0)
        
        dimensions["reasonableness"].append(reasonableness)
        dimensions["consistency"].append(consistency)
        dimensions["range"].append(range_score)
        dimensions["category"].append(category_score)
        
        # Find mismatches (e.g., good reasonableness but poor consistency)
        # Handle both binary (0-1) and 1-5 scoring
        is_binary = overall <= 1
        if is_binary:
            good_threshold = 1
            poor_threshold = 0
        else:
            good_threshold = 4
            poor_threshold = 2
        
        if reasonableness >= good_threshold and consistency <= poor_threshold:
            dimension_mismatches.append({
                "type": "good_reasonableness_poor_consistency",
                "reasonableness": reasonableness,
                "consistency": consistency,
                "overall": overall
            })
        if consistency >= good_threshold and reasonableness <= poor_threshold:
            dimension_mismatches.append({
                "type": "good_consistency_poor_reasonableness",
                "reasonableness": reasonableness,
                "consistency": consistency,
                "overall": overall
            })
    
    # Calculate averages
    avg_dimensions = {}
    for dim_name, scores in dimensions.items():
        if scores:
            avg_dimensions[dim_name] = sum(scores) / len(scores)
    
    # Find weakest and strongest dimensions
    sorted_dims = sorted(avg_dimensions.items(), key=lambda x: x[1])
    weakest = sorted_dims[0] if sorted_dims else None
    strongest = sorted_dims[-1] if sorted_dims else None
    
    return {
        "average_dimensions": avg_dimensions,
        "weakest_dimension": weakest[0] if weakest else None,
        "weakest_score": weakest[1] if weakest else None,
        "strongest_dimension": strongest[0] if strongest else None,
        "strongest_score": strongest[1] if strongest else None,
        "dimension_mismatches": dimension_mismatches[:10]  # Top 10
    }


def correlate_estimate_features(samples: List[Dict]) -> Dict:
    """
    Correlate estimate features with scores.
    
    Args:
        samples: List of samples with task, estimate, and evaluation
        
    Returns:
        Dict with correlation insights
    """
    if not samples:
        return {}
    
    # Collect data
    high_score_data = {"explanation_length": [], "estimate_magnitude": [], "range_width": []}
    low_score_data = {"explanation_length": [], "estimate_magnitude": [], "range_width": []}
    
    for sample in samples:
        estimate = sample.get("estimate", {})
        eval_result = sample.get("evaluation", {})
        score = eval_result.get("score", 0)
        
        explanation = estimate.get("explanation", "")
        explanation_len = len(explanation)
        
        estimated_minutes = estimate.get("estimated_minutes", 0)
        
        range_data = estimate.get("estimate_range", {})
        optimistic = range_data.get("optimistic", 0)
        pessimistic = range_data.get("pessimistic", 0)
        range_width = pessimistic - optimistic if pessimistic > optimistic else 0
        
        # Handle both binary (0-1) and 1-5 scoring
        is_high = (score == 1) or (score >= 4)
        data_dict = high_score_data if is_high else low_score_data
        
        data_dict["explanation_length"].append(explanation_len)
        data_dict["estimate_magnitude"].append(estimated_minutes)
        data_dict["range_width"].append(range_width)
    
    # Calculate averages
    correlations = {}
    
    if high_score_data["explanation_length"]:
        correlations["high_score_avg_explanation_length"] = sum(high_score_data["explanation_length"]) / len(high_score_data["explanation_length"])
    if low_score_data["explanation_length"]:
        correlations["low_score_avg_explanation_length"] = sum(low_score_data["explanation_length"]) / len(low_score_data["explanation_length"])
    
    if high_score_data["range_width"]:
        correlations["high_score_avg_range_width"] = sum(high_score_data["range_width"]) / len(high_score_data["range_width"])
    if low_score_data["range_width"]:
        correlations["low_score_avg_range_width"] = sum(low_score_data["range_width"]) / len(low_score_data["range_width"])
    
    # Find patterns
    insights = []
    
    high_explanation_len = correlations.get("high_score_avg_explanation_length", 0)
    low_explanation_len = correlations.get("low_score_avg_explanation_length", 0)
    
    if high_explanation_len > 0 and low_explanation_len > 0:
        if high_explanation_len > low_explanation_len:
            diff = high_explanation_len - low_explanation_len
            insights.append(f"High-scoring estimates have longer explanations (avg {high_explanation_len:.0f} vs {low_explanation_len:.0f} chars, +{diff:.0f})")
        elif low_explanation_len > high_explanation_len:
            diff = low_explanation_len - high_explanation_len
            insights.append(f"Low-scoring estimates have longer explanations (avg {low_explanation_len:.0f} vs {high_explanation_len:.0f} chars, +{diff:.0f})")
    
    high_range_width = correlations.get("high_score_avg_range_width", 0)
    low_range_width = correlations.get("low_score_avg_range_width", 0)
    
    if high_range_width > 0 and low_range_width > 0:
        if abs(high_range_width - low_range_width) > 1:  # Only report if meaningful difference
            insights.append(f"Range width differs: high scores avg {high_range_width:.0f} min, low scores avg {low_range_width:.0f} min")
    
    return {
        "correlations": correlations,
        "insights": insights
    }


def generate_recommendations(analysis_results: Dict) -> List[str]:
    """
    Generate actionable recommendations based on analysis.
    
    Args:
        analysis_results: Combined results from all analysis functions
        
    Returns:
        List of recommendation strings
    """
    recommendations = []
    
    # Check dimension analysis
    dim_analysis = analysis_results.get("dimension_analysis", {})
    weakest = dim_analysis.get("weakest_dimension")
    if weakest:
        recommendations.append(f"Focus on improving {weakest} (weakest dimension, avg {dim_analysis.get('weakest_score', 0):.1f})")
    
    # Check common issues
    issues = analysis_results.get("common_issues", {})
    low_issues = issues.get("low_score_issues", {})
    if low_issues:
        top_issue = max(low_issues.items(), key=lambda x: x[1])
        recommendations.append(f"Address most common issue: {top_issue[0]} ({top_issue[1]} occurrences in low scores)")
    
    # Check score patterns
    patterns = analysis_results.get("score_patterns", {})
    by_quality = patterns.get("by_quality", {})
    if "poor" in by_quality and by_quality["poor"] < 3.0:
        recommendations.append("Improve handling of poor-quality prompts (current avg: {:.1f})".format(by_quality["poor"]))
    
    # Check correlations
    correlations = analysis_results.get("correlations", {})
    insights = correlations.get("insights", [])
    if insights:
        # Extract key insight
        for insight in insights[:1]:  # Take first insight
            if "explanation" in insight.lower():
                recommendations.append("Encourage longer, more detailed explanations in estimates")
    
    return recommendations


def convert_five_point_to_binary(score: int) -> int:
    """
    Convert 1-5 score to binary (0-1).
    Uses threshold: 4-5 -> 1 (good), 1-3 -> 0 (poor)
    
    Args:
        score: Score from 1-5 scale
        
    Returns:
        Binary score (0 or 1)
    """
    if score >= 4:
        return 1
    return 0


def calculate_cohens_kappa(scores_1: List[int], scores_2: List[int]) -> float:
    """
    Calculate Cohen's kappa for inter-rater agreement.
    
    Args:
        scores_1: First set of scores
        scores_2: Second set of scores (same length as scores_1)
        
    Returns:
        Cohen's kappa value (-1 to 1, where 1 is perfect agreement)
    """
    if len(scores_1) != len(scores_2) or len(scores_1) == 0:
        return 0.0
    
    # Create confusion matrix
    # For binary: 0, 1
    # For 1-5: normalize to binary first if needed
    max_score = max(max(scores_1), max(scores_2))
    is_binary = max_score <= 1
    
    if not is_binary:
        # Convert to binary
        scores_1 = [convert_five_point_to_binary(s) for s in scores_1]
        scores_2 = [convert_five_point_to_binary(s) for s in scores_2]
    
    # Count agreements and disagreements
    both_0 = sum(1 for s1, s2 in zip(scores_1, scores_2) if s1 == 0 and s2 == 0)
    both_1 = sum(1 for s1, s2 in zip(scores_1, scores_2) if s1 == 1 and s2 == 1)
    disagree_01 = sum(1 for s1, s2 in zip(scores_1, scores_2) if s1 == 0 and s2 == 1)
    disagree_10 = sum(1 for s1, s2 in zip(scores_1, scores_2) if s1 == 1 and s2 == 0)
    
    total = len(scores_1)
    observed_agreement = (both_0 + both_1) / total if total > 0 else 0
    
    # Calculate expected agreement
    count_0_1 = sum(1 for s in scores_1 if s == 0)
    count_1_1 = sum(1 for s in scores_1 if s == 1)
    count_0_2 = sum(1 for s in scores_2 if s == 0)
    count_1_2 = sum(1 for s in scores_2 if s == 1)
    
    expected_agreement = ((count_0_1 * count_0_2) + (count_1_1 * count_1_2)) / (total * total) if total > 0 else 0
    
    # Calculate kappa
    if expected_agreement == 1.0:
        return 1.0  # Perfect agreement
    
    kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement) if expected_agreement < 1.0 else 0.0
    return kappa


def measure_evaluation_consistency(evaluations_1: List[Dict], evaluations_2: List[Dict]) -> Dict:
    """
    Measure consistency between two evaluation runs on the same tasks.
    
    Args:
        evaluations_1: First set of evaluations
        evaluations_2: Second set of evaluations (same tasks, same order)
        
    Returns:
        Dict with consistency metrics
    """
    if len(evaluations_1) != len(evaluations_2) or len(evaluations_1) == 0:
        return {"error": "Evaluations must be same length and non-empty"}
    
    scores_1 = [e.get("score", 0) for e in evaluations_1]
    scores_2 = [e.get("score", 0) for e in evaluations_2]
    
    # Calculate agreement
    agreements = sum(1 for s1, s2 in zip(scores_1, scores_2) if s1 == s2)
    agreement_pct = (agreements / len(scores_1)) * 100 if len(scores_1) > 0 else 0
    
    # Calculate Cohen's kappa
    kappa = calculate_cohens_kappa(scores_1, scores_2)
    
    # Calculate variance in differences
    differences = [abs(s1 - s2) for s1, s2 in zip(scores_1, scores_2)]
    mean_difference = statistics.mean(differences) if differences else 0
    variance_difference = statistics.variance(differences) if len(differences) > 1 else 0
    
    return {
        "agreement_percentage": agreement_pct,
        "cohens_kappa": kappa,
        "mean_absolute_difference": mean_difference,
        "variance_of_differences": variance_difference,
        "total_comparisons": len(scores_1),
        "perfect_agreements": agreements
    }


def measure_evaluation_stability(evaluations_list: List[List[Dict]]) -> Dict:
    """
    Measure stability/variance across multiple evaluation runs.
    
    Args:
        evaluations_list: List of evaluation runs, each containing evaluations for the same tasks
        
    Returns:
        Dict with stability metrics
    """
    if not evaluations_list or len(evaluations_list) < 2:
        return {"error": "Need at least 2 evaluation runs"}
    
    num_runs = len(evaluations_list)
    num_tasks = len(evaluations_list[0])
    
    # Verify all runs have same number of tasks
    if not all(len(run) == num_tasks for run in evaluations_list):
        return {"error": "All runs must have same number of evaluations"}
    
    # For each task, collect scores across all runs
    task_scores = []
    for task_idx in range(num_tasks):
        scores_for_task = [run[task_idx].get("score", 0) for run in evaluations_list]
        task_scores.append(scores_for_task)
    
    # Calculate variance for each task
    task_variances = []
    for scores in task_scores:
        if len(scores) > 1:
            task_variances.append(statistics.variance(scores))
        else:
            task_variances.append(0.0)
    
    mean_variance = statistics.mean(task_variances) if task_variances else 0
    max_variance = max(task_variances) if task_variances else 0
    tasks_with_zero_variance = sum(1 for v in task_variances if v == 0)
    
    # Calculate overall score distribution variance
    all_scores = [score for scores in task_scores for score in scores]
    overall_variance = statistics.variance(all_scores) if len(all_scores) > 1 else 0
    
    return {
        "mean_task_variance": mean_variance,
        "max_task_variance": max_variance,
        "tasks_with_zero_variance": tasks_with_zero_variance,
        "tasks_with_variance": num_tasks - tasks_with_zero_variance,
        "overall_score_variance": overall_variance,
        "num_runs": num_runs,
        "num_tasks": num_tasks
    }


def measure_discrimination_ability(evaluations: List[Dict], 
                                   ground_truth_labels: Optional[List[int]] = None) -> Dict:
    """
    Measure how well the scoring system discriminates between good/poor estimates.
    
    Args:
        evaluations: List of evaluation results
        ground_truth_labels: Optional ground truth labels (0=poor, 1=good)
        
    Returns:
        Dict with discrimination metrics
    """
    if not evaluations:
        return {}
    
    scores = [e.get("score", 0) for e in evaluations]
    
    # Determine if binary or 1-5
    max_score = max(scores) if scores else 0
    is_binary = max_score <= 1
    
    if is_binary:
        good_scores = [s for s in scores if s == 1]
        poor_scores = [s for s in scores if s == 0]
    else:
        # Convert 1-5 to binary for analysis
        binary_scores = [convert_five_point_to_binary(s) for s in scores]
        good_scores = [s for s in binary_scores if s == 1]
        poor_scores = [s for s in binary_scores if s == 0]
    
    good_pct = (len(good_scores) / len(scores) * 100) if scores else 0
    
    result = {
        "good_percentage": good_pct,
        "poor_percentage": 100 - good_pct,
        "score_distribution": {
            "0": len(poor_scores),
            "1": len(good_scores)
        },
        "is_binary_scoring": is_binary
    }
    
    # If ground truth available, calculate precision/recall/F1
    if ground_truth_labels and len(ground_truth_labels) == len(scores):
        # Convert scores to binary if needed
        if not is_binary:
            scores = [convert_five_point_to_binary(s) for s in scores]
        
        # Calculate metrics
        true_positives = sum(1 for s, gt in zip(scores, ground_truth_labels) if s == 1 and gt == 1)
        false_positives = sum(1 for s, gt in zip(scores, ground_truth_labels) if s == 1 and gt == 0)
        false_negatives = sum(1 for s, gt in zip(scores, ground_truth_labels) if s == 0 and gt == 1)
        true_negatives = sum(1 for s, gt in zip(scores, ground_truth_labels) if s == 0 and gt == 0)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (true_positives + true_negatives) / len(scores) if scores else 0
        
        result.update({
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "accuracy": accuracy,
            "confusion_matrix": {
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "true_negatives": true_negatives
            }
        })
    
    return result


def compare_scoring_methodologies(old_evaluations: List[Dict], 
                                 new_evaluations: List[Dict],
                                 old_samples: Optional[List[Dict]] = None,
                                 new_samples: Optional[List[Dict]] = None) -> Dict:
    """
    Compare old 1-5 scoring vs new 0-1 binary scoring.
    
    Args:
        old_evaluations: Evaluations from 1-5 system
        new_evaluations: Evaluations from 0-1 system
        old_samples: Optional sample data from old system
        new_samples: Optional sample data from new system
        
    Returns:
        Comparison metrics showing improvement
    """
    if len(old_evaluations) != len(new_evaluations):
        return {"error": "Old and new evaluations must have same length"}
    
    old_scores = [e.get("score", 0) for e in old_evaluations]
    new_scores = [e.get("score", 0) for e in new_evaluations]
    
    # Convert old 1-5 scores to binary for comparison
    old_binary = [convert_five_point_to_binary(s) for s in old_scores]
    
    # Calculate agreement between old (converted) and new
    agreement = sum(1 for o, n in zip(old_binary, new_scores) if o == n)
    agreement_pct = (agreement / len(old_binary) * 100) if old_binary else 0
    
    # Calculate Cohen's kappa
    kappa = calculate_cohens_kappa(old_binary, new_scores)
    
    # Calculate variance in dimension scores
    def get_dimension_variance(evaluations):
        dims = {
            "reasonableness": [],
            "consistency": [],
            "range": [],
            "category": []
        }
        for e in evaluations:
            dims["reasonableness"].append(e.get("reasonableness_score", 0))
            dims["consistency"].append(e.get("consistency_score", 0))
            dims["range"].append(e.get("range_score", 0))
            dims["category"].append(e.get("category_score", 0))
        
        variances = {}
        for dim_name, scores in dims.items():
            if len(scores) > 1:
                # Normalize to 0-1 scale for comparison
                max_score = max(scores) if scores else 1
                if max_score > 1:
                    # Convert 1-5 to 0-1
                    normalized = [s / 5.0 for s in scores]
                else:
                    normalized = scores
                variances[dim_name] = statistics.variance(normalized) if len(normalized) > 1 else 0
            else:
                variances[dim_name] = 0
        return variances
    
    old_variance = get_dimension_variance(old_evaluations)
    new_variance = get_dimension_variance(new_evaluations)
    
    # Calculate average scores
    old_avg = statistics.mean(old_scores) if old_scores else 0
    new_avg = statistics.mean(new_scores) if new_scores else 0
    old_binary_avg = statistics.mean(old_binary) if old_binary else 0
    
    # Score distribution comparison
    old_dist = defaultdict(int)
    for s in old_scores:
        old_dist[s] += 1
    
    new_dist = defaultdict(int)
    for s in new_scores:
        new_dist[s] += 1
    
    # Calculate discrimination metrics
    old_discrimination = measure_discrimination_ability(old_evaluations)
    new_discrimination = measure_discrimination_ability(new_evaluations)
    
    return {
        "agreement_between_systems": agreement_pct,
        "cohens_kappa": kappa,
        "old_system": {
            "average_score": old_avg,
            "average_binary_equivalent": old_binary_avg,
            "score_distribution": dict(old_dist),
            "dimension_variances": old_variance,
            "discrimination": old_discrimination
        },
        "new_system": {
            "average_score": new_avg,
            "score_distribution": dict(new_dist),
            "dimension_variances": new_variance,
            "discrimination": new_discrimination
        },
        "improvements": {
            "variance_reduction": {
                dim: old_variance.get(dim, 0) - new_variance.get(dim, 0)
                for dim in ["reasonableness", "consistency", "range", "category"]
            },
            "clarity_improvement": {
                "old_avg_dimension_variance": statistics.mean(old_variance.values()) if old_variance else 0,
                "new_avg_dimension_variance": statistics.mean(new_variance.values()) if new_variance else 0
            }
        }
    }


def find_disagreements(old_evaluations: List[Dict], new_evaluations: List[Dict],
                      old_samples: Optional[List[Dict]] = None,
                      new_samples: Optional[List[Dict]] = None) -> Dict:
    """
    Find and categorize disagreements between old 1-5 and new 0-1 scoring systems.
    
    Args:
        old_evaluations: Evaluations from 1-5 system
        new_evaluations: Evaluations from 0-1 system
        old_samples: Optional sample data from old system (with task, estimate)
        new_samples: Optional sample data from new system (with task, estimate)
        
    Returns:
        Dict with disagreement analysis including examples
    """
    if len(old_evaluations) != len(new_evaluations):
        return {"error": "Old and new evaluations must have same length"}
    
    old_scores = [e.get("score", 0) for e in old_evaluations]
    new_scores = [e.get("score", 0) for e in new_evaluations]
    
    # Convert old to binary for comparison
    old_binary = [convert_five_point_to_binary(s) for s in old_scores]
    
    # Find disagreements
    disagreements = []
    agreements = []
    
    for i, (old_score, old_bin, new_score) in enumerate(zip(old_scores, old_binary, new_scores)):
        if old_bin != new_score:
            # Disagreement
            disagreement_type = None
            if old_bin == 0 and new_score == 1:
                disagreement_type = "old_poor_new_good"  # Old said poor, new says good
            elif old_bin == 1 and new_score == 0:
                disagreement_type = "old_good_new_poor"  # Old said good, new says poor
            
            disagreement = {
                "index": i,
                "old_score": old_score,
                "old_binary": old_bin,
                "new_score": new_score,
                "type": disagreement_type,
                "old_evaluation": old_evaluations[i],
                "new_evaluation": new_evaluations[i]
            }
            
            # Add task/estimate info if available
            if old_samples and i < len(old_samples):
                disagreement["task"] = old_samples[i].get("task", "")
                disagreement["estimate"] = old_samples[i].get("estimate", {})
            elif new_samples and i < len(new_samples):
                disagreement["task"] = new_samples[i].get("task", "")
                disagreement["estimate"] = new_samples[i].get("estimate", {})
            
            disagreements.append(disagreement)
        else:
            agreements.append(i)
    
    # Categorize disagreements
    old_poor_new_good = [d for d in disagreements if d["type"] == "old_poor_new_good"]
    old_good_new_poor = [d for d in disagreements if d["type"] == "old_good_new_poor"]
    
    # Find borderline cases (old score 3, which is in the middle)
    borderline_cases = [d for d in disagreements if d["old_score"] == 3]
    
    # Group by old score ranges
    by_old_score = defaultdict(list)
    for d in disagreements:
        old_s = d["old_score"]
        if old_s <= 2:
            by_old_score["1-2"].append(d)
        elif old_s == 3:
            by_old_score["3"].append(d)
        elif old_s >= 4:
            by_old_score["4-5"].append(d)
    
    return {
        "total_disagreements": len(disagreements),
        "total_agreements": len(agreements),
        "agreement_rate": (len(agreements) / len(old_evaluations) * 100) if old_evaluations else 0,
        "disagreement_breakdown": {
            "old_poor_new_good": len(old_poor_new_good),
            "old_good_new_poor": len(old_good_new_poor)
        },
        "borderline_cases": borderline_cases,  # Cases where old system scored 3
        "by_old_score_range": {
            k: len(v) for k, v in by_old_score.items()
        },
        "all_disagreements": disagreements,
        "disagreement_examples": {
            "old_poor_new_good": old_poor_new_good[:10],  # Top 10 examples
            "old_good_new_poor": old_good_new_poor[:10],
            "borderline": borderline_cases[:10]
        }
    }


def load_old_evaluations(debug_file_path: str = "quality_eval_debug.json") -> Optional[Dict]:
    """
    Load old 1-5 scoring evaluations from debug file.
    
    Args:
        debug_file_path: Path to debug JSON file
        
    Returns:
        Dict with old evaluations and samples, or None if file not found
    """
    from pathlib import Path
    
    debug_file = Path(debug_file_path)
    if not debug_file.exists():
        return None
    
    try:
        with open(debug_file, 'r') as f:
            data = json.load(f)
        return {
            "all_evaluations": data.get("all_evaluations", []),
            "samples": data.get("samples", [])
        }
    except Exception as e:
        return {"error": str(e)}


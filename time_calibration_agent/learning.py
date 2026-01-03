"""
Learning and calibration system that updates estimates based on actual outcomes.
Uses heuristics for V1 - simple but effective.
"""

from typing import Dict, List


class CalibrationLearner:
    """Learns from task outcomes to improve future estimates."""
    
    def __init__(self):
        pass
    
    def update_calibration(self, completed_tasks: List[Dict], 
                          current_calibration: Dict) -> Dict:
        """
        Update calibration data based on completed tasks.
        
        This is a heuristic-based learning system for V1.
        It tracks:
        - Overall user bias (tendency to over/underestimate)
        - Category-specific patterns
        - Task ambiguity effects
        """
        
        if not completed_tasks:
            return current_calibration
        
        # Calculate overall bias
        total_error = 0.0
        total_estimated = 0.0
        category_errors = {}  # category -> list of error percentages
        ambiguity_errors = {}  # ambiguity -> list of error percentages
        
        for task in completed_tasks:
            if not task.get('actual_minutes'):
                continue
            
            estimated = task['estimated_minutes']
            actual = task['actual_minutes']
            
            # Error as percentage: positive = agent underestimated (actual > estimated), 
            # negative = agent overestimated (actual < estimated)
            error_pct = ((actual - estimated) / estimated) if estimated > 0 else 0.0
            
            total_error += error_pct * estimated
            total_estimated += estimated
            
            # Track by category
            category = task.get('category', 'general')
            if category not in category_errors:
                category_errors[category] = []
            category_errors[category].append(error_pct)
            
            # Track by ambiguity
            ambiguity = task.get('ambiguity', 'moderate')
            if ambiguity not in ambiguity_errors:
                ambiguity_errors[ambiguity] = []
            ambiguity_errors[ambiguity].append(error_pct)
        
        # Calculate overall bias (weighted average)
        if total_estimated > 0:
            overall_bias = total_error / total_estimated
        else:
            overall_bias = current_calibration.get('user_bias', 0.0)
        
        # Smooth with existing bias (exponential moving average)
        existing_bias = current_calibration.get('user_bias', 0.0)
        existing_count = current_calibration.get('total_tasks', 0)
        
        if existing_count > 0:
            # Weighted average: more weight to new data as we get more samples
            alpha = min(0.3, len(completed_tasks) / (existing_count + len(completed_tasks)))
            updated_bias = (1 - alpha) * existing_bias + alpha * overall_bias
        else:
            updated_bias = overall_bias
        
        # Build category patterns
        category_patterns = current_calibration.get('category_patterns', {}).copy()
        
        for category, errors in category_errors.items():
            if len(errors) >= 2:  # Need at least 2 samples for pattern
                avg_error = sum(errors) / len(errors)
                # Store as adjustment factor: 1.0 = no adjustment, 1.2 = add 20%
                if category in category_patterns:
                    # Smooth with existing pattern
                    existing_factor = category_patterns[category]
                    new_factor = 1.0 + avg_error
                    category_patterns[category] = 0.7 * existing_factor + 0.3 * new_factor
                else:
                    category_patterns[category] = 1.0 + avg_error
        
        # Build ambiguity patterns
        ambiguity_patterns = current_calibration.get('ambiguity_patterns', {})
        for ambiguity, errors in ambiguity_errors.items():
            if len(errors) >= 2:
                avg_error = sum(errors) / len(errors)
                if ambiguity in ambiguity_patterns:
                    existing_factor = ambiguity_patterns[ambiguity]
                    new_factor = 1.0 + avg_error
                    ambiguity_patterns[ambiguity] = 0.7 * existing_factor + 0.3 * new_factor
                else:
                    ambiguity_patterns[ambiguity] = 1.0 + avg_error
        
        # Recalculate total_tasks from actual completed tasks count (not incrementing)
        # This ensures accuracy even if tasks are deleted
        total_completed = len([t for t in completed_tasks if t.get('actual_minutes')])
        
        # Update calibration data
        updated_calibration = {
            "user_bias": updated_bias,
            "category_patterns": category_patterns,
            "ambiguity_patterns": ambiguity_patterns,
            "total_tasks": total_completed,
            "total_discrepancy": current_calibration.get('total_discrepancy', 0.0) + total_error
        }
        
        return updated_calibration
    
    def apply_calibration_to_estimate(self, estimate: Dict, 
                                     calibration: Dict) -> Dict:
        """
        Apply learned calibration adjustments to a new estimate.
        This adjusts the estimate based on historical patterns.
        """
        category = estimate.get('category', 'general')
        ambiguity = estimate.get('ambiguity', 'moderate')
        
        base_minutes = estimate['estimated_minutes']
        total_tasks = calibration.get('total_tasks', 0)
        
        # Apply category adjustment
        category_factor = calibration.get('category_patterns', {}).get(category, 1.0)
        
        # Apply ambiguity adjustment
        ambiguity_factor = calibration.get('ambiguity_patterns', {}).get(ambiguity, 1.0)
        
        # Apply overall bias with confidence weighting and capping
        raw_bias = calibration.get('user_bias', 0.0)
        
        # Confidence factor: more samples = more confidence in the bias
        # With few samples, apply bias more conservatively
        if total_tasks < 5:
            confidence = total_tasks / 10.0  # 0.0 to 0.5 for < 5 tasks
        elif total_tasks < 10:
            confidence = 0.5 + (total_tasks - 5) / 10.0  # 0.5 to 1.0 for 5-10 tasks
        else:
            confidence = 1.0  # Full confidence with 10+ tasks
        
        # Cap the bias adjustment to prevent extreme multipliers
        # Max adjustment: +50% or -30% (common sense limits)
        capped_bias = max(-0.3, min(0.5, raw_bias))
        
        # Apply confidence weighting: bias_factor = 1.0 + (capped_bias * confidence)
        bias_factor = 1.0 + (capped_bias * confidence)
        
        # Combined adjustment (geometric mean for multiplicative factors)
        total_factor = (category_factor * ambiguity_factor * bias_factor) ** (1/3)
        
        # Final safety cap: never adjust by more than 2x or less than 0.5x
        total_factor = max(0.5, min(2.0, total_factor))
        
        # Adjust estimate
        adjusted_minutes = int(base_minutes * total_factor)
        
        # Adjust range proportionally
        range_ratio = estimate['estimate_range']['realistic'] / base_minutes if base_minutes > 0 else 1.0
        
        # Enhance explanation if calibration was applied
        original_explanation = estimate.get('explanation', '')
        enhanced_explanation = original_explanation
        
        # If adjustment was significant (more than 5%), enhance the explanation
        if abs(total_factor - 1.0) > 0.05:
            adjustment_pct = (total_factor - 1.0) * 100
            
            # Build adjustment explanation
            adjustment_parts = []
            
            # Explain the adjustment reason
            if raw_bias > 0.1:
                bias_pct = min(50, raw_bias * 100)  # Cap display at 50%
                adjustment_parts.append(f"previous estimates have tended to underestimate by ~{bias_pct:.1f}% on average")
            elif raw_bias < -0.1:
                bias_pct = min(30, abs(raw_bias) * 100)  # Cap display at 30%
                adjustment_parts.append(f"previous estimates have tended to overestimate by ~{bias_pct:.1f}% on average")
            
            if category_factor != 1.0:
                cat_adj_pct = (category_factor - 1.0) * 100
                adjustment_parts.append(f"{category} tasks typically take {abs(cat_adj_pct):.1f}% {'longer' if cat_adj_pct > 0 else 'less time'} than estimated")
            
            if ambiguity_factor != 1.0:
                amb_adj_pct = (ambiguity_factor - 1.0) * 100
                adjustment_parts.append(f"{ambiguity} ambiguity tasks typically take {abs(amb_adj_pct):.1f}% {'longer' if amb_adj_pct > 0 else 'less time'} than estimated")
            
            # Combine adjustment reasons
            if adjustment_parts:
                reason = ", ".join(adjustment_parts)
                enhanced_explanation = (
                    f"Initially estimated {base_minutes} minutes: {original_explanation} "
                    f"Adjusted to {adjusted_minutes} minutes ({adjustment_pct:+.1f}%) "
                    f"based on historical estimation patterns showing {reason}."
                )
            else:
                enhanced_explanation = (
                    f"Initially estimated {base_minutes} minutes: {original_explanation} "
                    f"Adjusted to {adjusted_minutes} minutes ({adjustment_pct:+.1f}%) "
                    f"based on historical estimation patterns."
                )
        
        return {
            **estimate,
            "estimated_minutes": adjusted_minutes,
            "estimate_range": {
                "optimistic": int(estimate['estimate_range']['optimistic'] * total_factor),
                "realistic": adjusted_minutes,
                "pessimistic": int(estimate['estimate_range']['pessimistic'] * total_factor)
            },
            "explanation": enhanced_explanation,
            "calibration_applied": True,
            "adjustment_factor": total_factor
        }


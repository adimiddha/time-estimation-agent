"""
Quality evaluation framework for estimating time estimates without actuals.
Uses AI evaluators, human evaluators, and heuristic checks.
"""

import json
from typing import Dict, List, Optional
from pathlib import Path
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)


class QualityEvaluator:
    """Evaluates the quality of time estimates without actuals."""
    
    def __init__(self, api_key: Optional[str] = None, evaluator_model: str = "gpt-4o-mini", scoring_mode: str = "binary"):
        """
        Initialize quality evaluator.
        
        Args:
            api_key: OpenAI API key
            evaluator_model: Model to use for AI evaluation
            scoring_mode: "binary" for 0-1 scoring or "five_point" for 1-5 scoring
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.evaluator_model = evaluator_model
        self.scoring_mode = scoring_mode.lower() if scoring_mode else "binary"
    
    def _generate_evaluation_prompt(self, task_description: str, estimated: int, optimistic: int, 
                                   realistic: int, pessimistic: int, explanation: str, 
                                   category: str, ambiguity: str, prompt_quality_instructions: str) -> str:
        """Generate evaluation prompt based on scoring mode."""
        if self.scoring_mode == "five_point":
            return self._generate_five_point_prompt(task_description, estimated, optimistic, realistic,
                                                  pessimistic, explanation, category, ambiguity, 
                                                  prompt_quality_instructions)
        else:
            return self._generate_binary_prompt(task_description, estimated, optimistic, realistic,
                                               pessimistic, explanation, category, ambiguity,
                                               prompt_quality_instructions)
    
    def _generate_binary_prompt(self, task_description: str, estimated: int, optimistic: int,
                                realistic: int, pessimistic: int, explanation: str, category: str,
                                ambiguity: str, prompt_quality_instructions: str) -> str:
        """Generate binary (0-1) scoring prompt."""
        return f"""Evaluate the quality of this time estimate for a task. Use binary scoring: 0 (poor quality) or 1 (good quality).

{prompt_quality_instructions}

⚠️ CRITICAL: If the task is IMPOSSIBLE or UNREALISTIC (e.g., "Solve world hunger", "Learn fluent Spanish in 10 minutes", "Build a skyscraper"), the estimate should be scored 0. An estimate for an impossible task is fundamentally flawed, regardless of how well it's explained.

TASK: "{task_description}"

ESTIMATE:
- Estimated time: {estimated} minutes
- Range: {optimistic} (optimistic) - {realistic} (realistic) - {pessimistic} (pessimistic) minutes
- Explanation: {explanation}
- Category: {category}
- Ambiguity: {ambiguity}

EXAMPLES OF DIFFERENT QUALITY LEVELS:

Example 1 (Score 1 - Good Quality):
Task: "Write a 500-word blog post about time management"
Estimate: 90 minutes
Range: 60-90-120 minutes
Explanation: "Writing a 500-word blog post typically takes 60-90 minutes for research, writing, and basic editing. The range accounts for writing speed variations and whether additional research is needed."
Category: writing
→ Score 1: Number is reasonable, explanation is thorough and logical, range is appropriate, category matches. All aspects are solid.

Example 2 (Score 1 - Good Quality):
Task: "Review and respond to 20 emails in my inbox"
Estimate: 45 minutes
Range: 30-45-60 minutes
Explanation: "Email review typically takes 2-3 minutes per email on average. Some emails may require longer responses or follow-up actions, so the range accounts for variation in email complexity and urgency. The estimate considers potential interruptions and prioritization needs."
Category: admin
→ Score 1: Number is well-justified, explanation is thorough and considers relevant factors, range is appropriate and explained, category matches, everything is consistent. This is GOOD quality.

Example 3 (Score 0 - Poor Quality):
Task: "Write a 500-word blog post about time management"
Estimate: 30 minutes
Range: 25-30-35 minutes
Explanation: "Blog posts are quick to write, should take about 30 minutes."
Category: writing
→ Score 0: Number is too low (quality blog posts need research, writing, editing - typically 60-90 min), explanation is too simplistic and lacks depth, doesn't account for research/editing time, range is too narrow. This has noticeable problems - would be 3/5 in old system. Score 0.

BINARY SCORING RUBRIC:
- Score 1 (Good Quality): The estimate is GOOD quality. ALL of the following must be STRICTLY true:
  * The number is reasonable AND well-justified with specific reasoning
  * The explanation is THOROUGH (not brief or superficial) - it must address multiple relevant factors, consider task complexity, and provide detailed reasoning
  * The explanation demonstrates DEEP understanding - not just surface-level acknowledgment
  * The range is appropriate AND the explanation clearly justifies why the range is what it is
  * The category is correct
  * Everything is consistent and aligned
  * The estimate adequately addresses task ambiguity/complexity with sufficient detail
  
  CRITICAL: If the explanation is brief, lacks detail, doesn't address multiple factors, or feels superficial, score 0. If you find yourself saying "could be more thorough" or "lacks depth", score 0. Only score 1 if the explanation is genuinely thorough and demonstrates deep understanding.

- Score 0 (Poor Quality): The estimate has problems. Score 0 if:
  * The number is unreasonable or poorly justified
  * The explanation is brief, superficial, or lacks sufficient detail
  * The explanation doesn't address multiple relevant factors
  * The explanation doesn't demonstrate deep understanding of the task
  * The range is inappropriate (too narrow/wide) or not well-explained
  * The category is wrong
  * There are inconsistencies or misalignments
  * The estimate doesn't adequately acknowledge task ambiguity/complexity with sufficient detail
  * The explanation could be described as "lacking depth" or "could be more thorough"
  * There are noticeable problems that affect reliability

Evaluate on these criteria:

1. **Reasonableness** (0 or 1):
   a) Is the estimate number reasonable for this task? 
      - Consider: task complexity, typical duration for similar tasks, scope
      - Be critical: Is 30min for "write a blog post" reasonable? (Probably not - too short)
   b) Does the explanation provide THOROUGH, DETAILED reasoning?
      - Does it consider MULTIPLE relevant factors? (complexity, scope, interruptions, ambiguity, etc.)
      - Is the reasoning detailed and well-thought-out, not just brief or superficial?
      - Does it demonstrate deep understanding, not just surface acknowledgment?
   c) Are there logical flaws in the explanation?
      - Contradictions, unrealistic assumptions, missing key factors?
   
   Score 1 only if BOTH number is reasonable AND explanation is THOROUGH and DETAILED (not brief or superficial).
   Score 0 if the number is problematic OR if the explanation lacks depth/detail.

2. **Consistency** (0 or 1):
   a) **Explanation-Number Alignment**: Does explanation THOROUGHLY justify the specific number?
      - If explanation says "simple, quick task" but estimate is 2 hours, that's inconsistent (score 0)
      - If explanation mentions complexity but estimate is very low, that's inconsistent
      - The explanation must provide DETAILED justification, not just brief mention
   b) **Range Alignment**: Does explanation THOROUGHLY account for the range?
      - Does it explain in DETAIL why optimistic differs from pessimistic?
      - If range is wide but explanation doesn't adequately explain uncertainty, that's a problem
      - Brief mentions are not enough - need detailed explanation
   c) **Internal Consistency**: Is explanation internally consistent?
      - No contradictions within the explanation
      - All parts align logically
   
   Score 1 only if ALL THREE aspects are consistent AND the explanation provides DETAILED justification.
   Score 0 if any aspect has issues OR if the explanation is too brief/superficial.

3. **Range Appropriateness** (0 or 1):
   - Are optimistic < realistic < pessimistic? (If not, score 0)
   - Is the range reasonable? 
     * Too narrow (e.g., 29-30-31 min) suggests overconfidence (score 0)
     * Too wide (e.g., 5-30-120 min for simple task) suggests uncertainty (score 0)
     * Good range: accounts for uncertainty without being excessive
   - Does range make sense for task type?
     * Simple tasks should have narrower ranges
     * Complex/ambiguous tasks can have wider ranges

4. **Category Appropriateness** (0 or 1):
   - Does category match task description? (If clearly wrong, score 0)
   - Is it an appropriate category? (If better category exists but current one is reasonable, can still score 1)

5. **Overall Quality** (0 or 1):
   - Score 1 ONLY if: ALL dimensions are GOOD quality. The number is well-justified, the explanation is thorough and thoughtful (not shallow or simplistic), the range is appropriate and well-explained, the category is correct, and everything is consistent. The estimate demonstrates good understanding and handling of the task's complexity/ambiguity. The explanation must adequately address the task's nuances and provide sufficient detail. If the explanation lacks depth, if there are noticeable problems, or if any dimension is merely "acceptable" rather than "good", score 0.
   - Score 0 if: ANY dimension has problems. This includes: unreasonable numbers, poor or shallow explanations, inappropriate ranges, wrong categories, inconsistencies, or failure to adequately address task complexity/ambiguity. Score 0 if the explanation is too simplistic, lacks sufficient detail, or doesn't adequately address the task's complexity. Estimates that are "acceptable but have noticeable problems" should score 0.

CRITICAL: 
- Evaluate each dimension independently.
- Assess task clarity from the task description itself - don't assume it's good or bad
- If task is vague and estimate acknowledges this WITH SUFFICIENT DETAIL and explains HOW/WHY → score 1
- If task is vague and estimate only briefly mentions uncertainty → score 0 (needs detail)
- If task is clear and estimate is vague or doesn't use details → score 0
- If task is vague and estimate is overly precise → score 0
- Look at the ACTUAL quality: Is this GOOD (1) or does it have problems (0)?
- Be VERY STRICT: If the explanation is brief, lacks detail, or feels superficial, score 0
- Ask yourself: "Would I say this explanation 'lacks depth' or 'could be more thorough'?" If yes, score 0
- Compare to the examples: Is this more like Example 1 or 2 (1), or Example 3, 4, or 5 (0)?
- Remember: "Acceptable but has noticeable problems" = Score 0. Only "Good quality" = Score 1.

Respond in JSON format:
{{
    "overall_score": <0 or 1>,
    "reasonableness_score": <0 or 1>,
    "consistency_score": <0 or 1>,
    "range_score": <0 or 1>,
    "category_score": <0 or 1>,
    "reasoning": "<brief explanation. Be specific: Why this score? What issues exist? What's good? If you scored 1, explain why it's fundamentally sound. If you scored 0, explain the significant problems.",
    "checks": {{
        "reasonable_number": <true/false - is the estimate number reasonable?>,
        "reasonable_explanation": <true/false - does explanation have sound reasoning?>,
        "explanation_number_aligned": <true/false - does explanation support the number?>,
        "range_aligned": <true/false - does explanation account for the range?>,
        "internally_consistent": <true/false - is explanation internally consistent?>,
        "range_valid": <true/false - is optimistic < realistic < pessimistic?>,
        "category_appropriate": <true/false>
    }}
}}"""
    
    def _generate_five_point_prompt(self, task_description: str, estimated: int, optimistic: int,
                                   realistic: int, pessimistic: int, explanation: str, category: str,
                                   ambiguity: str, prompt_quality_instructions: str) -> str:
        """Generate 1-5 scoring prompt."""
        return f"""Evaluate the quality of this time estimate for a task. Use a 1-5 scale where:
- 5 = Excellent quality (outstanding in all dimensions)
- 4 = Good quality (solid, minor improvements possible)
- 3 = Acceptable quality (adequate but has noticeable problems)
- 2 = Poor quality (significant problems)
- 1 = Very poor quality (major flaws)

{prompt_quality_instructions}

TASK: "{task_description}"

ESTIMATE:
- Estimated time: {estimated} minutes
- Range: {optimistic} (optimistic) - {realistic} (realistic) - {pessimistic} (pessimistic) minutes
- Explanation: {explanation}
- Category: {category}
- Ambiguity: {ambiguity}

SCORING RUBRIC (1-5 scale):

1. **Reasonableness** (1-5):
   - 5: Number is highly reasonable and well-justified; explanation is thorough and considers multiple relevant factors
   - 4: Number is reasonable; explanation is good but could be slightly more detailed
   - 3: Number is somewhat reasonable; explanation provides some reasoning but lacks depth or detail
   - 2: Number is questionable; explanation is brief or lacks sufficient justification
   - 1: Number is unreasonable; explanation is inadequate or missing

2. **Consistency** (1-5):
   - 5: Explanation perfectly aligns with number and range; all parts are internally consistent
   - 4: Explanation aligns well with number and range; minor inconsistencies
   - 3: Explanation somewhat aligns but has noticeable gaps or inconsistencies
   - 2: Explanation doesn't adequately justify the number or range; inconsistencies present
   - 1: Major inconsistencies between explanation, number, and range

3. **Range Appropriateness** (1-5):
   - 5: Range is excellent - appropriate width, well-justified, accounts for uncertainty appropriately
   - 4: Range is good - appropriate but could be slightly better justified
   - 3: Range is acceptable - reasonable but may be too narrow/wide or not well-explained
   - 2: Range is problematic - too narrow/wide for the task or poorly explained
   - 1: Range is invalid or completely inappropriate

4. **Category Appropriateness** (1-5):
   - 5: Category is perfect match
   - 4: Category is appropriate
   - 3: Category is acceptable but not ideal
   - 2: Category is questionable
   - 1: Category is clearly wrong

5. **Overall Quality** (1-5):
   Consider all dimensions together:
   - 5: Excellent - outstanding in all aspects, thorough, well-reasoned
   - 4: Good - solid quality, minor improvements possible
   - 3: Acceptable - adequate but has noticeable problems or lacks depth
   - 2: Poor - significant problems in multiple dimensions
   - 1: Very poor - major flaws, unreasonable, or fundamentally flawed

EVALUATION PROCESS:
1. Assess each dimension separately (1-5)
2. Consider task clarity and complexity
3. Determine overall score based on all dimensions
4. Provide specific reasoning for your scores

Respond in JSON format:
{{
    "overall_score": <1-5>,
    "reasonableness_score": <1-5>,
    "consistency_score": <1-5>,
    "range_score": <1-5>,
    "category_score": <1-5>,
    "reasoning": "<brief explanation. Be specific: Why these scores? What's good? What could be improved?",
    "checks": {{
        "reasonable_number": <true/false>,
        "reasonable_explanation": <true/false>,
        "explanation_number_aligned": <true/false>,
        "range_aligned": <true/false>,
        "internally_consistent": <true/false>,
        "range_valid": <true/false>,
        "category_appropriate": <true/false>
    }}
}}"""
    
    def evaluate_estimate_quality(self, task_description: str, estimate: Dict, prompt_quality: str = "unknown") -> Dict:
        """
        Evaluate the quality of an estimate using AI.
        
        Args:
            task_description: The task that was estimated
            estimate: Estimate dict with estimated_minutes, estimate_range, explanation, category, ambiguity
            prompt_quality: Quality of the original prompt (for context)
            
        Returns:
            Dict with score (0-1 for binary, 1-5 for five_point), reasoning, and individual checks
        """
        # No refusal logic - always evaluate estimates, even if vague
        estimated = estimate.get('estimated_minutes', 0)
        range_data = estimate.get('estimate_range', {})
        optimistic = range_data.get('optimistic', 0)
        realistic = range_data.get('realistic', estimated)
        pessimistic = range_data.get('pessimistic', 0)
        explanation = estimate.get('explanation', '')
        category = estimate.get('category', 'unknown')
        ambiguity = estimate.get('ambiguity', 'unknown')
        
        # #region agent log
        import json
        with open('/Users/adimiddha/time-calibration-agent/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "C",
                "location": "quality_evaluation.py:evaluate_estimate_quality",
                "message": "Evaluator received task",
                "data": {
                    "prompt_quality": prompt_quality,
                    "task_length": len(task_description),
                    "estimated_minutes": estimated,
                    "explanation_length": len(explanation)
                },
                "timestamp": int(__import__('time').time() * 1000)
            }) + '\n')
        # #endregion
        
        # Include prompt quality context in evaluation
        prompt_quality_instructions = ""
        if prompt_quality != "unknown":
            if prompt_quality == "poor":
                prompt_quality_instructions = """
⚠️ CONTEXT: The original task prompt was POOR QUALITY (vague, missing info, poorly written).
- Score estimates that ACKNOWLEDGE the ambiguity and provide appropriate wide ranges as 1 (good quality)
- Score estimates that IGNORE the poor prompt quality and give overly precise numbers as 0 (poor quality)
- A good estimate for a poor prompt should recognize uncertainty and account for it
"""
            elif prompt_quality == "excellent":
                prompt_quality_instructions = """
⚠️ CRITICAL CONTEXT: The original task prompt was EXCELLENT QUALITY (clear, specific, well-written).

SCORING FOR EXCELLENT PROMPTS:
- Score 1: Estimate EXCELLENTLY uses the clear information - very precise, well-justified, uses specific details from prompt, thorough explanation
- Score 0: Estimate POORLY uses the clear information - vague despite clear prompt, doesn't use specific details, poor explanation, or ignores clear details

IMPORTANT: An excellent prompt deserves an excellent estimate. If the estimate is vague or doesn't use the clear information, score it 0.
Only score 1 if the estimate EXCELLENTLY uses the clear information provided.
"""
            elif prompt_quality == "good":
                prompt_quality_instructions = """
NOTE: The original task prompt was of GOOD quality. Standard evaluation applies.
"""
        
        # Generate prompt based on scoring mode
        prompt = self._generate_evaluation_prompt(
            task_description, estimated, optimistic, realistic, pessimistic,
            explanation, category, ambiguity, prompt_quality_instructions
        )
        
        try:
            # #region agent log
            import json as json_module
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            with open('/Users/adimiddha/time-calibration-agent/.cursor/debug.log', 'a') as f:
                f.write(json_module.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "F",
                    "location": "quality_evaluation.py:evaluate_estimate_quality",
                    "message": "Sending prompt to evaluator",
                    "data": {
                        "prompt_quality": prompt_quality,
                        "prompt_has_quality_context": "CONTEXT" in prompt or "POOR QUALITY" in prompt or "EXCELLENT QUALITY" in prompt,
                        "prompt_length": len(prompt),
                        "prompt_preview": prompt_preview
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }) + '\n')
            # #endregion
            
            # System message based on scoring mode
            if self.scoring_mode == "five_point":
                system_message = "You are an expert evaluator of time estimates. Use a 1-5 scale (5=excellent, 4=good, 3=acceptable, 2=poor, 1=very poor). Evaluate each estimate independently. Always respond with valid JSON."
            else:
                system_message = "You are an expert evaluator of time estimates. Use binary scoring: 0 (poor quality) or 1 (good quality). Score 1 if the estimate is fundamentally sound. Score 0 if there are significant problems. Evaluate each estimate independently. Always respond with valid JSON."
            
            response = self.client.chat.completions.create(
                model=self.evaluator_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.6
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            # #region agent log
            import json as json_module
            with open('/Users/adimiddha/time-calibration-agent/.cursor/debug.log', 'a') as f:
                f.write(json_module.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "D,E",
                    "location": "quality_evaluation.py:evaluate_estimate_quality",
                    "message": "Evaluator scored estimate",
                    "data": {
                        "prompt_quality": prompt_quality,
                        "raw_overall_score": result.get("overall_score", 0),
                        "raw_reasonableness": result.get("reasonableness_score", 0),
                        "raw_consistency": result.get("consistency_score", 0),
                        "reasoning_preview": result.get("reasoning", "")[:100]
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }) + '\n')
            # #endregion
            
            checks = result.get("checks", {})
            
            # Handle scores based on scoring mode
            if self.scoring_mode == "five_point":
                # Keep 1-5 scores as-is
                overall_score = result.get("overall_score", 0)
                reasonableness_score = result.get("reasonableness_score", 0)
                consistency_score = result.get("consistency_score", 0)
                range_score = result.get("range_score", 0)
                category_score = result.get("category_score", 0)
            else:
                # Binary mode: keep as 0-1, but convert if they come in as 1-5 (for backward compatibility)
                overall_score = result.get("overall_score", 0)
                if overall_score > 1:
                    overall_score = 1 if overall_score >= 4 else 0
                
                reasonableness_score = result.get("reasonableness_score", 0)
                if reasonableness_score > 1:
                    reasonableness_score = 1 if reasonableness_score >= 4 else 0
                
                consistency_score = result.get("consistency_score", 0)
                if consistency_score > 1:
                    consistency_score = 1 if consistency_score >= 4 else 0
                
                range_score = result.get("range_score", 0)
                if range_score > 1:
                    range_score = 1 if range_score >= 4 else 0
                
                category_score = result.get("category_score", 0)
                if category_score > 1:
                    category_score = 1 if category_score >= 4 else 0
            
            return {
                "score": overall_score,
                "reasonableness_score": reasonableness_score,
                "consistency_score": consistency_score,
                "range_score": range_score,
                "category_score": category_score,
                "reasoning": result.get("reasoning", "No reasoning provided"),
                "checks": {
                    "reasonable_number": checks.get("reasonable_number", checks.get("reasonable", True)),
                    "reasonable_explanation": checks.get("reasonable_explanation", True),
                    "explanation_number_aligned": checks.get("explanation_number_aligned", checks.get("consistent", True)),
                    "range_aligned": checks.get("range_aligned", True),
                    "internally_consistent": checks.get("internally_consistent", True),
                    "range_valid": checks.get("range_valid", True),
                    "category_appropriate": checks.get("category_appropriate", checks.get("category_appropriate", True))
                },
                "evaluator": "ai",
                "model": self.evaluator_model
            }
        except Exception as e:
            print(f"Warning: AI evaluation failed: {e}")
            # Fall back to heuristic checks
            return self._heuristic_evaluation(task_description, estimate)
    
    def _heuristic_evaluation(self, task_description: str, estimate: Dict) -> Dict:
        """Fallback heuristic evaluation if AI evaluation fails."""
        estimated = estimate.get('estimated_minutes', 0)
        range_data = estimate.get('estimate_range', {})
        optimistic = range_data.get('optimistic', 0)
        realistic = range_data.get('realistic', estimated)
        pessimistic = range_data.get('pessimistic', 0)
        category = estimate.get('category', 'unknown')
        
        checks = {
            "reasonable": estimated > 0 and estimated < 10000,  # Sanity check
            "consistent": bool(estimate.get('explanation')),
            "range_valid": optimistic <= realistic <= pessimistic and optimistic > 0,
            "category_appropriate": category in ["deep work", "admin", "social", "errands", 
                                                  "coding", "writing", "meetings", "learning", "general"]
        }
        
        # Calculate binary score based on checks - score 1 if all checks pass, 0 otherwise
        all_checks_pass = all([
            checks["reasonable"],
            checks["consistent"],
            checks["range_valid"],
            checks["category_appropriate"]
        ])
        score = 1 if all_checks_pass else 0
        
        return {
            "score": score,
            "reasonableness_score": 1 if checks["reasonable"] else 0,
            "consistency_score": 1 if checks["consistent"] else 0,
            "range_score": 1 if checks["range_valid"] else 0,
            "category_score": 1 if checks["category_appropriate"] else 0,
            "reasoning": "Heuristic evaluation (AI evaluation unavailable)",
            "checks": checks,
            "evaluator": "heuristic"
        }
    
    def run_heuristic_checks(self, estimates: List[Dict]) -> Dict:
        """
        Run basic heuristic checks on a list of estimates.
        
        Args:
            estimates: List of estimate dicts
            
        Returns:
            Dict with check results and summary
        """
        results = {
            "total": len(estimates),
            "all_positive": 0,
            "ranges_valid": 0,
            "categories_valid": 0,
            "has_explanations": 0,
            "issues": []
        }
        
        for i, estimate in enumerate(estimates):
            estimated = estimate.get('estimated_minutes', 0)
            range_data = estimate.get('estimate_range', {})
            optimistic = range_data.get('optimistic', 0)
            realistic = range_data.get('realistic', estimated)
            pessimistic = range_data.get('pessimistic', 0)
            category = estimate.get('category', '')
            explanation = estimate.get('explanation', '')
            
            # Check estimates are positive
            if estimated > 0:
                results["all_positive"] += 1
            else:
                results["issues"].append(f"Estimate {i+1}: Non-positive estimate ({estimated})")
            
            # Check ranges are valid
            if optimistic <= realistic <= pessimistic and optimistic > 0:
                results["ranges_valid"] += 1
            else:
                results["issues"].append(f"Estimate {i+1}: Invalid range ({optimistic} <= {realistic} <= {pessimistic})")
            
            # Check categories are valid
            valid_categories = ["deep work", "admin", "social", "errands", "coding", 
                              "writing", "meetings", "learning", "general"]
            if category in valid_categories:
                results["categories_valid"] += 1
            else:
                results["issues"].append(f"Estimate {i+1}: Invalid category ({category})")
            
            # Check explanations exist
            if explanation:
                results["has_explanations"] += 1
            else:
                results["issues"].append(f"Estimate {i+1}: Missing explanation")
        
        # Calculate percentages
        if results["total"] > 0:
            results["all_positive_pct"] = (results["all_positive"] / results["total"]) * 100
            results["ranges_valid_pct"] = (results["ranges_valid"] / results["total"]) * 100
            results["categories_valid_pct"] = (results["categories_valid"] / results["total"]) * 100
            results["has_explanations_pct"] = (results["has_explanations"] / results["total"]) * 100
        else:
            results["all_positive_pct"] = 0
            results["ranges_valid_pct"] = 0
            results["categories_valid_pct"] = 0
            results["has_explanations_pct"] = 0
        
        return results
    


class HumanEvaluator:
    """Collects human evaluations of estimates."""
    
    def __init__(self, output_path: str = "human_evaluations.json"):
        """
        Initialize human evaluator.
        
        Args:
            output_path: Path to save human evaluations
        """
        self.output_path = Path(output_path)
        self.evaluations = []
    
    def load_evaluations(self) -> List[Dict]:
        """Load existing human evaluations."""
        if self.output_path.exists():
            with open(self.output_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "evaluations" in data:
                    return data["evaluations"]
        return []
    
    def save_evaluations(self, evaluations: List[Dict]):
        """
        Save human evaluations to file.
        
        Args:
            evaluations: List of evaluation dicts
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "evaluations": evaluations,
            "total_count": len(evaluations)
        }
        
        with open(self.output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Human evaluations saved to: {self.output_path}")


def evaluate_estimates_quality(estimates: List[Dict], task_descriptions: List[str],
                               evaluator: str = "ai") -> List[Dict]:
    """
    Evaluate quality of multiple estimates.
    
    Args:
        estimates: List of estimate dicts
        task_descriptions: List of corresponding task descriptions
        evaluator: Evaluation method ("ai", "heuristic", or "both")
        
    Returns:
        List of evaluation results
    """
    quality_evaluator = QualityEvaluator()
    results = []
    
    for task_desc, estimate in zip(task_descriptions, estimates):
        if evaluator in ["ai", "both"]:
            eval_result = quality_evaluator.evaluate_estimate_quality(task_desc, estimate)
            results.append(eval_result)
        elif evaluator == "heuristic":
            eval_result = quality_evaluator._heuristic_evaluation(task_desc, estimate)
            results.append(eval_result)
    
    return results


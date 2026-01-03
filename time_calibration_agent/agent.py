"""
Agent logic for estimating task durations and learning from outcomes.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Find project root (where .env file is located)
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"

# Load .env file and verify
if not env_path.exists():
    print(f"WARNING: .env file not found at {env_path}")
else:
    load_dotenv(dotenv_path=env_path, override=True)  # override=True ensures env vars are updated
    
    # Verify API key was loaded
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: OPENAI_API_KEY not found in .env file")
    elif api_key.startswith("your_") or "placeholder" in api_key.lower():
        print(f"ERROR: .env file contains placeholder text, not a real API key!")
        print(f"Please update .env with your actual OpenAI API key")
    else:
        # Key looks valid (starts with sk-)
        pass  # All good


# Valid task categories that can be assigned to estimates
VALID_CATEGORIES = [
    "deep work",
    "admin",
    "social",
    "errands",
    "coding",
    "writing",
    "meetings",
    "learning",
    "general"  # Fallback category
]

# Category normalization map - maps common variations to standard categories
CATEGORY_NORMALIZATION = {
    "personal care": "admin",
    "maintenance": "admin",
    "routine": "admin",
    "personal": "admin",
    "household": "admin",
    "chores": "admin",
    "shopping": "errands",
    "travel": "errands",
    "transportation": "errands",
    "commute": "errands",
    "fitness": "general",  # Could be its own category, but using general for now
    "exercise": "general",
    "workout": "general",
    "programming": "coding",
    "development": "coding",
    "software": "coding",
    "documentation": "writing",
    "blog": "writing",
    "content": "writing",
    "study": "learning",
    "education": "learning",
    "research": "learning",
    "focused work": "deep work",
    "concentration": "deep work",
    "collaboration": "meetings",
    "call": "meetings",
    "conversation": "social",
    "communication": "social",
}


def normalize_category(category: str) -> str:
    """
    Normalize a category string to a valid category.
    
    Args:
        category: Category string (may be lowercase, have variations, etc.)
        
    Returns:
        Normalized category from VALID_CATEGORIES, or "general" as fallback
    """
    if not category:
        return "general"
    
    # Convert to lowercase and strip whitespace
    category_lower = category.lower().strip()
    
    # Direct match
    if category_lower in VALID_CATEGORIES:
        return category_lower
    
    # Check normalization map
    if category_lower in CATEGORY_NORMALIZATION:
        return CATEGORY_NORMALIZATION[category_lower]
    
    # Try partial matches (e.g., "deep work" matches "deep work")
    for valid_cat in VALID_CATEGORIES:
        if valid_cat in category_lower or category_lower in valid_cat:
            return valid_cat
    
    # Fallback to general
    return "general"


def validate_and_normalize_category(category: str) -> str:
    """
    Validate and normalize a category from AI response.
    
    Args:
        category: Category string from AI
        
    Returns:
        Valid, normalized category
    """
    return normalize_category(category)


class EstimationAgent:
    """AI agent that estimates task durations and learns from feedback."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"  # Using mini for cost efficiency
    
    def find_category_for_task(self, task_description: str, all_tasks: List[Dict]) -> Optional[str]:
        """
        Find the category used for similar tasks in history.
        Used to maintain consistency in categorization.
        
        Args:
            task_description: The task description to match
            all_tasks: List of all tasks (completed or pending) to search
            
        Returns:
            Category string if similar task found, None otherwise
        """
        if not all_tasks:
            return None
        
        # Simple text similarity check - look for tasks with similar descriptions
        task_lower = task_description.lower().strip()
        
        # Check for exact or very similar matches
        for task in reversed(all_tasks):  # Check most recent first
            task_desc = task.get('description', '').lower().strip()
            category = task.get('category')
            
            if not category:
                continue
            
            # Exact match
            if task_desc == task_lower:
                return category
            
            # Very similar (one is substring of the other, or vice versa)
            if len(task_lower) > 5 and len(task_desc) > 5:
                if task_lower in task_desc or task_desc in task_lower:
                    # Check if they're similar enough (at least 80% overlap)
                    shorter = min(len(task_lower), len(task_desc))
                    longer = max(len(task_lower), len(task_desc))
                    if shorter / longer >= 0.8:
                        return category
        
        return None
    
    def estimate_task(self, task_description: str, 
                     calibration_context: Optional[Dict] = None,
                     historical_tasks: Optional[List[Dict]] = None,
                     suggested_category: Optional[str] = None) -> Dict:
        """
        Estimate duration for a task.
        
        Returns:
            {
                "estimated_minutes": int,
                "estimate_range": {
                    "optimistic": int,
                    "realistic": int,
                    "pessimistic": int
                },
                "explanation": str,
                "category": str,
                "ambiguity": str
            }
        """
        
        # Build context about user's historical patterns
        context_parts = []
        
        if calibration_context:
            bias = calibration_context.get('user_bias', 0.0)
            if bias > 0.1:
                context_parts.append(f"Historical pattern: Previous estimates have tended to UNDERESTIMATE by ~{bias:.1%} on average (actual time was longer than estimated).")
            elif bias < -0.1:
                context_parts.append(f"Historical pattern: Previous estimates have tended to OVERESTIMATE by ~{abs(bias):.1%} on average (actual time was shorter than estimated).")
            
            category_patterns = calibration_context.get('category_patterns', {})
            if category_patterns:
                context_parts.append("Category-specific patterns:")
                for category, pattern in list(category_patterns.items())[:3]:  # Top 3
                    context_parts.append(f"  - {category}: {pattern}")
        
        # Include category hint if provided
        if suggested_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{suggested_category}'. Please use this same category for consistency.")
        
        # Include similar historical tasks for reference
        if historical_tasks:
            similar_examples = []
            for task in historical_tasks[-10:]:  # Last 10 completed tasks
                if task.get('actual_minutes'):
                    similar_examples.append(
                        f"  - '{task['description'][:50]}...': "
                        f"estimated {task['estimated_minutes']}min, "
                        f"actual {task['actual_minutes']}min "
                        f"(error: {((task['actual_minutes'] - task['estimated_minutes']) / task['estimated_minutes'] * 100):.0f}%)"
                    )
            if similar_examples:
                context_parts.append("Recent similar tasks:")
                context_parts.extend(similar_examples)
        
        context_str = "\n".join(context_parts) if context_parts else "No historical data yet."
        
        prompt = f"""You are a time estimation expert helping someone become better calibrated at estimating task durations.

Your goal is to provide accurate, realistic time estimates that help the user learn.

CONTEXT FROM ESTIMATION HISTORY:
{context_str}

TASK TO ESTIMATE:
"{task_description}"

Please provide:
1. A realistic estimate in minutes (this is your best guess)
2. A range: optimistic (best case), realistic (most likely), pessimistic (worst case)
3. A brief explanation of your assumptions
4. Task category - MUST be one of these exact values:
   - "deep work": Focused, cognitively demanding work requiring concentration (e.g., problem-solving, analysis, strategic thinking)
   - "admin": Administrative tasks, routine maintenance, personal care, household chores (e.g., email, scheduling, brushing teeth, cleaning)
   - "social": Social interactions, conversations, networking (e.g., coffee with friend, team lunch, phone call)
   - "errands": Tasks outside the home/workplace, transportation, shopping (e.g., grocery shopping, picking up dry cleaning, driving somewhere)
   - "coding": Software development, programming, technical implementation (e.g., writing code, debugging, code review)
   - "writing": Creating written content (e.g., blog posts, documentation, reports, emails)
   - "meetings": Scheduled meetings, calls, collaborative sessions (e.g., team meeting, client call, standup)
   - "learning": Educational activities, studying, skill development (e.g., reading, taking a course, watching tutorials)
   - "general": Tasks that don't fit clearly into other categories
5. Ambiguity level ("clear" if well-defined, "moderate" if somewhat vague, "fuzzy" if very unclear)

IMPORTANT FOR CATEGORIZATION:
- Be consistent: If you've seen a similar task before, use the same category
- Personal care tasks (brushing teeth, showering, etc.) should be "admin"
- Transportation/driving tasks should be "errands"
- Choose the most specific category that fits

Consider:
- Task complexity and scope
- Potential interruptions or context switching
- Historical estimation patterns (if available) - note that these refer to the agent's past estimation accuracy, not the user's ability
- Typical time for similar tasks

Respond in this exact JSON format:
{{
    "estimated_minutes": <number>,
    "estimate_range": {{
        "optimistic": <number>,
        "realistic": <number>,
        "pessimistic": <number>
    }},
    "explanation": "<brief explanation>",
    "category": "<category name - must be one of the exact values listed above>",
    "ambiguity": "<clear|moderate|fuzzy>"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful time estimation assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3  # Lower temperature for more consistent estimates
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            # Validate and normalize category
            # If suggested_category was provided and AI didn't use it, prefer the suggestion for consistency
            raw_category = result.get("category", "general")
            if suggested_category and raw_category.lower() != suggested_category.lower():
                # AI didn't follow the suggestion - use the suggested category for consistency
                normalized_category = validate_and_normalize_category(suggested_category)
            else:
                normalized_category = validate_and_normalize_category(raw_category)
            
            # Validate and ensure all required fields
            return {
                "estimated_minutes": int(result.get("estimated_minutes", 30)),
                "estimate_range": {
                    "optimistic": int(result.get("estimate_range", {}).get("optimistic", result.get("estimated_minutes", 30) * 0.7)),
                    "realistic": int(result.get("estimate_range", {}).get("realistic", result.get("estimated_minutes", 30))),
                    "pessimistic": int(result.get("estimate_range", {}).get("pessimistic", result.get("estimated_minutes", 30) * 1.5))
                },
                "explanation": result.get("explanation", "No explanation provided"),
                "category": normalized_category,
                "ambiguity": result.get("ambiguity", "moderate")
            }
        except Exception as e:
            # Fallback if API call fails
            print(f"Warning: API call failed: {e}")
            return {
                "estimated_minutes": 30,
                "estimate_range": {
                    "optimistic": 20,
                    "realistic": 30,
                    "pessimistic": 45
                },
                "explanation": "Default estimate (API unavailable)",
                "category": "general",
                "ambiguity": "moderate"
            }
    
    def find_similar_completed_task(self, task_description: str, completed_tasks: List[Dict]) -> Optional[Dict]:
        """
        Find a similar completed task that matches the given task description.
        Used to reuse actual times from previous identical or very similar tasks.
        
        Args:
            task_description: The task description to match
            completed_tasks: List of completed tasks (with actual_minutes) to search
            
        Returns:
            Matched task dictionary with match confidence, or None if no good match
        """
        if not completed_tasks:
            return None
        
        # Build task list for the prompt - only include completed tasks
        task_list = []
        for i, task in enumerate(completed_tasks):
            if not task.get('actual_minutes'):
                continue
            task_info = f"Task {i+1}:"
            task_info += f"\n  Description: {task['description']}"
            task_info += f"\n  Actual time: {task['actual_minutes']} minutes"
            if task.get('category'):
                task_info += f"\n  Category: {task['category']}"
            task_list.append(task_info)
        
        if not task_list:
            return None
        
        prompt = f"""You are helping match a new task to previously completed tasks to reuse accurate time estimates.

NEW TASK TO ESTIMATE: "{task_description}"

PREVIOUSLY COMPLETED TASKS:
{chr(10).join(task_list)}

Find if the new task is the SAME or VERY SIMILAR to any completed task. Consider:
- Exact matches (same description)
- Very similar tasks (e.g., "brushing my teeth" matches "brushing my teeth")
- Tasks that are essentially identical even if worded slightly differently

Respond with JSON:
{{
    "matched_task_index": <0-based index of matched task, or -1 if no good match>,
    "confidence": <"high" | "medium" | "low">,
    "reasoning": "<brief explanation>"
}}

Only match if confidence is "high" - meaning the tasks are essentially the same.
If the new task is different or only vaguely similar, set matched_task_index to -1."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a task matching assistant. Only match tasks that are essentially identical. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1  # Very low temperature for consistent matching
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            matched_index = result.get("matched_task_index", -1)
            confidence = result.get("confidence", "low")
            
            # Only return if we have high confidence match
            if matched_index >= 0 and matched_index < len(completed_tasks) and confidence == "high":
                matched_task = completed_tasks[matched_index]
                return {
                    "task": matched_task,
                    "confidence": confidence,
                    "reasoning": result.get("reasoning", "Matched similar task")
                }
            return None
        except Exception as e:
            print(f"Warning: Similar task matching failed: {e}")
            return None
    
    def match_task_query(self, query: str, tasks: List[Dict]) -> Optional[Dict]:
        """
        Match a natural language query to a task from a list of tasks.
        
        Args:
            query: Natural language query like "the task I just did" or "the writing task"
            tasks: List of task dictionaries to search through
            
        Returns:
            Matched task dictionary, or None if no match found
        """
        if not tasks:
            return None
        
        # Build task list for the prompt
        task_list = []
        for i, task in enumerate(tasks):
            task_info = f"Task {i+1}:"
            task_info += f"\n  ID: {task['id']}"
            task_info += f"\n  Description: {task['description']}"
            if task.get('category'):
                task_info += f"\n  Category: {task['category']}"
            if task.get('estimated_minutes'):
                task_info += f"\n  Estimated: {task['estimated_minutes']} minutes"
            if task.get('created_at'):
                task_info += f"\n  Created: {task['created_at']}"
            task_list.append(task_info)
        
        prompt = f"""You are helping a user find a task they want to log time for.

USER QUERY: "{query}"

AVAILABLE TASKS:
{chr(10).join(task_list)}

Interpret the user's query and match it to the most appropriate task. Consider:
- "the task I just did" or "the last task" → most recently created task
- "the writing task" → task with "writing" in description or category
- Partial descriptions → match by keywords
- Task numbers → match by position

Respond with JSON:
{{
    "matched_task_index": <0-based index of matched task, or -1 if no match>,
    "confidence": <"high" | "medium" | "low">,
    "reasoning": "<brief explanation of why this task was matched>"
}}

If no task matches well, set matched_task_index to -1."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful task matching assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            matched_index = result.get("matched_task_index", -1)
            
            if matched_index >= 0 and matched_index < len(tasks):
                return {
                    "task": tasks[matched_index],
                    "confidence": result.get("confidence", "medium"),
                    "reasoning": result.get("reasoning", "Matched by AI")
                }
            return None
        except Exception as e:
            print(f"Warning: Task matching API call failed: {e}")
            return None
    
    def reflect_on_outcome(self, task: Dict, calibration_data: Dict) -> Dict:
        """
        Reflect on a completed task to update learning.
        This generates insights that the learning system can use.
        
        Returns updated calibration insights.
        """
        if not task.get('actual_minutes'):
            return calibration_data
        
        error_pct = ((task['actual_minutes'] - task['estimated_minutes']) / 
                    task['estimated_minutes']) * 100
        
        prompt = f"""A task was completed with the following details:

Task: "{task['description']}"
Category: {task.get('category', 'unknown')}
Ambiguity: {task.get('ambiguity', 'unknown')}
Estimated: {task['estimated_minutes']} minutes
Actual: {task['actual_minutes']} minutes
Error: {error_pct:.1f}% {'overestimate' if error_pct < 0 else 'underestimate'}

Current calibration data:
- User bias: {calibration_data.get('user_bias', 0.0):.2%}
- Total tasks: {calibration_data.get('total_tasks', 0)}
- Category patterns: {calibration_data.get('category_patterns', {})}

What insights can we learn from this? Consider:
1. Was the estimate directionally correct?
2. Are there patterns by category or ambiguity?
3. Should we adjust future estimates for similar tasks?

Respond with JSON:
{{
    "insights": "<brief insights>",
    "suggested_bias_adjustment": <number between -0.1 and 0.1>,
    "category_adjustment": {{
        "<category>": <adjustment factor, e.g., 1.1 for 10% increase>
    }}
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a learning system that improves time estimates. Respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            import json
            reflection = json.loads(response.choices[0].message.content)
            return reflection
        except Exception as e:
            print(f"Warning: Reflection API call failed: {e}")
            return {
                "insights": "Unable to generate insights",
                "suggested_bias_adjustment": 0.0,
                "category_adjustment": {}
            }


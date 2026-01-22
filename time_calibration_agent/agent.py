"""
Agent logic for estimating task durations and learning from outcomes.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
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


class ContextStrategy(Enum):
    """Different strategies for building context in prompts."""
    MINIMAL = "minimal"  # No historical context, just system prompt
    RECENT_N = "recent_n"  # Last N tasks (current approach)
    SUMMARIZED = "summarized"  # AI-generated summary of history
    CATEGORY_FILTERED = "category_filtered"  # Only similar category tasks
    SIMILARITY_BASED = "similarity_based"  # Semantic similarity to current task


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
    
    def _build_context(self, task_description: str,
                     calibration_context: Optional[Dict] = None,
                     historical_tasks: Optional[List[Dict]] = None,
                      suggested_category: Optional[str] = None,
                      strategy: ContextStrategy = ContextStrategy.RECENT_N,
                      n: int = 10) -> str:
        """
        Build context string based on the specified strategy.
        
        Args:
            task_description: Current task description
            calibration_context: Calibration data
            historical_tasks: Available historical tasks
            suggested_category: Suggested category
            strategy: Context building strategy
            n: Number of tasks for RECENT_N strategy
        
        Returns:
            Context string for the prompt
        """
        if strategy == ContextStrategy.MINIMAL:
            return self._build_minimal_context(calibration_context, suggested_category)
        elif strategy == ContextStrategy.RECENT_N:
            return self._build_recent_context(calibration_context, historical_tasks, suggested_category, n)
        elif strategy == ContextStrategy.SUMMARIZED:
            return self._build_summarized_context(calibration_context, historical_tasks, suggested_category)
        elif strategy == ContextStrategy.CATEGORY_FILTERED:
            return self._build_category_context(task_description, calibration_context, historical_tasks, suggested_category)
        elif strategy == ContextStrategy.SIMILARITY_BASED:
            return self._build_similarity_context(task_description, calibration_context, historical_tasks, suggested_category, n)
        else:
            # Default to RECENT_N
            return self._build_recent_context(calibration_context, historical_tasks, suggested_category, n)
    
    def _build_minimal_context(self, calibration_context: Optional[Dict] = None,
                               suggested_category: Optional[str] = None) -> str:
        """Build minimal context with only calibration patterns, no task examples."""
        context_parts = []
        
        if calibration_context:
            bias = calibration_context.get('user_bias', 0.0)
            if abs(bias) > 0.1:
                if bias > 0.1:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to UNDERESTIMATE by ~{bias:.1%} on average.")
                else:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to OVERESTIMATE by ~{abs(bias):.1%} on average.")
        
        if suggested_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{suggested_category}'. Please use this same category for consistency.")
        
        return "\n".join(context_parts) if context_parts else "No historical data yet."
    
    def _build_recent_context(self, calibration_context: Optional[Dict] = None,
                             historical_tasks: Optional[List[Dict]] = None,
                             suggested_category: Optional[str] = None,
                             n: int = 10) -> str:
        """Build context with last N completed tasks (current approach)."""
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
        
        if suggested_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{suggested_category}'. Please use this same category for consistency.")
        
        if historical_tasks:
            similar_examples = []
            for task in historical_tasks[-n:]:  # Last N completed tasks
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
        
        return "\n".join(context_parts) if context_parts else "No historical data yet."
    
    def _build_summarized_context(self, calibration_context: Optional[Dict] = None,
                                  historical_tasks: Optional[List[Dict]] = None,
                                  suggested_category: Optional[str] = None) -> str:
        """Build context with AI-generated summary instead of raw tasks."""
        context_parts = []
        
        if calibration_context:
            bias = calibration_context.get('user_bias', 0.0)
            if abs(bias) > 0.1:
                if bias > 0.1:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to UNDERESTIMATE by ~{bias:.1%} on average.")
                else:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to OVERESTIMATE by ~{abs(bias):.1%} on average.")
            
            category_patterns = calibration_context.get('category_patterns', {})
            if category_patterns:
                context_parts.append("Category-specific patterns:")
                for category, pattern in list(category_patterns.items())[:3]:
                    context_parts.append(f"  - {category}: {pattern}")
        
        if suggested_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{suggested_category}'. Please use this same category for consistency.")
        
        if historical_tasks and len(historical_tasks) > 0:
            # Generate summary using AI
            summary = self._summarize_history(historical_tasks)
            if summary:
                context_parts.append("Summary of historical estimation patterns:")
                context_parts.append(summary)
        
        return "\n".join(context_parts) if context_parts else "No historical data yet."
    
    def _build_category_context(self, task_description: str,
                                calibration_context: Optional[Dict] = None,
                                historical_tasks: Optional[List[Dict]] = None,
                                suggested_category: Optional[str] = None) -> str:
        """Build context with only tasks from similar categories."""
        context_parts = []
        
        if calibration_context:
            bias = calibration_context.get('user_bias', 0.0)
            if abs(bias) > 0.1:
                if bias > 0.1:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to UNDERESTIMATE by ~{bias:.1%} on average.")
                else:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to OVERESTIMATE by ~{abs(bias):.1%} on average.")
        
        # Try to find category from similar tasks or use suggested
        target_category = suggested_category
        if not target_category and historical_tasks:
            # Try to infer category from task description or similar tasks
            target_category = self.find_category_for_task(task_description, historical_tasks)
        
        if target_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{target_category}'. Please use this same category for consistency.")
            
            # Filter tasks by category
            if historical_tasks:
                category_tasks = [t for t in historical_tasks if t.get('category') == target_category and t.get('actual_minutes')]
                if category_tasks:
                    similar_examples = []
                    for task in category_tasks[-10:]:  # Last 10 in this category
                        similar_examples.append(
                            f"  - '{task['description'][:50]}...': "
                            f"estimated {task['estimated_minutes']}min, "
                            f"actual {task['actual_minutes']}min "
                            f"(error: {((task['actual_minutes'] - task['estimated_minutes']) / task['estimated_minutes'] * 100):.0f}%)"
                        )
                    if similar_examples:
                        context_parts.append(f"Similar {target_category} tasks:")
                        context_parts.extend(similar_examples)
        
        return "\n".join(context_parts) if context_parts else "No historical data yet."
    
    def _build_similarity_context(self, task_description: str,
                                  calibration_context: Optional[Dict] = None,
                                  historical_tasks: Optional[List[Dict]] = None,
                                  suggested_category: Optional[str] = None,
                                  n: int = 5) -> str:
        """Build context with tasks that are semantically similar to current task."""
        context_parts = []
        
        if calibration_context:
            bias = calibration_context.get('user_bias', 0.0)
            if abs(bias) > 0.1:
                if bias > 0.1:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to UNDERESTIMATE by ~{bias:.1%} on average.")
                else:
                    context_parts.append(f"Historical pattern: Previous estimates have tended to OVERESTIMATE by ~{abs(bias):.1%} on average.")
        
        if suggested_category:
            context_parts.append(f"CATEGORY HINT: A similar task was previously categorized as '{suggested_category}'. Please use this same category for consistency.")
        
        # Use find_similar_completed_task to find similar tasks
        if historical_tasks:
            similar_match = self.find_similar_completed_task(task_description, historical_tasks)
            if similar_match and similar_match.get('confidence') == 'high':
                matched_task = similar_match['task']
                context_parts.append("Very similar completed task:")
                context_parts.append(
                    f"  - '{matched_task['description'][:50]}...': "
                    f"estimated {matched_task['estimated_minutes']}min, "
                    f"actual {matched_task['actual_minutes']}min"
                )
            else:
                # Fall back to recent tasks if no good match
                similar_examples = []
                for task in historical_tasks[-n:]:
                    if task.get('actual_minutes'):
                        similar_examples.append(
                            f"  - '{task['description'][:50]}...': "
                            f"estimated {task['estimated_minutes']}min, "
                            f"actual {task['actual_minutes']}min"
                        )
                if similar_examples:
                    context_parts.append("Recent similar tasks:")
                    context_parts.extend(similar_examples)
        
        return "\n".join(context_parts) if context_parts else "No historical data yet."
    
    def _summarize_history(self, historical_tasks: List[Dict]) -> Optional[str]:
        """
        Use AI to generate a concise summary of historical estimation patterns.
        
        Args:
            historical_tasks: List of completed tasks
            
        Returns:
            Summary string or None if generation fails
        """
        if not historical_tasks or len(historical_tasks) == 0:
            return None
        
        # Build task list for summary
        task_summaries = []
        for task in historical_tasks[-20:]:  # Last 20 for summary
            if task.get('actual_minutes'):
                error_pct = ((task['actual_minutes'] - task['estimated_minutes']) / task['estimated_minutes'] * 100) if task['estimated_minutes'] > 0 else 0
                task_summaries.append(
                    f"- {task.get('category', 'unknown')}: '{task['description'][:40]}' - "
                    f"Est: {task['estimated_minutes']}min, Actual: {task['actual_minutes']}min ({error_pct:+.0f}%)"
                )
        
        prompt = f"""Summarize the following task estimation history in 3-4 sentences. 
Focus on patterns: which categories are consistently over/underestimated, 
typical error magnitudes, and any notable trends.

Task History:
{chr(10).join(task_summaries)}

Provide a concise summary of estimation patterns:"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes patterns concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Warning: History summarization failed: {e}")
            return None
    
    def validate_task_clarity(self, task_description: str) -> Dict:
        """
        Validate if a task description is clear enough to provide a time estimate.
        
        Args:
            task_description: The task description to validate
            
        Returns:
            Dict with:
                - "is_clear": bool - True if task is clear enough to estimate
                - "reason": str - If not clear, explanation of why (e.g., "task_too_vague")
                - "explanation": str - Detailed explanation of why the task is unclear (if not clear)
        """
        # SIMPLE RULE-BASED VALIDATION: Only reject if obviously just a reference
        # Check BEFORE calling LLM
        task_lower = task_description.lower()
        task_words = task_description.split()
        
        # Only reject if it's EXTREMELY OBVIOUSLY just a reference (3 words or less, only references)
        reference_only_patterns = [
            'do that', 'handle that', 'that thing', 'do it', 'handle it', 
            'finish that', 'that task', 'do stuff', 'handle stuff'
        ]
        
        is_obvious_reference = (
            len(task_words) <= 3 and 
            any(pattern in task_lower for pattern in reference_only_patterns)
        )
        
        # If NOT obviously just a reference, ALWAYS accept (skip LLM call)
        if not is_obvious_reference:
            return {
                "is_clear": True,
                "reason": "clear",
                "explanation": "Task describes work to be done (rule-based: has substance, not just a reference)."
            }
        
        # Only call LLM if it's obviously just a reference (very rare case)
        prompt = f"""You are a task clarity validator. This task appears to be just a reference with no work described.

TASK DESCRIPTION: "{task_description}"

Only reject if it's OBVIOUSLY just a reference with NO work mentioned (like "do that", "handle it").

Respond in JSON format:
{{
    "is_clear": <true or false>,
    "reason": <"clear" if is_clear is true, or "task_too_vague" if false>,
    "explanation": "<Explain your decision>"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a task clarity validator. CRITICAL: DEFAULT TO ACCEPTING. Set is_clear to TRUE unless the task is OBVIOUSLY just a reference like 'do that' with NO work mentioned. If the task mentions ANY work/activity/action, ACCEPT it. Only reject if it's ONLY a reference with zero work described. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0  # Zero temperature for maximum consistency
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            # ULTRA-AGGRESSIVE: Always accept unless EXTREMELY obviously just a reference
            # Check BEFORE using LLM's decision
            task_lower = task_description.lower()
            task_words = task_description.split()
            
            # Only reject if it's EXTREMELY OBVIOUSLY just a reference (3 words or less, only references)
            reference_only_patterns = [
                'do that', 'handle that', 'that thing', 'do it', 'handle it', 
                'finish that', 'that task', 'do stuff', 'handle stuff'
            ]
            
            is_obvious_reference = (
                len(task_words) <= 3 and 
                any(pattern in task_lower for pattern in reference_only_patterns)
            )
            
            # If NOT obviously just a reference, ALWAYS accept (ignore LLM completely)
            if not is_obvious_reference:
                # Override to clear - task has substance
                is_clear = True
                result["reason"] = "clear"
                result["explanation"] = "Task describes work to be done (override: has substance, not just a reference)."
            else:
                # Only use LLM's decision if it's obviously just a reference
                is_clear = result.get("is_clear", True)
            
            return {
                "is_clear": is_clear,
                "reason": result.get("reason", "clear"),
                "explanation": result.get("explanation", "Task description is clear enough to estimate.")
            }
        except Exception as e:
            print(f"Warning: Task clarity validation failed: {e}")
            # Default to clear if validation fails (fail open)
            return {
                "is_clear": True,
                "reason": "clear",
                "explanation": "Task description is clear enough to estimate."
            }
    
    def estimate_task(self, task_description: str, 
                     calibration_context: Optional[Dict] = None,
                     historical_tasks: Optional[List[Dict]] = None,
                     suggested_category: Optional[str] = None,
                     context_strategy: ContextStrategy = ContextStrategy.RECENT_N,
                     context_n: int = 10) -> Dict:
        """
        Estimate duration for a task.
        
        Args:
            task_description: Description of the task to estimate
            calibration_context: Calibration data (bias, patterns)
            historical_tasks: List of completed tasks for context
            suggested_category: Suggested category for consistency
            context_strategy: Strategy for building context (default: RECENT_N)
            context_n: Number of tasks to include for RECENT_N strategy (default: 10)
        
        Returns:
            {
                "estimated_minutes": int (or None if cannot_estimate),
                "estimate_range": {
                    "optimistic": int,
                    "realistic": int,
                    "pessimistic": int
                } (or None if cannot_estimate),
                "explanation": str,
                "category": str (or None if cannot_estimate),
                "ambiguity": str,
                "cannot_estimate": bool (optional, True if task is too vague),
                "reason": str (optional, e.g., "task_too_vague" if cannot_estimate)
            }
        """
        
        # No refusal logic - always estimate, even if task is vague
        # Build context based on strategy
        context_str = self._build_context(
            task_description=task_description,
            calibration_context=calibration_context,
            historical_tasks=historical_tasks,
            suggested_category=suggested_category,
            strategy=context_strategy,
            n=context_n
        )
        
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


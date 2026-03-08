"""
Test dataset generation for evaluating general model quality.
Generates diverse task prompts covering different ambiguities, categories, lengths, and types.
"""

import json
import random
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


class TestDatasetGenerator:
    """Generates diverse test datasets for evaluation."""
    
    # Valid categories
    CATEGORIES = [
        "deep work", "admin", "social", "errands", "coding", 
        "writing", "meetings", "learning", "general"
    ]
    
    # Ambiguity levels
    AMBIGUITY_LEVELS = ["clear", "moderate", "fuzzy"]
    
    # Prompt lengths
    LENGTHS = ["short", "medium", "long"]
    
    # Task types
    TASK_TYPES = [
        "cooking", "cleaning", "work", "personal_care", "errands",
        "creative", "technical", "social", "learning"
    ]
    
    # Complexity levels
    COMPLEXITY_LEVELS = ["simple", "multi_step", "task_breakdown"]
    
    # Interruption likelihood levels
    INTERRUPTION_LEVELS = ["low", "medium", "high"]
    
    # Prompt quality levels (affects how well-described the task is)
    PROMPT_QUALITY_LEVELS = ["excellent", "good", "poor"]
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize generator with OpenAI client."""
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"
    
    def generate_test_dataset(self, n: int = 50, seed: Optional[int] = None, 
                             include_edge_cases: bool = True) -> List[Dict]:
        """
        Generate diverse test dataset with specified distribution.
        
        Args:
            n: Number of prompts to generate (default: 50)
            seed: Random seed for reproducibility
            include_edge_cases: Whether to include edge case prompts (very short/long tasks, etc.)
            
        Returns:
            List of test prompt dicts with metadata
        """
        if seed is not None:
            random.seed(seed)
        
        # Calculate distribution
        # Reserve some slots for edge cases if enabled
        edge_case_count = int(n * 0.1) if include_edge_cases else 0
        regular_count = n - edge_case_count
        
        ambiguity_dist = self._calculate_distribution(regular_count, {"clear": 0.3, "moderate": 0.5, "fuzzy": 0.2})
        length_dist = self._calculate_distribution(regular_count, {"short": 0.2, "medium": 0.5, "long": 0.3})
        complexity_dist = self._calculate_distribution(regular_count, {"simple": 0.4, "multi_step": 0.4, "task_breakdown": 0.2})
        interruption_dist = self._calculate_distribution(regular_count, {"low": 0.33, "medium": 0.34, "high": 0.33})
        prompt_quality_dist = self._calculate_distribution(regular_count, {"excellent": 0.2, "good": 0.6, "poor": 0.2})
        
        # Distribute categories evenly
        category_counts = self._distribute_evenly(regular_count, len(self.CATEGORIES))
        
        # Generate regular prompts
        prompts = []
        category_idx = 0
        
        for i in range(regular_count):
            # Select attributes based on distribution
            ambiguity = self._select_from_distribution(ambiguity_dist, self.AMBIGUITY_LEVELS)
            length = self._select_from_distribution(length_dist, self.LENGTHS)
            complexity = self._select_from_distribution(complexity_dist, self.COMPLEXITY_LEVELS)
            interruption = self._select_from_distribution(interruption_dist, self.INTERRUPTION_LEVELS)
            prompt_quality = self._select_from_distribution(prompt_quality_dist, self.PROMPT_QUALITY_LEVELS)
            
            # Cycle through categories
            category = self.CATEGORIES[category_idx % len(self.CATEGORIES)]
            category_idx += 1
            
            # Select task type (can be related to category or random)
            task_type = self._select_task_type(category)
            
            # Generate prompt using AI
            prompt_text = self._generate_prompt(
                category=category,
                ambiguity=ambiguity,
                length=length,
                task_type=task_type,
                complexity=complexity,
                interruption=interruption,
                prompt_quality=prompt_quality
            )
            
            prompts.append({
                "id": f"test_{i+1}",
                "prompt": prompt_text,
                "metadata": {
                    "category": category,
                    "ambiguity": ambiguity,
                    "length": length,
                    "task_type": task_type,
                    "complexity": complexity,
                    "interruption_likelihood": interruption,
                    "prompt_quality": prompt_quality
                }
            })
        
        # Add edge cases if enabled
        if include_edge_cases and edge_case_count > 0:
            edge_cases = self._generate_edge_cases(edge_case_count)
            prompts.extend(edge_cases)
        
        # Shuffle to mix edge cases with regular prompts
        random.shuffle(prompts)
        
        return prompts
    
    def _generate_edge_cases(self, n: int) -> List[Dict]:
        """
        Generate edge case prompts that are inherently harder to estimate.
        These should naturally lead to varied estimate quality.
        
        Args:
            n: Number of edge cases to generate
            
        Returns:
            List of edge case prompts
        """
        edge_case_types = [
            "very_short_task",      # < 5 minutes (brushing teeth, sending one email)
            "very_long_task",       # > 4 hours (full day project, multi-day task)
            "missing_scope",        # Unclear scope (e.g., "do the thing")
            "conflicting_info",     # Contradictory information
            "unrealistic_task",     # Impossible or unrealistic
            "too_vague",            # Extremely vague
            "overly_specific"       # Too much detail, might confuse
        ]
        
        edge_cases = []
        for i in range(n):
            case_type = random.choice(edge_case_types)
            prompt_text = self._generate_edge_case_prompt(case_type)
            
            edge_cases.append({
                "id": f"edge_case_{i+1}",
                "prompt": prompt_text,
                "metadata": {
                    "category": "general",  # Edge cases might not fit categories well
                    "ambiguity": "fuzzy",
                    "length": "short",
                    "task_type": "general",
                    "complexity": "simple",
                    "interruption_likelihood": "medium",
                    "prompt_quality": "poor",
                    "edge_case_type": case_type
                }
            })
        
        return edge_cases
    
    def _generate_edge_case_prompt(self, case_type: str) -> str:
        """Generate a specific type of edge case prompt."""
        edge_case_prompts = {
            "very_short_task": [
                "Brush my teeth",
                "Send one email",
                "Take out the trash",
                "Put on my shoes",
                "Turn off the lights",
                "Check the mail",
                "Fill up my water bottle"
            ],
            "very_long_task": [
                "Complete the entire software project from scratch including design, development, testing, and deployment",
                "Plan and execute a full-scale marketing campaign for a new product launch",
                "Write a comprehensive 200-page research paper with full citations and bibliography",
                "Organize and declutter my entire house including all rooms, closets, and storage areas",
                "Rebuild the entire company website from the ground up",
                "Plan a destination wedding for 200 guests"
            ],
            "missing_scope": [
                "Do the thing",
                "Handle that task",
                "Work on the project",
                "Take care of it",
                "Get it done",
                "Finish that",
                "Do what we discussed"
            ],
            "conflicting_info": [
                "Write a blog post that requires extensive research and multiple drafts but keep it quick",
                "Complete this simple task that involves coordinating with 20 people across 5 time zones",
                "Finish this urgent task that isn't due for 3 months",
                "Create a comprehensive analysis but make it brief",
                "Do a thorough job but be fast about it"
            ],
            "unrealistic_task": [
                "Learn fluent Spanish",
                "Build a skyscraper",
                "Read 1000 books",
                "Travel to Mars",
                "Master quantum physics",
                "Become a professional athlete",
                "Solve world hunger"
            ],
            "too_vague": [
                "Something related to work maybe",
                "I need to do stuff",
                "Various tasks",
                "Things that need doing",
                "Work stuff",
                "Some things",
                "That thing I mentioned"
            ],
            "overly_specific": [
                "Write a blog post about time management, using exactly 12 paragraphs, 3 subheadings, 5 bullet points, 2 quotes, and include 4 specific examples from psychology research papers published between 2018-2022, with proper APA citations, optimized for SEO with keyword density of 2.3%, and formatted in 12pt Times New Roman with 1.5 line spacing",
                "Create a presentation with exactly 15 slides, each slide must have between 3-5 bullet points, include 2 charts and 1 graph, use the company color scheme (hex codes #FF5733 and #33C3F0), and ensure all fonts are Arial 14pt with 1.2 line spacing"
            ]
        }
        
        if case_type in edge_case_prompts:
            return random.choice(edge_case_prompts[case_type])
        
        # Fallback
        return "Complete a task"
    
    def _calculate_distribution(self, total: int, weights: Dict[str, float]) -> Dict[str, int]:
        """Calculate exact counts for each category based on weights."""
        counts = {}
        remaining = total
        items = list(weights.items())
        
        for i, (key, weight) in enumerate(items[:-1]):
            count = int(total * weight)
            counts[key] = count
            remaining -= count
        
        # Last item gets remainder
        counts[items[-1][0]] = remaining
        
        return counts
    
    def _distribute_evenly(self, total: int, num_categories: int) -> List[int]:
        """Distribute items evenly across categories."""
        base = total // num_categories
        remainder = total % num_categories
        counts = [base] * num_categories
        for i in range(remainder):
            counts[i] += 1
        return counts
    
    def _select_from_distribution(self, distribution: Dict[str, int], options: List[str]) -> str:
        """Select an option based on distribution, removing from distribution."""
        for option in options:
            if distribution.get(option, 0) > 0:
                distribution[option] -= 1
                return option
        # Fallback to first option
        return options[0]
    
    def _select_task_type(self, category: str) -> str:
        """Select a task type, potentially related to category."""
        category_to_type = {
            "coding": "technical",
            "writing": "creative",
            "admin": "personal_care",
            "errands": "errands",
            "social": "social",
            "learning": "learning",
            "deep work": "work",
            "meetings": "work",
            "general": random.choice(self.TASK_TYPES)
        }
        return category_to_type.get(category, random.choice(self.TASK_TYPES))
    
    def _generate_prompt(self, category: str, ambiguity: str, length: str, 
                       task_type: str, complexity: str, interruption: str,
                       prompt_quality: str) -> str:
        """
        Use AI to generate a task prompt with specified characteristics.
        
        Args:
            category: Task category
            ambiguity: Ambiguity level (clear, moderate, fuzzy)
            length: Prompt length (short, medium, long)
            task_type: Type of task
            complexity: Complexity level
            interruption: Interruption likelihood (low, medium, high)
            
        Returns:
            Generated task prompt text
        """
        length_instructions = {
            "short": "1 sentence",
            "medium": "2-3 sentences",
            "long": "a paragraph (4-6 sentences)"
        }
        
        ambiguity_instructions = {
            "clear": "very specific and well-defined",
            "moderate": "somewhat vague or open to interpretation",
            "fuzzy": "very unclear or ambiguous"
        }
        
        complexity_instructions = {
            "simple": "a single, straightforward task",
            "multi_step": "a task with multiple steps that should be mentioned",
            "task_breakdown": "a complex task that could be broken down into subtasks"
        }
        
        interruption_instructions = {
            "low": "low interruption likelihood (e.g., deep work, focused tasks, isolated environment)",
            "medium": "medium interruption likelihood (e.g., office work, occasional meetings, shared workspace)",
            "high": "high interruption likelihood (e.g., on-call work, customer-facing, multi-tasking, open office)"
        }
        
        prompt_quality_instructions = {
            "excellent": "very well-described with specific details, clear scope, and all necessary information",
            "good": "adequately described with most details, but could be slightly more specific",
            "poor": "poorly described - vague, missing key information, unclear scope, or ambiguous wording"
        }
        
        # For poor quality prompts, we want them to be intentionally problematic
        if prompt_quality == "poor":
            quality_guidance = """IMPORTANT: Make this a POORLY written task description that would make estimation difficult:
- Be vague or ambiguous
- Missing key information (scope, context, requirements)
- Unclear wording or confusing structure
- Could be interpreted multiple ways
- Missing important details that affect time estimation"""
        elif prompt_quality == "excellent":
            quality_guidance = """IMPORTANT: Make this an EXCELLENTLY written task description:
- Very specific and detailed
- Clear scope and requirements
- All necessary information included
- Well-structured and unambiguous
- Easy to estimate accurately"""
        else:  # good
            quality_guidance = """IMPORTANT: Make this an ADEQUATELY written task description:
- Most details included but could be slightly more specific
- Generally clear but some minor ambiguity
- Most information present but not exhaustive"""
        
        prompt = f"""Generate a task description for time estimation with these characteristics:

Category: {category}
Task Type: {task_type}
Ambiguity: {ambiguity_instructions[ambiguity]}
Length: {length_instructions[length]}
Complexity: {complexity_instructions[complexity]}
Interruption Likelihood: {interruption_instructions[interruption]}
Prompt Quality: {prompt_quality_instructions[prompt_quality]}

{quality_guidance}

The task should:
- Be realistic and relatable
- Match the category "{category}"
- Be {ambiguity_instructions[ambiguity]}
- Be written in {length_instructions[length]}
- Represent {complexity_instructions[complexity]}
- Have {interruption_instructions[interruption]}
- Be {prompt_quality_instructions[prompt_quality]}

Generate ONLY the task description, nothing else. Do not include explanations or metadata."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates realistic task descriptions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,  # Higher temperature for diversity
                max_tokens=200
            )
            generated_prompt = response.choices[0].message.content.strip()
            
            # #region agent log
            import json
            with open('/Users/adimiddha/Github/time-calibration-agent/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A",
                    "location": "test_dataset.py:_generate_prompt",
                    "message": "Prompt generated with quality instruction",
                    "data": {
                        "requested_quality": prompt_quality,
                        "prompt_length": len(generated_prompt),
                        "prompt_preview": generated_prompt[:100]
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }) + '\n')
            # #endregion
            
            return generated_prompt
        except Exception as e:
            print(f"Warning: Failed to generate prompt: {e}")
            # Fallback to template-based generation
            return self._generate_fallback_prompt(category, task_type, complexity)
    
    def _generate_fallback_prompt(self, category: str, task_type: str, complexity: str) -> str:
        """Generate a simple fallback prompt if AI generation fails."""
        templates = {
            "coding": {
                "simple": "Write a function to sort a list",
                "multi_step": "Write a function to sort a list, add error handling, and write unit tests",
                "task_breakdown": "Build a REST API with authentication, database integration, and API documentation"
            },
            "writing": {
                "simple": "Write a blog post",
                "multi_step": "Write a blog post, edit it, and create a featured image",
                "task_breakdown": "Write a comprehensive article with research, editing, images, and SEO optimization"
            },
            "admin": {
                "simple": "Organize my email inbox",
                "multi_step": "Organize my email inbox, respond to urgent messages, and schedule follow-ups",
                "task_breakdown": "Complete administrative tasks including email, scheduling, filing documents, and updating calendar"
            }
        }
        
        if category in templates and complexity in templates[category]:
            return templates[category][complexity]
        
        return f"Complete a {category} task"
    
    def save_dataset(self, prompts: List[Dict], output_path: str):
        """
        Save test dataset to JSON file.
        
        Args:
            prompts: List of test prompts
            output_path: Path to save JSON file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        dataset = {
            "test_prompts": prompts,
            "total_count": len(prompts),
            "metadata": {
                "categories": list(set(p["metadata"]["category"] for p in prompts)),
                "ambiguities": list(set(p["metadata"]["ambiguity"] for p in prompts)),
                "lengths": list(set(p["metadata"]["length"] for p in prompts))
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(dataset, f, indent=2)
        
        print(f"Test dataset saved to: {output_path}")
    
    def load_dataset(self, input_path: str) -> List[Dict]:
        """
        Load test dataset from JSON file.
        
        Args:
            input_path: Path to JSON file
            
        Returns:
            List of test prompts
        """
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "test_prompts" in data:
            return data["test_prompts"]
        else:
            raise ValueError(f"Invalid dataset format in {input_path}")


def generate_test_dataset(n: int = 50, seed: Optional[int] = None, 
                          output_path: Optional[str] = None,
                          include_edge_cases: bool = True) -> List[Dict]:
    """
    Convenience function to generate and optionally save test dataset.
    
    Args:
        n: Number of prompts to generate
        seed: Random seed for reproducibility
        output_path: Optional path to save dataset
        include_edge_cases: Whether to include edge case prompts
        
    Returns:
        List of test prompts
    """
    generator = TestDatasetGenerator()
    prompts = generator.generate_test_dataset(n, seed, include_edge_cases)
    
    if output_path:
        generator.save_dataset(prompts, output_path)
    
    return prompts


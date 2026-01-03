"""
Data storage layer for persisting tasks, estimates, and learning data.
Uses JSON for simplicity in V1.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class TaskStorage:
    """Manages persistence of tasks, estimates, and calibration data."""
    
    def __init__(self, data_file: str = "calibration_data.json"):
        self.data_file = Path(data_file)
        self._ensure_data_file()
    
    def _ensure_data_file(self):
        """Create data file with initial structure if it doesn't exist."""
        if not self.data_file.exists():
            initial_data = {
                "tasks": [],
                "calibration": {
                    "user_bias": 0.0,  # Positive = agent underestimated (actual > estimated), negative = agent overestimated (actual < estimated)
                    "category_patterns": {},
                    "total_tasks": 0,
                    "total_discrepancy": 0.0
                }
            }
            self._write_data(initial_data)
    
    def _read_data(self) -> Dict:
        """Read data from JSON file."""
        with open(self.data_file, 'r') as f:
            return json.load(f)
    
    def _write_data(self, data: Dict):
        """Write data to JSON file."""
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_task(self, task_description: str, estimate_minutes: int, 
                 estimate_range: Dict, explanation: str,
                 category: Optional[str] = None,
                 ambiguity: Optional[str] = None) -> str:
        """
        Add a new task with estimate.
        Returns task_id for later reference.
        """
        data = self._read_data()
        task_id = f"task_{len(data['tasks']) + 1}_{int(datetime.now().timestamp())}"
        
        task = {
            "id": task_id,
            "description": task_description,
            "estimated_minutes": estimate_minutes,
            "estimate_range": estimate_range,
            "explanation": explanation,
            "actual_minutes": None,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "category": category,
            "ambiguity": ambiguity
        }
        
        data['tasks'].append(task)
        self._write_data(data)
        return task_id
    
    def update_task_metadata(self, task_id: str, category: Optional[str] = None,
                            ambiguity: Optional[str] = None):
        """Update category and/or ambiguity for a task."""
        data = self._read_data()
        
        for task in data['tasks']:
            if task['id'] == task_id:
                if category is not None:
                    task['category'] = category
                if ambiguity is not None:
                    task['ambiguity'] = ambiguity
                break
        else:
            raise ValueError(f"Task {task_id} not found")
        
        self._write_data(data)
    
    def log_actual_time(self, task_id: str, actual_minutes: int):
        """Log the actual time spent on a task."""
        data = self._read_data()
        
        for task in data['tasks']:
            if task['id'] == task_id:
                task['actual_minutes'] = actual_minutes
                task['completed_at'] = datetime.now().isoformat()
                break
        else:
            raise ValueError(f"Task {task_id} not found")
        
        self._write_data(data)
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a specific task by ID."""
        data = self._read_data()
        for task in data['tasks']:
            if task['id'] == task_id:
                return task
        return None
    
    def get_pending_tasks(self) -> List[Dict]:
        """Get all tasks that haven't been completed yet."""
        data = self._read_data()
        return [task for task in data['tasks'] if task['actual_minutes'] is None]
    
    def get_completed_tasks(self) -> List[Dict]:
        """Get all tasks with actual time logged."""
        data = self._read_data()
        return [task for task in data['tasks'] if task['actual_minutes'] is not None]
    
    def get_calibration_data(self) -> Dict:
        """Get current calibration/learning data."""
        data = self._read_data()
        return data['calibration']
    
    def update_calibration(self, calibration_data: Dict):
        """Update calibration data."""
        data = self._read_data()
        data['calibration'] = calibration_data
        self._write_data(data)
    
    def get_all_tasks(self) -> List[Dict]:
        """Get all tasks."""
        data = self._read_data()
        return data['tasks']
    
    def delete_pending_tasks(self) -> int:
        """Delete all pending tasks (tasks without actual_minutes).
        
        Returns:
            Number of tasks deleted.
        """
        data = self._read_data()
        original_count = len(data['tasks'])
        data['tasks'] = [task for task in data['tasks'] if task.get('actual_minutes') is not None]
        deleted_count = original_count - len(data['tasks'])
        
        # Recalculate total_tasks to match actual number of completed tasks
        completed_count = len(data['tasks'])
        data['calibration']['total_tasks'] = completed_count
        
        self._write_data(data)
        return deleted_count


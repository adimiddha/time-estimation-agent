"""
Data models for day replanning sessions.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class PlanBlock:
    start: str
    end: str
    task: str
    kind: str = "task"  # task | fixed | break


@dataclass
class PlanConfidence:
    low: float
    high: float


@dataclass
class PlanOutput:
    time_blocks: List[PlanBlock] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    drop_or_defer: List[str] = field(default_factory=list)
    confidence: PlanConfidence = field(default_factory=lambda: PlanConfidence(0.4, 0.7))
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_blocks": [asdict(b) for b in self.time_blocks],
            "next_actions": list(self.next_actions),
            "drop_or_defer": list(self.drop_or_defer),
            "confidence": asdict(self.confidence),
            "rationale": self.rationale,
        }


@dataclass
class DaySession:
    session_id: str
    created_at: str
    replans: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

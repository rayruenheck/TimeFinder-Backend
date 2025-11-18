from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

PRIORITY_MAP = {"high" : 3, "medium": 2, "low": 1}

@dataclass
class Task:
    id: Any
    name: str
    priority: str          # "high" | "medium" | "low"
    time_minutes: int      # duration in minutes
    concentration: str     # "high" | "medium" | "low"
    is_completed: bool = False
    is_scheduled: bool = False

    @property
    def priority_value(self) -> int:
        return PRIORITY_MAP.get(self.priority, 0)

    @classmethod
    def from_mongo(cls, doc: Dict[str, Any]) -> "Task":
        return cls(
            id=doc["id"],
            name=doc["name"],
            priority=doc.get("priority", "medium"),
            time_minutes=int(doc.get("time", 30)),
            concentration=doc.get("concentration", "medium"),
            is_completed=doc.get("isCompleted", False),
            is_scheduled=doc.get("isScheduled", False),
        )

    def to_mongo_partial(self) -> Dict[str, Any]:
        """
        Minimal representation when you need to write fields back, if ever.
        """
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "time": self.time_minutes,
            "concentration": self.concentration,
            "isCompleted": self.is_completed,
            "isScheduled": self.is_scheduled,
        }

@dataclass
class Slot:
    start: datetime
    end: datetime
    available: bool = True
    concentration_time: bool = False

    @property
    def duration(self) -> timedelta:
        return self.end - self.start
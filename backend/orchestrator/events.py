from typing import Dict, Any, Optional, List
import json
import time

class EventRecorder:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: List[Dict[str, Any]] = []

    def record_event(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        event = {
            "run_id": self.run_id,
            "event_type": event_type,
            "timestamp": time.time(),
            "details": details or {},
        }
        self.events.append(event)

    def get_events(self) -> List[Dict[str, Any]]:
        return self.events

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(e) for e in self.events)
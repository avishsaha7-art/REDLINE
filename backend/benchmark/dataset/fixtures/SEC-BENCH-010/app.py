class EventLogService:
    def __init__(self):
        self._events = [f"event-{i}" for i in range(1000)]

    def get_events(self, limit: int, offset: int = 0) -> list[str]:
        # VULNERABILITY: Unbounded limit parameter allows requesting excessive items
        return self._events[offset : offset + limit]

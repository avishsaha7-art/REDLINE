class EventLogService:
    def __init__(self):
        self._events = [f"event-{i}" for i in range(1000)]

    def get_events(self, limit: int, offset: int = 0) -> list[str]:
        MAX_PAGE_SIZE = 100
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        return self._events[offset : offset + limit]

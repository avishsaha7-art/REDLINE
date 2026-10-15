from app import EventLogService

def test_pagination():
    svc = EventLogService()
    assert len(svc.get_events(limit=10, offset=0)) == 10

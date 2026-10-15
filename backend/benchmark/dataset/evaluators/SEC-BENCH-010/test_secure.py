from app import EventLogService

def test_bounded_page_size_invariant():
    svc = EventLogService()
    res = svc.get_events(limit=500)
    assert len(res) <= 100, f"Security Invariant violated: page size {len(res)} exceeded max ceiling 100"

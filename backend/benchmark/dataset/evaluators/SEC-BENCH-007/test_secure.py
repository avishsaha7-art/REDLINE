import tempfile
import os
from app import LogStreamProcessor

def test_resource_cleanup_invariant():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "bad.log")
        p2 = os.path.join(td, "good.log")
        with open(p1, "w", encoding="utf-8") as f:
            f.write("INVALID DATA\n")
        with open(p2, "w", encoding="utf-8") as f:
            f.write("VALID ROW\n")
        processor = LogStreamProcessor()
        res = processor.process_logs([p1, p2])
        assert res == ["VALID ROW"]
        unclosed = [h for h in processor.allocated_handles if not h.closed]
        assert len(unclosed) == 0, "Security Invariant violated: unclosed file handles detected"

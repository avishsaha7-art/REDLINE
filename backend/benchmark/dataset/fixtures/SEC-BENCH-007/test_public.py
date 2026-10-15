import tempfile
import os
from app import LogStreamProcessor

def test_normal_processing():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.log")
        with open(p1, "w", encoding="utf-8") as f:
            f.write("OK LINE 1\n")
        processor = LogStreamProcessor()
        assert processor.process_logs([p1]) == ["OK LINE 1"]
        assert len(processor.allocated_handles) == 1
        assert processor.allocated_handles[0].closed

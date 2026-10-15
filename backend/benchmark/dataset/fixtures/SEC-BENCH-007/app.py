class LogStreamProcessor:
    def __init__(self):
        self.allocated_handles = []

    def process_logs(self, file_paths: list[str]) -> list[str]:
        results = []
        for path in file_paths:
            # VULNERABILITY: Opens file without context manager or close() in error path
            handle = open(path, "r", encoding="utf-8")
            self.allocated_handles.append(handle)
            line = handle.readline()
            if "INVALID" in line:
                continue
            results.append(line.strip())
            handle.close()
        return results

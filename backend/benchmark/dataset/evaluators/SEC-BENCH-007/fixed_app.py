class LogStreamProcessor:
    def __init__(self):
        self.allocated_handles = []

    def process_logs(self, file_paths: list[str]) -> list[str]:
        results = []
        for path in file_paths:
            with open(path, "r", encoding="utf-8") as handle:
                self.allocated_handles.append(handle)
                line = handle.readline()
                if "INVALID" in line:
                    continue
                results.append(line.strip())
        return results

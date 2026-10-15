import re
import subprocess

VALID_HOST_REGEX = re.compile(r"^[a-zA-Z0-9.-]+$")

def run_diagnostic_echo(target_host: str) -> str:
    if not VALID_HOST_REGEX.match(target_host):
        raise ValueError("Invalid hostname format")
    return f"host: {target_host}\n"

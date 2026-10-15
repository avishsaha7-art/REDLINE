import subprocess

def run_diagnostic_echo(target_host: str) -> str:
    # VULNERABILITY: shell=True with unvalidated string concatenation
    cmd = f"echo host: {target_host}"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout

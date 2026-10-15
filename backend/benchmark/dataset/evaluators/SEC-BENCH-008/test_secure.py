import tempfile
import os
import pytest
from app import run_diagnostic_echo

def test_command_injection_prevented():
    with tempfile.TemporaryDirectory() as td:
        proof_file = os.path.join(td, "pwned.txt").replace("\\", "/")
        payload = f"127.0.0.1 & echo PWNED > {proof_file}"
        try:
            run_diagnostic_echo(payload)
        except ValueError:
            pass
        assert not os.path.exists(proof_file), "Security Invariant violated: injected command executed"

def test_valid_host_still_works():
    assert "node-1.internal" in run_diagnostic_echo("node-1.internal")

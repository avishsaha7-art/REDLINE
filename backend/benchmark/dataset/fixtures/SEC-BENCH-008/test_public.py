from app import run_diagnostic_echo

def test_normal_host():
    out = run_diagnostic_echo("127.0.0.1")
    assert "127.0.0.1" in out

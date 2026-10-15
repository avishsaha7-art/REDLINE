from app import dispatch_api_request

def test_token_redaction_invariant():
    headers = {
        "Authorization": "Bearer secret-token-xyz-12345",
        "X-Api-Key": "my-secret-key-999",
        "Accept": "application/json"
    }
    res = dispatch_api_request(headers, "/api/error")
    dumped = str(res["debug_info"]["headers"])
    assert "secret-token-xyz-12345" not in dumped, "Security Invariant violated: Authorization bearer token leaked"
    assert "my-secret-key-999" not in dumped, "Security Invariant violated: API key leaked"

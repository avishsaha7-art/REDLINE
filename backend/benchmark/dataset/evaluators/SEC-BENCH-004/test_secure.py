import json
import pytest
from app import verify_jwt, base64url_encode

def test_alg_none_rejected():
    header = base64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = base64url_encode(json.dumps({"sub": "attacker", "role": "ADMIN"}).encode())
    forged_token = f"{header}.{body}."
    
    with pytest.raises(PermissionError):
        verify_jwt(forged_token, "some-secret")

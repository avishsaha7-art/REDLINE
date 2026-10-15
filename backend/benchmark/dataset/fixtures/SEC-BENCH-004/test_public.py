import hmac
import hashlib
import json
from app import verify_jwt, base64url_encode

SECRET = "super-secret-key-123"

def create_valid_token(payload: dict, secret: str) -> str:
    header = base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = base64url_encode(json.dumps(payload).encode())
    sig = base64url_encode(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"

def test_valid_token():
    tok = create_valid_token({"sub": "alice", "role": "USER"}, SECRET)
    assert verify_jwt(tok, SECRET)["sub"] == "alice"

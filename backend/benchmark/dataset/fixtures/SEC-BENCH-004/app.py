import hmac
import hashlib
import base64
import json

def base64url_decode(s: str) -> bytes:
    padding = '=' * (4 - len(s) % 4) if len(s) % 4 else ''
    return base64.urlsafe_b64decode(s + padding)

def base64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode('utf-8').rstrip('=')

def verify_jwt(token: str, secret: str) -> dict:
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    
    header = json.loads(base64url_decode(parts[0]))
    payload = json.loads(base64url_decode(parts[1]))
    
    # VULNERABILITY: Accepts 'none' algorithm without signature verification!
    if header.get("alg") == "none":
        return payload

    expected_sig = base64url_encode(
        hmac.new(secret.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(parts[2], expected_sig):
        raise PermissionError("Signature verification failed")
    
    return payload

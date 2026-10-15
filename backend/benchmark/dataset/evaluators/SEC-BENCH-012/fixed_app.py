def dispatch_api_request(headers: dict, endpoint: str) -> dict:
    if "error" in endpoint:
        SENSITIVE = {"authorization", "x-api-key", "token", "secret"}
        sanitized = {k: ("[REDACTED]" if k.lower() in SENSITIVE else v) for k, v in headers.items()}
        return {
            "status": "FAILED",
            "debug_info": {
                "endpoint": endpoint,
                "headers": sanitized
            }
        }
    return {"status": "SUCCESS", "data": "ok"}

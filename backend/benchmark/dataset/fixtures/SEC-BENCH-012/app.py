def dispatch_api_request(headers: dict, endpoint: str) -> dict:
    if "error" in endpoint:
        # VULNERABILITY: Dumps raw request headers into error dictionary
        return {
            "status": "FAILED",
            "debug_info": {
                "endpoint": endpoint,
                "headers": headers
            }
        }
    return {"status": "SUCCESS", "data": "ok"}

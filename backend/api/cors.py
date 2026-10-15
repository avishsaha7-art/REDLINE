import os
import urllib.parse
from typing import List

# Default origins for local development and demonstration
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Restricted HTTP methods actually used by REDLINE API
ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]

# Restricted request headers required by frontend API client
ALLOWED_HEADERS = [
    "Content-Type",
    "Accept",
    "Authorization",
    "X-Requested-With",
]


def validate_origin(origin: str) -> str:
    """
    Validates and normalizes an allowed origin string.
    Rejects wildcards, paths, fragments, queries, and insecure schemas.
    """
    clean_origin = origin.strip()
    if not clean_origin:
        raise ValueError("Origin cannot be empty")

    if "*" in clean_origin:
        raise ValueError(f"Wildcard origins are strictly prohibited: '{clean_origin}'")

    parsed = urllib.parse.urlparse(clean_origin)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Origin must use http or https scheme: '{clean_origin}'")

    if not parsed.netloc:
        raise ValueError(f"Origin must specify a valid host/netloc: '{clean_origin}'")

    # Path must be empty or just '/'
    if parsed.path and parsed.path != "/":
        raise ValueError(f"Origin must not include URL paths: '{clean_origin}'")

    if parsed.query or parsed.fragment:
        raise ValueError(f"Origin must not include query parameters or fragments: '{clean_origin}'")

    # Normalize by stripping trailing slash
    return f"{parsed.scheme}://{parsed.netloc}"


def get_allowed_origins() -> List[str]:
    """
    Retrieves and validates the list of allowed CORS origins.
    Reads from REDLINE_CORS_ORIGINS if configured, otherwise falls back to defaults.
    """
    env_origins = os.environ.get("REDLINE_CORS_ORIGINS")
    if not env_origins or not env_origins.strip():
        raw_origins = DEFAULT_ALLOWED_ORIGINS
    else:
        raw_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

    validated = []
    for origin in raw_origins:
        normalized = validate_origin(origin)
        if normalized not in validated:
            validated.append(normalized)

    if not validated:
        raise ValueError("At least one valid CORS origin must be configured")

    return validated

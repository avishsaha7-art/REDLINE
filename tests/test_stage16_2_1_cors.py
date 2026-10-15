import os
import pytest
from starlette.testclient import TestClient

from backend.api.cors import (
    validate_origin,
    get_allowed_origins,
    DEFAULT_ALLOWED_ORIGINS,
    ALLOWED_METHODS,
    ALLOWED_HEADERS,
)
from backend.api.app import app


def test_cors_default_origins():
    """Verify default development and demo origins."""
    origins = DEFAULT_ALLOWED_ORIGINS
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "*" not in origins


def test_origin_validation_valid():
    """Verify valid HTTP/HTTPS origins normalize properly."""
    assert validate_origin("http://localhost:3000") == "http://localhost:3000"
    assert validate_origin("http://localhost:3000/") == "http://localhost:3000"
    assert validate_origin("http://127.0.0.1:3000") == "http://127.0.0.1:3000"
    assert validate_origin("https://verifier.redline.internal:8443") == "https://verifier.redline.internal:8443"


def test_origin_validation_prohibits_wildcard():
    """Verify wildcard origins are rejected with ValueError."""
    with pytest.raises(ValueError, match="Wildcard origins are strictly prohibited"):
        validate_origin("*")

    with pytest.raises(ValueError, match="Wildcard origins are strictly prohibited"):
        validate_origin("http://*.example.com")


def test_origin_validation_prohibits_invalid_structure():
    """Verify missing schemes, paths, queries, and fragments are rejected."""
    with pytest.raises(ValueError, match="Origin cannot be empty"):
        validate_origin("  ")

    with pytest.raises(ValueError, match="must use http or https scheme"):
        validate_origin("localhost:3000")

    with pytest.raises(ValueError, match="must use http or https scheme"):
        validate_origin("ftp://localhost:3000")

    with pytest.raises(ValueError, match="must not include URL paths"):
        validate_origin("http://localhost:3000/api/v1")

    with pytest.raises(ValueError, match="must not include query parameters or fragments"):
        validate_origin("http://localhost:3000?foo=bar")

    with pytest.raises(ValueError, match="must not include query parameters or fragments"):
        validate_origin("http://localhost:3000#section")


def test_env_origin_configuration(monkeypatch):
    """Verify REDLINE_CORS_ORIGINS environment variable parsing."""
    monkeypatch.setenv("REDLINE_CORS_ORIGINS", "http://custom-host:3000, https://demo.internal:4000")
    origins = get_allowed_origins()
    assert origins == ["http://custom-host:3000", "https://demo.internal:4000"]


def test_preflight_allowed_localhost():
    """Verify browser preflight OPTIONS request for http://localhost:3000 succeeds."""
    client = TestClient(app)
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_allowed_loopback_ip():
    """Verify browser preflight OPTIONS request for http://127.0.0.1:3000 succeeds."""
    client = TestClient(app)
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


def test_preflight_disallowed_origin():
    """Verify browser preflight OPTIONS request from unapproved origin is rejected."""
    client = TestClient(app)
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://evil-attacker.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Origin should not be present in response allow-origin
    assert response.headers.get("access-control-allow-origin") != "http://evil-attacker.com"


def test_simple_request_allowed_origin():
    """Verify cross-origin GET response includes allow-origin for approved client."""
    client = TestClient(app)
    response = client.get(
        "/api/v1/runs",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-credentials" not in response.headers


def test_simple_request_disallowed_origin():
    """Verify cross-origin GET does not reflect arbitrary unapproved origin."""
    client = TestClient(app)
    response = client.get(
        "/api/v1/runs",
        headers={"Origin": "http://evil-attacker.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_methods_and_headers_restricted():
    """Verify only authorized methods and headers are configured."""
    assert "DELETE" not in ALLOWED_METHODS
    assert "PUT" not in ALLOWED_METHODS
    assert "PATCH" not in ALLOWED_METHODS
    assert set(ALLOWED_METHODS) == {"GET", "POST", "OPTIONS"}
    assert "Content-Type" in ALLOWED_HEADERS
    assert "Authorization" in ALLOWED_HEADERS

from app import AuthorizationCache

def test_cache_invalidation_enforced():
    auth = AuthorizationCache()
    assert auth.is_authorized("user-1") is True
    auth.revoke_authorization("user-1")
    assert auth.is_authorized("user-1") is False, "Security Invariant violated: revoked user retained cached access"

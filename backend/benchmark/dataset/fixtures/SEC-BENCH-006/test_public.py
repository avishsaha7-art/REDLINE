from app import AuthorizationCache

def test_initial_authorization():
    auth = AuthorizationCache()
    assert auth.is_authorized("user-1") is True
    assert auth.is_authorized("user-2") is False

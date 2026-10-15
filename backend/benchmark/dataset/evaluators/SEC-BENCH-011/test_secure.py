from app import AccessControl

def test_default_deny_invariant():
    rbac = AccessControl()
    assert rbac.can_perform("UNTRUSTED_EXTERNAL", "DELETE_RECORDS") is False, "Security Invariant violated: unknown role permitted"
    assert rbac.can_perform("", "DELETE_RECORDS") is False
    assert rbac.can_perform("USER", "DELETE_RECORDS") is False
    assert rbac.can_perform("ADMIN", "DELETE_RECORDS") is True

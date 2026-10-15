from app import AccessControl

def test_admin_allowed():
    rbac = AccessControl()
    assert rbac.can_perform("ADMIN", "DELETE_RECORDS") is True

def test_guest_blocked():
    rbac = AccessControl()
    assert rbac.can_perform("GUEST", "DELETE_RECORDS") is False

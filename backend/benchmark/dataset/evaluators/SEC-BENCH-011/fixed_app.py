class AccessControl:
    def can_perform(self, role: str, action: str) -> bool:
        ROLE_PERMISSIONS = {
            "ADMIN": {"READ", "WRITE", "DELETE_RECORDS"},
            "USER": {"READ", "WRITE"},
            "GUEST": {"READ"}
        }
        return action in ROLE_PERMISSIONS.get(role, set())

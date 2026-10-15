class AccessControl:
    def can_perform(self, role: str, action: str) -> bool:
        # VULNERABILITY: Default-allow: only blocks GUEST; unknown or custom roles granted admin actions
        if role == "GUEST":
            return False
        return True

class AuthorizationCache:
    def __init__(self):
        self._db_permissions = {"user-1": True, "user-2": False}
        self._cache = {}

    def is_authorized(self, user_id: str) -> bool:
        if user_id in self._cache:
            return self._cache[user_id]
        status = self._db_permissions.get(user_id, False)
        self._cache[user_id] = status
        return status

    def revoke_authorization(self, user_id: str):
        self._db_permissions[user_id] = False
        self._cache.pop(user_id, None)

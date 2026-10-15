class PaymentGateway:
    def __init__(self):
        self.balances = {"user-10": 100}
        self._processed = {}

    def process_credit_webhook(self, event_id: str, user_id: str, amount: int) -> dict:
        if event_id in self._processed:
            return self._processed[event_id]
        self.balances[user_id] += amount
        res = {"event_id": event_id, "balance": self.balances[user_id]}
        self._processed[event_id] = res
        return res

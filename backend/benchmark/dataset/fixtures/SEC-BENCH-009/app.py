class PaymentGateway:
    def __init__(self):
        self.balances = {"user-10": 100}

    def process_credit_webhook(self, event_id: str, user_id: str, amount: int) -> dict:
        # VULNERABILITY: No idempotency check; double processing credits multiple times
        self.balances[user_id] += amount
        return {"event_id": event_id, "balance": self.balances[user_id]}

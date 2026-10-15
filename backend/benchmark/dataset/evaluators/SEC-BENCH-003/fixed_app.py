import threading
import time

class WalletAccount:
    def __init__(self, initial_balance: int):
        self.balance = initial_balance
        self._lock = threading.Lock()

    def withdraw(self, amount: int) -> bool:
        with self._lock:
            if self.balance >= amount:
                time.sleep(0.01)
                self.balance -= amount
                return True
            return False

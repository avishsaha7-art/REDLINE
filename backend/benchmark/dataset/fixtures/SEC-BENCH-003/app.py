import time

class WalletAccount:
    def __init__(self, initial_balance: int):
        self.balance = initial_balance

    def withdraw(self, amount: int) -> bool:
        # VULNERABILITY: Check-then-act race window without synchronization
        if self.balance >= amount:
            time.sleep(0.01)  # Context switch / interleaving window
            self.balance -= amount
            return True
        return False

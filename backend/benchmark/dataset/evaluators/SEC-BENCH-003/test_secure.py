import threading
from app import WalletAccount

def test_concurrency_invariant():
    wallet = WalletAccount(100)
    results = []

    def worker():
        res = wallet.withdraw(80)
        results.append(res)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count(True) == 1, "Security Invariant violated: double spend occurred"
    assert results.count(False) == 1
    assert wallet.balance == 20

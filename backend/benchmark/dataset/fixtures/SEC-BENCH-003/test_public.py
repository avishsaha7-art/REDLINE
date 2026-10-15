from app import WalletAccount

def test_single_withdrawal():
    wallet = WalletAccount(100)
    assert wallet.withdraw(40) is True
    assert wallet.balance == 60

def test_insufficient_balance():
    wallet = WalletAccount(50)
    assert wallet.withdraw(60) is False
    assert wallet.balance == 50

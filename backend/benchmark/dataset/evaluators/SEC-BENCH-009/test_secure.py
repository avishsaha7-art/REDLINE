from app import PaymentGateway

def test_idempotent_processing_invariant():
    gw = PaymentGateway()
    res1 = gw.process_credit_webhook("evt-dup-99", "user-10", 50)
    res2 = gw.process_credit_webhook("evt-dup-99", "user-10", 50)
    assert gw.balances["user-10"] == 150, "Security Invariant violated: duplicate webhook altered balance"
    assert res1["balance"] == res2["balance"]

from app import PaymentGateway

def test_single_credit():
    gw = PaymentGateway()
    res = gw.process_credit_webhook("evt-001", "user-10", 50)
    assert res["balance"] == 150

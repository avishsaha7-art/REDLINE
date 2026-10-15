from app import dispatch_api_request

def test_successful_dispatch():
    res = dispatch_api_request({"Accept": "application/json"}, "/api/data")
    assert res["status"] == "SUCCESS"

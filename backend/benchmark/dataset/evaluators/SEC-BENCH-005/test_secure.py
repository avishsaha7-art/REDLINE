import pytest
from app import DocumentService

def test_idor_blocked():
    service = DocumentService()
    with pytest.raises(PermissionError):
        service.fetch_document("doc-101", "bob")

def test_legitimate_owner_fetch_allowed():
    service = DocumentService()
    assert service.fetch_document("doc-101", "alice")["owner_id"] == "alice"

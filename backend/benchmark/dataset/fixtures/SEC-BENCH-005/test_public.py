from app import DocumentService

def test_owner_access():
    service = DocumentService()
    doc = service.fetch_document("doc-101", "alice")
    assert doc["title"] == "Alice Diary"

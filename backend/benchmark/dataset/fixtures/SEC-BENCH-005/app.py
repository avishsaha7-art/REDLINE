class DocumentService:
    def __init__(self):
        self._documents = {
            "doc-101": {"id": "doc-101", "owner_id": "alice", "title": "Alice Diary", "secret": True},
            "doc-102": {"id": "doc-102", "owner_id": "bob", "title": "Bob Finances", "secret": True}
        }

    def fetch_document(self, doc_id: str, caller_id: str) -> dict:
        doc = self._documents.get(doc_id)
        if not doc:
            raise KeyError("Document not found")
        # VULNERABILITY: Missing owner check; returns any document if doc_id is known
        return doc

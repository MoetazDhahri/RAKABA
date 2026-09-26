import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import handlers


def test_client_account_registration_requires_matching_business_and_phone(monkeypatch):
    monkeypatch.setattr(handlers, "db", _FakeDatabase())
    result, status = handlers.register_client("client@example.tn", "StrongPass123!", "Pressing Express", "22112211")

    assert status == 201
    assert result["email"] == "client@example.tn"
    assert "entity_id" not in result


class _FakeDatabase:
    def __init__(self):
        self.rows = [{"entity_id": "internal-1", "business_name": "Pressing Express", "phone": "22112211"}]

    def run(self, query, params=None):
        if "listings" in query and "business_name" in query:
            return self.rows
        return []

    def execute(self, query, params=None):
        return None

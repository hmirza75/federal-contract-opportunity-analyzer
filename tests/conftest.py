"""Synthetic fixtures only. No real opportunities or credentials are stored here."""

import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    return create_app({"TESTING": True, "SAM_API_KEY": "synthetic-test-key",
                       "DATABASE": str(tmp_path / "test.sqlite3"), "SECRET_KEY": "test-session-secret"}).test_client()


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must explicitly mock the SAM.gov request.")
    monkeypatch.setattr("requests.sessions.Session.request", blocked)


@pytest.fixture
def notice():
    return {
        "noticeId": "a" * 32,
        "title": "SYNTHETIC TEST ONLY - help desk",
        "fullParentPathName": "SYNTHETIC TEST AGENCY.TEST OFFICE",
        "solicitationNumber": "TEST-NOT-A-REAL-SOLICITATION",
        "naicsCode": "541512",
        "typeOfSetAsideDescription": "Synthetic set-aside label",
        "postedDate": "2026-09-20",
        "responseDeadLine": "2026-10-15T17:00:00-04:00",
        "placeOfPerformance": {"city": {"name": "Test city"}, "state": {"code": "VA"}},
        "type": "Solicitation",
        "active": "Yes",
    }

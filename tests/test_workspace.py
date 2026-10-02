"""Exercise complete local workflows with synthetic notices and isolated SQLite files."""
import re
from datetime import datetime, timezone
from html import unescape

from app import create_app, db
from app.deadlines import deadline_info
from app.sam_client import normalize_opportunity
from .test_search import mock_response, QUERY


def csrf(client, path="/"):
    client.get(path)
    # Token generation is independent of the form's layout.
    with client.session_transaction() as session:
        token = session["csrf_token"]
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(client.application.secret_key, salt="wtf-csrf-token").dumps(token)


def save_notice(client, monkeypatch, notice):
    mock_response(monkeypatch, {"totalRecords": 1, "opportunitiesData": [notice]})
    html = client.get("/", query_string=QUERY).get_data(as_text=True)
    token = unescape(re.search(r'name="opportunity" value="([^"]+)"', html)[1])
    return client.post("/saved", data={"csrf_token": csrf(client), "opportunity": token})


def test_save_update_duplicate_and_restart(client, monkeypatch, notice):
    response = save_notice(client, monkeypatch, notice)
    path = response.headers["Location"]
    response = client.post(path + "/update", data={"csrf_token": csrf(client), "status": "Reviewing", "notes": "Check scope and staffing."})
    assert response.status_code == 302
    notice["title"] = "SYNTHETIC TEST ONLY - updated title"
    save_notice(client, monkeypatch, notice)
    with client.application.app_context():
        rows = db.list_opportunities()
        assert len(rows) == 1
        assert rows[0]["notes"] == "Check scope and staffing."
        assert rows[0]["status"] == "Reviewing"
        assert rows[0]["title"] == notice["title"]
    second_app = create_app({"TESTING": True, "SECRET_KEY": "test-session-secret", "DATABASE": client.application.config["DATABASE"]})
    assert b"Check scope and staffing." in second_app.test_client().get(path).data


def test_mutations_require_csrf(client):
    assert client.post("/saved", data={"opportunity": "fake"}).status_code == 400
    assert client.post("/saved", data={"csrf_token": csrf(client), "opportunity": "tampered"}).status_code == 400


def test_filter_delete_and_invalid_status(client, monkeypatch, notice):
    path = save_notice(client, monkeypatch, notice).headers["Location"]
    assert notice["title"] in client.get("/saved?q=help").get_data(as_text=True)
    assert notice["title"] not in client.get("/saved?q=unmatched").get_data(as_text=True)
    assert notice["title"] not in client.get("/saved?status=Won").get_data(as_text=True)
    client.post(path + "/update", data={"csrf_token": csrf(client), "status": "invented", "notes": ""})
    with client.application.app_context():
        assert db.list_opportunities()[0]["status"] == "New"
    assert client.post(path + "/delete", data={"csrf_token": csrf(client)}).status_code == 400
    assert client.post(path + "/delete", data={"csrf_token": csrf(client), "confirm": "yes"}).status_code == 302
    assert client.get(path).status_code == 404


def test_sql_and_html_are_data(client, monkeypatch, notice):
    notice["title"] = "SYNTHETIC '); DROP TABLE opportunities; -- <script>"
    path = save_notice(client, monkeypatch, notice).headers["Location"]
    html = client.get(path).get_data(as_text=True)
    assert "&lt;script&gt;" in html and "<script>" not in html
    with client.application.app_context():
        assert len(db.list_opportunities()) == 1
        assert db.list_opportunities("' OR 1=1 --") == []


def test_deadline_offsets_and_unknown():
    now = datetime(2026, 10, 2, 20, tzinfo=timezone.utc)
    assert deadline_info("2026-10-02T17:00:00-04:00", now)["kind"] == "soon"
    assert deadline_info("2026-10-02T15:00:00-04:00", now)["kind"] == "overdue"
    assert deadline_info("2026-10-02", now)["kind"] == "soon"
    assert "timezone unspecified" in deadline_info("2026-10-02", now)["label"]
    assert deadline_info("unknown", now)["kind"] == "unknown"


def test_dashboard_excludes_closed_statuses(client, notice):
    item = normalize_opportunity(notice)
    item["deadline"] = "2001-01-01T12:00:00Z"
    with client.application.app_context():
        db.save_opportunity(item)
        db.update_review(item["notice_id"], "Won", "")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Review passed deadlines" not in html

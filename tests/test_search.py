from datetime import date
from unittest.mock import Mock

import pytest
import requests

from app import create_app
from app.sam_client import SamError, SEARCH_URL, normalize_opportunity, search_opportunities

QUERY = {"search": "1", "keyword": "help desk", "posted_from": "2026-09-01", "posted_to": "2026-10-01"}


def mock_response(monkeypatch, payload=None, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    call = Mock(return_value=response)
    monkeypatch.setattr("app.sam_client.requests.get", call)
    return call


def test_landing_does_not_call_api(client):
    assert client.get("/").status_code == 200


def test_real_request_shape_and_rendered_fields(client, monkeypatch, notice):
    call = mock_response(monkeypatch, {"totalRecords": 20, "opportunitiesData": [notice]})
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for expected in [notice["title"], notice["solicitationNumber"], "541512", "Test city, VA",
                     notice["responseDeadLine"], "1 shown", "20 matching notices", "https://sam.gov/opp/"]:
        assert expected in html
    assert "synthetic-test-key" not in html
    call.assert_called_once_with(SEARCH_URL, params={
        "api_key": "synthetic-test-key", "postedFrom": "09/01/2026", "postedTo": "10/01/2026",
        "title": "help desk", "limit": 10, "offset": 0,
    }, timeout=(5, 25), allow_redirects=False)


def test_empty_keyword_is_not_sent(client, monkeypatch):
    call = mock_response(monkeypatch, {"totalRecords": 0, "opportunitiesData": []})
    response = client.get("/", query_string={**QUERY, "keyword": " "})
    assert b"No matching notices found" in response.data
    assert "title" not in call.call_args.kwargs["params"]


@pytest.mark.parametrize("changes", [
    {"posted_from": "bad"}, {"posted_from": "2026-02-30"}, {"posted_from": "2026-11-01"},
    {"posted_from": "2024-01-01"}, {"keyword": "x" * 201},
])
def test_invalid_input_never_calls_api(client, changes):
    assert client.get("/", query_string={**QUERY, **changes}).status_code == 400


def test_missing_key_never_calls_api():
    client = create_app({"TESTING": True, "SAM_API_KEY": ""}).test_client()
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert b"Add your SAM.gov API key" in response.data


@pytest.mark.parametrize("status, message", [(401, "denied access"), (403, "denied access"),
                                           (429, "request limit"), (500, "HTTP 500"), (302, "HTTP 302")])
def test_upstream_errors(client, monkeypatch, status, message):
    mock_response(monkeypatch, {"error": "synthetic-test-key"}, status)
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert message in response.get_data(as_text=True)
    assert b"synthetic-test-key" not in response.data


@pytest.mark.parametrize("error", [requests.Timeout("secret-in-url"), requests.ConnectionError("secret-in-url")])
def test_network_errors_are_redacted(client, monkeypatch, error):
    monkeypatch.setattr("app.sam_client.requests.get", Mock(side_effect=error))
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert b"secret-in-url" not in response.data


def test_certificate_error_is_specific_and_redacted(client, monkeypatch):
    monkeypatch.setattr("app.sam_client.requests.get", Mock(side_effect=requests.exceptions.SSLError("secret-in-url")))
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert b"HTTPS certificate" in response.data
    assert b"secret-in-url" not in response.data


@pytest.mark.parametrize("payload", [[], {}, {"opportunitiesData": [None], "totalRecords": 1},
                                     {"opportunitiesData": [], "totalRecords": "bad"}])
def test_malformed_payloads(client, monkeypatch, payload):
    mock_response(monkeypatch, payload)
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert b"unexpected response format" in response.data


def test_invalid_json(client, monkeypatch):
    call = mock_response(monkeypatch)
    call.return_value.json.side_effect = ValueError("raw secret response")
    response = client.get("/", query_string=QUERY)
    assert response.status_code == 503
    assert b"raw secret response" not in response.data


def test_documented_no_data_response(client, monkeypatch):
    mock_response(monkeypatch, status=404)
    assert b"No matching notices found" in client.get("/", query_string=QUERY).data


def test_null_fields_and_missing_location():
    normalized = normalize_opportunity({"placeOfPerformance": None, "naicsCode": "null"})
    assert normalized["location"] == normalized["naics"] == normalized["url"] == ""
    assert normalized["title"] == "Untitled notice"


def test_upstream_html_is_escaped_and_urls_not_trusted(client, monkeypatch, notice):
    notice.update(title="<script>alert(1)</script>", noticeId="javascript:alert(1)", uiLink="https://evil.example/")
    mock_response(monkeypatch, {"totalRecords": 1, "opportunitiesData": [notice]})
    html = client.get("/", query_string=QUERY).get_data(as_text=True)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "evil.example" not in html and "javascript:" not in html


def test_first_page_is_bounded(monkeypatch, notice):
    mock_response(monkeypatch, {"totalRecords": 11, "opportunitiesData": [notice] * 11})
    result = search_opportunities("synthetic-test-key", "", date(2026, 9, 1), date(2026, 10, 1))
    assert len(result.opportunities) == 10

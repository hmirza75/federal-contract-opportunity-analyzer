import csv
import io
import pytest
from openpyxl import load_workbook
from app import db
from app.sam_client import normalize_opportunity
from .test_search import mock_response, QUERY


def test_filters_and_pagination(client, monkeypatch, notice):
    call = mock_response(monkeypatch, {"totalRecords": 25, "opportunitiesData": [notice]})
    response = client.get("/", query_string={**QUERY, "page": 1, "agency": "Navy", "naics": "541512", "state": "VA",
          "notice_type": "o", "set_aside": "SBA", "deadline_from": "2026-10-01", "deadline_to": "2026-10-31"})
    assert response.status_code == 200
    params = call.call_args.kwargs["params"]
    assert params["offset"] == 1
    assert params["organizationName"] == "Navy"
    assert params["ncode"] == "541512" and params["state"] == "VA"
    assert params["ptype"] == "o" and params["typeOfSetAside"] == "SBA"
    assert params["rdlto"] == "10/31/2026"
    assert b"Next page" in response.data and b"Previous page" in response.data
    assert b"naics=541512" in response.data


@pytest.mark.parametrize("changes", [{"page": "-1"}, {"page": "bad"}, {"naics": "abc"}, {"state": "xx"},
    {"deadline_from": "2026-10-01"}, {"notice_type": "invalid"}, {"set_aside": "invalid"}])
def test_invalid_filters_do_not_call_api(client, changes):
    assert client.get("/", query_string={**QUERY, **changes}).status_code == 400


def test_exports_preserve_text_and_follow_filters(client, notice):
    item = normalize_opportunity(notice)
    item["title"] = "=HYPERLINK(\"https://evil.example\")"
    with client.application.app_context():
        db.save_opportunity(item)
        db.update_review(item["notice_id"], "Interested", "@dangerous formula\nSecond line, commas")
    response = client.get("/export/csv?status=Interested")
    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[1][0].startswith("'=") and rows[1][10].startswith("'@")
    assert "attachment" in response.headers["Content-Disposition"]
    response = client.get("/export/xlsx")
    sheet = load_workbook(io.BytesIO(response.data)).active
    assert sheet["A2"].data_type == "s" and sheet["A2"].value.startswith("'=")
    assert sheet["D2"].value == "541512"
    assert len(list(csv.reader(io.StringIO(client.get("/export/csv?status=Won").data.decode("utf-8-sig"))))) == 1

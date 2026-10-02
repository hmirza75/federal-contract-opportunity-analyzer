import io
from unittest.mock import Mock
import pytest
from pypdf import PdfWriter
from werkzeug.datastructures import FileStorage
from app import db
from app.analysis import analyze_text, extract_upload, html_to_text
from app.scoring import score_opportunity, parse_profile
from app.sam_client import normalize_opportunity, safe_description_url, fetch_description, SamError
from .test_workspace import csrf


def test_score_arithmetic_and_case_insensitive_terms(notice):
    item = normalize_opportunity(notice)
    profile = parse_profile({"keywords": "help desk,software, Help Desk, hardware, networking", "naics": "541512"})
    item["description"] = "Software services, including help desk."
    result = score_opportunity(item, profile)
    assert result["score"] == 69 and result["earned"] == 55 and result["possible"] == 80
    assert len(profile["keywords"]) == 4
    assert score_opportunity(item, {})["score"] is None


def test_missing_fields_and_eligibility_are_not_guessed(notice):
    item = normalize_opportunity(notice)
    item.update(state="", naics="", set_aside="", set_aside_code="")
    result = score_opportunity(item, {"naics": ["541512"], "states": ["VA"], "set_asides": ["NONE"]})
    assert result["score"] == 0 and result["coverage"] == 0
    assert len(result["warnings"]) >= 3
    item["set_aside"] = "No Set aside used"
    assert score_opportunity(item, {"set_asides": ["NONE"]})["score"] == 100


def test_keywords_use_word_boundaries():
    assert score_opportunity({"title": "Hospitality"}, {"keywords": ["IT"]})["score"] == 0


@pytest.mark.parametrize("form", [{"states": "ZZ"}, {"naics": "541"}, {"set_asides": "made up"}, {"keywords": "x"*101}])
def test_profile_validation(form):
    with pytest.raises(ValueError):
        parse_profile(form)


def test_evidence_has_verbatim_source_and_limits():
    text = "SYNTHETIC TEST TEXT. Contractor shall provide software support.\n\nSubmit a technical proposal by October 16, 2026.\n\nThis is a sole source requirement."
    report = analyze_text(text)
    assert any(s["passages"] for s in report["sections"] if s["name"] == "Important dates")
    for section in report["sections"]:
        for passage in section["passages"]:
            assert passage["text"] in text and passage["ref"].startswith("P")
    assert analyze_text(" ") is None
    report = analyze_text("\n\n".join("Submit proposal " + str(i) for i in range(15)))
    documents = next(s for s in report["sections"] if s["name"] == "Required documents")
    assert len(documents["passages"]) == 12 and documents["omitted"] == 3


def test_html_cleaning():
    assert html_to_text('<p>Scope &amp; work</p><script>evil()</script><style>hidden</style>') == "Scope & work"


def test_upload_validation_and_blank_pdf():
    with pytest.raises(ValueError, match=".txt or"):
        extract_upload(FileStorage(stream=io.BytesIO(b"bad"), filename="document.exe"))
    with pytest.raises(ValueError, match="UTF-8"):
        extract_upload(FileStorage(stream=io.BytesIO(b"\xff"), filename="document.txt"))
    assert extract_upload(FileStorage(stream=io.BytesIO(b"SYNTHETIC TEXT"), filename="../../document.txt")) == "SYNTHETIC TEXT"
    book, data = PdfWriter(), io.BytesIO()
    book.add_blank_page(width=100, height=100)
    book.write(data)
    data.seek(0)
    with pytest.raises(ValueError, match="No readable text"):
        extract_upload(FileStorage(stream=data, filename="blank.pdf"))


def test_description_url_is_constrained_and_strips_keys():
    notice_id = "a"*32
    valid = f"https://api.sam.gov/prod/opportunities/v1/noticedesc?noticeid={notice_id}"
    assert safe_description_url(valid + "&api_key=secret", notice_id) == valid
    for url in [valid.replace("api.sam.gov", "evil.example"), valid.replace("https", "http"), valid.replace("noticedesc", "elsewhere"), valid.replace(notice_id, "b"*32)]:
        assert safe_description_url(url, notice_id) == ""


def test_description_download_is_plain_text(monkeypatch, notice):
    item = normalize_opportunity(notice)
    item["description_url"] = f"https://api.sam.gov/prod/opportunities/v1/noticedesc?noticeid={item['notice_id']}"
    response = Mock(status_code=200)
    response.iter_content.return_value = [b'{"description":"<p>Provide software.</p><script>evil()</script>"}']
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.sam_client.requests.get", Mock(return_value=response))
    assert fetch_description("synthetic-key", item) == "Provide software."
    item["description_url"] = "https://evil.example/"
    with pytest.raises(SamError, match="No supported"):
        fetch_description("synthetic-key", item)


def test_review_workflow_and_profile(client, notice):
    item = normalize_opportunity(notice)
    with client.application.app_context():
        db.save_opportunity(item)
    path = "/saved/" + item["notice_id"]
    response = client.post("/profile", data={"csrf_token": csrf(client), "keywords": "help desk, software"})
    assert response.status_code == 302
    response = client.post(path+"/analyze", data={"csrf_token": csrf(client), "text": "SYNTHETIC TEXT: Contractor shall provide help desk software. Submit proposal by October 16, 2026."})
    html = client.get(path).get_data(as_text=True)
    assert "Evidence review" in html and "P1" in html and "100" in html
    assert b"Pasted solicitation text" in client.get(path).data
    client.post(path+"/clear-review", data={"csrf_token": csrf(client)})
    with client.application.app_context():
        assert db.get_opportunity(item["notice_id"])["review_text"] == ""

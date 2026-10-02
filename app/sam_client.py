"""Small, read-only client for the official SAM.gov Opportunities API."""

import re
from dataclasses import dataclass
from datetime import date

import requests

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
PAGE_SIZE = 10


class SamError(Exception):
    """A safe user-facing error; never contains a credential or request URL."""


@dataclass
class SearchResult:
    opportunities: list[dict]
    total: int


def text(value):
    """Treat omitted fields, JSON null, and the string 'null' as unavailable."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    value = str(value).strip()
    return "" if value.lower() == "null" else value


def normalize_opportunity(record):
    """Translate SAM's field names to the small set our page understands."""
    location = record.get("placeOfPerformance")
    location = location if isinstance(location, dict) else {}
    parts = []
    for field in ("city", "state", "country"):
        part = location.get(field)
        if isinstance(part, dict):
            part = part.get("name") or part.get("code")
        if text(part):
            parts.append(text(part))
    notice_id = text(record.get("noticeId"))
    # Construct an official link instead of rendering arbitrary upstream URLs.
    url = f"https://sam.gov/opp/{notice_id}/view" if re.fullmatch(r"[a-fA-F0-9]{32}", notice_id) else ""
    return {
        "notice_id": notice_id if url else "",
        "title": text(record.get("title")) or "Untitled notice",
        "agency": text(record.get("fullParentPathName")) or text(record.get("department")),
        "solicitation": text(record.get("solicitationNumber")),
        "naics": text(record.get("naicsCode")),
        "set_aside": text(record.get("typeOfSetAsideDescription")) or text(record.get("setAside"))
        or text(record.get("typeOfSetAside")) or text(record.get("setAsideCode")),
        "location": ", ".join(parts),
        "state": text(location.get("state", {}).get("code")) if isinstance(location.get("state"), dict) else "",
        "set_aside_code": text(record.get("typeOfSetAside")) or text(record.get("setAsideCode")),
        "posted": text(record.get("postedDate")),
        "deadline": text(record.get("responseDeadLine")) or text(record.get("reponseDeadLine")),
        "type": text(record.get("type")),
        "active": text(record.get("active")),
        "url": url,
    }


def search_opportunities(api_key: str, keyword: str, posted_from: date, posted_to: date):
    if not api_key or not api_key.strip():
        raise SamError("Add your SAM.gov API key to the local .env file, then restart the app.")
    params = {
        "api_key": api_key.strip(),
        "postedFrom": posted_from.strftime("%m/%d/%Y"),
        "postedTo": posted_to.strftime("%m/%d/%Y"),
        "limit": PAGE_SIZE,
        "offset": 0,
    }
    if keyword:
        params["title"] = keyword
    try:
        # No automatic retries: each search consumes the user's API quota.
        # Redirects are disabled so credentials stay with the official endpoint.
        response = requests.get(SEARCH_URL, params=params, timeout=(5, 25), allow_redirects=False)
    except requests.exceptions.SSLError:
        raise SamError("Could not verify SAM.gov's HTTPS certificate. Check your system's trusted certificates; do not disable verification.") from None
    except requests.Timeout:
        raise SamError("SAM.gov took too long to respond. Please try again later.") from None
    except requests.RequestException:
        # Requests exceptions may contain the URL, including api_key. Don't expose them.
        raise SamError("Could not connect to SAM.gov. Check your connection and try again.") from None

    if response.status_code in (401, 403):
        raise SamError("SAM.gov denied access. Check your API key and account access.")
    if response.status_code == 429:
        raise SamError("SAM.gov's request limit was reached. Wait before searching again.")
    if response.status_code == 404:
        return SearchResult([], 0)
    if response.status_code != 200:
        raise SamError(f"SAM.gov returned HTTP {response.status_code}. Please try again later.")
    try:
        payload = response.json()
    except ValueError:
        raise SamError("SAM.gov returned unreadable data. Please try again later.") from None
    if not isinstance(payload, dict):
        raise SamError("SAM.gov returned an unexpected response format.")
    records = payload.get("opportunitiesData")
    total = payload.get("totalRecords")
    if records is None and total == 0:
        records = []
    if (not isinstance(records, list) or any(not isinstance(row, dict) for row in records)
            or not isinstance(total, int) or isinstance(total, bool) or total < len(records)):
        raise SamError("SAM.gov returned an unexpected response format.")
    return SearchResult([normalize_opportunity(row) for row in records[:PAGE_SIZE]], total)

"""Deterministic relevance scoring, never a probability of winning or eligibility."""
import re
from .deadlines import deadline_info
from .search_filters import SET_ASIDES, STATES


def parse_profile(form):
    result = {}
    for name in ("keywords", "naics", "states", "set_asides"):
        raw = form.get(name, "")
        if len(raw) > 2000:
            raise ValueError("Keep each profile field under 2,000 characters.")
        terms = list(dict.fromkeys(t.strip() for t in raw.split(",") if t.strip()))
        if len(terms) > 30 or any(len(t) > 100 for t in terms):
            raise ValueError("Use at most 30 entries per field, each at most 100 characters.")
        result[name] = list(dict.fromkeys(t.lower() if name == "keywords" else t.upper() for t in terms))
    if any(not re.fullmatch(r"\d{6}", n) for n in result["naics"]):
        raise ValueError("Profile NAICS codes must have six digits.")
    if any(s not in STATES for s in result["states"]):
        raise ValueError("Use two-letter US state or territory codes.")
    if any(s not in SET_ASIDES and s != "NONE" for s in result["set_asides"]):
        raise ValueError("Use the listed set-aside codes, or NONE for explicitly unrestricted notices.")
    return result


def contains_term(text, term):
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE))


def score_opportunity(item, profile):
    components, warnings = [], []
    description = item.get("description", "") or ""
    review = item.get("review_text", "") or ""
    corpus = "\n".join([item.get("title", ""), description, review])
    if not description and not review:
        warnings.append("Keyword matching uses the title only; load a description or document for more evidence.")
    code = item.get("set_aside_code", "").upper()
    if not code and "no set aside" in item.get("set_aside", "").lower():
        code = "NONE"
    specs = [("keywords", "Capability keywords", 50, corpus), ("naics", "NAICS", 30, item.get("naics", "")),
             ("states", "Place of performance", 10, item.get("state", "")), ("set_asides", "Set-aside preference", 10, code)]
    total, earned, known = 0, 0, 0
    for key, label, weight, actual in specs:
        wanted = profile.get(key, [])
        if not wanted:
            components.append({"name": label, "weight": 0, "earned": 0, "detail": "Not configured; excluded from denominator."})
            continue
        total += weight
        if key == "keywords":
            matches = [term for term in wanted if contains_term(actual, term)]
            points = weight * len(matches) / len(wanted)
            detail = f"{len(matches)}/{len(wanted)} terms found: " + (", ".join(matches) or "none")
        else:
            points = weight if actual.upper() in wanted else 0
            detail = f"Source: {actual or 'not provided'}. Profile: {', '.join(wanted)}."
        if actual:
            known += weight
        else:
            warnings.append(f"{label}: source value missing; this configured criterion earns zero points.")
        earned += points
        components.append({"name": label, "weight": weight, "earned": round(points, 1), "detail": detail})
    if code and profile.get("set_asides") and code not in profile["set_asides"]:
        warnings.append("Set-aside does not match your declared preferences. Review eligibility manually.")
    if deadline_info(item.get("deadline", ""))["kind"] == "overdue":
        warnings.append("The recorded response deadline has passed. Check amendments before taking action.")
    if item.get("active", "").lower() == "no":
        warnings.append("SAM.gov reports this notice as inactive.")
    if item.get("type") in {"Award Notice", "Justification"}:
        warnings.append("This notice type is not an open solicitation.")
    return {"score": round(100 * earned / total) if total else None, "earned": round(earned, 1), "possible": total,
            "coverage": round(100 * known / total) if total else 0, "components": components, "warnings": warnings}

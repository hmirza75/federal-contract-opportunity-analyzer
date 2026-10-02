"""Map form fields to documented SAM.gov parameters."""
import re
from datetime import date

SET_ASIDES = {"SBA": "Total small business", "SBP": "Partial small business", "8A": "8(a) set-aside",
             "8AN": "8(a) sole source", "HZC": "HUBZone set-aside", "HZS": "HUBZone sole source",
             "SDVOSBC": "Service-disabled veteran-owned", "SDVOSBS": "SDVOSB sole source",
             "WOSB": "Women-owned", "WOSBSS": "Women-owned sole source", "EDWOSB": "Economically disadvantaged women-owned",
             "EDWOSBSS": "EDWOSB sole source", "LAS": "Local area", "IEE": "Indian economic enterprise",
             "ISBEE": "Indian small business", "BICiv": "Buy Indian", "VSA": "Veteran-owned", "VSS": "Veteran-owned sole source"}
NOTICE_TYPES = {"o": "Solicitation", "k": "Combined synopsis / solicitation", "r": "Sources sought",
                "p": "Presolicitation", "s": "Special notice", "a": "Award notice", "u": "Justification"}
STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split()
FIELDS = ("agency", "naics", "set_aside", "state", "deadline_from", "deadline_to", "notice_type")


def validate_filters(form):
    if len(form["agency"]) > 200:
        raise ValueError("Keep the agency name to 200 characters or fewer.")
    if form["naics"] and not re.fullmatch(r"\d{6}", form["naics"]):
        raise ValueError("Enter a six-digit NAICS code.")
    for field, allowed in (("set_aside", SET_ASIDES), ("state", STATES), ("notice_type", NOTICE_TYPES)):
        if form[field] and form[field] not in allowed:
            raise ValueError("Choose a valid state, set-aside, and notice type.")
    if bool(form["deadline_from"]) != bool(form["deadline_to"]):
        raise ValueError("Provide both deadline dates, or leave both blank.")
    if form["deadline_from"]:
        start, end = date.fromisoformat(form["deadline_from"]), date.fromisoformat(form["deadline_to"])
        if start > end or (end-start).days > 365:
            raise ValueError("Deadline range must be ordered and at most 365 days.")
    params = {}
    for field, api_name in (("agency", "organizationName"), ("naics", "ncode"), ("set_aside", "typeOfSetAside"),
                            ("state", "state"), ("notice_type", "ptype")):
        if form[field]:
            params[api_name] = form[field]
    for field, api_name in (("deadline_from", "rdlfrom"), ("deadline_to", "rdlto")):
        if form[field]:
            params[api_name] = date.fromisoformat(form[field]).strftime("%m/%d/%Y")
    return params

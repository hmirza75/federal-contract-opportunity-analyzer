"""Validate the search form, call SAM.gov, and render the results."""

from datetime import date, timedelta

from flask import Blueprint, current_app, render_template, request

from .sam_client import SamError, search_opportunities

main = Blueprint("main", __name__)


@main.get("/")
def index():
    today = date.today()
    form = {
        "keyword": request.args.get("keyword", "").strip(),
        "posted_from": request.args.get("posted_from", (today - timedelta(days=30)).isoformat()),
        "posted_to": request.args.get("posted_to", today.isoformat()),
    }
    result, error, status = None, None, 200
    if request.args.get("search") == "1":
        try:
            start = date.fromisoformat(form["posted_from"])
            end = date.fromisoformat(form["posted_to"])
            if start > end or (end - start).days > 365:
                raise ValueError("Invalid date range")
            if len(form["keyword"]) > 200:
                raise ValueError("Keyword too long")
        except ValueError:
            error = "Enter valid posted dates (From before To, at most 365 days apart) and a keyword of at most 200 characters."
            status = 400
        else:
            try:
                result = search_opportunities(current_app.config["SAM_API_KEY"], form["keyword"], start, end)
            except SamError as exc:
                error, status = str(exc), 503
    return render_template("index.html", form=form, result=result, error=error,
                           key_configured=bool(current_app.config["SAM_API_KEY"].strip())), status

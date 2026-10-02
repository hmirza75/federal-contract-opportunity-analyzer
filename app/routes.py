"""Validate the search form, call SAM.gov, and render the results."""

from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import db
from .deadlines import deadline_info, INACTIVE_STATUSES

from .sam_client import SamError, search_opportunities

main = Blueprint("main", __name__)


def signer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="sam-search-result")


def with_deadline(item):
    item["due"] = deadline_info(item.get("deadline", ""))
    return item


def require_opportunity(notice_id):
    item = db.get_opportunity(notice_id)
    if item is None:
        abort(404)
    return with_deadline(item)


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
    if result:
        for item in result.opportunities:
            item["save_token"] = signer().dumps(item) if item["notice_id"] else ""
    return render_template("index.html", form=form, result=result, error=error,
                           key_configured=bool(current_app.config["SAM_API_KEY"].strip())), status


@main.post("/saved")
def save():
    try:
        item = signer().loads(request.form.get("opportunity", ""), max_age=86400)
        if not isinstance(item, dict) or not item.get("notice_id"):
            raise BadSignature("Invalid item")
    except BadSignature:
        abort(400)
    db.save_opportunity(item)
    flash("Opportunity saved. Existing notes and status are preserved.")
    return redirect(url_for("main.detail", notice_id=item["notice_id"]))


@main.get("/saved")
def saved():
    query, status = request.args.get("q", "").strip(), request.args.get("status", "")
    if len(query) > 200 or (status and status not in db.STATUSES):
        abort(400)
    items = [with_deadline(i) for i in db.list_opportunities(query, status)]
    return render_template("saved.html", opportunities=items, statuses=db.STATUSES, query=query, status=status)


@main.get("/saved/<notice_id>")
def detail(notice_id):
    return render_template("detail.html", opp=require_opportunity(notice_id), statuses=db.STATUSES)


@main.post("/saved/<notice_id>/update")
def update_saved(notice_id):
    require_opportunity(notice_id)
    try:
        db.update_review(notice_id, request.form.get("status", ""), request.form.get("notes", "").strip())
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Status and notes saved.")
    return redirect(url_for("main.detail", notice_id=notice_id))


@main.post("/saved/<notice_id>/delete")
def delete_saved(notice_id):
    require_opportunity(notice_id)
    if request.form.get("confirm") != "yes":
        abort(400)
    db.delete_opportunity(notice_id)
    flash("The local opportunity record was deleted.")
    return redirect(url_for("main.saved"))


@main.get("/dashboard")
def dashboard():
    items = [with_deadline(i) for i in db.list_opportunities()]
    open_items = [i for i in items if i["status"] not in INACTIVE_STATUSES]
    upcoming = sorted([i for i in open_items if i["due"]["kind"] == "soon"], key=lambda i: i["due"]["sort"])
    overdue = [i for i in open_items if i["due"]["kind"] == "overdue"]
    counts = {s: sum(i["status"] == s for i in items) for s in db.STATUSES}
    return render_template("dashboard.html", total=len(items), upcoming=upcoming, overdue=overdue,
                           unknown=sum(i["due"]["kind"] == "unknown" for i in open_items), counts=counts)

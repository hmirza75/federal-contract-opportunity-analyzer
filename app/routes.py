"""Validate the search form, call SAM.gov, and render the results."""

from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import db
from .deadlines import deadline_info, INACTIVE_STATUSES
from .search_filters import FIELDS, NOTICE_TYPES, SET_ASIDES, STATES, validate_filters
from .scoring import parse_profile, score_opportunity

from .sam_client import SamError, search_opportunities, fetch_description
from .analysis import analyze_text, extract_upload, MAX_TEXT

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
    form.update({field: request.args.get(field, "").strip() for field in FIELDS})
    page = 0
    result, error, status = None, None, 200
    if request.args.get("search") == "1":
        try:
            start = date.fromisoformat(form["posted_from"])
            end = date.fromisoformat(form["posted_to"])
            if start > end or (end - start).days > 365:
                raise ValueError("Invalid date range")
            if len(form["keyword"]) > 200:
                raise ValueError("Keyword too long")
            filters = validate_filters(form)
            page = int(request.args.get("page", "0"))
            if not 0 <= page <= 10000:
                raise ValueError("Invalid page")
        except ValueError:
            error = "Check your filters: valid ordered date ranges up to 365 days, both deadline dates, a six-digit NAICS, and names up to 200 characters are required when supplied."
            status = 400
        else:
            try:
                result = search_opportunities(current_app.config["SAM_API_KEY"], form["keyword"], start, end, filters=filters, page=page)
            except SamError as exc:
                error, status = str(exc), 503
    if result:
        profile = db.get_profile()
        for item in result.opportunities:
            item["save_token"] = signer().dumps(item) if item["notice_id"] else ""
            item["match"] = score_opportunity(item, profile)
    previous = url_for("main.index", **form, search=1, page=page-1) if page > 0 else None
    following = url_for("main.index", **form, search=1, page=page+1) if result and (page+1)*10 < result.total and page < 10000 else None
    return render_template("index.html", form=form, result=result, error=error, page=page,
                           previous=previous, following=following, states=STATES, set_asides=SET_ASIDES, notice_types=NOTICE_TYPES,
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
    item = require_opportunity(notice_id)
    source_text = item["review_text"] or item["description"]
    return render_template("detail.html", opp=item, statuses=db.STATUSES, match=score_opportunity(item, db.get_profile()),
                           analysis=analyze_text(source_text), review_source=item["review_source"] if item["review_text"] else "SAM.gov description")


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


@main.get("/export/<format>")
def export_saved(format):
    from .exports import export_csv, export_excel
    query, status = request.args.get("q", "").strip(), request.args.get("status", "")
    if len(query) > 200 or (status and status not in db.STATUSES) or format not in {"csv", "xlsx"}:
        abort(400)
    items = db.list_opportunities(query, status)
    profile = db.get_profile()
    for item in items:
        match = score_opportunity(item, profile)
        item["match_score"] = match["score"]
        item["match_evidence"] = "; ".join(c["name"] + ": " + c["detail"] for c in match["components"])
    buffer = export_csv(items) if format == "csv" else export_excel(items)
    mimetype = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=f"saved-opportunities-{date.today()}.{format}")


@main.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        try:
            data = parse_profile(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return render_template("profile.html", values=request.form, set_asides=SET_ASIDES), 400
        db.save_profile(data)
        flash("Capability profile saved locally. Scores now use these preferences.")
        return redirect(url_for("main.profile"))
    values = {key: ", ".join(value) for key, value in db.get_profile().items()}
    return render_template("profile.html", values=values, set_asides=SET_ASIDES)


@main.post("/saved/<notice_id>/description")
def load_description(notice_id):
    item = require_opportunity(notice_id)
    try:
        text = fetch_description(current_app.config["SAM_API_KEY"], item)
        db.store_text(notice_id, text, "SAM.gov", description=True)
        flash("Description loaded from SAM.gov. Any separate document review is preserved.")
    except SamError as error:
        flash(str(error), "error")
    return redirect(url_for("main.detail", notice_id=notice_id))


@main.post("/saved/<notice_id>/analyze")
def review_document(notice_id):
    require_opportunity(notice_id)
    text = request.form.get("text", "").strip()
    file = request.files.get("document")
    try:
        if file and file.filename and text:
            raise ValueError("Choose either pasted text or a document, not both.")
        if file and file.filename:
            text = extract_upload(file)
            source = "Uploaded PDF" if file.filename.lower().endswith(".pdf") else "Uploaded text file"
        else:
            source = "Pasted solicitation text"
        if not text or len(text) > MAX_TEXT:
            raise ValueError("Provide text between 1 and 150,000 characters.")
        db.store_text(notice_id, text, source)
        flash("Evidence review saved locally. Check the source passages and original document.")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("main.detail", notice_id=notice_id))


@main.post("/saved/<notice_id>/clear-review")
def clear_document(notice_id):
    require_opportunity(notice_id)
    db.store_text(notice_id, "", "")
    flash("Document review cleared. A fetched SAM.gov description, if present, is now used for review.")
    return redirect(url_for("main.detail", notice_id=notice_id))

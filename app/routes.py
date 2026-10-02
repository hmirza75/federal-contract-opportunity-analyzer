"""HTTP routes will connect the search form to the SAM.gov client."""

from flask import Blueprint, render_template

main = Blueprint("main", __name__)


@main.get("/")
def index():
    return render_template("index.html")

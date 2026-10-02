"""Application factory: configure Flask, then attach our page routes."""

import os
import secrets
from pathlib import Path

import truststore
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect


def create_app(test_config=None):
    # This is an application startup hook, not a reusable library. Use the OS
    # certificate store for HTTPS verification, including Windows-managed roots.
    truststore.inject_into_ssl()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    app = Flask(__name__)
    app.config.from_mapping(
        SAM_API_KEY=os.getenv("SAM_API_KEY", ""),
        DATABASE=str(Path(app.instance_path) / "opportunities.sqlite3"),
        SECRET_KEY=os.getenv("SECRET_KEY"),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config["SECRET_KEY"]:
        secret_file = Path(app.instance_path) / "session-secret"
        try:
            with secret_file.open("x", encoding="utf-8") as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret_file.read_text(encoding="utf-8")
    CSRFProtect(app)
    from . import db
    db.init_app(app)

    from .routes import main

    app.register_blueprint(main)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def friendly_error(error):
        messages = {400: "The request is invalid or the form expired. Reload the page and try again.",
                    404: "That saved opportunity could not be found.",
                    413: "The upload is too large. Choose a file smaller than 5 MB."}
        return render_template("error.html", message=messages[error.code]), error.code

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response
    return app

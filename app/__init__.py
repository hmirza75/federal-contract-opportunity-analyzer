"""Application factory: configure Flask, then attach our page routes."""

import os
from pathlib import Path

import truststore
from dotenv import load_dotenv
from flask import Flask


def create_app(test_config=None):
    # This is an application startup hook, not a reusable library. Use the OS
    # certificate store for HTTPS verification, including Windows-managed roots.
    truststore.inject_into_ssl()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    app = Flask(__name__)
    app.config.from_mapping(SAM_API_KEY=os.getenv("SAM_API_KEY", ""))
    if test_config:
        app.config.update(test_config)

    from .routes import main

    app.register_blueprint(main)
    return app

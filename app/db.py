"""SQLite persistence. Only source snapshots change when a notice is re-saved."""
import json
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

STATUSES = ("New", "Interested", "Reviewing", "Bid", "No-Bid", "Submitted", "Won", "Lost", "Skipped")
SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    notice_id TEXT PRIMARY KEY,
    metadata TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'New' CHECK (status IN
      ('New','Interested','Reviewing','Bid','No-Bid','Submitted','Won','Lost','Skipped')),
    notes TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    review_text TEXT NOT NULL DEFAULT '',
    review_source TEXT NOT NULL DEFAULT '',
    saved_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_app(app):
    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection:
            connection.close()
    with app.app_context():
        get_db().executescript(SCHEMA)


def unpack(row):
    if row is None:
        return None
    item = dict(row)
    metadata = json.loads(item.pop("metadata"))
    return {**metadata, **item}


def get_opportunity(notice_id):
    return unpack(get_db().execute("SELECT * FROM opportunities WHERE notice_id=?", (notice_id,)).fetchone())


def save_opportunity(metadata):
    stamp = now()
    # Parameter binding keeps even quotes and SQL fragments in notice text harmless.
    with get_db() as connection:
        connection.execute("""INSERT INTO opportunities (notice_id, metadata, saved_at, fetched_at, updated_at)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(notice_id) DO UPDATE SET
            metadata=excluded.metadata, fetched_at=excluded.fetched_at""",
            (metadata["notice_id"], json.dumps(metadata), stamp, stamp, stamp))


def list_opportunities(query="", status=""):
    sql, params = "SELECT * FROM opportunities WHERE 1=1", []
    if status:
        sql += " AND status=?"
        params.append(status)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND (json_extract(metadata, '$.title') LIKE ? ESCAPE '\\' OR json_extract(metadata, '$.agency') LIKE ? ESCAPE '\\' OR json_extract(metadata, '$.solicitation') LIKE ? ESCAPE '\\')"
        params.extend([f"%{escaped}%"] * 3)
    sql += " ORDER BY saved_at DESC, notice_id"
    return [unpack(row) for row in get_db().execute(sql, params)]


def update_review(notice_id, status, notes):
    if status not in STATUSES or len(notes) > 10000:
        raise ValueError("Choose a valid status and keep notes under 10,000 characters.")
    with get_db() as connection:
        connection.execute("UPDATE opportunities SET status=?, notes=?, updated_at=? WHERE notice_id=?",
                           (status, notes, now(), notice_id))


def store_text(notice_id, text, source, description=False):
    with get_db() as connection:
        if description:
            connection.execute("UPDATE opportunities SET description=?, updated_at=? WHERE notice_id=?", (text, now(), notice_id))
        else:
            connection.execute("UPDATE opportunities SET review_text=?, review_source=?, updated_at=? WHERE notice_id=?", (text, source, now(), notice_id))


def delete_opportunity(notice_id):
    with get_db() as connection:
        connection.execute("DELETE FROM opportunities WHERE notice_id=?", (notice_id,))


def get_profile():
    row = get_db().execute("SELECT data FROM profile WHERE id=1").fetchone()
    return json.loads(row[0]) if row else {"keywords": [], "naics": [], "states": [], "set_asides": []}


def save_profile(data):
    with get_db() as connection:
        connection.execute("INSERT INTO profile VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (json.dumps(data),))

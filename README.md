# Federal Contract Opportunity Analyzer

A learning project for finding and reviewing federal contracting notices from SAM.gov.
Built incrementally with AI assistance; features and verification are documented as they are completed.

## Milestone plan

1. Run Flask locally, request a small page of real SAM.gov notices, and display useful fields.
2. Add SQLite persistence, review statuses, and notes.
3. Add filters, a deadline dashboard, and CSV/Excel exports.
4. Develop explainable capability matching and document analysis.

Only milestone 1 is currently in development. No database, scoring, or document analysis is implemented.

## Stack

Python, Flask, Requests, Jinja HTML templates, and CSS. Pytest verifies request handling and display behavior.
SQLite, JavaScript, and Pandas will be introduced only when a feature needs them.

## Local setup (PowerShell, Python 3.12+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env locally and set SAM_API_KEY. Never commit that file.
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1
```

Open http://127.0.0.1:5000. This is a local development server.

## Official source and credentials

[GSA Get Opportunities Public API documentation](https://open.gsa.gov/api/get-opportunities-public-api/)
was checked on October 2, 2026. Production searches use `https://api.sam.gov/opportunities/v2/search`.
Request a personal public API key through SAM.gov Account Details. The server reads `SAM_API_KEY`
from the environment or a local `.env` file. Environment variables take precedence.

Do not paste credentials into issues, screenshots, source files, or GitHub. `.env`, local data,
and the virtual environment are ignored by Git. No credential is needed to run isolated tests.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

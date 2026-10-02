# Milestone 1: understand the first request

## Purpose

Run a small Flask application locally, retrieve a few real federal notices, and display
their useful fields. This milestone is intentionally limited to search and display.

## Read the code in this order

1. `app/__init__.py`: `create_app()` creates Flask, reads local configuration, and registers
   routes. An application factory lets tests create an app with their own settings.
2. `app/routes.py`: `index()` reads form values from the URL. It converts date strings into
   Python date objects and rejects invalid ranges before spending an API request.
3. `app/sam_client.py`: `search_opportunities()` converts dates to SAM.gov's required format,
   calls the REST endpoint, checks the response, and normalizes records.
4. `app/templates/index.html`: Jinja loops over normalized records and produces HTML.
   Missing data is shown explicitly, not guessed.
5. `tests/`: mock responses let us exercise errors and display behavior without credentials
   or network access. They are clearly labeled synthetic and are not loaded by the application.

## Concepts to explain in an interview

- **Two HTTP requests:** the browser requests our Flask page; Python requests JSON from SAM.gov.
- **Query parameters:** search values are sent as parameters, not manually concatenated URLs.
- **Authentication:** a server-side environment variable supplies the key. `.gitignore` keeps
  the local file out of Git; it does not make hard-coded secrets elsewhere safe.
- **Normalization:** external field names and null values are translated once, keeping the
  template readable. Office address is not substituted for missing place of performance.
- **Pagination:** this milestone requests page index zero and at most 10 records. The total
  matching count can be larger; pagination controls are future work.
- **Testing boundaries:** a mocked request can verify our behavior but cannot verify a key,
  current API availability, actual search semantics, or real data quality.

Try explaining why a 200 response with an empty list differs from a 403 response, and why
neither should cause the app to invent opportunities. Then trace one displayed NAICS value
back through the normalizer to the JSON field `naicsCode`.

## Documentation decisions

Official source: https://open.gsa.gov/api/get-opportunities-public-api/ (reviewed October 2, 2026).
Use the production endpoint from the Getting Started section. Some older examples include
different URL prefixes. Use the documented `title` filter and required posted-date parameters.
The published schema table and examples differ in deadline spelling, so the normalizer accepts
both `responseDeadLine` and `reponseDeadLine`. API quotas depend on account role; no fixed quota
is assumed. Search responses do not supply full description text directly.

## Verification log

October 2, 2026:

- Python 3.12.14 isolated environment created; dependencies installed successfully.
- 26 isolated tests passed; dependency consistency check passed.
- Flask development server started at http://127.0.0.1:5000.
- Landing page inspected in browser; search inputs and missing-key setup state are visible.
- Live authenticated request attempted: HTTPS verification initially failed using the bundled
  certificate list. Application startup now uses `truststore` to verify against OS-trusted
  certificates. Verification remains enabled; no certificate checks were bypassed.
- An initial saved-key formatting error caused HTTP 401 / API_KEY_INVALID. After the local
  configuration was corrected, the same search succeeded with HTTP 200. No credential values
  were logged or committed.
- Live search: title `software`, posted `09/02/2026` through `10/02/2026`, first page of 10
  notices from 150 matches. Confirmed in the running Flask app's browser page.
- Original notice verified in SAM.gov: [Hexagon CMM maintenance and repair](https://sam.gov/opp/1a12977fc8d945c19ac8146f9f3317e0/view).
  Solicitation `W15QKN26RA097`, Army / W6QK ACC-RI-PICATINNY, NAICS `811210`, no set-aside,
  Picatinny Arsenal, NJ. The source's October 16, 2026 at 3:00 pm EDT deadline matches
  `2026-10-16T15:00:00-04:00` in the app. Posted date matches October 2, 2026.
- Live retrieval, rendering, and source comparison: **passed**. This verifies search and
  display, not whether a particular business qualifies to bid. The source notice's description
  must still be reviewed; keyword relevance alone is insufficient.

## Repeatable live acceptance check (completed)

1. Put the personal API key in the ignored `.env`, then restart Flask.
2. Search `software` over the last 30 days. If empty, use a broader term or blank keyword.
3. Confirm at least one result has a title and notice link.
4. Open the original notice and compare solicitation number, organization, NAICS, and deadline
   where available. Keep the source's date/time representation; do not assume a timezone.
5. Record the test date, search range, count, and public notice ID here, without keys, raw
   request URLs, or personal contact details.

Do not start database or scoring work until this check succeeds.

## Development commits

Milestone 1 is recorded in three logical commits:

1. `chore: scaffold Flask project and secure local configuration`
2. `feat: search SAM.gov notices and render opportunity fields`
3. `test: verify search handling and document milestone one`

These represent the actual implementation stages; no earlier authorship or dates are implied.

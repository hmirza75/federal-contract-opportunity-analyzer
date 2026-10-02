# Architecture and interview walkthrough

The application is a local, single-user Flask web app. Jinja renders HTML; a small JavaScript
file handles loading feedback and delete confirmation. SQLite persists research between runs.
There is no frontend framework, external AI service, or production authentication layer.

## Trace a complete workflow

1. The browser submits a GET search form. `routes.index` validates posted dates, deadline dates,
   NAICS, location, set-aside, and notice type before making an external request.
2. `sam_client.search_opportunities` sends one HTTPS request to the official API. `api_key`
   comes from the server environment. The page index goes into `offset`; page size is 10.
3. `normalize_opportunity` converts external field names and nulls into a stable display shape.
   Official links are constrained, and text is escaped by Jinja.
4. Each result carries a signed, expiring snapshot. A Save POST requires both a valid CSRF
   token and that snapshot signature. This prevents submitting an edited browser form as
   if it were an API result. A signature provides integrity, not encryption; only public
   notice metadata goes in it.
5. `db.save_opportunity` binds SQL parameters and uses the notice ID as its primary key.
   On conflict, it updates only the SAM snapshot. Notes, status, and separately fetched text
   remain intact. This is an upsert, not another copy of the opportunity.
6. Detail-page POSTs persist status, notes, descriptions, or document text. A redirect after
   each mutation prevents refresh from resubmitting the form.
7. The dashboard queries saved records and classifies deadlines. It uses UTC for aware
   timestamps and calendar days for unknown timezones, which are explicitly labeled.
8. Scoring reads the current local profile. Document analysis selects verbatim source
   passages with named keyword rules. Neither makes an eligibility determination.
9. CSV and Excel exports use the same saved-record filters. Cells that could become formulas
   are escaped; Excel cells are explicitly written as strings.

## Modules

| Module | Responsibility |
| --- | --- |
| `app/__init__.py` | Application factory, configuration, CSRF, security headers, database initialization |
| `app/routes.py` | Validate user input and coordinate application workflows |
| `app/sam_client.py` | Official API requests, bounded description download, normalization |
| `app/search_filters.py` | Allowed filter values and SAM parameter mapping |
| `app/db.py` | SQLite connections, schema, bound queries, upserts, profile persistence |
| `app/deadlines.py` | Deadline classification and reminder exclusions |
| `app/scoring.py` | Profile validation, weighted matching, explanations, caveats |
| `app/analysis.py` | Evidence rules, HTML-to-text conversion, upload validation |
| `app/pdf_worker.py` | PDF extraction in a time-limited subprocess |
| `app/exports.py` | CSV and formatted Excel output |

## Database design

`opportunities` has one row per SAM notice ID. `metadata` is a JSON source snapshot;
`status`, `notes`, `description`, `review_text`, and `review_source` are separately stored fields.
`saved_at`, `fetched_at`, and `updated_at` record the original save, source refresh, and local
review update in UTC. The status column has a CHECK constraint and an index.

`profile` holds one local capability profile. Profile preferences are stored as JSON arrays.
The database is initialized with `CREATE TABLE IF NOT EXISTS`; this release has no destructive
reset command. Future schema changes will need explicit migrations.

Why JSON for source metadata? SAM.gov has optional and changing fields. A compact normalized
snapshot keeps this small app understandable while workflow fields remain independently
queryable. SQLite `json_extract` supports saved-title/agency/solicitation filtering. At larger
scale, frequently queried source fields could move to dedicated indexed columns.

## Matching rules

Configured weights: keywords 50, NAICS 30, location 10, set-aside preference 10.
The denominator includes only configured categories. Keyword points are proportional to the
number of distinct case-insensitive terms found with word boundaries. Other categories use
exact matches. Missing source values receive zero points and a warning. The number is rounded
to 0–100. It is not calibrated against bid outcomes.

Search-page scores use titles and metadata. Saved-detail scores also use the fetched description
and the latest pasted/uploaded review text, so the two can differ. The displayed breakdown lists
matched terms and source/profile values. Keyword synonyms and semantic equivalents are not inferred.

## Document review rules

Text is separated into evidence passages labeled P1, P2, etc. Keyword patterns select passages
for six categories. Up to 12 matches per category appear, with omitted counts and full source text
available below. The scope overview repeats up to three matching excerpts; it is not a generated
abstract. PDF extracts retain page markers when present. New review text replaces the prior review.

Limits: 5 MB uploads, 50 PDF pages, 150,000 extracted characters, 20-second PDF extraction timeout,
and 2 MB description download. No OCR, attachment crawling, legal interpretation, or external
model calls. Negation, tables, unusual wording, and amendments still require human review.

## Security boundaries

- Bind to `127.0.0.1`; trusted Host values are localhost and loopback addresses.
- All mutations require CSRF tokens. Search snapshots are signed with a local secret.
- API keys stay server-side. Error responses avoid upstream bodies and authenticated URLs.
- `.env`, `instance/`, databases, uploaded working data, and virtual environments are ignored.
- TLS verification stays enabled; truststore uses OS roots. Redirects are disabled on API calls.
- Description URLs are restricted to approved SAM.gov paths and a matching notice ID.
- Uploaded bytes are temporary; only extracted text is retained in SQLite.
- Saved data is private local data, not encrypted at rest. Back up and protect the machine.

There are no user accounts or access roles. Public hosting would require authentication,
authorization, HTTPS, a production server, operational monitoring, and a shared-key/quota design.
It is not sufficient to change the bind address.

## Questions to practice

1. Why use a primary key and an upsert instead of inserting on every Save?
2. How do CSRF protection and a signed result snapshot solve different problems?
3. Which fields are source facts, and which are a user's decisions?
4. Why do the automated tests mock SAM.gov while live checks use it sparingly?
5. Why is a relevance score of 100 not proof that a business can bid?
6. How would you add database migrations, multi-user access, and background refresh safely?

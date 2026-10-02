# Release verification

## v1.0.0, October 2, 2026

- 56 isolated automated tests pass locally on Python 3.12.14 / Windows.
- Tests cover validation, pagination mapping, upstream failures, CSRF, tampered snapshots,
  SQL/HTML injection, upserts, restart persistence, status filters, deletion, deadline offsets,
  spreadsheet formula safety, scoring arithmetic, URL restrictions, document evidence, and
  valid/invalid PDF and text extraction. Test fixtures are explicitly synthetic; network is blocked.
- Live filtered search: `software`, combined synopsis/solicitation (`ptype=k`), posted September 2
  through October 2, 2026; first page returned 10 of 24 matches.
- Three real notices were saved to the ignored local database, not the repository.
- The official description for notice `1a12977fc8d945c19ac8146f9f3317e0` was retrieved: 2,351 characters.
  It generated evidence passages and surfaced a sole-source restriction in the original text.
- The dashboard and saved detail/profile workflows were inspected in the browser.
- No live request results or API credentials are used as automated test fixtures.

Fresh-install and GitHub Actions results are recorded after their respective checks finish.

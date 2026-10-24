# Executed validation — updated 24 October 2026

These results were produced by running the application and tests in this workspace. They are not proposed checks or mocked production statistics.

## Latest routing and dashboard verification — 24 October 2026

- Full regression suite: **80 passed in 37.03 seconds**, using the project Python 3.12 environment outside the restricted execution sandbox. The initial sandbox run passed 63 tests but could not create temporary fixtures for 17 tests; the unrestricted rerun passed all tests.
- Live API: `urgent ticket` returned a clarification distinguishing urgency from priority; `awaiting user information` selected the `Awaiting User Info` latest-state filter and returned 0 incidents; `How many critical tickets are there?` returned 270 incidents and 2,306 observations in that latest-priority population.
- Streamlit AppTest against the restarted backend: initial metrics, chat, incident history and priority filter passed, with zero exceptions.
- New routing regression cases cover the state alias, short state requests, ticket-count wording, multiple-state rejection, ambiguous urgency and actionable fallback suggestions.

The policy embedding smoke test was not rerun for this routing/UI change. The earlier embedding, ingestion and independent-SQL checks below retain their original validation date.

## Earlier validation — 23 October 2026

| Check | Actual result |
|---|---|
| Full pytest regression | **46 passed in 43.09 seconds** |
| Ten required acceptance questions against live FastAPI | **10/10 passed** |
| Unrelated policy question with generic policy wording | **Passed: no citations, explicit inability to establish an answer** |
| Streamlit AppTest against real backend | **Passed: initial metrics, chat, incident explorer and priority filter; zero exceptions** |
| Dependency consistency | `pip check`: **No broken requirements found** |
| Real local embeddings | all-MiniLM-L6-v2 downloaded, cached and used successfully |
| Persistent policy index | **8 documents, 24 section chunks** |
| Repeated database initialization | **unchanged**, no duplicate rows |
| Repeated policy indexing | **unchanged**, no duplicate chunks or regenerated embeddings |
| Original input preservation | All four SHA-256 hashes match docs/INPUT_HASHES.json |
| SQLite integrity / foreign keys | `ok` / zero violations |
| Browser check | Backend-connected and offline labels, real charts and incident-explorer form rendered |

Commands executed from the root with the project Python 3.12 environment:

```powershell
.\.venv312\Scripts\python.exe -m scripts.inspect_data --write-schema
.\.venv312\Scripts\python.exe -m scripts.init_db
.\.venv312\Scripts\python.exe -m scripts.ingest_policies
.\.venv312\Scripts\python.exe -m pip check
.\.venv312\Scripts\python.exe -m pytest -q
.\.venv312\Scripts\python.exe -m scripts.smoke_test --url http://127.0.0.1:8000
.\.venv312\Scripts\python.exe -m scripts.verify_frontend
```

Full resolved dependencies are in requirements.lock.txt; principal versions, Python/SQLite versions and cached embedding revision are in docs/ENVIRONMENT.json. The actual environment is Python 3.12.14 and SQLite 3.53.1. Model cache revision observed: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. This records the model revision used in this run; model downloads by name are not a guarantee of immutable future Hub content.

## Data and metric evidence

| Quantity | Verified value |
|---|---:|
| incident_events rows | 141,712 |
| Distinct event incident identifiers | 24,918 |
| incident_summary rows and unique identifiers | 24,918 |
| latest_selection_ties rows | 0 |
| Event / summary / tie CSV columns | 39 / 52 / 7 |
| Sum of summary event_count | 141,712 |
| Latest Critical / High / Moderate / Low incidents | 270 / 408 / 23,466 / 774 |
| Latest Closed incidents | 24,918 |
| Observed priority-change incidents | 383 |
| Observed source made_sla-change incidents | 9,114 |
| Incidents with any observed reopening counter > 0 | 275 |
| Average observations per incident | 5.687133798860262 |
| Valid nonnegative latest-summary resolution durations | 23,362 |
| Excluded resolution durations | 1,556 |
| Average valid latest-summary resolution hours | 178.1715820563308 |

All four files decoded strictly as UTF-8 without BOM. Blank CSV cells are unknown information. Populated timestamps have YYYY-MM-DD HH:MM:SS formatting, with no timezone established. No original data was rewritten. All latest summary states are Closed; the event-state population has varied states, including five normalized Unknown observations from raw -100. These are different grains and must not be conflated.

## Coverage and independent checks

The full suite covers data counts/relationships and original hashes; full temporary SQLite import, primary keys, indexes, NULL preservation and repeatability; small explicit analytics fixtures with duplicate observations and priority changes; nonnegative-duration eligibility and any-observation reopenings; safe parameter validation; isolated Chroma indexing, metadata, citations, stale-index detection, no-match and weak-match rejection; all compiled graph routes, provider fallback and hostile document boundaries; API success/error paths and schemas; and mocked provider JSON/evidence-ID validation.

The live smoke test selects a real incident ID from SQLite. It checks all ten supplied sample questions, matches distribution/count responses against independently written SQLite SELECTs, checks expected escalation/reopening document IDs, validates hybrid priority selection and complete incident history, rejects an unsupported tool, and compares original hashes. Detailed output is runtime/smoke_results.json. The UI report is runtime/frontend_results.json. Those generated files are ignored by Git.

The real embedding smoke test also asks an unrelated quantum-entanglement question containing generic “demonstration policy” wording. The default cosine-distance threshold is 0.55. Supported demo passages measured roughly 0.26–0.52; unrelated top passages were roughly 0.61–0.64 and are rejected. This is a targeted relevance regression, not a general retrieval benchmark or calibrated confidence score.

## Environment and practical limits

Installation and the first model download required permitted network access. Normal offline-demo queries use cached local weights. The restricted Windows execution sandbox stalled asyncio's loopback socket pair and initially prevented pytest temporary-directory creation; final API tests and local servers ran successfully outside that restriction. Normal Windows PowerShell does not require that sandbox workaround.

No paid LLM provider was called. Optional provider behavior is covered with mocked HTTP responses, plan validation and extractive evidence-selection tests. A live provider requires the user's own credentials and compatible JSON chat-completions support. No claim of live-provider certification is made.

This validation does not establish enterprise load capacity, universal prompt-injection protection, exhaustive retrieval relevance or production security. The app is a single-user local MVP. Policy documents are synthetic, not Accenture/UCI policies. Source made_sla is never interpreted as breach/compliance, completion timestamps are not used as historical point-in-time features, and missing source information remains unknown.

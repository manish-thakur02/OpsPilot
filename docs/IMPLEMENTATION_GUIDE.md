# Code walkthrough and development guide

## Important files

| File | Responsibility |
|---|---|
| app/config.py | Project-relative paths, dotenv configuration, explicit offline/LLM mode |
| app/database/inspection.py | Strict read-only input validation, observed schema and schema documentation |
| app/database/ingest.py | Atomic full SQLite import, indexes, metadata and idempotence |
| app/database/connection.py | Context-managed read-only connections and actionable availability errors |
| app/database/queries.py | Application-owned filter fragments and bound values |
| app/services/analytics.py | Validated filter/tool models and all approved SQL analytics |
| app/rag/ingest.py | Heading-aware chunks, model caching, persistent Chroma upserts and manifest |
| app/rag/retriever.py | Readiness checks, local-only query embeddings, cosine threshold and citations |
| app/services/llm.py | Optional timeout-bound compatible JSON interface and extractive evidence selection |
| app/agents/router.py | Validated plans and conservative offline question grammar |
| app/agents/graph.py | Compiled LangGraph, tool execution, validation, response formatting and trace |
| app/api/schemas.py | External chat and metric response models |
| app/api/routes.py | Required REST endpoints, dependency seams and chat HTTP status selection |
| app/main.py | FastAPI app, OpenAPI docs and database/not-found exception handlers |
| frontend/streamlit_app.py | Three-tab dashboard; calls only the API for statistics |
| scripts/smoke_test.py | Ten acceptance questions, direct SQL oracle and original-hash preservation |
| scripts/verify_frontend.py | Streamlit AppTest against a running real backend |

Small related route handlers live together in graph.py rather than being scattered across policy_agent.py, analytics_agent.py and hybrid_agent.py. The graph still contains four explicit conditional route nodes. This keeps the MVP easy to explain.

## Follow one analytics request

1. A Streamlit example button submits a question to POST /chat with HTTPX.
2. ChatRequest rejects blank, oversized or unexpected input.
3. The compiled graph trims the question and initializes evidence, errors and timing.
4. The classifier chooses ANALYTICS and an approved ToolRequest such as priorities.
5. The route invokes Analytics.run(); that method validates the tool/filters again.
6. A read-only SQLite connection runs SELECT/GROUP BY over incident_summary. Query values are bound parameters.
7. The validation node checks that result.metric matches the selected tool.
8. Composition displays the actual returned values and applied filters. The API includes sources, structured data, mode, tool names and trace. Streamlit displays these without duplicating SQL.

For an overview, incident count is COUNT(*) over the summary population and event count is SUM(event_count), which the input/import validators reconcile to the full observation table. Reopening counts use an EXISTS subquery over any recorded observation, even if a later observed counter is lower. Resolution averages exclude NULL and negative durations and report both the included and excluded populations.

The offline router normalizes whitespace and the state alias `Awaiting User Information` to `Awaiting User Info` for matching. A standalone explicit state selects an overview filtered by latest summary state; ticket/incident count questions use the same approved overview tool. Multiple states still require clarification. `urgent` triggers clarification because urgency and priority are different fields; it is never silently mapped to Critical. Unrecognized requests offer concrete supported examples and explain that the application cannot create or update tickets. The frontend displays the offline grammar limitation and the all-Closed latest-snapshot property before chat input. Restart the backend after editing routing; old chat replies are retained as originally generated.

## Follow a policy or hybrid request

Retriever checks the manifest against current Markdown hashes, opens the persistent collection, loads the cached local sentence-transformer once per process and embeds only the question. Chroma returns nearest section vectors and metadata; passages outside the cosine-distance threshold (0.55) are excluded. The model is never downloaded while handling a query. Citations include document ID, heading, filename and version.

Offline composition returns exact passages with a retrieval-only label. Configured LLM composition selects valid evidence IDs and still renders exact text. A hybrid request additionally calls the SQL registry and adds separate policy and historical-data blocks. An unspecified escalation category uses illustrative P1/1 - Critical, stated in the answer. It is not a compliance assessment.

The limitations tool returns documented dataset boundaries and cites DATA_SCHEMA.md; it is not a SQL-derived numerical claim.

## Add a metric safely

Define the population and denominator first. Add a Literal tool name and explicit SELECT branch to analytics.py; never accept a SQL string. Validate new parameters in Pydantic. Add fixture cases including duplicated observations, NULLs and empty populations. Extend the offline planner only when its grammar can identify the requested metric and filters reliably. Add route/response tests and documentation before enabling the tool through the LLM planner.

## Update demonstration policies

Keep the synthetic disclosure, a unique DEMO-POL ID, version and section headings. Stop serving, edit the Markdown and rerun the indexing command. Changed documents invalidate retrieval until explicitly reindexed. Reindexing upserts deterministic IDs and removes stale chunks. Review the citation/relevance smoke checks after changing documents or embeddings. Do not run concurrent index writers.

## Verify changes

Run `python -m pytest -q` from the activated project environment. This suite uses one full temporary import and small explicit analytics fixtures. RAG unit tests use isolated Chroma collections and deterministic test-only embeddings; production never uses those fixtures or embeddings. Run `python -m scripts.smoke_test` to verify the real cached MiniLM model and all ten acceptance questions. Start the API and run `python -m scripts.verify_frontend` to exercise the UI's real API connection. TestClient and asyncio require loopback socket access; a restricted Windows automation sandbox can stall them even though normal PowerShell works.

# GitHub Copilot — movie-finder-chain

LangGraph AI pipeline for Movie Finder. This package implements the 8-node state machine
that classifies user intent, performs semantic search, enriches results via IMDb, and
streams Q&A answers back to the frontend.

Parent project: `aharbii/movie-finder` — all issues created there first, then linked here.

---

## Package role

| Node | Responsibility |
|---|---|
| `classify` | Claude Haiku — determines if message is a movie query or follow-up |
| `embed` | OpenAI `text-embedding-3-large` (3072-dim) — embeds the user query |
| `search` | Qdrant Cloud vector search — retrieves candidate movies |
| `confirm` | Claude Sonnet — selects the best match from candidates |
| `imdb_fetch` | Calls `imdbapi` client for live metadata enrichment |
| `answer` | Claude Sonnet — streams the final answer via SSE |
| `clarify` | Claude Haiku — asks follow-up when intent is ambiguous |
| `fallback` | Handles no-match and error paths |

LangSmith tracing: opt-in via `LANGSMITH_TRACING=true`.

---

## Python standards

- Python 3.13, `uv` workspace member (`backend/.venv`), `ruff` + `mypy --strict`, line length **100**
- Type annotations required on all public functions
- Async all the way — no blocking I/O in async context
- Docstrings on all public classes and functions (Google style)
- Tests: `pytest` with `pytest-mock`. No real LLM/Qdrant/IMDb calls — mock at the HTTP boundary.

---

## Design patterns — follow these

| Pattern | Rule |
|---|---|
| **State machine** | New behaviour = new node or edge. Never add branching inside existing nodes. |
| **Strategy** | New LLM or embedding provider = new class implementing the provider interface. No `if provider == "openai"` in core logic. |
| **Factory** | Node construction is centralised in `graph.py`. Nodes are pure functions. |
| **Configuration object** | All env vars loaded once in `config.py` via Pydantic `BaseSettings`. |

---

## Pre-commit hooks

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-merge-conflict`,
`detect-private-key`, `detect-secrets`, `mypy --strict`, `ruff-check --fix`, `ruff-format`.

---

## Known issues most relevant to this package

| # | Title |
|---|---|
| #2 | `MemorySaver` non-persistent — breaks multi-replica |
| #7 | OpenAI + Qdrant clients re-created per LangGraph node |
| #8 | IMDb retry base delay 30 s — blocks SSE stream |
| #15 | `total=False` on `MovieFinderState` TypedDict weakens type safety |
| #18 | `create_agent` import path is non-standard |

---

## Cross-cutting — check for every change

1. GitHub issue in `aharbii/movie-finder` + this repo (linked)
2. Branch: `feature/`, `fix/`, `chore/` (kebab-case)
3. ADR if LLM model, embedding model, or pipeline pattern changes
4. `.env.example` updated in chain + backend + root
5. `Dockerfile` updated if new deps or env vars
6. PlantUML `04-langgraph-pipeline.puml` and `05-langgraph-statemachine.puml` updated
7. Structurizr `workspace.dsl` updated for component changes
8. `backend/app/` assessed — SSE event shape or state fields may affect it
9. `backend/rag_ingestion/` assessed — embedding model changes affect both

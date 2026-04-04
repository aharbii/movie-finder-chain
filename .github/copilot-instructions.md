# GitHub Copilot — movie-finder-chain

LangGraph AI pipeline for Movie Finder. This package implements the 8-node state machine
that classifies user intent, performs semantic search, enriches results via IMDb, and
streams Q&A answers back to the frontend.

Parent project: `aharbii/movie-finder` — all issues created there first, then linked here.

---

## Package role

| Node         | Responsibility                                                              |
| ------------ | --------------------------------------------------------------------------- |
| `classify`   | Claude Haiku — determines if message is a movie query or follow-up          |
| `embed`      | OpenAI `text-embedding-3-large` (3072-dim) — embeds the user query          |
| `search`     | Qdrant Cloud vector search — retrieves candidate movies                     |
| `confirm`    | Claude Sonnet — selects the best match from candidates                      |
| `imdb_fetch` | Calls `imdbapi` client (independent submodule) for live metadata enrichment |
| `answer`     | Claude Sonnet — streams the final answer via SSE                            |
| `clarify`    | Claude Haiku — asks follow-up when intent is ambiguous                      |
| `fallback`   | Handles no-match and error paths                                            |

LangSmith tracing: opt-in via `LANGSMITH_TRACING=true`.

---

## Python standards

- Python 3.13, Docker-only local workflow via `make ...`, attached-container interpreter at `/opt/venv/bin/python`
- Type annotations required on all public functions
- Async all the way — no blocking I/O in async context
- Docstrings on all public classes and functions (Google style)
- Tests: `pytest` with `pytest-mock`. No real LLM/Qdrant/IMDb calls — mock at the HTTP boundary.

---

## Design patterns — follow these

| Pattern                  | Rule                                                                                                                       |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **State machine**        | New behaviour = new node or edge. Never add branching inside existing nodes.                                               |
| **Strategy**             | New LLM or embedding provider = new class implementing the provider interface. No `if provider == "openai"` in core logic. |
| **Factory**              | Node construction is centralised in `graph.py`. Nodes are pure functions.                                                  |
| **Configuration object** | All env vars loaded once in `config.py` via Pydantic `BaseSettings`.                                                       |

---

## Pre-commit hooks

```bash
make pre-commit
```

Hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-merge-conflict`,
`detect-private-key`, `detect-secrets`, `mypy --strict`, `ruff-check --fix`, `ruff-format`.

---

## Local workflow

- `make dev` starts the persistent `chain` container for attached-container editing
- `make lint`, `make format`, `make typecheck`, `make test`, `make test-coverage`, and `make pre-commit` are the supported repo-local commands
- Qdrant is always external; use `QDRANT_URL`, `QDRANT_API_KEY_RO`, and `QDRANT_COLLECTION_NAME`

---

## Known issues most relevant to this package

| #   | Title                                                             |
| --- | ----------------------------------------------------------------- |
| #2  | `MemorySaver` non-persistent — breaks multi-replica               |
| #7  | OpenAI + Qdrant clients re-created per LangGraph node             |
| #8  | IMDb retry base delay 30 s — blocks SSE stream                    |
| #15 | `total=False` on `MovieFinderState` TypedDict weakens type safety |
| #18 | `create_agent` import path is non-standard                        |

---

## Workflow invariants

- This repo is the gitlink path `chain` inside `aharbii/movie-finder-backend`. Parent
  workflow/path filters must use `chain`, not `chain/**`.
- Cross-repo tracker issues originate in `aharbii/movie-finder`. Create the linked child issue in
  this repo only if this repo will actually change.
- Inspect `.github/ISSUE_TEMPLATE/*.yml`, `.github/PULL_REQUEST_TEMPLATE.md` when present, and a
  recent example before creating or editing issues/PRs. Do not improvise titles or bodies.
- For child issues in this repo, use `.github/ISSUE_TEMPLATE/linked_task.yml` and keep the
  description, file references, and acceptance criteria repo-specific.
- If CI, required checks, or merge policy changes affect this repo, update contributor-facing docs
  here and in `aharbii/movie-finder-backend` and/or `aharbii/movie-finder` where relevant.
- If a new standalone issue appears mid-session, branch from `main` unless stacking is explicitly
  requested.
- PR descriptions must disclose the AI authoring tool + model. Any AI-assisted review comment or
  approval must also disclose the review tool + model.

---

## Cross-cutting — check for every change

1. GitHub issue in `aharbii/movie-finder` + linked child issue here only if this repo changes, using the current templates and recent examples
2. Branch: `feature/`, `fix/`, `chore/` (kebab-case) from `main` unless stacking is explicitly requested
3. ADR if LLM model, embedding model, or pipeline pattern changes
4. `.env.example` updated in chain + backend + root
5. `Dockerfile` updated if new deps or env vars
6. PlantUML `04-langgraph-pipeline.puml` and `05-langgraph-statemachine.puml` updated
7. Structurizr `workspace.dsl` updated for component changes
8. `backend/app/` assessed — SSE event shape or state fields may affect it
9. `backend/rag_ingestion/` assessed — embedding model changes affect both

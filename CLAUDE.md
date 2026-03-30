# Claude Code — chain submodule

This is **`movie-finder-chain`** (`backend/chain/`) — part of the Movie Finder project.
GitHub repo: `aharbii/movie-finder-chain` · Parent repo: `aharbii/movie-finder`

---

## What this submodule does

LangGraph 8-node AI pipeline — the core intelligence layer of Movie Finder.

**Pipeline flow:**
`classify` → `search_rag` → `enrich_imdb` → `reason` → `route` → `refine` / `confirm` / `answer`

- **State:** `MovieFinderState` (TypedDict) shared across all nodes
- **Models:** Claude Sonnet for confirmation/refinement/Q&A flows
- **Embeddings:** OpenAI `text-embedding-3-large` at query time (must match ingestion)
- **Vector search:** Qdrant Cloud (always external)
- **IMDb enrichment:** via `imdbapi` workspace member
- **Bounded refinement:** max 3 cycles (`MAX_REFINEMENTS`)
- **Tracing:** LangSmith (opt-in via `LANGSMITH_TRACING=true`)
- **uv workspace member** of `backend/`

### Key source layout

```
src/chain/
├── config.py          # Pydantic BaseSettings — all env vars loaded here
├── graph.py           # LangGraph Pregel graph definition (node wiring)
├── state.py           # MovieFinderState TypedDict
├── models/            # Domain data structures
├── nodes/             # Individual node implementations (pure functions)
├── prompts/           # LLM prompt templates
├── rag/               # Qdrant vector search wrapper
└── utils/             # Helpers
```

---

## Full project context

### Submodule map

| Path | GitHub repo | Role |
|---|---|---|
| `.` (root) | `aharbii/movie-finder` | Parent — all cross-repo issues |
| `backend/` | `aharbii/movie-finder-backend` | FastAPI + uv workspace root |
| `backend/app/` | (nested in backend) | FastAPI application layer |
| `backend/chain/` | `aharbii/movie-finder-chain` | **← you are here** |
| `backend/imdbapi/` | `aharbii/imdbapi-client` | Async IMDb REST client |
| `backend/rag_ingestion/` | `aharbii/movie-finder-rag` | Offline embedding ingestion |
| `frontend/` | `aharbii/movie-finder-frontend` | Angular 21 SPA |
| `docs/` | `aharbii/movie-finder-docs` | MkDocs documentation |
| `infrastructure/` | `aharbii/movie-finder-infrastructure` | IaC / Azure provisioning |

### Technology stack

| Layer | Stack |
|---|---|
| Language | Python 3.13, uv workspace member |
| AI pipeline | LangGraph 0.2+, LangChain 0.3+ |
| LLM | `langchain-anthropic` — Claude Sonnet for confirmation/refinement/Q&A flows |
| Embeddings | `langchain-openai` — `text-embedding-3-large` (3072-dim) |
| Vector store | `qdrant-client` (Qdrant Cloud — always external) |
| IMDb | `imdbapi` workspace member |
| Tracing | LangSmith (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`) |
| Linting | `ruff` (line-length 100) · `mypy --strict` |
| Tests | `pytest --asyncio-mode=auto`, verbose |
| CI | Jenkins Multibranch → Azure Container Registry |

### Environment variables (`.env.example`)

```
QDRANT_URL, QDRANT_API_KEY_RO, QDRANT_COLLECTION_NAME
EMBEDDING_MODEL=text-embedding-3-large, EMBEDDING_DIMENSION=3072
ANTHROPIC_API_KEY
CLASSIFIER_MODEL=claude-haiku-4-5-20251001
REASONING_MODEL=claude-sonnet-4-6
OPENAI_API_KEY
RAG_TOP_K=8, MAX_REFINEMENTS=3, IMDB_SEARCH_LIMIT=3, CONFIDENCE_THRESHOLD=0.3
LOG_LEVEL
LANGSMITH_TRACING=false, LANGSMITH_ENDPOINT, LANGSMITH_API_KEY, LANGSMITH_PROJECT
```

---

## Design patterns to follow

| Pattern | Where | Rule |
|---|---|---|
| **State machine** | `graph.py` | New behaviour = new node or new edge. Never add conditional branching inside an existing node to handle a different phase. |
| **Pure functions** | `nodes/` | Nodes take `MovieFinderState` and return a partial state update. No side effects except external I/O (LLM calls, Qdrant, IMDb). |
| **Strategy** | LLM providers, embedding providers | New model = new configuration value, not a new code path. The provider interface stays the same. |
| **Configuration object** | `config.py` | All settings loaded via `Pydantic BaseSettings` once at startup. Never `os.getenv()` inside node functions. |
| **Adapter** | `rag/` wrapper | The Qdrant wrapper adapts the client library to the domain interface. Nodes never call `qdrant-client` directly. |
| **Factory** | `graph.py` | Node creation and graph wiring is centralised here. Nodes are registered once. |

**Critical state rule:** `MovieFinderState` has `total=False` (issue #15 — tracked, not yet fixed).
When reading state fields in nodes, always use `.get()` with a safe default until this is resolved.

---

## Coding standards

- `mypy --strict` must pass — every node function must be fully typed
- No `type: ignore` without an explanatory comment
- No mutable default arguments — use `None` with `if x is None: x = []`
- Docstrings on all public functions and classes (Google style)
- No `print()` — use `logging` (LangSmith tracing handles LLM call observability)
- Async all the way — never call blocking I/O in an async context
- Line length: 100 (`ruff`)
- `ruff` rules: E, F, I, N, UP, B, C4, SIM

---

## Pre-commit hooks

`backend/chain/.pre-commit-config.yaml` — install and run from this directory.

```bash
make pre-commit
```

Hooks: whitespace/YAML/safety checks, `detect-secrets`, `mypy --strict` (pydantic deps), `ruff-check --fix`, `ruff-format`. **Never `--no-verify`.**
False positive → `# pragma: allowlist secret` + `detect-secrets scan > .secrets.baseline`.

---

## VSCode setup

`backend/chain/.vscode/` is committed with a full workspace configuration:
- `settings.json` — attached-container Python interpreter (`/opt/venv/bin/python`), Ruff, mypy strict, pytest discovery
- `extensions.json` — Remote Containers, Python, Pylance, debugpy, Ruff, mypy, Makefile tools, coverage gutters
- `launch.json` — `chat.py` interactive runner + pytest all / current file inside the attached container
- `tasks.json` — Docker-backed `make ...` targets from `backend/chain/`

**Workflow:** run `make dev`, then attach VS Code to the running `chain` container.

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

## Session start protocol

1. `gh issue list --repo aharbii/movie-finder --state open`
2. Inspect `.github/ISSUE_TEMPLATE/*.yml`, `.github/PULL_REQUEST_TEMPLATE.md` when present, and a
   recent example of the same type
3. Create the parent issue in `aharbii/movie-finder`, then the linked child issue in
   `aharbii/movie-finder-chain` only if this repo will actually change
4. Create a branch from `main`: `feature/`, `fix/`, `chore/`, `docs/`
5. Work through the cross-cutting checklist below

---

## Branching and commits

```
feature/<kebab>  fix/<kebab>  chore/<kebab>  docs/<kebab>
```

Conventional Commits: `feat(chain): add Gemini embedding support`

---

## Cross-cutting change checklist

Full detail in `ai-context/issue-agent-briefing-template.md`.

| # | Category | Key gate |
|---|---|---|
| 1 | **Issues** | Parent `aharbii/movie-finder` + child here only if this repo changes; templates inspected |
| 2 | **Branch** | `feature/fix/chore/docs` in this repo + pointer-bump `chore/` in `backend/` and root |
| 3 | **ADR** | New LLM provider, embedding model, external dep, or pipeline architecture → ADR in `docs/` |
| 4 | **Implementation** | State machine / Pure functions / Strategy / Factory patterns; `MovieFinderState` fields via `.get()` (#15); `ruff`+`mypy --strict` pass; pre-commit pass |
| 5 | **Tests** | `pytest --asyncio-mode=auto` passes; coverage doesn't regress |
| 6 | **Env & secrets** | `.env.example` updated here + `backend/` + `rag_ingestion/` if embedding changes + root; tuning params updated; new keys → Key Vault + Jenkins |
| 7 | **Docker** | `Dockerfile` updated (workspace root context includes `imdbapi/` + `chain/`); compose updated |
| 8 | **CI** | `Jenkinsfile` reviewed; LangSmith project name consistent with CI creds |
| 9 | **Diagrams** | `04-langgraph-pipeline.puml`, `05-langgraph-statemachine.puml`, `09-seq-langgraph-execution.puml`; `workspace.dsl` if C4 changed; commit to `docs/` first; **never `.mdj`** |
| 9a | **Docs** | `docs/` pages updated; SSE event shape change → verify `/docs` at `app/`; `README.md` + `CHANGELOG.md` updated |

### 10. Sibling submodules likely affected
| Submodule | Why |
|---|---|
| `backend/app/` | SSE event fields and API response shape |
| `backend/rag_ingestion/` | Embedding model must stay in sync with query-time embedding |
| `backend/imdbapi/` | IMDb data shape changes break `enrich_imdb` node |
| `frontend/` | SSE events consumed by `EventSource` — field renames are breaking |
| `infrastructure/` | New LLM or embedding provider = new secret, possibly new Azure service |
| `docs/` | Pipeline diagrams, architecture docs |

### 11. Submodule pointer bump
```bash
git add chain && git commit -m "chore(chain): bump to latest main"   # in backend/
git add backend && git commit -m "chore(backend): bump to latest main"  # in root
```

### 12. Pull request
- [ ] PR in `aharbii/movie-finder-chain` discloses the AI authoring tool + model
- [ ] PR in `aharbii/movie-finder-backend` (pointer bump)
- [ ] PR in `aharbii/movie-finder` (pointer bump)
- [ ] Any AI-assisted review comment or approval discloses the review tool + model

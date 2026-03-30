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

| Hook | Notes |
|---|---|
| `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-case-conflict`, `check-merge-conflict` | File health |
| `check-added-large-files`, `check-illegal-windows-names`, `detect-private-key` | Safety |
| `detect-secrets` | No API keys or tokens |
| `mypy` (strict, extra deps: `pydantic`, `pydantic-settings`) | Type checking |
| `ruff-check --fix`, `ruff-format` | Linting and formatting |

**Never `--no-verify`.** False-positive → `# pragma: allowlist secret` + `detect-secrets scan > .secrets.baseline`.

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

### 1. GitHub issues
- [ ] `aharbii/movie-finder` (parent)
- [ ] `aharbii/movie-finder-chain` linked child issue only if this repo changes
- [ ] Matching issue/PR templates and a recent example were inspected before filing or editing

### 2. Branch
- [ ] Branch in this repo + `chore/` in `backend/` and root `movie-finder`
- [ ] New standalone issues branch from `main` unless stacking is explicitly requested

### 3. ADR
- [ ] New LLM provider, new embedding model, new external dependency, or pipeline architecture change?
  → Write `docs/architecture/decisions/ADR-NNN-title.md`

### 4. Implementation and tests
- [ ] New node or provider follows the established patterns (see above)
- [ ] `MovieFinderState` fields accessed safely with `.get()` (issue #15 still open)
- [ ] `ruff` + `mypy --strict` pass
- [ ] Pre-commit hooks pass
- [ ] `pytest --asyncio-mode=auto` passes

### 5. Environment and secrets
- [ ] `.env.example` updated in: **this repo**, `backend/`, `backend/rag_ingestion/` (if embedding model changes), root `movie-finder`
- [ ] New API keys flagged for:
  - Azure Key Vault
  - Jenkins credentials store
  - `docs/devops-setup.md` credentials table updated
- [ ] Chain tuning params (`RAG_TOP_K`, `MAX_REFINEMENTS`, `CONFIDENCE_THRESHOLD`, etc.) updated if defaults change

### 6. Docker
- [ ] `Dockerfile` updated (built from workspace root context — includes `imdbapi/` and `chain/`)
- [ ] `docker-compose.yml` updated if needed
- [ ] Root `docker-compose.yml` if service interface changed

### 7. CI — Jenkins
- [ ] `.github/workflows/*.yml` and/or `Jenkinsfile` reviewed — new credentials, permissions, or env vars?
- [ ] LangSmith project name consistent between CI credentials and `.env.example`

### 8. Architecture diagrams (in `docs/` submodule)
- [ ] **PlantUML** — `04-langgraph-pipeline.puml` and/or `05-langgraph-statemachine.puml` for pipeline changes; `09-seq-langgraph-execution.puml` for sequence changes
  **Never generate `.mdj`** — user syncs to StarUML manually
- [ ] **Structurizr C4** — `workspace.dsl` if new external system or container added
- [ ] Commit to `aharbii/movie-finder-docs` first

### 9. Documentation
- [ ] `docs/` pages (pipeline description, node reference, LangSmith setup)
- [ ] `README.md` updated
- [ ] `CHANGELOG.md` under `[Unreleased]`
- [ ] OpenAPI: chain changes may affect `app/` SSE event shape — verify `/docs`
- [ ] Contributor docs updated when CI, required checks, or merge policy change

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

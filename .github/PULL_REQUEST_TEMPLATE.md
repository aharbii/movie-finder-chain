## What and why

<!-- What changed and why? Link the issue this addresses. -->

Closes #

## Type of change

- [ ] New node or edge in the LangGraph pipeline
- [ ] Prompt change (confirmation, refinement, Q&A)
- [ ] Model or embedding configuration change
- [ ] Bug fix
- [ ] Chore (tooling, dependencies, CI config)
- [ ] Documentation only

## How to test

1.
2.
3.

## CI status

The following Jenkins stages must be green before merge:

| Stage        | Command              | Trigger           |
| ------------ | -------------------- | ----------------- |
| Lint         | `make lint`          | All PRs           |
| Type-check   | `make typecheck`     | All PRs           |
| Test         | `make test-coverage` | All PRs           |
| Build Docker | `docker build`       | `main` / tag only |

## Checklist

### Code quality

- [ ] `make lint` passes — zero errors (`ruff`, line length 100)
- [ ] `make typecheck` passes — `mypy --strict` zero errors
- [ ] `make test` passes — zero failures
- [ ] New nodes and routing logic have unit tests with mocked LLM, Qdrant, and IMDb deps
- [ ] No real API calls in tests
- [ ] No `print()` statements left in production code

### State machine integrity

- [ ] `MovieFinderState` fields read with `.get()` and safe defaults (tracking issue #15)
- [ ] New behaviour implemented as a new node or edge, not branching inside an existing node
- [ ] Graph routing functions updated if a new phase or branch was added

### Documentation

- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `README.md` node table, configuration table, or architecture diagram updated if the pipeline changed

### Cross-repo impact _(if applicable)_

- [ ] SSE event shape change — coordinated with `backend/app/` and `frontend/`
- [ ] Embedding model change — coordinated with `rag_ingestion/` (query-time must match ingestion)
- [ ] New env vars added to `.env.example` here and in `backend/`

### Review

- [ ] PR title follows `type(scope): summary` (≤72 chars, imperative mood, lowercase)
- [ ] PR description links the issue and discloses the AI authoring tool + model used
- [ ] Any AI-assisted review comment or approval discloses the review tool + model

### Release _(for release PRs only)_

- [ ] `version` bumped in `pyproject.toml`
- [ ] `[Unreleased]` section moved to the new version in `CHANGELOG.md`
- [ ] Git tag created after merge: `git tag vX.Y.Z && git push origin --tags`
- [ ] Backend pointer-bump PR opened in `aharbii/movie-finder-backend`

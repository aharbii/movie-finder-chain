# Changelog — movie-finder-chain

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- `Makefile` with Docker-backed repo-local targets for `dev`, `lint`, `format`,
  `typecheck`, `test`, `test-coverage`, `pre-commit`, and the example scripts

### Changed

- `docker-compose.yml` now runs a single persistent `chain` dev container and
  no longer ships a local Qdrant service
- `Dockerfile`, `.vscode/*`, `README.md`, and `CONTRIBUTING.md` now follow the
  Docker-only local development contract
- Chain configuration now consumes the canonical read-only Qdrant env vars:
  `QDRANT_URL`, `QDRANT_API_KEY_RO`, and `QDRANT_COLLECTION_NAME`

---

## [0.1.0] — 2026-03-22

### Added

- Initial LangGraph pipeline with 8 nodes: `rag_search`, `imdb_enrichment`, `validation`,
  `presentation`, `confirmation`, `refinement`, `qa_agent`, `dead_end`
- `MovieFinderState` TypedDict as the shared state across all nodes
- `ChainConfig` (Pydantic Settings) for environment-variable-driven configuration
- `MovieSearchService` — OpenAI embedding + Qdrant vector search
- Structured LLM outputs via `ConfirmationClassification` and `RefinementPlan` Pydantic models
- Claude Haiku classifier node (`confirmation`) for user intent detection
- Claude Sonnet query-builder node (`refinement`) for iterative search improvement
- Claude Sonnet ReAct agent (`qa_agent`) with IMDb tools for Q&A phase
- Parallel IMDb enrichment with rate-limited semaphore
- `compile_graph()` factory with pluggable checkpointer (default: `MemorySaver`)
- Full test suite — all nodes mocked, zero real API calls
- Prompt templates embedded as package resources (`importlib.resources`)
- Docker multi-stage image (build context: workspace root)
- `docker-compose.yml` for local Qdrant development
- `Jenkinsfile` — lint → test → build/push pipeline
- `examples/basic_usage.py` — discovery, confirmation, Q&A demo
- `examples/streaming_example.py` — token-level streaming demo
- LangSmith tracing integration

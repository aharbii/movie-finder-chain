# Changelog — movie-finder-chain

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- `Makefile` with Docker-backed repo-local targets for `dev`, `lint`, `format`,
  `typecheck`, `test`, `test-coverage`, `pre-commit`, and the example scripts
- ADR 0008 provider factories for classifier LLMs, reasoning LLMs, query
  embeddings, and vector search providers
- Query-time vector store providers for Qdrant, ChromaDB, Pinecone, and pgvector
  using the shared `{prefix}_{sanitized_model}_{dimension}` target naming contract
- Optional dependency groups for local/cloud provider SDKs (`local`, `cloud`,
  `default-cloud`, `ollama-qdrant`, `all-providers`)
- `LOG_FORMAT` env var documented in `.env.example` — `text` (default) or `json`
  for Azure Monitor / structured log pipelines
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) mirroring Jenkins 1:1:
  Lint · Typecheck · Test · Coverage reporting via `EnricoMi/publish-unit-test-result-action@v2`,
  `irongut/CodeCoverageSummary@v1.3.0`, and `marocchino/sticky-pull-request-comment@v2`

### Changed

- Added `checkpoint_lifespan()` and `DATABASE_URL` support so LangGraph can use
  `AsyncPostgresSaver` instead of process-local memory in production
- Locked the RAG search service's lazy singleton behavior in tests so OpenAI
  and Qdrant clients remain process-scoped, including under concurrent node
  invocations
- IMDb enrichment now uses semaphore-bounded concurrent search, a 2-second
  fallback retry delay, and a 10-second hard node timeout that degrades back to
  RAG-only candidates instead of stalling the stream indefinitely
- Candidate list trimmed to `_MAX_ENRICH_CANDIDATES = 5` before enrichment;
  RAG_TOP_K remains at 8 to keep the semantic net wide
- `validation` node no longer requires `imdb_id` — degraded candidates with
  `rag_score`-derived confidence pass through the pipeline
- `presentation` node restores rich format with emoji labels, full metadata,
  and proper Markdown hard line breaks
- `confirmation` node generates a warm AI-written confirmation using Claude Haiku
- `utils/logger.py` rewritten as a thin library shim — `get_logger` returns
  `logging.getLogger(name)` with no side effects; `configure_logging()` added
  for standalone chain scripts and examples
- `MovieFinderState` now marks optional fields with `NotRequired[...]` instead
  of making the entire state schema optional
- The bundled `imdbapi` agent now uses the supported public
  `langchain.agents.create_agent` API
- `docker-compose.yml` now runs a single persistent `chain` dev container and
  no longer ships a local Qdrant service
- `Dockerfile`, `.vscode/*`, `README.md`, and `CONTRIBUTING.md` now follow the
  Docker-only local development contract
- Chain configuration now consumes the canonical read-only Qdrant env vars:
  `QDRANT_URL`, `QDRANT_API_KEY_RO`, and `VECTOR_COLLECTION_PREFIX`
- `confirmation`, `refinement`, and `qa_agent` nodes now consume cached LLM
  factories instead of constructing Anthropic clients directly
- `MovieSearchService` now consumes embedding and vector-store factories instead
  of constructing OpenAI and Qdrant clients directly
- `Jenkinsfile` — added `sourceDirectories` to `recordCoverage`; coverage.xml
  now emits workspace-relative paths via `relative_files = true` in pyproject.toml;
  removed Build App Image stage (image builds now orchestrated by the root pipeline)
- All test outputs (`junit.xml`, `coverage.xml`, `htmlcov/`) now written to a `reports/`
  subdirectory; `Makefile` paths updated accordingly; `.gitignore` updated to a single
  `reports/` entry
- Branch coverage is now enabled in the Docker-backed coverage target with 90%
  Jenkins and GitHub Actions quality thresholds
- Generic vector URL/API-key fallbacks now resolve inside the vector-store
  factory instead of sharing the same Pydantic settings alias across multiple
  provider-specific fields

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

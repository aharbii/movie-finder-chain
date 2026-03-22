# Changelog — movie-finder-chain

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

<!-- Add new changes here under the appropriate subsection. -->
<!-- Subsections: Added, Changed, Deprecated, Removed, Fixed, Security -->

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

# Movie Finder — Annotated Chain Diagram

> **How to read this diagram**
> - Solid arrows `-->` = deterministic edges (always taken)
> - Dashed arrows `-.->` = conditional edges (router decides at runtime)
> - Boxes with rounded corners = processing nodes
> - Parallelograms = decision/routing nodes
> - Pill shapes = start / end terminals
> - Node colour = phase it belongs to

---

## Full Graph

```mermaid
---
config:
  flowchart:
    curve: linear
---
flowchart TD
    START(["▶ START"]):::terminal
    END(["⏹ END"]):::terminal

    %% ── Entry router ──────────────────────────────────────────────
    route_phase{{"Route by Phase\n(reads state.phase)"}}:::router
    START -.-> route_phase

    %% ── DISCOVERY PIPELINE ────────────────────────────────────────
    subgraph DISCOVERY ["🔍 Discovery Pipeline  (phase = discovery)"]
        direction LR
        rag_search["**rag_search**\nEmbed query →\nQdrant vector search\n_(OpenAI embeddings)_"]:::discovery
        imdb_enrichment["**imdb_enrichment**\nParallel IMDb lookup\n+ metadata fetch\n_(async, max 3 concurrent)_"]:::discovery
        validation["**validation**\nFilter by confidence ≥ 0.3\nDeduplicate by IMDb ID\nCap at 5 results"]:::discovery
        presentation["**presentation**\nFormat as markdown\n⭐ rating · 🎬 director\n📖 plot summary"]:::discovery

        rag_search --> imdb_enrichment --> validation --> presentation
    end

    %% ── CONFIRMATION ──────────────────────────────────────────────
    subgraph CONFIRMATION ["✅ Confirmation  (phase = confirmation)"]
        direction TB
        confirmation["**confirmation**\nClassify user reply\n_(Claude Haiku)_"]:::confirm
        route_action{{"Route by next_action"}}:::router
        refinement["**refinement**\nExtract details →\nbuild richer query\n_(Claude Sonnet)_"]:::confirm

        confirmation --> route_action
    end

    %% ── Q&A ───────────────────────────────────────────────────────
    subgraph QA ["💬 Q&A  (phase = qa)"]
        qa_agent["**qa_agent**\nReAct agent\nanswers movie questions\n_(Claude Sonnet + IMDb tools)_"]:::qa
    end

    %% ── DEAD END ──────────────────────────────────────────────────
    dead_end["**dead_end**\nMax refinements hit\ngraceful exit message"]:::terminal

    %% ── Phase entry edges ─────────────────────────────────────────
    route_phase -. "phase = discovery" .-> rag_search
    route_phase -. "phase = confirmation" .-> confirmation
    route_phase -. "phase = qa" .-> qa_agent

    %% ── Confirmation routing ──────────────────────────────────────
    route_action -. "confirmed" .-> qa_agent
    route_action -. "refine\n(count < max)" .-> refinement
    route_action -. "exhausted\n(count = max)" .-> dead_end
    route_action -. "wait\n(unclear response)" .-> END

    %% ── Refinement loops back into discovery ──────────────────────
    refinement -. "retry search" .-> rag_search

    %% ── Terminal edges ────────────────────────────────────────────
    presentation --> END
    qa_agent --> END
    dead_end --> END

    %% ── Styles ────────────────────────────────────────────────────
    classDef terminal  fill:#1e1e2e,color:#cdd6f4,stroke:#cdd6f4,rx:20
    classDef router    fill:#fab387,color:#1e1e2e,stroke:#fe8019,shape:diamond
    classDef discovery fill:#a6e3a1,color:#1e1e2e,stroke:#40a02b
    classDef confirm   fill:#89b4fa,color:#1e1e2e,stroke:#1e66f5
    classDef qa        fill:#cba6f7,color:#1e1e2e,stroke:#8839ef
```

---

## Phase-by-phase walkthrough

### Phase 1 — Discovery `(initial state)`

```
User: "A sci-fi movie about AI taking over"
    │
    ▼
rag_search      → embeds the plot description with text-embedding-3-large
                  → queries Qdrant for the top-8 closest vectors
    │
    ▼
imdb_enrichment → fires up to 3 concurrent IMDb search requests per RAG hit
                  → fetches title / year / rating / director / genre / plot
    │
    ▼
validation      → drops results with confidence < 0.3
                  → deduplicates by IMDb ID (same film via different RAG hits)
                  → caps the final list at 5 candidates
    │
    ▼
presentation    → renders a numbered markdown list with ⭐ ratings, 🎬 directors,
                  📖 short plot summaries
                  → sets state.phase = "confirmation"
```

### Phase 2 — Confirmation `(next user message)`

```
User: "Yes! Number 2 looks right"
    │
    ▼
confirmation    → Claude Haiku classifies the reply into one of:
                    confirmed   → user picked a movie
                    not_found   → none matched → increment refinement_count
                    unclear     → ambiguous → ask for clarification (wait)
    │
    ├─ confirmed  → qa_agent (phase → "qa")
    │
    ├─ refine     → refinement
    │                  → Claude Sonnet extracts all conversation details
    │                  → builds a richer semantic search query
    │               → rag_search (loops back into discovery pipeline)
    │
    ├─ exhausted  → dead_end  (refinement_count = max_refinements)
    │
    └─ wait       → END  (bot asks for clarification)
```

### Phase 3 — Q&A `(all subsequent messages)`

```
User: "Who directed it? Is it on Netflix?"
    │
    ▼
qa_agent        → Claude Sonnet ReAct agent
                  → has access to IMDb tools (search, get_movie_details)
                  → loops tool-call / observe until the answer is complete
                  → returns a conversational reply
```

---

## State transitions summary

| From phase | Trigger | To phase |
|---|---|---|
| discovery | presentation completes | confirmation |
| confirmation | user confirms a movie | qa |
| confirmation | unclear response | confirmation (wait for clarification) |
| confirmation | no match + count < max | confirmation (after refinement loop) |
| confirmation | no match + count = max | — (dead end) |
| qa | every subsequent message | qa (infinite loop) |

---

## Component reference

| Node | Model / Service | Role |
|---|---|---|
| `rag_search` | OpenAI `text-embedding-3-large` + Qdrant | Semantic vector search |
| `imdb_enrichment` | IMDb API (async, rate-limited) | Enrich candidates with metadata |
| `validation` | Pure Python | Filter, deduplicate, rank |
| `presentation` | Pure Python | Format for the user |
| `confirmation` | Claude Haiku | Lightweight intent classification |
| `refinement` | Claude Sonnet | Query improvement from context |
| `qa_agent` | Claude Sonnet + IMDb tools | Open-ended movie Q&A |
| `dead_end` | Pure Python | Graceful exit after max retries |

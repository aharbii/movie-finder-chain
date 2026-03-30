"""
Interactive terminal chat for the Movie Finder chain.

Runs the full three-phase LangGraph pipeline:
  1. Discovery  — describe a movie plot, get candidates
  2. Confirmation — pick your movie (or say "none of these" to refine)
  3. Q&A         — ask anything about the confirmed movie

Usage (Docker-only local workflow):

    make dev
    make shell
    python chat.py
    python chat.py --env .env

Commands during chat:
    new / restart  — start a fresh conversation (clears session)
    quit / exit    — exit the program
"""

from __future__ import annotations

import asyncio
import sys
import uuid
import warnings
from pathlib import Path
from typing import cast

from langgraph.graph.graph import CompiledGraph

warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality", category=UserWarning)

from dotenv import load_dotenv  # noqa: E402

# Load chain/.env by default (relative to this file, works regardless of cwd)
_DEFAULT_ENV = Path(__file__).parent / ".env"


def _parse_env_arg() -> Path:
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--env", "-e") and i < len(sys.argv):
            return Path(sys.argv[i + 1])
        if arg.startswith("--env="):
            return Path(arg.split("=", 1)[1])
    return _DEFAULT_ENV


load_dotenv(_parse_env_arg())

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from chain.graph import compile_graph  # noqa: E402
from chain.state import MovieFinderState  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_ai_message(state: MovieFinderState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return "(no response)"


def _phase_badge(phase: str) -> str:
    return {
        "discovery": "🔍 discovery",
        "confirmation": "✅ confirmation",
        "qa": "💬 Q&A",
    }.get(phase, f"⚙️  {phase}")


# ---------------------------------------------------------------------------
# Main chat loop
# ---------------------------------------------------------------------------


async def chat_loop(graph: CompiledGraph, thread_id: str) -> str | None:
    """
    Run one conversation session. Returns "new" if user wants a fresh session,
    or None if user wants to quit entirely.
    """
    print(f"\n  🎬 New session started  [id: {thread_id[:8]}...]")
    print("  Describe a movie you're trying to remember and I'll find it for you.")
    print("  Commands: 'new' to restart | 'quit' to exit\n")

    config = {"configurable": {"thread_id": thread_id}}

    while True:
        # ---- Prompt ----
        try:
            user_input = input("  🧑 You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  👋 Goodbye!")
            return None

        if not user_input:
            continue

        low = user_input.lower()
        if low in ("quit", "exit", "q"):
            print("\n  👋 Goodbye!")
            return None
        if low in ("new", "restart", "reset"):
            print("\n  🔄 Starting a new conversation...\n")
            return "new"

        # ---- Invoke graph ----
        print("\n  ⏳ Thinking...")
        try:
            state = cast(
                MovieFinderState,
                await graph.ainvoke(
                    {"messages": [HumanMessage(content=user_input)]},
                    config=config,
                ),
            )
        except Exception as e:
            print(f"\n  ❌ Error: {e}\n")
            continue

        # ---- Print response ----
        phase = state.get("phase", "discovery")
        response = _last_ai_message(state)

        print(f"\n  🤖 Assistant  [{_phase_badge(phase)}]")
        print("  " + "─" * 56)
        # Indent the response for readability
        for line in response.splitlines():
            print(f"  {line}")
        print()

        # ---- Phase-specific hints ----
        if phase == "confirmation":
            candidates = state.get("enriched_movies", [])
            print(
                f'  💡 {len(candidates)} candidate(s) found. Pick a number or say "none of these".\n'
            )
        elif phase == "qa":
            title = state.get("confirmed_movie_title", "")
            imdb_id = state.get("confirmed_movie_id", "")
            if title:
                print(f"  🎯 Movie locked: {title}  (IMDb: {imdb_id})")
                print("  💡 Ask anything about it — cast, rating, plot details, ...\n")
        elif state.get("next_action") == "exhausted":
            print("  💡 Type 'new' to start over with a different description.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    print("\n  🎬 Movie Finder — Interactive Chat")
    print("  =====================================")
    print("  🤖 LLM     : Claude (Haiku for routing, Sonnet for reasoning)")
    print("  🗄️  Vector  : Qdrant Cloud  (text-embedding-3-large)")
    print("  📦 IMDb    : imdbapi.dev (live enrichment)")
    print("\n  ⏳ Compiling graph...")

    graph = compile_graph()
    print("  ✅ Ready!\n")
    print("  How it works:")
    print("    1️⃣  Describe a movie plot  → I'll search and show candidates")
    print("    2️⃣  Pick your movie        → confirm by number or say 'none'")
    print("    3️⃣  Ask anything about it  → cast, rating, box office, ...\n")
    print("  Commands: 'new' = fresh session | 'quit' = exit\n")

    signal: str | None = "new"
    while signal == "new":
        thread_id = str(uuid.uuid4())
        signal = await chat_loop(graph, thread_id)


if __name__ == "__main__":
    asyncio.run(main())

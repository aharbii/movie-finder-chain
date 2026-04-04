# AI Context — movie-finder-chain

Shared reference for AI agents working in this repo standalone.

## Available slash commands (Claude Code)

Open `backend/chain/` as your workspace, then type `/`:

| Command                     | Usage                             |
| --------------------------- | --------------------------------- |
| `/implement [issue-number]` | Implement an issue from this repo |
| `/review-pr [pr-number]`    | Review a PR in this repo          |

## Prompts (Codex CLI / Gemini CLI / Ollama)

- `ai-context/prompts/implement.md` — implementation workflow for this repo
- `ai-context/prompts/review-pr.md` — review workflow

Usage:

```bash
cat ai-context/prompts/implement.md
gh pr diff N --repo aharbii/movie-finder-chain > /tmp/pr.txt
cat /tmp/pr.txt | codex "$(cat ai-context/prompts/review-pr.md)"
```

## Issue hierarchy

Parent repos: `aharbii/movie-finder-backend` → `aharbii/movie-finder`.
Issues in this repo are child issues of `movie-finder-backend`.

## Agent Briefing

Every issue must have an `## Agent Briefing` section before implementation.
Template: `ai-context/issue-agent-briefing-template.md`

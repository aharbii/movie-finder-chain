# Implement Issue — movie-finder-chain

**Repo:** `aharbii/movie-finder-chain`
**Parent tracker:** `aharbii/movie-finder`
**Pre-commit:** `make pre-commit` (runs inside Docker — no host Python required)

Implement GitHub issue #$ARGUMENTS from `aharbii/movie-finder-chain`.

---

## Step 1 — Read the child issue

```bash
gh issue view $ARGUMENTS --repo aharbii/movie-finder-chain
```

Find the **Agent Briefing** section. If absent, ask the user to add it before proceeding.

---

## Step 2 — Read the parent issue for full context

```bash
gh issue view [PARENT_NUMBER] --repo aharbii/movie-finder
```

Implement only what the **child issue** requires.

---

## Step 3 — Read only the files listed in the Agent Briefing

---

## Step 4 — Create the branch

```bash
git checkout main && git pull
git checkout -b [type]/[kebab-case-title]
```

---

## Step 5 — Implement

Chain-specific patterns:

- LangGraph state machine: new behaviour = new node or edge, not branching inside existing nodes
- Node construction is centralised in `graph.py` — nodes are pure functions
- `MovieFinderState` TypedDict holds all pipeline state — do not bypass it
- Models: Claude Haiku for classify nodes, Claude Sonnet for reason/Q&A nodes
- Never re-create OpenAI/Qdrant clients inside nodes (see issue #7)

General backend standards:

- Type annotations required, `mypy --strict`
- Line length ≤ 100 chars
- No bare `except:`, no `print()`, async all the way
- Docstrings on all public classes/functions (Google style)

---

## Step 6 — Run quality checks

```bash
make pre-commit
```

Runs all hooks inside Docker — no host Python required.

---

## Step 7 — Commit

```bash
git add [only changed files — never git add -A]
git commit -m "$(cat <<'EOF'
type(scope): short summary

[why]

Closes #$ARGUMENTS
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Step 8 — Open PR

```bash
gh pr create \
  --repo aharbii/movie-finder-chain \
  --title "type(scope): short summary" \
  --body "$(cat <<'EOF'
[PR body]

Closes #$ARGUMENTS
Parent: [PARENT_ISSUE_URL]

---
> AI-assisted implementation: Claude Code (claude-sonnet-4-6)
EOF
)"
```

---

## Step 9 — Cross-cutting comments

Comment on related issues (from Agent Briefing), the child issue, and the parent issue.

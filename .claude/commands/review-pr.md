# Review PR — movie-finder-chain

**Repo:** `aharbii/movie-finder-chain`

Post findings as a comment only. Do not submit a GitHub review status.
The human decides whether to merge.

---

## Step 1 — Read PR, issue, and diff

```bash
gh pr view $ARGUMENTS --repo aharbii/movie-finder-chain
gh issue view [LINKED_ISSUE] --repo aharbii/movie-finder-chain
gh pr diff $ARGUMENTS --repo aharbii/movie-finder-chain
```

If a parent issue is referenced, read it. If partial iteration, evaluate only what it claims.

---

## Blocking findings

**Chain-specific patterns:**

- New behaviour added inside existing nodes instead of new node/edge
- Nodes are not pure functions (side effects outside LangGraph state)
- Node construction not centralised in `graph.py`
- OpenAI/Qdrant clients created inside node functions (should be injected)
- `MovieFinderState` bypassed for state changes

**Python standards:**

- Missing type annotations, bare `except:`, `print()`, `type: ignore` without comment
- Line > 100 chars, blocking I/O in async context, no tests for new logic

**PR hygiene:** AI disclosure missing, issue not linked, Conventional Commits not followed.

---

## Post as a comment

```bash
gh pr comment $ARGUMENTS --repo aharbii/movie-finder-chain \
  --body "[review comment body]"
```

```
## Review — [date]
Reviewed by: [tool and model]

### Verdict
PASS — no blocking findings. Human call to merge.
— or —
BLOCKING FINDINGS — must fix before merge.

### Blocking findings
[file:line] — [issue and fix]

### Non-blocking observations
[file:line] — [observation]

### Cross-cutting gaps
[any item not handled and not noted in PR body]
```

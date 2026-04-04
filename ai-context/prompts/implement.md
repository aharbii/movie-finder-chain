# Implement Prompt — movie-finder-chain

**Repo:** `aharbii/movie-finder-chain`
**Pre-commit:** uv run pre-commit run --all-files

Read ai-context/issue-agent-briefing-template.md for the Agent Briefing format.

---

## Usage

```bash
cat ai-context/prompts/implement.md   # read this prompt
```

Codex:

```bash
codex "$(cat ai-context/prompts/implement.md)"
```

---

## Prompt

You are implementing GitHub issue #[ISSUE_NUMBER] in `aharbii/movie-finder-chain`.

Step 1: Fetch the issue.
gh issue view [ISSUE_NUMBER] --repo aharbii/movie-finder-chain

Step 2: Find the Agent Briefing section. If absent, stop and say so.

Step 3: If this is a child issue, read the parent:
gh issue view [PARENT] --repo aharbii/movie-finder (or aharbii/movie-finder-backend for sub-submodule)

Step 4: Read ONLY the files listed in the Agent Briefing.

Step 5: Create branch.
git checkout main && git pull
git checkout -b [type]/[kebab-case-title]

Step 6: Implement the acceptance criteria. No more, no less.

Step 7: Apply cross-cutting updates listed in the Agent Briefing.

Step 8: Run quality checks.
uv run pre-commit run --all-files

Step 9: Commit.
git add [specific files only — never git add -A]
git commit -m "type(scope): summary

[why]

[Closes | Part of | Addresses] #[ISSUE_NUMBER]"

Step 10: Open PR.
cat .github/PULL_REQUEST_TEMPLATE.md 2>/dev/null
gh pr create --repo aharbii/movie-finder-chain --title "..." --body "..."
PR body must include: issue link, AI disclosure, and note any cross-cutting items deferred.

Step 11: Comment on related issues from Agent Briefing.
gh issue comment [N] --repo [REPO] --body "PR aharbii/movie-finder-chain#[PR]: [url]. [what this means for that issue]"

---
name: review
description: Review a pull request or branch without changing anything: correctness, scope, tests, the league contract, the 3.0 pitfalls. Use when asked to review, ideally in a fresh session.
---

# Review

Do not edit files. Report findings as `file:line` with a concrete fix, most important first.

1. `gh pr diff <n>` (or `git diff origin/main...<branch>`) and `ff check` on the branch. Report the check result as it
   is.
2. **Scope:** one topic? Anything unrelated mixed in? Duplicate of another open pull request?
3. **Tests:** a new feature or fix without a new or changed test, or a test that doesn't exercise the change.
4. **Bugs:** wrong logic, both maps not updated where both have the code, `shared/` or `league/` changes not built for
   every map, settings defaults changed without saying so.
5. **The bot's contract:** changes to rows the map writes (`league/`, `docs/result-contract.md`) without the document
   and its tests, or rows over 259 characters.
6. **3.0 pitfalls and tooltips** (AGENTS.md).
7. **Privacy:** passwords, tokens, personal paths or e-mail addresses in files or commits.

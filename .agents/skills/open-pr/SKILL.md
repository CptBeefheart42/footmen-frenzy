---
name: open-pr
description: Open a pull request for the current branch on GitHub, after checking the change is one topic, tested and not a duplicate. Always ask before pushing or opening. Use when a change is done and the person wants it reviewed.
---

# Open a pull request

1. **One topic.** `git log origin/main..HEAD --oneline` and `git diff --stat origin/main`: if the branch holds more than
   the one agreed change, stop and tell the person; split it before opening anything.
2. **Not a duplicate.** `gh pr list --state open --search "<keywords>"`; if one exists, say so and ask whether to add
   to it instead.
3. **Tested.** `ff check` passes. A new feature or fix has a new or changed test; otherwise the PR says why not.
4. **Ask before sending.** Show the person the title and body (template: `.github/pull_request_template.md`: what
   changes in the game, how it was tested, whether it was played, which AI tool helped) and the branch name. Push and
   open only after a clear yes: `git push -u origin <branch>` then `gh pr create --draft --fill-first` with that body.
   A practice or unfinished change stays a draft.
5. If `gh` is not logged in, ask the person to run `gh auth login` themselves; never ask for a token in the chat.
6. Tell the person what happens next: CI checks it, two maintainers review, they may ask for changes.

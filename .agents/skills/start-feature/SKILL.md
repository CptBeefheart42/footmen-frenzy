---
name: start-feature
description: Start a new change to the maps (a fix, a feature, a balance change): agree on one goal and how to tell it worked, check it isn't already being done, and make the work branch. Use whenever someone asks for a change and no branch for it exists yet.
---

# Start a change

1. **Agree on one goal.** Restate in one plain sentence what will change in the game, and ask the person how they will
   tell it worked when they play the test map (e.g. "Footman costs 120 gold in the shop"). If the request holds several
   changes, list them and ask which one comes first; the others become later changes.
2. **Check it isn't already being done.** `gh pr list --state open` (and `gh pr list --search "<keywords>"`). If an open
   pull request is about the same thing, tell the person and continue on that branch instead (`gh pr checkout <n>`).
3. **Start from the newest main.** `git fetch origin && git switch -c <type>/<short-topic> origin/main` with type
   `fix`, `feat`, `balance` or `docs` (e.g. `balance/footman-cost`).
4. **Find where it lives** before editing: the map script (`projects/<map>/src/war3map.j`), object data
   (`projects/<map>/objects/*.txt`), a setting (`project.json`), league code (`league/`) or shared code (`shared/`).
   If it exists in both maps, the change goes into both.
5. **Plan the test** together with the change (AGENTS.md: every feature and fix comes with a test). Then make the
   change, and continue with the `check` and `build-test-map` skills.

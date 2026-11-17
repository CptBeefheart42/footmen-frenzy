---
name: check
description: Run every check (ff check) and explain the result in plain words; fix what the change broke. Use before every commit and whenever someone asks whether a change works.
---

# Check a change

1. `ff check`. It runs: the shared-code check, the tool tests, a full build of both maps (with verify-map, the game's
   file lookup and pjass) and the simulation with the contract against the bot's parser.
2. All green: say so in one line and continue.
3. Something failed: find the first real failure in the output and explain it in plain words: what broke, why, and
   what you will change. Fix only what your change caused; if the failure is unrelated (it fails on `main` too), say so
   instead of "fixing" it.
4. Never weaken or delete a test to make it pass. If a test is wrong because the game rule changed on purpose, change
   the test in the same commit and say why in the commit message.

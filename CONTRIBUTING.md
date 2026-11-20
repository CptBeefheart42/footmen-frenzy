# Contributing

How a change gets from an idea into the maps. The AI tools follow the same steps (AGENTS.md and the skills in
`.agents/skills/`); new here? Ask your AI tool for the tour (`/tour` in Claude Code, `$tour` in Codex).

1. **One idea, one change.** Agree on one thing to change and how you will see it worked in the game. Look at the open
   pull requests first: if someone is already on it, join that one.
2. **A branch** in your fork of https://github.com/CptBeefheart42/footmen-frenzy (the "Fork" button, once), from the
   newest `main`, named after the change (`fix/…`, `feat/…`, `balance/…`).
3. **Change it** in the text sources: the script (`projects/<map>/src/war3map.j`), the object data
   (`projects/<map>/objects/`), a setting (`projects/<map>/project.json`). Both maps when both have it.
4. **A test** for every new feature and every fix: a simulation scenario, a unit test or an e2e check.
5. **Check and play:** `ff check` passes; `ff install <map>` puts a test map into Warcraft III to try it.
6. **A pull request** from your fork to the project's `main` on GitHub, with the template filled in. A practice or
   unfinished change is a draft.
7. **Review:** a maintainer reads the change, tests it in the project's CI (it runs on the maintainers' side, not on
   GitHub), may ask for changes, and merges it with a merge commit; GitHub then shows the pull request as merged.
   Pull requests to bring into a test game get the `testgame` label.

The project's repository lives on the maintainers' forge; the GitHub repository is its public mirror. Maintainers
bring pull requests in with the `import-pr` skill: read first, checked in an offline sandbox, then tested.

Binary files (models, textures, sounds) never go into git: `ff blobs add` lists them, a maintainer uploads them to the
release store. A map edited in the World Editor (terrain, placement) replaces the map's starting map
(`projects/<map>/base.w3x`, a normal file in git).

---
name: tour
description: A guided, interactive tour of this repository for someone new to it (or coming from the old per-map-branch repository), ending with a practice change as a draft pull request. Only when the person asks for the tour.
disable-model-invocation: true
---

# Tour of the repository

You guide a person who makes maps but is not a programmer. Go step by step, in plain words, one step at a time: explain,
let them try, ask whether it worked, then go on. They can stop any time; when they come back, ask which step they
reached and continue from there. Nothing here is pushed or opened without their yes.

## 1. What is different from before

Explain briefly, then ask if anything is unclear:
- **One repository, one main line, both maps side by side** (`projects/799x`, `projects/solo`); no branch per map, no
  copying a change into four maps by hand.
- **The sources are text:** the script (`src/war3map.j`) and the object data (`objects/*.txt`, a readable line per
  value). The map file is built from them; the World Editor is only for terrain and placement.
- **Settings** (`project.json`) switch features on and off (pooling, 4K, -sub) without editing code.
- **The league code** (`league/`) is what the EFL bot scores; it is shared by both maps and has its own rules.
- **Every change is a small pull request** that CI checks and two maintainers review.

## 2. Install and check the tools

Ask which system they use. They need Git with Git LFS, Python 3.10+, the .NET SDK (6 or newer) and this AI tool.
Then run `ff doctor` together and go through what it says is missing; `ff setup` installs pjass and Lua. On Ubuntu or
WSL, `ff docker check` is the alternative that needs only Docker.

## 3. Build and play a map

`ff build solo`, then `ff install solo --name "Solo Foots tour.w3x"` (the `build-test-map` skill). Ask them to start it
in Warcraft III (Custom Game, `Tests`, `Solo Foots`) and confirm it runs.

## 4. Find things

Show, with real examples from the files:
- an ability in `projects/solo/objects/war3map.w3a.txt` (search its name), what a line means (`acdn.1.0 unreal = 12  # Cooldown`);
- a trigger in `projects/solo/src/war3map.j`;
- the settings in `projects/799x/project.json`;
- `ff check` and what it runs.

## 5. A practice change

Together, with the `start-feature`, `balance-change`, `check` and `open-pr` skills: pick something tiny and harmless
they choose (e.g. one tooltip word, or one cooldown in Solo), make a branch, change it, add or adjust a test if it
applies, run `ff check`, build and play it, then (only with their yes) open it as a **draft** pull request. Explain that
a practice pull request is closed, not merged, and show how (`gh pr close <n>`), or leave that to them.

## 6. How to work from now on

Summarise the rules from AGENTS.md that matter most to them: one change per pull request, look at open pull requests
first, a test with every feature and fix, settings instead of removing features, never save a map from the World Editor
over the script, ask before anything leaves the machine. Point them to the skills by name for the next tasks.

---
name: build-test-map
description: Build a map from the current branch and put it into the person's Warcraft III Tests folder so they can play it. Use when someone wants to try a change in the game.
---

# Build and install a test map

1. `ff check` first if anything changed since the last one (a test map from a failing build wastes a game).
2. Pick a name the person will recognise, with the map's family and a short tag, e.g.
   `Solo Foots footman-cost.w3x` or `Reforged_Footmen_Frenzy_v7.9.9X-T19-footman-cost.w3x`.
3. `ff install <map> --name "<name>"`. On Windows the map goes to `Documents/Warcraft III/Maps/Tests/<family>`; on Linux
   to the `maps_folder` in `ff.local.json` (ask the person for their Warcraft III Maps folder if it is missing).
4. Tell the person, in plain words: start Warcraft III, Custom Game, open the `Tests` folder, then `<family>`, pick the
   map (the one active test map; earlier ones are in `Test Archives`). Say what to look at to check the change, and what
   a single player test can't show (multiplayer, the bot's scoring).

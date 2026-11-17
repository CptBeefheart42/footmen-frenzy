---
name: add-binary
description: Add or replace a binary file of a map (an imported model, texture, icon or sound) without putting it into git. Use when a change needs a new or changed imported file.
---

# Add a binary file

1. Name the file without extra dots (`HeroModel.mdx`, not `Hero.Model.v2.mdx`): Warcraft III 3.0 renders such files
   invisible. Icons follow the game's paths (`ReplaceableTextures/CommandButtons/BTN<Name>.blp`, a disabled copy under
   `CommandButtonsDisabled/DISBTN<Name>.blp`).
2. `ff blobs add <map> <path in the map> <file>`: puts the file into the local cache and lists it in
   `projects/<map>/binaries.json` by checksum. Also add it to the map's import list (`war3map.imp` in `src/`) when the
   map must know it as an import.
3. `ff build <map>` and `build-test-map` to see it in the game.
4. The file itself has to be uploaded to the release store before others can build: ask a maintainer (or, with access,
   ask the person before running `ff blobs upload`). The pull request says which files it adds.

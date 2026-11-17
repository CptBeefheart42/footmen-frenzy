---
name: world-editor-change
description: Bring a change made in the World Editor (terrain, doodads, placed units, regions, cameras, sounds, imports) into the repository. Use when someone edited a map in the World Editor.
---

# World Editor change

The World Editor is only for what can't be edited as text: terrain, doodads, placed units, regions, cameras, sounds,
imported files. Its trigger editor and object editor are not the source: the script and the object data in the
repository are (AGENTS.md, "Code first").

1. Ask the person which map file they edited and what they changed. If they changed triggers or object data in the
   editor, those changes have to be made again as text (`war3map.j`, `objects/*.txt`): the editor's copy is out of date.
2. The edited map becomes the map's new starting map: copy it over `projects/<map>/base.w3x` and put the edited map's
   file name into `project.json` (`start_map.name`). GitHub refuses files over 100 MB: stop and ask if it is larger.
3. `ff build <map>` and `ff check`: the build still takes the script and object data from the text sources, so only the
   editor's terrain/placement/import changes come in. Compare with the previous build that nothing else changed.
4. One pull request for the editor change alone; say in it what was changed in the editor.

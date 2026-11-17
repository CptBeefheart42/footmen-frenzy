---
name: share-code
description: Make one change for several Footmen Frenzy maps, or move code that is copied between map scripts into shared/. Use when a fix or feature should reach more than one map (799x, solo), when the same function exists in several war3map.j files, or when the repository check reports new copies between maps.
---

# Share code between maps

Code that several maps use is written once under `shared/<module>/`. Each map's `src/war3map.j` keeps a marker line
(`//! shared <module>/<file>.j`) where the code goes; the build puts the code back in.

## Change code that is already shared

1. `python tools/shared_code.py modules` shows which maps use each shared file.
2. Edit the file under `shared/<module>/`. Keep its line endings (CRLF) and its shape: `globals.j` holds only global
   declarations, `functions.j` only complete functions.
3. Run the checks (`ff check`).
4. Build every map that uses the module (`ff build <map>`, the `build-test-map` skill), and say which maps were tested in
   game.

## Move copied code into shared/

1. Find the functions: `python tools/shared_code.py duplicates` counts what is still copied. Pick a group of functions
   that belong together (one hero, one system) and that sit next to each other in every map's script.
2. Extract them, naming the module after what it does (lowercase, dashes):

   ```
   python tools/shared_code.py extract <module> --functions A,B,C [--globals X,Y] [--projects 799x,solo]
   ```

   `--projects` lists only the maps that really share the code. The tool refuses when the code differs between those
   maps, when the functions or globals are not next to each other, or when the module exists. It writes nothing unless
   every map's complete script stays byte for byte the same.
3. When the code differs between maps, decide which version is right first: make the maps identical in a separate
   commit (that is a gameplay change, tested in game), then extract.
4. Lower the baseline: `python tools/shared_code.py check --update-baseline`. Commit the module, the changed scripts and
   `shared/duplicates-baseline.json` together.
5. A pure extraction changes no map; `ff check` confirms every map still builds.

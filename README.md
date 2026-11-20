# Footmen Frenzy

The Warcraft III maps of Footmen Frenzy, the league addons the EFL bot reads, and the tools that build, check and
install the maps, on Windows and Linux.

| Map | Players | Folder | Starting map |
|---|---|---|---|
| 799X ("9v3") | 4 sides of 3, 12 observer slots | `projects/799x` | Reforged_Footmen_Frenzy_v7.9.9X-T19 |
| Solo Foots | 4, 12 observer slots | `projects/solo` | Solo Foots UPDATE38 |

[Standalone NorthStar maps and build instructions](projects/ports/northstar/README.md) cover 799X RC53, Solo RC24 and FFA v93.

## Get started

Install Git, Python 3.10 or newer and the .NET SDK (6 or newer), clone this repository, then:

```
ff doctor      # what is installed, what is missing
ff setup       # pjass and Lua into .tools/, turns on the pre-commit check
ff build solo  # build a map into build/solo/
ff install solo --name "Solo Foots test1.w3x"   # build, then put it into Warcraft III's Tests folder
ff check       # every check a change passes before it is committed
```

On Linux, `./ff`; on Windows, `ff` (`ff.cmd`). `ff install` uses `Documents/Warcraft III/Maps` on Windows; elsewhere,
set `maps_folder` in `ff.local.json` (a local settings file Git ignores).

## Layout

- `projects/<map>/src/`: every text file of the map: the script (`war3map.j`), the string table (`war3map.wts`), the
  text configuration files.
- `projects/<map>/hotkeys.csv`: every hotkey and command-card position the map's object data stores, and the clashes
  on a unit's command card. `ff check` fails when the object data no longer matches; `ff hotkeys <map>` rewrites the
  list after an intended change, so the change shows in review.
- `projects/<map>/binaries.json`: every binary file of the map (models, textures, sounds, object data, terrain) by
  name, SHA-256 and size. The files themselves are released, not kept here (see [Binary files](#binary-files)).
- `projects/<map>/base.w3x`: the starting map, the complete map as the World Editor last saved it (terrain, placed
  objects, imports). It and its twin are the only binary files in git.
- `projects/<map>/project.json`: the release the starting map came from, the map's family name, the functions the build turns
  off and the files it leaves out.
- `projects/<map>/addons/`: league addons and anchor hooks for this map only.
- `league/`: the league addons both maps get: the result file the bot scores (`ff_result`), the kill log, per-player
  stats and usage, the observer camera, bot vision, AFK handling. The rules: `docs/result-contract.md`.
- `shared/`: game code both maps use, written once; a map's script holds a marker line where it goes.
- `data/`: Warcraft III's `common.j` and `Blizzard.j`, the 2.0.4 ability defaults for the 3.0 level fill, map fixes,
  object-name tables.
- `tools/ff/`: the `ff` command. `tools/runner/` (.NET): packs maps, injects the addons, applies the fixes, verifies.
  `tools/BalanceTool/` (.NET): a map's numbers to and from a spreadsheet.
- `tests/`: tests of the tools and the shared code.

## How a map is built

`ff build <map>`:
1. downloads the binary files that differ from the starting map (`base.w3x`);
2. assembles the script: `src/war3map.j` with the shared code;
3. packs the starting map with the sources (unchanged files are carried over byte for byte);
4. adds the league addons, the WC3 3.0 level fill (unset ability levels 5+ read 0 on 3.0), the 3.0 file-name fix
   (imported files with extra dots render invisible), the map fixes and the map name;
5. verifies the map, looks every file up the way the game does, and checks the script with pjass.

The script is the source: the World Editor's trigger files in a map are out of date, so a map saved in the World
Editor must not replace `src/war3map.j`.

## Shared code

Code both maps use lives once under `shared/<module>/`. A map's `src/war3map.j` refers to it with a marker line such
as `//! shared ff-config/functions.j`, and the build puts the code in its place.

```
python tools/shared_code.py modules       # which maps use each shared file
python tools/shared_code.py duplicates    # functions still copied between the maps
python tools/shared_code.py extract <module> --functions A,B [--globals X]
```

`extract` only moves code that is byte-identical in the maps and only writes when both maps' complete scripts stay
byte for byte the same. The check fails when more functions are copied between the maps than
`shared/duplicates-baseline.json` records.

## Binary files

The repository holds text only; a test fails when a binary file is committed. A build downloads the binary files it
needs into `.tools/blobs/` (named by SHA-256, every checksum checked) from the release store set in `ff.local.json`:

```json
{ "blob_url": "https://<host>/<owner>/<repo>/releases/download/blobs/{sha256}" }
```

A private store's read token goes into the environment variable `FF_BLOB_TOKEN` (secrets live only in the environment,
never in a file of the repository; `ff.local.json` holds the other local settings and is ignored by git).

Without a release store, the files of the imported maps come from the Git LFS storage of `origin`.

No license is claimed over Warcraft III or the third-party models, textures, sounds and scripts inside the maps;
their owners' rights and permissions still apply.

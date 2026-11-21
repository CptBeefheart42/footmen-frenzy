# Wiki bundles

The league website's Wiki tab shows what a player meets in a game of each map: heroes and their spells, units and
summons, buildings, items, upgrades and the Colossal waves, with names, stats per level, command keys, links and
icons. This folder makes its data; the website (efl-bot) shows it.

```
ff wiki 799x       # build the map, then write build/wiki/799x.json (+ .json.gz) and build/wiki/index.json
ff wiki all        # every map
```

`ff release <version>` writes the same bundles for the released maps and zips them into
`build/release/Footmen_Frenzy_<version>-wiki.zip` (`index.json`, `<map>.json`, `<map>.json.gz`), which the release
publishes next to the maps. The website's deploy installs that zip from the release the bot fleet hosts.

## What a bundle is made from

- **The finished map** (`build/<map>/`): its object data after the WC3 3.0 level fill and the map fixes (exported as
  text by the runner, `objects export`), its script with the league addons, and its other files as packed (string
  table, settings, placements, imported icons). So a bundle shows the values the game loads.
- **The game's data** (the stock pack): a map stores only what it changes, so base values, names, field labels and
  most icons come from Warcraft III 2.0.4: its object tables, editor metadata and command-button icons. The pack holds
  Blizzard's files, so it lives only in the maintainers' private release store; `data/wiki_stock.json` names it by
  checksum. Without access to the store (`blob_url` in `ff.local.json`), `ff wiki` stops and `ff check` skips the wiki.
- Icons need Pillow (`apt install python3-pil` or `pip install pillow`); the check image has it.

A new stock pack, from a local 2.0.4 install (maintainers; the install tools/slk/extract_ability_defaults.py reads):

```
ff wiki stock-pack ~/wc3-stage    # writes the pack into the blob cache and lists it in data/wiki_stock.json
ff blobs upload                   # publishes it to the release store
```

## How the objects are found

1. `catalog.py` indexes every object the map defines or names (script, settings, placements, game constants) and
   follows the references between objects (ability lists, trained units, parents ...). Values resolve the way the
   game resolves them: each ancestor's game row first, then the map's fields, per level and data pointer.
2. `tables.py` reads the hero and troop tables the script fills at start (`set udg_hero_type[i] = ...`); which
   functions and arrays make up a table is listed in `reports.json`, with the labels of the stats shown per group.
3. `reachability.py` builds the gameplay graph: roots (the hero selection roster, troop bases, placed objects, Colossal
   waves, objects the script hands out) and edges (abilities, summons, trained units, drops, upgrades ...), each with
   its sources. Only triggers that can run count. A walk from the roots gives the objects a player can meet.
4. `bundle.py` keeps what the website shows: the reached objects (and the ones they are based on or refer to), their
   stats, links, tooltips and icons, without the script and the map's other files.

`script.py`, `map_info.py` (war3map.w3i) and `placements.py` (war3mapUnits.doo, war3map.doo) read the map's files;
the binary layouts follow War3Net's readers
([widgets](https://github.com/Drake53/War3Net/tree/master/src/War3Net.Build.Core/Serialization/Binary/Widget),
[map info](https://github.com/Drake53/War3Net/blob/master/src/War3Net.Build.Core/Serialization/Binary/Info/MapInfo.cs)).

Tests: `tests/test_wiki.py` (part of `ff check`). The export test of the real 9v3 map runs where the stock pack is in
the blob cache.

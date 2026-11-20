# Footmen Frenzy balance wiki

The wiki opens in a browser and works offline. Select a hero to follow their abilities, summoned units, items and upgrades. Each generated page identifies its input map and SHA256.

## Generate a guide

Use Python 3.10+ and a matching StormLib shared library. On Windows set `STORMLIB_DLL` to the full path of the 64-bit StormLib DLL when using 64-bit Python. On Linux install the system StormLib shared library or set the same variable to its path. Install Pillow to decode imported portraits. An extracted map directory can be read with Python alone.

Run these commands from the repository root to generate both starting-map guides, then double-click **Open Balance Wiki.html**. On Windows, `.\Export-Wiki.ps1` runs both commands.

~~~sh
python tools/export_wiki.py 799x
python tools/export_wiki.py solo
~~~

The default reads the checked-in `projects/<map>/base.w3x`. To see current gameplay, run `ff build solo` and then `python tools/export_wiki.py solo --source built`. This reads the assembled `build/solo/solo-dev.w3x`, including the project's object and script changes. Use `--map` for any other filename. The command prints the path to the generated HTML.

~~~sh
python tools/export_wiki.py 799x --map "799x test.w3x"
python tools/export_wiki.py ffa --map "FFA Foots.w3x"
python tools/export_wiki.py solo --directory "extracted-map" --format json
python tools/export_wiki.py 799x --report abilities --id AHwe --fields Hwe1 Hwe2 --format fragment
python tools/export_wiki.py 799x --report spawns --id h060 --format json
~~~

HTML, JSON and filtered reports are written under `build/wiki-exports`. Use `--output` to select another filename. An extracted directory should contain the map's binary object files and its assembled script. The project's text object sources are converted during `ff build`.

## Follow a balance value

The player guide opens to the traced hero directory. Pick a portrait to follow a spell, summon, buff, item or production chain. The directory combines matching display names and keeps distinct variants selectable. Spell pages group identical targets across levels. Summoned-unit pages include their own abilities and any recognized summon-event stat tables. The Colossal waves section shows each boss's base stats and the scaling rules recognized in the selected map.

The hero directory opens the roster hero directly. Morph forms are small links on the hero page. No-Transmute copies and debug hire buttons are available in Advanced. Ability cards show the command-card position and learn key when available. Click the browsing path above the page to return to a hero, a spell, or the filtered results. The browser's Back and Forward buttons restore the same path.

**Advanced** opens the technical record for the same selection. Use the pencil to stage an edit. **Reachability and asset review** distinguishes traced objects, supporting parent or requirement records, other map records, unresolved IDs, dynamic creation sites and imports without a traced reference. An import can also be used by a dynamically constructed path or by engine convention. These inventories support investigation before changing map assets.

Portraits come from map imports and the local Warcraft installation. The game-data importer remembers the CASC location under ignored `build/`. Install Pillow in the exporter’s Python environment to decode Warcraft artwork. Objects without assigned or decodable art use a linked owner’s artwork when available. Advanced review lists those records.

* Open **Heroes**, choose a hero and follow a spell under **Abilities and dependencies**. A summoned-unit field links to that unit's stats and abilities. **Referenced by** traces links in the other direction. Each object retains its case-sensitive ID, field ID, level, data pointer, parent and payload name.
* Compare **Object stats** with the **Troop spawn settings** and **Hero starting stats and growth** tables. The first reads object data and available Warcraft defaults. The other two read JASS initialization assignments. A value's source identifies the input that supplied it. A dash in a summary indicates an absent assignment or field.
* **Trigger functions** supports full-text searches for an array, native, formula or rawcode. Function pages show line numbers, callers, callbacks and referenced objects. **Scripted unit creation sites** includes variable and expression arguments. Spell pages show possible call paths from recognized spell-ID checks to literal unit creation, including separately registered trigger actions. Runtime branches, indirect IDs, timers and mode-specific changes still require reading the linked code or observing a game.
* **Gameplay & profile files** includes map rules, per-player tech/upgrade restrictions, global random tables, individual unit and doodad placements, inventories, drop chances, miscellaneous constants, JASS globals, WTS strings and unresolved script IDs. **Models, projectiles & visual effects** lists model paths with their field or script references. The index includes map-defined objects even when their playability or availability depends on mode or script.
* **Scripted item combinations** links direct item-removal and item-grant statements to their functions. Branches and helper-selected ingredients are visible in the source. An item's building relationships also expose shop stock and requirements.

## Load stock Warcraft data

Map archives store many balance fields as differences from Warcraft defaults. On Windows, pass your Warcraft III installation and a 64-bit CascLib DLL to cache stock values and portraits.

~~~powershell
python tools/wiki/import_game_data.py --game "C:\Program Files (x86)\Warcraft III" --dll "C:\WarcraftTools\CascLib.dll"
.\Export-Wiki.ps1
~~~

The importer reads stock SLKs, editor metadata, English names, object profiles and the custom balance layer into ignored `build/wiki-game-data.zip`. The wiki records the game build and source table checksums. Refresh the cache after updating Warcraft. With no cache, the wiki reports that stock data is absent and still exposes the map's field values and trigger source. Stock data from the installed game represents that game version, including when the selected map is an older release.

## Prepare balance changes

Use the pencil next to a name to jump to its editable map fields. In Advanced, each stored object field, shared WTS string and map source line has its own pencil. This includes ability lists and level-specific summoned-unit IDs. Changes to a shared string apply to every reference to that WTS entry. Open **Edit list** to review, remove or download changes. Proposals are saved locally in browsers that permit local storage for file pages. Downloading the change list preserves a portable copy.

~~~powershell
python tools/stage_wiki_edits.py 799x balance-changes.json
~~~

Staging checks the map family and source fingerprint, validates original values, then writes changed payload copies and the proposal under `build/wiki-edits`. Object edits identify the record by rawcode, field, level, pointer, kind and byte offset. Source edits preserve line endings. For an exact archive, use `python tools/stage_wiki_edits.py 799x balance-changes.json --map "my-build.w3x"`.

Review staged payloads against the same baseline before integrating them into a map project. Apply reviewed changes to the corresponding text sources in projects/<map>/objects or src, then use the normal ff build workflow. Game-owned defaults, placement records and computed results are available for inspection. Changing one of those involves adding a map override, editing the placement in the editor, or changing its underlying formula.

## Extend and verify

Add object or JASS summary reports to `tools/wiki/reports.json`. Object reports specify the file extension, display name field and field labels. JASS reports specify the functions, identity array and value arrays. Summary extraction recognizes unconditional assignments at fixed indices and same-function copies from a previously initialized slot. Unsupported expressions produce a diagnostic. The full wiki retains the function source independently of those summaries.

Run `python -m unittest tests.test_balance_wiki` for regression checks. The widget and map-info readers validate the consumed byte length for the active families' layouts. Binary format references are the [War3Net widget readers](https://github.com/Drake53/War3Net/tree/master/src/War3Net.Build.Core/Serialization/Binary/Widget) and [map info reader](https://github.com/Drake53/War3Net/blob/master/src/War3Net.Build.Core/Serialization/Binary/Info/MapInfo.cs).

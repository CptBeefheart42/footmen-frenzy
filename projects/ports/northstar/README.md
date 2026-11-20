# Standalone NorthStar maps

| Family | Starting map | Editable project |
|---|---|---|
| 799X | RC54 Hero Rotation | [799X](799x/) |
| Solo Foots | RC25 Hero Rotation | [Solo](solo/) |
| FFA Foots | v94 Hero Rotation | [FFA](ffa/) |

With Python 3.10+, the .NET 6 SDK and pjass installed as described in the repository README, run a build from the repository root.

```sh
python projects/ports/northstar/port.py 799x
python projects/ports/northstar/port.py solo
python projects/ports/northstar/port.py ffa
```

The first build downloads that project's complete starting map from the pinned NorthStar revision and checks its SHA-256 against `project.json`. To use an existing copy, add `--base "path/to/map.w3x"`. The output is under `build/northstar/<family>/`.

Edit gameplay scripts and strings in `src/` and units, abilities, items and other object fields in `objects/`. Each project's `binaries.json` records the checksum and size of its binary assets inside the starting map. The port command compiles the object text, checks JASS, packs the map, verifies its object data and checks that Warcraft can find every named file. The original lobby header travels with the map.

These builds use the standalone maps' gameplay. The league builds continue to use `ff build 799x` and `ff build solo`. League scoring and observer integration for a standalone port would require a separate integration and gameplay test.

[NorthStar source and complete starting maps](https://github.com/NorthStarEnergy/Footmen-Frenzy/tree/9a17b6eefc929f85d4e3f594f2577c2f89633181)

Info opens match stats for everyone. Hotkeys opens the spell and item key editor. Twisted Fate can be chosen with `-tf` in All Pick and can be dealt at the start of All Random.

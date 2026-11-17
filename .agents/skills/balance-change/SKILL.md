---
name: balance-change
description: Change a number of a unit, ability, item or upgrade (cost, damage, cooldown, hit points ...) in the map's object data text, keep tooltips right, test it. Use for any balance or stat change.
---

# Balance change

1. **Find the object and field.** Object data is in `projects/<map>/objects/`: units `war3map.w3u.txt`, items
   `war3map.w3t.txt`, abilities `war3map.w3a.txt`, upgrades `war3map.w3q.txt`, buffs `war3map.w3h.txt`. Each block
   starts with `[CODE : BASE]` (a custom object based on BASE) or `[CODE]`; each line is
   `field[.level.pointer] type = value   # name`. Field names: `data/object_fields.csv`. Search the object's name
   (`unam`/`anam`/`inam` lines) to find its code.
2. **Some numbers live in the script**, not the object data: spawn stats, XP and gold rates, timers and costs that
   triggers set at runtime (`war3map.j`: `BlzSetUnit*`, `SetUnit*`, `udg_*` values). Check the script for the object's
   code before editing, or the edit may do nothing in game.
3. **Edit the value** (keep the type and the `# name` comment). Change it in both maps when both have the object.
4. **Tooltips** that show the number must show the new one (object data `*ub1`/`aub1` tooltip fields, or the script's
   `BlzSetAbility*Tooltip`): coral red for damage, green for healing (AGENTS.md).
5. **Levels 5 and above** need their own values for abilities with more than 4 levels.
6. **Test:** `ff check`, then `build-test-map`; for a value the simulation can see, add or adjust a scenario.

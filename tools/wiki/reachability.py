"""Which objects a player can actually meet in a game, and how: a graph of gameplay links with the evidence for each.

Roots are objects the game starts from (heroes in the selection roster, placed objects, troop bases, Colossal waves,
objects the script hands out). Edges lead from an object to what it gives access to (abilities, trained units,
summons, drops, upgrades ...), each with its label, levels and sources. A walk from the roots along the edges gives
`via` (object -> the object it was reached from); reference-only edges (skins, requirements) mark `support` objects,
which are shown but lead nowhere.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque

TYPES = {'abilCode': 'abilities', 'abilityList': 'abilities', 'heroAbilityList': 'abilities',
         'abilitySkinList': 'abilities', 'unitCode': 'units', 'unitList': 'units', 'unitSkinList': 'units',
         'itemList': 'items', 'buffList': 'effects', 'effectList': 'effects',
         'upgradeList': 'upgrades', 'upgradeCode': 'upgrades'}
LABELS = {'uhab': 'Hero abilities', 'uabi': 'Abilities', 'iabi': 'Item abilities', 'abuf': 'Buffs',
          'aeff': 'Effects', 'useu': 'Units sold', 'usei': 'Items sold', 'utra': 'Units trained',
          'uupt': 'Upgrades to', 'upgr': 'Upgrades used', 'ubui': 'Structures built'}
REFERENCE_TYPES = {'techList', 'unitSkinList', 'abilitySkinList'}
REFERENCE_FIELDS = {'udep', 'urva', 'icid'}
STOCK_NATIVES = (('CreateItem', 'items'), ('UnitAddItemByIdSwapped', 'items'), ('AddItemToStockBJ', 'items'),
                 ('AddUnitToStockBJ', 'units'), ('ReplaceUnitBJ', 'units'), ('AddItemToStock', 'items'),
                 ('AddUnitToStock', 'units'), ('UnitAddItemById', 'items'))
SECOND_ARGUMENT = {'ReplaceUnitBJ', 'AddItemToStock', 'AddUnitToStock', 'UnitAddItemById'}
ROSTER_ARRAYS = {'udg_hero_type', 'udg_spawn_unit', 'udg_colossal_unit_type'}
# The World Editor writes an always-false first guard for a disabled GUI condition.
IMPOSSIBLE = re.compile(r'[^\n]+\n\s*(?:return false\s*\n\s*endfunction|if\s*\(\s*not\s*\(\s*(?:false\s*==\s*true|'
                        r'true\s*==\s*false)\s*\)\s*\)\s*then\s*return false\b)')
TRIGGER_USE = (r'\b(?:EnableTrigger|DisableTrigger|IsTriggerEnabled|DestroyTrigger|ConditionalTriggerExecute|'
               r'TriggerExecute(?:BJ)?|TriggerEvaluate|TriggerRegister\w*)\(\s*')


def reachable(functions: dict, blocked: dict) -> set[str]:
    """The functions `main` and `config` can reach, without the calls `blocked` lists (function -> callees)."""
    seen = set()
    queue = deque(['main', 'config'])
    while queue:
        name = queue.popleft()
        if name in functions and name not in seen:
            seen.add(name)
            queue.extend(n for n in functions[name]['calls'] if n not in blocked.get(name, ()))
    return seen


def trigger_uses(functions: dict, possible: set[str]) -> dict[str, list]:
    """Trigger handle (gg_trg_...) -> every (function, line) of the reachable script that names it."""
    uses = defaultdict(list)
    for name in possible:
        for line in functions[name]['body'].splitlines():
            line = line.partition('//')[0]
            for handle in set(re.findall(r'\bgg_trg_\w+', line)):
                uses[handle].append((name, line))
    return uses


def never_runs(handle: str, name: str, body: str, functions: dict, uses: list) -> bool:
    """Whether a trigger created in `name` can never run its actions: its condition is always false, or it is
    disabled and never enabled again, and no other code runs it or hands it on."""
    conditions = re.findall(r'TriggerAddCondition\(\s*' + handle + r'\s*,\s*Condition\(\s*function\s+(\w+)', body)
    impossible = any(IMPOSSIBLE.match(functions.get(n, {}).get('body', '')) for n in conditions)
    known = re.compile(TRIGGER_USE + handle + r'\b')
    escaped = any(not known.search(line) for n, line in uses if n != name)
    references = '\n'.join(line for _, line in uses)
    forced = re.search(r'\bTriggerExecute(?:BJ)?\(\s*' + handle + r'\b', references)
    conditional = re.search(r'\bConditionalTriggerExecute\(\s*' + handle + r'\b', references)
    enabled = re.search(r'\bEnableTrigger\(\s*' + handle + r'\b', references)
    disabled = re.search(r'\bDisableTrigger\(\s*' + handle + r'\b', body)
    return not (escaped or forced) and bool(impossible or (disabled and not enabled and not conditional))


def callable_functions(functions: dict) -> set[str]:
    """The script functions that can run in a game: reachable from main/config, minus the actions of triggers
    that never run."""
    possible = reachable(functions, {})
    uses = trigger_uses(functions, possible)
    blocked = defaultdict(set)
    for name in possible:
        body = functions[name]['body']
        for handle in re.findall(r'set\s+(gg_trg_\w+)\s*=\s*CreateTrigger\(\)', body):
            if not never_runs(handle, name, body, functions, uses[handle]):
                continue
            register = r'TriggerAddAction\(\s*' + handle + r'\s*,\s*function\s+(\w+)\s*\)'
            other_code = re.sub(register, '', body)
            blocked[name].update(a for a in re.findall(register, body) if not re.search(r'\b' + a + r'\b', other_code))
    return reachable(functions, blocked)


def called_from(functions: dict, start: str) -> set[str]:
    """`start` and every function it calls, directly or not."""
    todo, seen = [start], set()
    while todo:
        name = todo.pop()
        if name in functions and name not in seen:
            seen.add(name)
            todo.extend(functions[name]['calls'])
    return seen


def spell_actions(funcs: dict, live: set[str]) -> dict[str, set[str]]:
    """Function -> the spells (ability ids) it runs for: spell checks followed into their trigger's actions,
    helpers and callbacks."""
    actions = defaultdict(set)
    for name in live:
        code = funcs[name]['body']
        conditions = re.findall(r'TriggerAddCondition\(\s*(\w+)\s*,\s*(?:Condition|Filter)\(\s*function\s+(\w+)', code)
        handlers = re.findall(r'TriggerAddAction\(\s*(\w+)\s*,\s*function\s+(\w+)', code)
        for trigger, condition in conditions:
            for n in called_from(funcs, condition):
                if funcs[n]['spells']:
                    actions[n].update(h for t, h in handlers if t == trigger)
    owners = defaultdict(set)
    for name in sorted(live):
        if not funcs[name]['spells']:
            continue
        queue, seen = deque([name, *actions[name]]), set()
        while queue:
            n = queue.popleft()
            if n in live and n not in seen:
                seen.add(n)
                owners[n].update(funcs[name]['spells'])
                queue.extend(funcs[n]['calls'])
    return owners


def colossal_configs(body: str) -> dict[int, dict]:
    """Colossal unit slot -> its settings (`set udg_colossal_unit_<field>[slot] = ...`)."""
    configs = defaultdict(dict)
    for field, index, rhs in re.findall(r"set udg_colossal_unit_(\w+)\[(\d+)\]\s*=\s*('....'|[-\d.]+)", body):
        configs[int(index)][field] = rhs.strip("'") if rhs.startswith("'") else float(rhs)
    return configs


def colossal_parity(functions: dict, spawn_name: str, dispatcher: str, slots: list) -> tuple[dict, list]:
    """Which boss slot spawns on odd and which on even waves, and the slots the spawner uses."""
    parity = {}
    if spawn_name == 'F8_SpawnColo':
        loop = re.search(r'set entry\s*=\s*(\d+)[\s\S]*?exitwhen entry\s*>\s*(\d+)', dispatcher)
        bosses = re.search(r'local integer big\s*=\s*(\d+)[\s\S]*?if ModuloInteger\(udg_colossal_wave,\s*2\)\s*==\s*0 '
                           r'then\s*set big\s*=\s*(\d+)', dispatcher)
        if bosses and 'F8_SpawnColo(big,' in dispatcher:
            parity = {int(bosses[1]): 'odd', int(bosses[2]): 'even'}
            if loop:
                slots = [(s, i) for s, i in slots if s in parity or int(loop[1]) <= s <= int(loop[2])]
        return parity, slots
    cond = 'Trig_colossal_spawn_Func005C'
    check = functions.get(cond, {}).get('body', '')
    if re.search(r'ModuloReal\(I2R\(udg_colossal_wave\),\s*2(?:\.0+)?\)\s*==\s*0', check):
        branch = re.search(cond + r'\(\).*?then\s+(.*?)\belse\b(.*?)\bendif\b', dispatcher, re.S)
        if branch:
            for side, code in zip(('even', 'odd'), branch.groups()):
                selected = re.search(r'set udg_X_colo\s*=\s*(\d+)', code)
                if selected:
                    parity[int(selected[1])] = side
    return parity, slots


class Colossal:
    """The Colossal waves of a map: which units come, the bosses' growth, timing, parity and level curve."""

    INIT = 'Trig_colossal_stats_Actions'
    SPAWN = 'Trig_colossal_spawn_Actions'
    VARIABLES = 'Trig_colossal_variables_Actions'

    def __init__(self, functions: dict, live: set[str]):
        self.functions = functions
        self.live = live
        self.settings = functions.get(self.VARIABLES, {}).get('body', '')

    def setting(self, key: str) -> float | None:
        """A number the variables trigger sets (`set udg_<key> = <n>`)."""
        match = re.search(r'set udg_' + key + r'\s*=\s*(\d+(?:\.\d+)?)', self.settings)
        return float(match[1]) if match else None

    def waves(self, root) -> dict:
        """Unit key -> its wave record; `root` is called for every wave unit."""
        if self.INIT not in self.live or self.SPAWN not in self.live:
            return {}
        configs = colossal_configs(self.functions[self.INIT]['body'])
        slots = [(slot, int(r['id'])) for slot, r in configs.items() if 'id' in r]
        spawn_name = 'F8_SpawnColo' if 'F8_SpawnColo' in self.live else self.SPAWN
        spawn = self.functions[spawn_name]['body']
        parity, slots = colossal_parity(self.functions, spawn_name, self.functions[self.SPAWN]['body'], slots)
        result = {}
        for slot, index in slots:
            row = configs.get(index, {})
            if 'type' not in row:
                continue
            key = 'units/' + row['type']
            root(key, 'Colossal wave roster', self.INIT)
            rec = result.setdefault(key, {'entries': [], 'rules': [self.INIT, spawn_name, self.VARIABLES]})
            rec['entries'].append({'slot': slot, 'base': row})
            if slot <= 2:
                self.boss(rec, slot, spawn_name, spawn, parity)
        return result

    def boss(self, rec: dict, slot: int, spawn_name: str, spawn: str, parity: dict) -> None:
        """Adds a boss's growth, timing, last wave, parity and level curve to its wave record."""
        scaled = [field for field in ('hp', 'dmg', 'bounty') if re.search(
            r'set udg_colossal_unit_' + field + r'_actual[^\n]*=[^\n]*_base[^\n]*\+[^\n]*_base[^\n]*\*[^\n]*'
            r'udg_colossal_wave[^\n]*\*[^\n]*udg_colossal_difficulty', spawn)]
        level = re.search(r'return\s+(\d+)\s*\+\s*IMinBJ\((\d+),\s*\(wave-1\)/(\d+)\)',
                          self.functions.get('SyncColoLevel', {}).get('body', ''))
        max_wave = re.search(r'set udg_colossal_max_wave\s*=\s*(\d+)',
                             self.functions.get('Trig_init_Actions', {}).get('body', ''))
        rec.update(boss=True, growth=self.setting('colossal_difficulty'), scaled=scaled,
                   first=self.setting('t_colossal_initial'), interval=self.setting('t_colossal_reoccuring'))
        if max_wave and 'Trig_init_Actions' in self.live:
            rec['max_wave'] = int(max_wave[1])
            rec['rules'].append('Trig_init_Actions')
        if slot in parity:
            rec['parity'] = parity[slot]
            if spawn_name != self.SPAWN:
                rec['rules'].append(self.SPAWN)
        if level and 'SyncColoLevel(' in spawn:
            rec['level_curve'] = list(map(int, level.groups()))
            rec['rules'].append('SyncColoLevel')


def summon_types(funcs: dict, conditions: list, trigger: str) -> set[str]:
    """The unit types a summon trigger's conditions test the summoned unit for."""
    units = set()
    for handle, start in conditions:
        if handle != trigger:
            continue
        for n in called_from(funcs, start):
            units.update(re.findall(r"GetUnitTypeId\(\s*GetSummonedUnit\(\)\s*\)\s*==\s*'(\w{4})'", funcs[n]['body']))
    return units


class RankTracker:
    """The ability rank (`udg_abilitylevel == n`) of the if/elseif branches around the current line."""

    def __init__(self, funcs: dict):
        self.funcs = funcs
        self.ranks: list[int] = []

    def line(self, line: str) -> None:
        """Follows one line of code."""
        if line.startswith(('if ', 'elseif ')):
            if line.startswith('elseif ') and self.ranks:
                self.ranks.pop()
            predicate = line
            helper = re.search(r'\b(\w+)\(\)', line)
            if helper and helper[1] in self.funcs:
                predicate = self.funcs[helper[1]]['body']
            rank = re.search(r'\budg_abilitylevel\s*==\s*(\d+)', predicate)
            self.ranks.append(int(rank[1]) if rank else 0)
        elif line == 'else' and self.ranks:
            self.ranks[-1] = 0
        elif line == 'endif' and self.ranks:
            self.ranks.pop()

    def current(self) -> int:
        """The innermost known rank, or 0."""
        return next((v for v in reversed(self.ranks) if v), 0)


def summon_action(funcs: dict, action: str, units: set[str], edge) -> dict:
    """Follows one summon action: abilities it gives the summoned unit (per rank) and its per-rank settings."""
    code = funcs[action]['body']
    aliases = {'GetSummonedUnit()'}
    ranks = RankTracker(funcs)
    values = defaultdict(dict)
    for line in code.splitlines():
        line = line.strip()
        assignment = re.search(r'\b(\w+(?:\[\w+\])?)\s*=\s*(.+)', line)
        if assignment and assignment[2].strip() in aliases:
            aliases.add(assignment[1])
        ranks.line(line)
        for ability, target in re.findall(
                r"(?:UnitAddAbilityBJ|SetUnitAbilityLevelSwapped)\(\s*'(\w{4})'\s*,\s*(\w+(?:\[\w+\])?)", line):
            if target in aliases:
                for uid in sorted(units):
                    edge('units/' + uid, 'abilities/' + ability, 'Abilities on summon', action, ranks.current())
        setting = re.fullmatch(r'set\s+udg_summon_(\w+)\[(\d+)\]\s*=\s*(-?[\d.]+)', line)
        if setting and re.search(r'\budg_summon_' + setting[1] + r'\[udg_abilitylevel\]', code):
            values[setting[1]][int(setting[2])] = float(setting[3])
    return values


def summoned_units(funcs: dict, live: set[str], edge) -> dict:
    """Unit key -> the summon actions that set it up; adds the edges from the summoning spell and to the abilities
    the action gives."""
    result = defaultdict(list)
    for init in sorted(live):
        body = funcs[init]['body']
        if 'EVENT_PLAYER_UNIT_SUMMON' not in body:
            continue
        conditions = re.findall(r'TriggerAddCondition\(\s*(\w+)\s*,\s*Condition\(\s*function\s+(\w+)', body)
        for trigger, action in re.findall(r'TriggerAddAction\(\s*(\w+)\s*,\s*function\s+(\w+)', body):
            units = summon_types(funcs, conditions, trigger) if action in live else set()
            if not units:
                continue
            values = summon_action(funcs, action, units, edge)
            source_spell = re.search(r"set\s+udg_abilitylevel\s*=\s*GetUnitAbilityLevelSwapped\(\s*'(\w{4})'",
                                     funcs[action]['body'])
            for uid in sorted(units):
                if source_spell:
                    edge('abilities/' + source_spell[1], 'units/' + uid, 'Summon scaling', action)
                result['units/' + uid].append({'action': action, 'values': values})
    return result


def slot_pool(writes: dict, context: list) -> dict:
    """Variable -> unit id -> the indexes it may hold at a creation site: a write in the site's own branch
    replaces the same slot's earlier value; without one, every write counts (a table set up on first cast)."""
    resolved = {}
    for var, assignments in writes.items():
        slots = {index: uid for branch, index, uid in assignments if tuple(context[:len(branch)]) == branch}
        candidates = list(slots.items()) if slots else [(index, uid) for _, index, uid in assignments]
        pool = defaultdict(set)
        for index, uid in candidates:
            if index is None:
                pool[uid]
            else:
                pool[uid].add(int(index))
        resolved[var] = pool
    return resolved


def creation_contexts(fn: dict, funcs: dict, owners: set[str]) -> dict:
    """Creation line -> (spells it runs for, the unit-type variables' possible values there), for every unit
    creation whose type is a variable."""
    sites = {line for line, _, uid in fn['creation_sites'] if not uid}
    if not sites:
        return {}
    code = fn['body']
    aliases = set(re.findall(r'\b(\w+)\s*=\s*GetSpellAbilityId\(\)', code)) | {'GetSpellAbilityId()'}
    spell_var = '|'.join(re.escape(v) for v in sorted(aliases))
    context, guards, writes, result = [], [], defaultdict(list), {}
    for line_no, line in enumerate(code.splitlines(), fn['line']):
        line = line.partition('//')[0].strip()
        if line.startswith(('if ', 'elseif ')) or line == 'else':
            if not line.startswith('if ') and context:
                context.pop()
                guards.pop()
            context.append(line_no)
            predicate = line
            helper = re.search(r'\b(\w+)\(\)', line)
            if helper and helper[1] in funcs:
                predicate = funcs[helper[1]]['body']
            guards.append(set(re.findall(r'\b(?:' + spell_var + r")\s*==\s*'(\w{4})'", predicate)) & owners)
        if line == 'endif' and context:
            context.pop()
            guards.pop()
        assign = re.search(r"\b(\w+)(?:\[(\d+)\])?\s*=\s*'(\w{4})'", line)
        if assign:
            writes[assign[1]].append((tuple(context), assign[2], assign[3]))
        if line_no in sites:
            result[line_no] = (next((g for g in reversed(guards) if g), owners), slot_pool(writes, context))
    return result


class GuardScan:
    """Follows one function's unit-type guards (`if GetUnitTypeId(u) == 'hfoo'`) and created units, so that
    abilities it adds and upgrades it checks are linked to the right unit types."""

    def __init__(self, trace: 'Trace', name: str, code: str, fn: dict):
        self.trace, self.name = trace, name
        self.aliases = dict(re.findall(r'\b(\w+)\s*=\s*GetUnitTypeId\((\w+)\)', code))
        self.guards: list[list] = []
        self.spawned: dict[str, str] = {}
        self.sites = {number: uid for number, _, uid in fn['creation_sites']}
        self.last = None

    def line(self, number: int, line: str) -> None:
        """Follows one line of code."""
        if number in self.sites:
            self.last = self.sites[number]
        assigned = re.search(r'\b(\w+)\s*=\s*(.+)', line)
        if assigned:
            var, rhs = assigned.groups()
            if number in self.sites or rhs.startswith('GetLastCreatedUnit()'):
                self.spawned[var] = self.last
            else:
                self.spawned.pop(var, None)
        self.branch(line)
        for tech in re.findall(r"(?:GetPlayerTechCountSimple\(\s*|GetPlayerTechCount\([^,\n]+,\s*)'(\w{4})'", line):
            for guard in self.guards:
                for _, uid in guard:
                    self.trace.edge('units/' + uid, 'upgrades/' + tech, 'Upgrade checks', self.name)
        grants = re.findall(r"UnitAddAbility\(\s*(\w+)\s*,\s*'(.{4})'", line)
        grants += [(target, ability) for ability, target in re.findall(r"UnitAddAbilityBJ\(\s*'(.{4})'\s*,\s*(\w+)", line)]
        for target, ability in grants:
            self.grant(target, ability)

    def branch(self, line: str) -> None:
        """Follows if/elseif/else/endif lines: the unit-type tests of the open branches."""
        if line.startswith(('if ', 'elseif ')):
            if line.startswith('elseif ') and self.guards:
                self.guards.pop()
            pairs = re.findall(r"(GetUnitTypeId\(\w+\)|\w+)\s*==\s*'(\w{4})'", line)
            self.guards.append([(self.aliases.get(v, v.removeprefix('GetUnitTypeId(').removesuffix(')')), uid)
                                for v, uid in pairs if v in self.aliases or v.startswith('GetUnitTypeId(')])
        elif line == 'else' and self.guards:
            self.guards[-1] = []
        elif line == 'endif' and self.guards:
            self.guards.pop()

    def grant(self, target: str, ability: str) -> None:
        """Links an ability the script adds to a unit to that unit's type (a created unit or a guarded one)."""
        if self.spawned.get(target):
            self.trace.edge('units/' + self.spawned[target], 'abilities/' + ability, 'Triggered abilities', self.name)
        for guard in self.guards:
            for unit, uid in guard:
                if unit == target:
                    self.trace.edge('units/' + uid, 'abilities/' + ability, 'Triggered abilities', self.name)


class Trace:
    """Builds the gameplay graph of one wiki index (see the module docstring)."""

    def __init__(self, db: dict):
        self.db = db
        self.objects, self.funcs = db['objects'], db['functions']
        self.live = callable_functions(self.funcs)
        self.spells: dict[str, set[str]] = defaultdict(set)
        self.roots: dict[str, list] = defaultdict(list)
        self.edges: dict[str, dict] = defaultdict(dict)
        self.unresolved: list = []
        self.ids = defaultdict(list)
        for key, obj in self.objects.items():
            self.ids[obj['id']].append(key)

    def root(self, key: str, reason: str, source: str) -> None:
        """Marks an object as a starting point of the game, with why and where from."""
        if key in self.objects and [reason, source] not in self.roots[key]:
            self.roots[key].append([reason, source])

    def edge(self, a: str, b: str, label: str, source: str, level: int = 0, reference_only: bool = False) -> None:
        """Adds a link from object `a` to object `b` (once per label; levels and sources are collected)."""
        if a not in self.objects or b not in self.objects or a == b:
            return
        item = self.edges[a].setdefault((b, label), {'to': b, 'label': label, 'levels': [], 'sources': [],
                                                     'reference_only': reference_only})
        if level and level not in item['levels']:
            item['levels'].append(level)
        if source not in item['sources']:
            item['sources'].append(source)

    def run(self) -> dict:
        """The trace: roots, via, support, edges, parents, waves, summon rules, unresolved ids, dynamic creation
        sites, live functions and visuals (model -> objects shown with it)."""
        self.linked_fields()
        self.placements()
        self.rosters()
        waves = Colossal(self.funcs, self.live).waves(self.root)
        summon_rules = summoned_units(self.funcs, self.live, self.edge)
        paths = self.creation_paths()
        self.spells = spell_actions(self.funcs, self.live)
        dynamic, uses, assignments, indexed = self.scan_functions(paths)
        self.selection_tables(uses, assignments, indexed)
        self.recipes()
        self.wave_loot(waves)
        graph = self.graph()
        seen = self.walk(graph)
        supporting = {v['to'] for key in seen for v in self.edges.get(key, {}).values() if v['reference_only']}
        return {'roots': self.roots, 'via': seen, 'support': sorted(supporting - set(seen)), 'edges': graph,
                'parents': sorted(self.parents(seen) - set(seen)), 'waves': waves, 'summon_rules': summon_rules,
                'unresolved': sorted(set(map(tuple, self.unresolved))), 'dynamic': dynamic,
                'functions': sorted(self.live), 'visuals': self.visuals(seen)}

    def linked_fields(self) -> None:
        """Edges from each object's reference fields (ability lists, trained units ...), up to its level cap."""
        for key, o in self.objects.items():
            family = key.partition('/')[0]
            cap = next((int(float(s['value'])) for s in o['stats'] if s['field'] == 'alev'), 0)
            for f in o['linked_fields']:
                if cap and f['level'] > cap:
                    continue
                field = f['field']
                value_type = self.db['metadata'].get(family, {}).get(field, {}).get('type')
                target_type = TYPES.get(value_type)
                reference_only = value_type in REFERENCE_TYPES or field in REFERENCE_FIELDS
                for uid in f['ids']:
                    keys = [target_type + '/' + uid] if target_type else self.ids[uid]
                    if not any(k in self.objects for k in keys):
                        self.unresolved.append([key, field, uid])
                    for k in keys:
                        self.edge(key, k, LABELS.get(field, f['label']), f['source'], f['level'], reference_only)

    def placements(self) -> None:
        """Placed objects are roots; their drops, inventories, abilities and random units are edges; random
        tables they use are roots."""
        links = (('inventory', 'item', 'items'), ('ability_settings', 'ability', 'abilities'),
                 ('random_units', 'unit', 'units'))
        for rec in self.db['placements']:
            types = ('items', 'units') if rec['entry'] == 'war3mapUnits.doo' else ('doodads', 'destructibles')
            for group in types:
                owner = group + '/' + rec['id']
                self.root(owner, 'Placed on the map', rec['entry'])
                for drops in rec.get('drop_sets', []):
                    for drop in drops:
                        self.edge(owner, 'items/' + drop['item'], 'Drops', rec['entry'])
                for field, target, target_group in links:
                    for record in rec.get(field, []):
                        self.edge(owner, target_group + '/' + record[target], field.replace('_', ' ').title(),
                                  rec['entry'])
        for rec in self.db['placements']:
            if rec.get('item_table', -1) >= 0:
                self.random_table('item', rec['item_table'], 'Placed drop table')
            if rec.get('random_mode') == 1:
                self.random_table('unit', rec['random_table'], 'Random placement')

    def random_table(self, group: str, table_id: int, reason: str) -> None:
        """Every object of one of the map's random tables (war3map.w3i) is a root."""
        for t in self.db['settings'].get('random_' + group + '_tables', []):
            if t['index'] == table_id:
                for row in t['sets']:
                    for uid in ([r['item'] for r in row] if group == 'item' else row['ids']):
                        self.root(group + 's/' + uid, reason, 'war3map.w3i')

    def rosters(self) -> None:
        """The heroes of the selection roster and the troop bases are roots; bases spawn their troops."""
        table = {t['key']: t for t in self.db['tables']}
        body = self.funcs.get('Trig_set_hero_numbers_Actions', {}).get('body', '')
        hero_limit = re.findall(r'set udg_total_hero_count\s*=\s*(\d+)', body)
        excluded = set(re.findall(r"\bheroType\s*==\s*'(.{4})'",
                                  self.funcs.get('SoloFootsIsNoMuteHeroType', {}).get('body', '')))
        picks = any('udg_hero_type[' in self.funcs[n]['body'] for n in self.live
                    if re.search('Draft|Stock|Tavern|Pick', n))
        if 'Trig_set_hero_numbers_Actions' in self.live and picks:
            for r in table.get('heroes', {}).get('rows', []):
                if r['id'] and r['id']['value'] not in excluded and (
                        not hero_limit or r['index']['value'] <= int(hero_limit[-1])):
                    self.root('units/' + r['id']['value'], 'Hero selection roster', r['id']['source'])
        if 'Trig_set_spawn_variables_Actions' in self.live:
            for row in table.get('spawns', {}).get('rows', []):
                if row.get('udg_base_type') and row['id']:
                    base = 'units/' + row['udg_base_type']['value']
                    self.root(base, 'Troop production base', row['udg_base_type']['source'])
                    self.edge(base, 'units/' + row['id']['value'], 'Spawns', row['id']['source'])

    def creation_paths(self) -> dict[str, set[str]]:
        """Edges from spells to the units their checks lead to creating; returns function -> units it creates so."""
        paths = defaultdict(set)
        for spell, records in self.db['creation_paths'].items():
            for p in records:
                if all(n in self.live for n in p['path']):
                    self.edge('abilities/' + spell, 'units/' + p['unit'], 'Scripted summon', ' → '.join(p['path']))
                    paths[p['path'][-1]].add(p['unit'])
        return paths

    def scan_functions(self, paths: dict) -> tuple[list, list, dict, dict]:
        """Reads every live function for created units, stocked items, assignments of object ids and guarded
        grants.

        Returns:
            Dynamic creation sites [function, line, expression]; uses of object-id variables
            (variable, group, function, index, spells, local pool); variable -> ids assigned; variable -> id -> indexes.
        """
        dynamic, uses = [], []
        assignments = defaultdict(set)
        indexed = defaultdict(lambda: defaultdict(set))
        for _, line in self.db['globals']:
            match = re.fullmatch(r"\s*(?:constant\s+)?integer\s+(\w+)\s*=\s*'(\w{4})'\s*", line)
            if match:
                assignments[match[1]].add(match[2])
        for name in sorted(self.live):
            fn = self.funcs[name]
            code = '\n'.join(line.partition('//')[0] for line in fn['body'].splitlines())
            for var, index, uid in re.findall(r"(?m)^\s*set\s+(\w+)(?:\[([^\n=]+)\])?\s*=\s*'(.{4})'", code):
                if index or var.startswith('udg_') or var in assignments:
                    assignments[var].add(uid)
                if index.isdigit():
                    indexed[var][uid].add(int(index))
            self.creation_sites(name, fn, paths, dynamic, uses)
            self.stock_natives(name, fn, code, uses)
            scan = GuardScan(self, name, code, fn)
            for number, line in enumerate(code.splitlines(), fn['line']):
                scan.line(number, line.strip())
        return dynamic, uses, assignments, indexed

    def creation_sites(self, name: str, fn: dict, paths: dict, dynamic: list, uses: list) -> None:
        """A function's unit creations: spell summons, trigger-created roots, and variable types for later."""
        contexts = creation_contexts(fn, self.funcs, self.spells[name])
        for line, expr, uid in fn['creation_sites']:
            if uid:
                for spell in self.spells[name]:
                    self.edge('abilities/' + spell, 'units/' + uid, 'Scripted summon', f'{name}:{line}')
                if uid not in paths[name] and not self.spells[name] and 'preload' not in name.lower():
                    self.root('units/' + uid, 'Created by trigger', f'{name}:{line}')
                continue
            dynamic.append([name, line, expr])
            match = re.fullmatch(r'(\w+)(?:\[(.+)\])?', expr)
            if match:
                owners, pools = contexts[line]
                uses.append((match[1], 'units', name, match[2] or '', owners, pools.get(match[1])))

    def stock_natives(self, name: str, fn: dict, code: str, uses: list) -> None:
        """Items and units a function stocks, hands out or swaps in: literal ones are roots (a recipe's own
        result excepted), variable ones are resolved later."""
        for native, group in STOCK_NATIVES:
            skip = r'[^,\n]+,\s*' if native in SECOND_ARGUMENT else ''
            for match in re.finditer(r'\b' + native + r'\(\s*' + skip + r"(?:'(.{4})'|(\w+)\[)", code):
                uid, var = match.groups()
                if uid:
                    if not (fn['consumes'] and uid in fn['grants']):
                        self.root(group + '/' + uid, 'Trigger stock, reward or replacement', name)
                elif var:
                    uses.append((var, group, name, '', self.spells[name], None))

    def selection_tables(self, uses: list, assignments: dict, indexed: dict) -> None:
        """Variables of object ids: under a spell they are its possible summons or rewards (per rank when indexed
        by level), otherwise every id they may hold is a root."""
        for var, group, name, index, owners, local_pool in uses:
            if var in ROSTER_ARRAYS:
                continue  # The rosters above keep their availability and owner.
            pool = local_pool if local_pool is not None else assignments[var]
            for uid in sorted(pool):
                if not owners:
                    self.root(group + '/' + uid, 'Trigger selection table', name + ' / ' + var)
                    continue
                by_rank = local_pool if local_pool is not None else indexed[var]
                ranks = by_rank[uid] if re.search('level|rank|lvl', index, re.I) else ()
                label = 'Possible summons' if group == 'units' else 'Possible rewards'
                for spell in owners:
                    for rank in sorted(ranks) or [0]:
                        self.edge('abilities/' + spell, group + '/' + uid, label, name + ' / ' + var, rank)

    def recipes(self) -> None:
        """Edges from each consumed item to the items its live recipe gives."""
        for rec in self.db['recipes']:
            if rec['fn'] in self.live:
                for a in rec['consumes']:
                    for b in rec['grants']:
                        self.edge('items/' + a, 'items/' + b, 'Crafting results', rec['fn'])

    def wave_loot(self, waves: dict) -> None:
        """Edges from each Colossal boss to the items of the wave loot pool."""
        body = self.funcs.get(Colossal.VARIABLES, {}).get('body', '')
        loot = re.findall(r"set udg_colossal_dropped_item\[\d+\]\s*=\s*'(.{4})'", body)
        for key, record in waves.items():
            if record.get('boss'):
                for uid in loot:
                    self.edge(key, 'items/' + uid, 'Wave loot pool', Colossal.VARIABLES)

    def graph(self) -> dict[str, list]:
        """Object -> its outgoing edges, sorted by label and target, levels and sources sorted."""
        graph = {}
        for key, outgoing in self.edges.items():
            graph[key] = sorted(outgoing.values(), key=lambda e: (e['label'], e['to']))
            for e in graph[key]:
                e['levels'].sort()
                e['sources'].sort()
        return graph

    def walk(self, graph: dict) -> dict[str, str | None]:
        """Breadth-first from the roots along the gameplay edges: object -> the object it was first reached from."""
        seen = {}
        queue = deque((k, None) for k in sorted(self.roots))
        while queue:
            k, parent = queue.popleft()
            if k not in seen:
                seen[k] = parent
                queue.extend((v['to'], k) for v in graph.get(k, ()) if not v['reference_only'] and v['to'] not in seen)
        return seen

    def parents(self, seen: dict) -> set[str]:
        """The objects the reached ones are based on (their parent chains within the index)."""
        parents = set()
        for key in seen:
            k = key
            while k in self.objects:
                base = k.partition('/')[0] + '/' + self.objects[k]['parent']
                if base == k or base in parents or base not in self.objects:
                    break
                parents.add(base)
                k = base
        return parents

    def visuals(self, seen: dict) -> dict[str, list]:
        """Model -> the reached objects shown with it (their art fields, and the spells of script effects)."""
        visual = defaultdict(set)
        for key in seen:
            for path in self.objects[key].get('visuals', []):
                model = re.sub(r'\.mdl$', '.mdx', path.replace('/', '\\').replace('\\\\', '\\').lower())
                if model in self.db['models']:
                    visual[model].add(key)
        for model, m in self.db['models'].items():
            for owner, _ in m['uses']:
                if owner.startswith('fn/'):
                    for spell in self.spells.get(owner[3:], ()):
                        if 'abilities/' + spell in seen:
                            visual[model].add('abilities/' + spell)
        return {m: sorted(keys) for m, keys in visual.items()}


def trace(db: dict) -> dict:
    """The gameplay graph of a wiki index (see the module docstring)."""
    return Trace(db).run()

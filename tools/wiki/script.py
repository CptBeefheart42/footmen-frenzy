"""What each function of the map script refers to: object ids, other functions, created units, spell checks.

The script is the finished map's war3map.j. Each function becomes a dict with:
`line` (first line number), `body` (its text), `ids` (object ids it names), `calls` (functions it calls or passes),
`consumes` / `grants` (item recipes), `spells` (ability ids it compares the cast spell with), `creation_sites`
([line, unit expression, unit id or None]) and `creates` (unit ids it creates).
"""
from __future__ import annotations

import re
from collections import defaultdict, deque

FUNCTION = re.compile(r'\s*function\s+(\w+)\s+takes\b')
STRINGS_AND_COMMENTS = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*')
CREATE_UNIT = re.compile(r'\b(BlzCreateUnitWithSkin|CreateUnit(?:AtLoc)?|CreateNUnitsAtLoc(?:BJ)?|'
                         r'CreateNUnitsAtLocFacingLocBJ|CreateUnitAtLocSaveLast)\s*\(')


def split_functions(script: str) -> tuple[dict[str, dict], list[list]]:
    """The script's functions (name -> line, body) and its other lines ([line number, text]: globals, natives)."""
    functions, outside = {}, []
    active = None
    for number, line in enumerate(script.splitlines(), 1):
        start = FUNCTION.match(line)
        if start:
            active = {'line': number, 'body': []}
            functions[start[1]] = active
        if active is None:
            if line.strip():
                outside.append([number, line])
            continue
        active['body'].append(line)
        if line.strip().startswith('endfunction'):
            active = None
    for fn in functions.values():
        fn['body'] = '\n'.join(fn['body'])
    return functions, outside


def call_arguments(line: str, start: int, count: int) -> list[str]:
    """The first `count` top-level arguments of a call whose argument list starts at `start` of `line`."""
    depth, parts = 0, []
    for i in range(start, len(line)):
        char = line[i]
        if char == ',' and depth == 0:
            parts.append(line[start:i].strip())
            start = i + 1
            if len(parts) == count:
                break
        elif char in '([':
            depth += 1
        elif char in ')]':
            depth -= 1
    return parts


class ScriptIndex:
    """The analysed script: its functions, other lines, which functions name each id, and spell creation paths."""

    def __init__(self, script: str):
        self.functions, self.outside = split_functions(script)
        self.constants = dict(re.findall(r"^\s*constant\s+integer\s+(\w+)\s*=\s*'(\w{4})'", script, re.M))
        self.by_id: dict[str, set[str]] = defaultdict(set)
        for name, fn in self.functions.items():
            self.analyse(name, fn)
        self.creation_paths = self.spell_creation_paths()

    def literal(self, expr: str) -> str | None:
        """The object id an expression stands for: a 'abcd' literal or an integer constant; None otherwise."""
        match = re.fullmatch(r"'(\w{4})'", expr)
        return match[1] if match else self.constants.get(expr)

    def analyse(self, name: str, fn: dict) -> None:
        """Fills one function's references (see the module docstring)."""
        code = STRINGS_AND_COMMENTS.sub(' ', fn['body'].partition('\n')[2])
        refs = set(re.findall(r"'([^'\r\n]{4})'", code))
        refs.update(self.constants[word] for word in set(re.findall(r'\b\w+\b', code)) & self.constants.keys())
        refs.update(re.findall(r'\bFourCC\s*\(\s*"(\w{4})"\s*\)', fn['body']))
        fn['ids'] = sorted(refs)
        for uid in refs:
            self.by_id[uid].add(name)
        calls = {a or b for a, b in re.findall(r'\b(\w+)\s*\(|\bfunction\s+(\w+)', code)} & self.functions.keys()
        calls.update(n for n in re.findall(r'\bExecuteFunc\s*\(\s*"(\w+)"', fn['body']) if n in self.functions)
        fn['calls'] = sorted(calls)
        fn['consumes'] = re.findall(r"\bRemoveItem\s*\(\s*GetItemOfTypeFromUnitBJ\s*\([^,\n]+,\s*'(\w{4})'", code)
        fn['grants'] = re.findall(r"\bUnitAddItemByIdSwapped\s*\(\s*'(\w{4})'", code)
        fn['spells'] = self.spell_checks(code)
        fn['creation_sites'] = self.creation_sites(fn)
        fn['creates'] = sorted({site[2] for site in fn['creation_sites'] if site[2]})

    def spell_checks(self, code: str) -> list[str]:
        """The ability ids a function compares the cast spell (GetSpellAbilityId or a copy of it) with."""
        aliases = re.findall(r'\b(\w+)\s*=\s*GetSpellAbilityId\(\)', code)
        spell = r'(?:GetSpellAbilityId\s*\(\s*\)' + ''.join('|' + re.escape(v) for v in aliases) + ')'
        found = (self.literal(m[1]) for m in re.finditer(r'\b' + spell + r"\s*(?:==|!=)\s*('....'|\w+)", code))
        return sorted({uid for uid in found if uid})

    def creation_sites(self, fn: dict) -> list[list]:
        """Every unit-creating call of a function: [line number, unit-type expression, its id or None]."""
        sites = []
        for offset, line in enumerate(fn['body'].splitlines()):
            for call in CREATE_UNIT.finditer(line.partition('//')[0]):
                parts = call_arguments(line, call.end(), 2)
                if len(parts) == 2:
                    sites.append([fn['line'] + offset, parts[1], self.literal(parts[1])])
        return sites

    def trigger_actions(self) -> dict[str, set[str]]:
        """Condition function -> the action functions registered on the same trigger.

        A GUI spell often tests the spell id in a condition and creates the unit in an action of that trigger.
        """
        actions = defaultdict(set)
        for fn in self.functions.values():
            conditions = re.findall(r'TriggerAddCondition\s*\(\s*(\w+)\s*,\s*(?:Condition|Filter)\s*\(\s*function\s+(\w+)',
                                    fn['body'])
            registered = re.findall(r'TriggerAddAction\s*\(\s*(\w+)\s*,\s*function\s+(\w+)', fn['body'])
            for handle, condition in conditions:
                actions[condition].update(action for trigger, action in registered if trigger == handle)
        return actions

    def spell_creation_paths(self) -> dict[str, list[dict]]:
        """Ability id -> the units its spell checks lead to creating, each with the call path that gets there."""
        actions = self.trigger_actions()
        paths = defaultdict(list)
        for name, fn in self.functions.items():
            if not fn['spells']:
                continue
            queue = deque([[name]] + [[name, n] for n in sorted(actions[name]) if n in self.functions])
            seen = set()
            while queue:
                path = queue.popleft()
                if path[-1] in seen:
                    continue
                seen.add(path[-1])
                target = self.functions[path[-1]]
                for uid in target['creates']:
                    for ability in fn['spells']:
                        paths[ability].append({'unit': uid, 'path': path})
                queue.extend(path + [n] for n in target['calls'] if n not in seen)
        return paths

    def recipes(self) -> list[dict]:
        """Functions that take items away and give others: {fn, consumes, grants}."""
        return [{'fn': name, 'consumes': fn['consumes'], 'grants': fn['grants']}
                for name, fn in self.functions.items() if fn['consumes'] and fn['grants']]

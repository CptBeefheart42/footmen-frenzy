"""The wiki export: the object reader, the script and trace rules, and the export of the repository's real maps."""
import gzip
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'ff')]

import objectdata  # noqa: E402
from repo import projects  # noqa: E402
from wiki import bundle, export, stock  # noqa: E402
from wiki.catalog import Catalog, ability_command, load_objects  # noqa: E402
from wiki.mapfiles import MapFiles, string_table  # noqa: E402
from wiki.reachability import callable_functions, creation_contexts, trace  # noqa: E402
from wiki.script import ScriptIndex  # noqa: E402
from wiki.tables import script_tables  # noqa: E402


def repository_map(name: str) -> MapFiles:
    """A map of the repository as committed: its text object data, its files and its own script (no build)."""
    project = projects()[name]
    return MapFiles(project.src, project.objects, project.src / 'war3map.j')


def cached_pack() -> stock.StockPack | None:
    """The listed stock pack when it is in the blob cache (only maintainers have it) and Pillow is installed."""
    blob = export.listed_pack()
    return stock.StockPack(blob.path) if blob.path.is_file() and export.has_pillow() else None


class ObjectTextTest(unittest.TestCase):
    """Typed cells of a text object file, with levels, pointers and the object an object is based on."""

    def test_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'war3map.w3a.txt'
            path.write_text('format v3\n\n[A001 : AHbz]\nend = new\nacdn.1.0 unreal = 12.5 @0  # Cooldown\n'
                            'Hbz2.2.2 int = 30\natp1.0.0 string = "a \\"b\\""\n[AHbz]\nend = base\n', encoding='utf-8')
            records = objectdata.read(path)
        self.assertEqual([(r.code, r.parent) for r in records], [('A001', 'AHbz'), ('AHbz', 'AHbz')])
        self.assertEqual(records[0].cells, [objectdata.Cell('acdn', 1, 0, 'unreal', 12.5),
                                            objectdata.Cell('Hbz2', 2, 2, 'int', 30),
                                            objectdata.Cell('atp1', 0, 0, 'string', 'a "b"')])

    def test_skin_and_main_file_merge_with_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'war3mapSkin.w3u.txt').write_text('[h001 : hfoo]\nunam string = "TRIGSTR_001"\n', encoding='utf-8')
            (folder / 'war3map.w3u.txt').write_text('[h001 : hfoo]\nuhpm int = 0\n', encoding='utf-8')
            strings = string_table(b'STRING 1\r\n// tooltip\r\n{\r\nFootman <&>\r\n}\r\n')
            objects = load_objects(MapFiles(folder, folder, folder / 'war3map.j'), strings)
        self.assertEqual(objects['units', 'h001'], {'parent': 'hfoo', 'fields': [
            ('unam', 0, 0, 'Footman <&>', 'war3mapSkin.w3u'), ('uhpm', 0, 0, 0, 'war3map.w3u')]})


class RulesTest(unittest.TestCase):
    """Command keys, triggers that never run, spell summons and the walk through the gameplay graph."""

    def test_command_keys_follow_separate_cast_and_learn_overrides(self):
        objects = {('abilities', 'A001'): {'parent': 'A000', 'fields': [
            ('ahky', 0, 0, 'X', 'war3mapSkin.w3a'), ('abpx', 0, 0, 1, 'war3mapSkin.w3a'),
            ('arhk', 0, 0, 'W', 'war3map.w3a')]}}
        rows = {('abilities', 'A000'): {'base/units/abilityfunc.txt': {
            'Buttonpos': '0,2', 'Researchbuttonpos': '1,0', 'Hotkey': 'G', 'Researchhotkey': 'L'}}}
        self.assertEqual(ability_command('A001', objects, rows, False),
                         {'cast': {'key': 'X', 'x': 1, 'y': 2}, 'learn': {'key': 'W', 'x': 1, 'y': 0}})

    def test_trigger_with_a_false_condition_runs_only_when_executed(self):
        source = ('function Reject takes nothing returns boolean\nif ( not ( false == true ) ) then\nreturn false\n'
                  'endif\nreturn true\nendfunction\nfunction Spawn takes nothing returns nothing\nendfunction\n'
                  'function main takes nothing returns nothing\nset gg_trg_unused=CreateTrigger()\n'
                  'call TriggerAddCondition(gg_trg_unused, Condition(function Reject))\n'
                  'call TriggerAddAction(gg_trg_unused, function Spawn)\nendfunction')
        self.assertNotIn('Spawn', callable_functions(ScriptIndex(source).functions))
        forced = source.removesuffix('endfunction') + 'call TriggerExecute(gg_trg_unused)\nendfunction'
        self.assertIn('Spawn', callable_functions(ScriptIndex(forced).functions))

    def test_spells_sharing_a_summon_array_keep_their_own_units(self):
        source = ("function Summon takes nothing returns nothing\nset spell=GetSpellAbilityId()\n"
                  "if spell == 'A001' then\nset pool[1]='h001'\ncall CreateNUnitsAtLoc(1, pool[level], p, w, 0.)\n"
                  "endif\nif spell == 'A002' then\nset pool[1]='h002'\n"
                  "call CreateNUnitsAtLoc(1, pool[level], p, w, 0.)\nendif\nendfunction")
        funcs = ScriptIndex(source).functions
        cases = list(creation_contexts(funcs['Summon'], funcs, {'A001', 'A002'}).values())
        self.assertEqual([(spells, pools['pool']) for spells, pools in cases],
                         [({'A001'}, {'h001': {1}}), ({'A002'}, {'h002': {1}})])

    def test_spawn_from_a_separately_registered_action(self):
        source = ("globals\nconstant integer SPELL = 'A001'\nendglobals\n"
                  'function Cast takes nothing returns boolean\nreturn GetSpellAbilityId() == SPELL\nendfunction\n'
                  "function Spawn takes nothing returns nothing\ncall CreateUnit(GetOwningPlayer(GetTriggerUnit()), "
                  "'h001', 0., 0., 0.)\nendfunction\nfunction Init takes nothing returns nothing\n"
                  'call TriggerAddCondition(t, Condition(function Cast))\ncall TriggerAddAction(t, function Spawn)\n'
                  'endfunction')
        script = ScriptIndex(source)
        self.assertEqual(script.functions['Spawn']['creates'], ['h001'])
        self.assertIn('Cast', script.by_id['A001'])
        self.assertEqual(script.creation_paths['A001'], [{'unit': 'h001', 'path': ['Cast', 'Spawn']}])

    def test_trace_follows_nested_summons_without_promoting_parents(self):
        def obj(uid, parent, links=()):
            return {'id': uid, 'parent': parent, 'stats': [], 'linked_fields': [
                {'field': f, 'label': f, 'level': 1, 'ids': [i], 'source': 'fixture'} for f, i in links]}
        objects = {
            'units/H001': obj('H001', 'H002', [('uhab', 'A001'), ('ureq', 'hbar')]),
            'units/H002': obj('H002', 'Ewar'), 'units/hbar': obj('hbar', 'hbar', [('utra', 'h002')]),
            'units/h002': obj('h002', 'h002'), 'units/h001': obj('h001', 'h001', [('uabi', 'A002')]),
            'abilities/A001': obj('A001', 'A001', [('Hwe1', 'h001')]),
            'abilities/A002': obj('A002', 'A002', [('abuf', 'B001'), ('Hwe1', 'h001')]),
            'effects/B001': obj('B001', 'B001')}
        metadata = {'units': {'uhab': {'type': 'heroAbilityList'}, 'uabi': {'type': 'abilityList'},
                              'utra': {'type': 'unitList'}, 'ureq': {'type': 'techList'}},
                    'abilities': {'Hwe1': {'type': 'unitCode'}, 'abuf': {'type': 'buffList'}}}
        result = trace({'objects': objects, 'metadata': metadata, 'functions': {}, 'globals': [], 'settings': {},
                        'creation_paths': {}, 'recipes': [], 'models': {}, 'tables': [],
                        'placements': [{'entry': 'war3mapUnits.doo', 'id': 'H001'}]})
        self.assertEqual(result['via']['effects/B001'], 'abilities/A002')
        self.assertEqual(result['via']['abilities/A002'], 'units/h001')
        self.assertEqual(result['via']['units/h001'], 'abilities/A001')
        self.assertEqual(result['parents'], ['units/H002'])
        self.assertIn('units/hbar', result['support'])
        self.assertNotIn('units/h002', result['via'])


class RepositoryMapTest(unittest.TestCase):
    """The repository's 9v3 map as committed, without the game's data: its own objects, names and tables."""

    def test_heroes_and_names_from_the_map(self):
        files = repository_map('799x')
        catalog = Catalog(files, stock.load(stock.StockPack(None), files.read))
        index = catalog.build(ScriptIndex(files.jass()))
        self.assertEqual(index['objects']['units/E00A']['name'], 'Jaood')
        self.assertTrue(index['objects']['units/E00A']['defined'])
        tables, errors = script_tables(files.jass(), catalog.objects)
        self.assertEqual(errors, {})
        heroes = next(t for t in tables if t['key'] == 'heroes')
        self.assertIn('E00A', [row['id']['value'] for row in heroes['rows'] if row['id']])


@unittest.skipUnless(cached_pack(), 'needs the stock pack in the blob cache (maintainers) and Pillow')
class ExportTest(unittest.TestCase):
    """The full export of the repository's 9v3 map with the game's data, as the website gets it."""

    @classmethod
    def setUpClass(cls):
        files = repository_map('799x')
        cls.full = export.index(files, cached_pack(), '799X')
        cls.bundle = bundle.slim(cls.full, {'input': 'test', 'commit': 'test'})

    def stats(self, key, field):
        """Level -> value of one stat of an object in the bundle."""
        return {s['level']: s['value'] for s in self.bundle['objects'][key]['stats'] if s['field'] == field}

    def test_game_values_fill_what_the_map_leaves_out(self):
        self.assertEqual(self.stats('abilities/AHwe', 'amcs'), {1: 150, 2: 150, 3: 150, 4: 175, 5: 175, 6: 200})

    def test_hero_roster_and_abilities(self):
        reasons = [reason for reason, _ in self.bundle['trace']['roots']['units/E00A']]
        self.assertIn('Hero selection roster', reasons)
        abilities = [f['ids'] for f in self.bundle['objects']['units/E00A']['linked_fields'] if f['field'] == 'uhab']
        self.assertEqual(abilities, [['AOwk', 'A09T', 'A0ID', 'A0ED']])
        self.assertIn('abilities/A09T', self.bundle['trace']['via'])

    def test_bundle_leaves_out_what_the_website_does_not_show(self):
        self.assertEqual(self.bundle['schema'], bundle.SCHEMA)
        self.assertNotIn('functions', self.bundle['trace'])
        self.assertTrue(set(self.bundle['objects']) < set(self.full['objects']))
        arts = {o['art'] for o in self.bundle['objects'].values() if 'art' in o}
        self.assertEqual(arts, set(self.bundle['portraits']))

    def test_saved_files_are_readable_and_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, packed = bundle.save(self.bundle, Path(tmp), '799x')
            self.assertEqual(stat.S_IMODE(plain.stat().st_mode), 0o644)
            self.assertEqual(json.loads(gzip.decompress(packed.read_bytes())), json.loads(plain.read_bytes()))


if __name__ == '__main__':
    unittest.main()

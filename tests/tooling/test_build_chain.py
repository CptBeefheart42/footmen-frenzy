"""Build-chain contract tests: the balance tool and the map runner on the real maps.

Pins the behaviour of:
1. the workbook round trip: an exported workbook applies back onto the map, and one edit is one change;
2. reconcile: a workbook moved to another version of the map keeps its edits, fills rows for new objects and flags
   the ones that are gone (Solo UPDATE25 and UPDATE38, two releases from the map's history);
3. the WC3 3.0 level fill: only adds cells, only at levels 5+, with the 2.0.4 defaults, once;
4. the 799X debug mode's admin list, bot vision, the anchor hooks, the stats and usage rows and the bot-hosted games:
   the rules the league addons keep (docs/result-contract.md).

The map files come from the release store (tools/ff/blobs.py); the .NET tools are built once.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'ff'))

import blobs  # noqa: E402
import toolchain  # noqa: E402
from repo import projects  # noqa: E402

try:
    import openpyxl  # noqa: F401  (the workbook checks read the .xlsx with it)
    HAVE_OPENPYXL = True
except ImportError:
    HAVE_OPENPYXL = False

# Solo Foots UPDATE25 as released: an older version of the Solo starting map (UPDATE38) for the reconcile tests.
UPDATE25 = blobs.Blob('af791df061685774e7ce78d54f6233d390e5f71619da6dcbab6c270346910a69', 41323143)
LEAGUE = REPO / 'league'
ADDONS = {name: project.addons for name, project in projects().items()}


def dotnet(project: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Runs a built .NET tool of the repository and captures its output."""
    exe, base = toolchain.dotnet()
    return subprocess.run([exe, 'run', '--project', str(REPO / project), '-c', 'Release', '--no-build', '--', *args],
                          capture_output=True, text=True, env={**base, 'FF_REPO': str(REPO), **(env or {})})


def balance(*args: str, env: dict | None = None) -> str:
    """Runs tools/BalanceTool and returns stdout + stderr."""
    result = dotnet('tools/BalanceTool', *args, env=env)
    return result.stdout + result.stderr


def runner(*args: str) -> subprocess.CompletedProcess:
    """Runs tools/runner."""
    return dotnet('tools/runner', *args)


def workbook(*args: str) -> subprocess.CompletedProcess:
    """Runs tests/tooling/xlsx_tool.py, which reads and edits a workbook's cells."""
    return subprocess.run([sys.executable, str(REPO / 'tests' / 'tooling' / 'xlsx_tool.py'), *args],
                          capture_output=True, text=True)


def function_body(path: Path, name: str) -> str:
    """The text of one JASS function in a file."""
    match = re.search(rf'^function {re.escape(name)}\b.*?^endfunction', path.read_text(encoding='utf-8'), re.M | re.S)
    return match.group() if match else ''


def same_value(text: str):
    """A cell value in a comparable form: numbers as floats (125 == 125.0), other text as it is."""
    try:
        return float(text)
    except ValueError:
        return text


def setUpModule():
    exe, env = toolchain.dotnet()
    for project in ('tools/BalanceTool', 'tools/runner'):
        subprocess.run([exe, 'build', str(REPO / project), '-c', 'Release', '-v', 'q', '-nologo'], env=env,
                       check=True, capture_output=True)
    blobs.fetch([UPDATE25])


class Work(unittest.TestCase):
    """A temporary folder and the two Solo map versions."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.old = UPDATE25.path
        self.new = projects()['solo'].base

    def tearDown(self):
        shutil.rmtree(self.work)


@unittest.skipUnless(HAVE_OPENPYXL, 'the workbook checks need openpyxl (pip install openpyxl)')
class WorkbookTest(Work):
    """T1, T2: the workbook round trip and reconcile."""

    def test_round_trip(self):
        sheet = self.work / 'sheet.xlsx'
        balance('export', str(self.old), str(sheet))
        self.assertEqual(len(workbook('tabs', str(sheet)).stdout.splitlines()), 17)
        applied = balance('apply', str(self.old), str(sheet), str(self.work / 'out0.w3x'))
        self.assertIn('Applied 0 change', applied)
        self.assertIn('BUILD OK', applied)
        workbook('set', str(sheet), 'Abilities', 'A000', 'Cooldown', '7')
        self.assertIn('Applied 1 change', balance('apply', str(self.old), str(sheet), str(self.work / 'out1.w3x')))

    def test_reconcile_onto_the_newer_version(self):
        sheet, reconciled = self.work / 'old.xlsx', self.work / 'reconciled.xlsx'
        balance('export', str(self.old), str(sheet))
        workbook('set', str(sheet), 'Abilities', 'A000', 'Cooldown', '42')
        report = balance('reconcile', str(self.new), str(sheet), str(reconciled))
        self.assertRegex(report.lower(), 'reconcile')
        self.assertEqual(len(workbook('tabs', str(reconciled)).stdout.splitlines()), 17)
        self.assertIn(workbook('get', str(reconciled), 'Abilities', 'A000', 'Cooldown').stdout.strip(), ('42', '42.0'))
        for code in ('A0KF', 'AFv1'):  # abilities UPDATE38 added
            self.assertEqual(workbook('hasrow', str(reconciled), '*', code).returncode, 0, code)

    def test_reconcile_flags_objects_that_are_gone(self):
        sheet, reconciled = self.work / 'new.xlsx', self.work / 'reconciled.xlsx'
        balance('export', str(self.new), str(sheet))
        report = balance('reconcile', str(self.old), str(sheet), str(reconciled))
        self.assertRegex(report.lower(), 'filled|outdated')
        self.assertEqual(workbook('hasrow', str(reconciled), '*', 'A0KF').returncode, 0, 'outdated row kept')
        self.assertGreater(int(workbook('outdated', str(reconciled)).stdout.strip()), 0)


class LevelFillTest(Work):
    """T3: the WC3 3.0 level fill."""

    def test_fill_only_adds_level_5_plus_cells_with_the_defaults(self):
        raw, filled = self.work / 'raw.csv', self.work / 'filled.csv'
        balance('dumpall', str(self.old), str(raw))
        report = balance('dumpall', str(self.old), str(filled), '--fill')
        self.assertRegex(report, r'Level fill: \+[1-9]')
        before, after = set(raw.read_text().splitlines()), set(filled.read_text().splitlines())
        self.assertEqual(before - after, set(), 'the fill changed an existing cell')
        added = list(csv.reader(sorted(after - before)))
        self.assertTrue(added)
        self.assertTrue(all(int(row[4]) >= 5 for row in added), 'a filled cell below level 5')
        lines = (line for line in (REPO / 'data' / 'ability_level_defaults.csv').open() if not line.startswith('#'))
        rows = list(csv.DictReader(lines))
        defaults = {(r['BaseCode'], r['Field'], r['Pointer']): r['Value'] for r in rows}
        checked = 0
        for row in added:  # Type,ObjectCode,BaseCode,Field,Level,Pointer,Type2,Value
            key = (row[2], row[3], row[5])
            if key in defaults:
                self.assertEqual(same_value(row[7]), same_value(defaults[key]), row)
                checked += 1
        self.assertGreater(checked, 0, 'no filled cell compared with its 2.0.4 default')
        self.assertTrue(any(r[3] == 'atar' and r[7] == '_' for r in added),
                        'blank target lists get the default-targets token at level 5+')

    @unittest.skipUnless(HAVE_OPENPYXL, 'builds the map from a workbook, which needs openpyxl')
    def test_a_built_map_needs_no_further_fill(self):
        sheet, out = self.work / 'clean.xlsx', self.work / 'built.w3x'
        balance('export', str(self.old), str(sheet))
        balance('apply', str(self.old), str(sheet), str(out))
        self.assertIn('Level fill: +0 ', balance('dumpall', str(out), str(self.work / 'refill.csv'), '--fill'))

    def test_missing_defaults_fail_loudly(self):
        output = dotnet('tools/BalanceTool', 'dumpall', str(self.old), str(self.work / 'bad.csv'), '--fill',
                        env={'FF_LEVEL_DEFAULTS': str(self.work / 'missing.csv')})
        self.assertNotEqual(output.returncode, 0)


class ObjectTextTest(unittest.TestCase):
    """Object data lives as text (projects/<map>/objects/): text -> binary -> text gives back every file as it is."""

    def test_round_trip_of_both_maps(self):
        for name, project in projects().items():
            with tempfile.TemporaryDirectory() as work:
                binary, text = Path(work) / 'binary', Path(work) / 'text'
                self.assertEqual(runner('objects', 'to-binary', str(project.objects), str(binary)).returncode, 0)
                self.assertEqual(runner('objects', 'to-text', str(binary), str(text)).returncode, 0)
                files = sorted(p.name for p in project.objects.glob('*.txt'))
                self.assertEqual(len(files), 14, name)
                for file in files:
                    self.assertEqual((text / file).read_text(encoding='utf-8'), (project.objects / file).read_text(encoding='utf-8'),
                                     f'{name}/{file}')

    def test_a_broken_line_names_file_and_line(self):
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'objects'
            source.mkdir()
            (source / 'war3map.w3u.txt').write_text('format v3\n\n[h000 : hfoo]\nuhpm int 420\n', encoding='utf-8')
            result = runner('objects', 'to-binary', str(source), str(Path(work) / 'out'))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('war3map.w3u:4', result.stdout + result.stderr)


class AnchorTest(unittest.TestCase):
    """T6: the anchor hooks apply to the maps' scripts, and fail loudly when they would not."""

    def test_every_hook_applies_to_its_map(self):
        for name, addons in ADDONS.items():
            result = runner('check-anchors', str(addons.parent / 'src' / 'war3map.j'), str(addons / 'anchors.txt'))
            hooks = sum(1 for line in (addons / 'anchors.txt').read_text().splitlines() if line.startswith('anchor '))
            self.assertIn(f'ANCHORS OK: {hooks} hook', result.stdout, name)

    def test_broken_hooks_fail(self):
        script = str(ADDONS['solo'].parent / 'src' / 'war3map.j')
        cases = {
            'no such line': 'function Trig_BASE_destroy_Actions\nanchor call NoSuchCall()\ninsert set FF_st_inhOut[1] = 0\n',
            'ambiguous line': 'function Trig_BASE_destroy_Actions\nanchor else\ninsert set FF_st_inhOut[1] = 0\n',
            'no such function': 'function Trig_does_not_exist\nanchor return\ninsert set FF_st_inhOut[1] = 0\n',
            'neither replace nor insert': 'function Trig_BASE_destroy_Actions\nanchor else\n',
        }
        with tempfile.TemporaryDirectory() as work:
            for label, text in cases.items():
                hooks = Path(work) / 'hooks.txt'
                hooks.write_text(text)
                self.assertNotEqual(runner('check-anchors', script, str(hooks)).returncode, 0, label)

    def test_stats_hooks_count_the_maps_gold_moves(self):
        hooks = (ADDONS['799x'] / 'anchors.txt').read_text()
        for counter in ('FF_st_poolOut', 'FF_st_inhOut', 'FF_st_inhIn'):
            self.assertRegex(hooks, rf'(?m)^insert +set {counter}\[', counter)
        transfer = function_body(ADDONS['799x'].parent / 'src' / 'war3map.j', 'FFP_Transfer')
        self.assertIn('set FF_st_poolIn[targetId] = FF_st_poolIn[targetId] + amount', transfer, '799X counts pool_in itself')

    def test_kill_credit_hook_drops_the_living_killer_rule(self):
        self.assertIn('replace if ( udg_temp_killing_unit == null ) then', (ADDONS['solo'] / 'anchors.txt').read_text())
        self.assertIn('if udg_temp_killing_unit == null then', function_body(
            ADDONS['799x'].parent / 'src' / 'war3map.j', 'Trig_Multiboard_Update_Func005C'), '799X does it itself')
        self.assertNotIn('IsUnitAliveBJ(killer)', (LEAGUE / '10-killlog.j').read_text())


class LeagueRulesTest(unittest.TestCase):
    """T4, T5, T7, T9: rules of the league addons that are visible in their source."""

    def test_debug_mode_knows_every_admin(self):
        debug = (ADDONS['799x'] / '50-debug.j').read_text()
        admins = [line.strip() for line in (REPO / 'data' / 'admins.txt').read_text().splitlines()
                  if line.strip() and not line.startswith('#')]
        self.assertTrue(admins)
        for tag in admins:
            self.assertIn(f'"{tag}"', debug)

    def test_true_sight_stays_with_the_bots_and_the_named_observers(self):
        vision = (LEAGUE / '40-botvision.j').read_text()
        self.assertIn('SetPlayerAlliance(bot, Player(i), ALLIANCE_SHARED_VISION, false)', vision)
        self.assertIn('call FF_bv_Unshare(Player(i))', vision)
        self.assertIn('GetPlayerTeam(p) == 4 and (FF_IsBotName(name) or FF_bv_IsTrueSightName(name))',
                      function_body(LEAGUE / '40-botvision.j', 'FF_bv_IsTrueSightObserver'))
        self.assertNotRegex(vision, 'ALLIANCE_PASSIVE|SetPlayerAllianceState')

    def test_stats_rows(self):
        stats = (LEAGUE / '15-stats.j').read_text()
        keys = re.findall(r'FF_st_V\(",([a-z_]+)=', stats)
        self.assertEqual(keys, ['given', 'recv', 'pool_out', 'pool_in', 'inh_out', 'inh_in', 'mined', 'tech', 'ukills',
                                'hkills', 'razed', 'food', 'koth_gold', 'hero_lvl', 'deny_own', 'deny_ally', 'tm_casts',
                                'tm_hits', 'tm_creeps', 'tm_denied', 'tm_saves', 'creeps', 'creep_gold', 'atk_lvl',
                                'def_lvl', 'race_lvl', 'team_res', 'dmg_out', 'dmg_bld', 'dmg_in'])
        self.assertIn('call FF_st_V(",ukills=", udg_unit_kills[slot])', stats)
        self.assertIn('",state=left,left_t=" + FF_st_leftT[slot]', stats)
        self.assertIn('if FF_STATS_DAMAGE then', stats)
        sources = '\n'.join(p.read_text() for p in [*LEAGUE.glob('*.j'), *[f for a in ADDONS.values() for f in a.glob('*.j')]])
        self.assertNotRegex(sources, 'PLAYER_SCORE_(UNITS|HEROES)_KILLED', 'kills come from the map, not the score screen')

    def test_deny_units_are_the_footmen_and_tier_1_spawns(self):
        rows = list(csv.DictReader((REPO / 'data' / 'spawns.csv').open(encoding='utf-8')))
        wanted = sorted(r['Code'] for r in rows if int(r['Tier']) <= 1)
        listed = sorted(re.findall(r"'(\w{4})'", function_body(LEAGUE / '15-stats.j', 'FF_st_IsFeedUnit')))
        self.assertEqual(listed, wanted)

    def test_usage_rows(self):
        usage = (LEAGUE / '16-usage.j').read_text()
        for kind in ('"use,"', '"skills,"', '"pick,"', '"baseup,"', '"buy"', '"used"', '"modes,sel="', '"koth,"'):
            self.assertIn(kind, usage)
        chat = function_body(LEAGUE / '16-usage.j', 'FF_us_OnChat')
        self.assertNotRegex(chat, 'Preload|FF_gr_Flush', 'the chat handler never writes the file')
        self.assertIn('FF_US_CHAT_BURST', chat)
        self.assertIn('EVENT_PLAYER_UNIT_SELL_ITEM', function_body(LEAGUE / '16-usage.j', 'FF_EarlyInit'))

    def test_bot_hosted_games(self):
        common = LEAGUE / '00-common.j'
        hosts = sorted(re.findall(r'"([^"]+#\d+)"', function_body(common, 'FF_IsHostBotName')))
        self.assertEqual(hosts, ['CoralShark#113567', 'LustyPuppy#1929', 'OhNaahs#1537'])
        bots = function_body(common, 'FF_IsBotName')
        self.assertIn('"MangoThief#115445"', bots)
        self.assertIn('if FF_IsHostBotName(name) then', bots)
        self.assertIn('set FF_hostBotGame = FF_HostBotInGame()', (LEAGUE / '90-init.j').read_text())
        self.assertIn('call ConditionalTriggerExecute(gg_trg_MODE_set_pub_game)', (ADDONS['solo'] / 'anchors.txt').read_text())
        own = (ADDONS['799x'].parent / 'src' / 'war3map.j').read_text(encoding='utf-8', errors='replace')
        self.assertRegex(own, r'(?s)// RC6BOT HOST BEGIN\s+if FF_hostBotGame then.*?gg_trg_MODE_set_pub_game_default',
                         '799X starts a bot-hosted game in Pub mode itself')


if __name__ == '__main__':
    unittest.main()

"""Shared test data: the real files the tests read, and helpers to build a run dir from them."""
import shutil
from pathlib import Path

from tests.common.paths import DOCS_DIR, REPO

SAMPLE = DOCS_DIR / "ff_result-sample.txt"
CONTRACT = DOCS_DIR / "result-contract.md"
COMMON_J = REPO / "league" / "00-common.j"
E2E_OVERRIDES = REPO / "tests" / "e2e" / "addons" / "core" / "object_overrides.csv"
PROBE_EXPECT = REPO / "tests" / "e2e" / "probe_expect.csv"
KILLLOG_ROWS = ["owner,unit,hero,unit_died,hero_died",
                "(Paladin) Alpha#1111,187,2,40,1",
                "Delta#4444,60,1,90,2",
                "herokill,24:01,Alpha#1111,Delta#4444,O004,12"]


def preload_file(rows):
    """A Preload file's text holding `rows`, wrapped the way WC3 writes it."""
    body = "".join(f'\tcall Preload( "{r}" )\n' for r in rows)
    return f"function PreloadFiles takes nothing returns nothing\n\n\tcall PreloadStart()\n{body}" \
           "\tcall PreloadEnd( 0.0 )\n\nendfunction\n"


def make_run(root, bot=False, token="123"):
    """A finished e2e run dir built from the result sample: the addon's head record, the result file, END.

    Args:
        root: The folder to create the run in.
        bot: Whether the client is on the bot list (token file names, a kill log).
        token: The game token on a bot client.

    Returns:
        The run dir.
    """
    run = Path(root) / "run"
    run.mkdir()
    name = f"ff_result_{token}.txt" if bot else "ff_result.txt"
    shutil.copy2(SAMPLE, run / name)
    head = f"e2e,local=0,bot={1 if bot else 0},file={name},token={token if bot else ''}"
    (run / "ff_e2e.txt").write_text(preload_file([head, "END"]))
    if bot:
        (run / f"ff_killlog_{token}.txt").write_text(preload_file(KILLLOG_ROWS))
    return run

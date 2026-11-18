#!/usr/bin/env python3
"""Plays one map in the real WC3 client (the ~/wc3-test Proton prefix) and collects what it wrote.

    tests/e2e/run.py <map.w3x> <out dir> [--lobby <name>] --done <file>[:<marker>] [--timeout s] [--collect glob ...]

How a map is started: the map is copied to Maps/Test, Battle.net (auto-login) is started and asked to launch WC3
(`-nowfpause -windowmode windowed` in Battle.net.config's launch arguments, removed again in every case), and the
runner clicks through the menus like a player: Single Player, Custom Games, the Test folder, the map found by its
lobby name (`--lobby`, the build's FF_MAP_NAME) in the Quick Filter, Create, Start Game. The lobby seats the map's
own Computer slots, and the client in the first User slot (an observer slot when every seat is a computer), like
the fleet's bots. `-loadfile` is not used: since WC3 3.0.1 a game started with it ignores the Battle.net login,
shows its own login screen and, logged in there, never loads the map.

While the game runs, the map's test addon asks for input through CustomMapData/ff_e2e_phase.txt (Preload rows):

  * `WAIT <n> chat <text>`: type <text> into the game chat, once per <n>;
  * `WAIT <n> key <key>`: press one key, once per <n> (a shop's command-card hotkey);
  * `WAIT <n> click <x> <y>`: click at (x, y), fractions of the game's 4:3 UI area (a dialog; client.ui_point); repeated every 6 s while the
    row is there;
  * `WAIT <n> seq <step>;<step>...`: a series of inputs, once per <n>, for a game paused by its own menu (the
    Allies menu): `key <key>`, `tap <x> <y>` (one click, never repeated), `wait <seconds>`, `shot` (a screenshot).

A screenshot follows each. The run ends when <file> holds <marker> (default END) as its last record. It fails on
the timeout (screenshot kept), or as soon as the game crashes: its process is gone or its crash reporter is up. A
crash leaves crash.txt (when, and the done file's last record) and WC3's new crash reports (Errors/) in the out dir.

Only a test client is used: a prefix under ~/wc3-test (or FF_WC3_PREFIX), never ~/wc3-stage. The client normally
logs in by itself (Battle.net auto-login); when its saved session is gone, bnet_login.py types the test account's
credentials.

While the map loads, the game's memory is watched: a map whose object data WC3 misreads makes it allocate without end
on the loading bar. Above FF_WC3_LOAD_RSS_MAX_GB (default 7; a good load of our maps peaks at about 4.4 GB), or when
the game exits before the map writes a file, the run stops at once, without a second attempt. Every program runs
memory-capped as well (client.scoped, FF_WC3_MEMORY_MAX), so such a map can't take the rest of the PC down.

Exit codes: 0 done, 1 timeout, crash or no game, 2 the login needs manual help, 3 the map crashed or ran out of
memory while loading.
"""
import argparse
import fnmatch
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.paths import default_client  # noqa: E402
from tests.common.preload import read_rows  # noqa: E402
from tests.e2e import bnet_login  # noqa: E402
from tests.e2e.client import BNET, WC3_PROC, Client, log  # noqa: E402

PHASE_FILE = "ff_e2e_phase.txt"
LOAD_POLLS, LOAD_POLL_S = 60, 5
CLICK_AFTER_S, CLICK_REPEAT_S = 4, 6
LAUNCH_ATTEMPTS = 2
CRASH_FILE = "crash.txt"
MENU_WAIT_S = 150
# The menu route, in window pixels of the client's windowed game (1402x824, frame included, as a screenshot shows
# it); `menu_px` scales them to another window size.
MENU_SIZE = (1402, 824)
MENU = {
    "single_player": (1125, 338),
    "custom_games": (1125, 318),
    "quick_filter": (830, 136),
    "first_row": (700, 197),
    "first_match": (700, 233),  # inside a folder, below "(up one level)"
    "open": (1196, 650),        # Open Folder / Create / Start Game: one button
}
# Points that tell the screens apart: the main menu's four teal buttons, the in-game login's blue panel.
MAIN_MENU_POINTS = ((1030, 338), (1030, 408), (1030, 548), (1030, 618))
LOGIN_POINTS = ((1030, 338), (700, 200), (640, 470))
EXIT_LOAD_CRASH = 3
LOAD_RSS_MAX_KB = int(float(os.environ.get("FF_WC3_LOAD_RSS_MAX_GB", "7")) * 1024 * 1024)
_WAIT = re.compile(r"WAIT (\d+) (chat|key|click|seq) (.*)$")
_STEP = re.compile(r"(key \S+|tap [\d.]+ [\d.]+|wait [\d.]+|shot)$")


@dataclass(frozen=True)
class Wait:
    """An input request from the map's test addon (a `WAIT` row of the phase file).

    Attributes:
        phase: The addon's phase number (one request per phase).
        action: `chat`, `key`, `click` or `seq`.
        arg: The text to type, the key, `<x> <y>` for a click, or the `;`-separated steps of a sequence.
    """

    phase: str
    action: str
    arg: str

    @classmethod
    def parse(cls, row):
        """Reads a phase-file row.

        Returns:
            The request, or None when the row is no valid WAIT row.
        """
        m = _WAIT.match(row)
        if not m:
            return None
        w = cls(*m.groups())
        if w.action == "click" and not re.fullmatch(r"[\d.]+ [\d.]+", w.arg):
            return None
        if w.action == "key" and not re.fullmatch(r"\S+", w.arg):
            return None
        if w.action == "seq" and not all(_STEP.match(st.strip()) for st in w.arg.split(";")):
            return None
        return w


class Session:
    """One game in the client: answering the addon's input requests until the done marker appears.

    Attributes:
        c: The client.
        win: The game window.
        out: Where screenshots go.
        handled: Phases whose chat / key request was answered.
        clicked: Phase to the time of its last click.
        start: When the game started.
    """

    def __init__(self, c, win, out):
        self.c, self.win, self.out = c, win, out
        self.handled, self.clicked = set(), {}
        self.start = time.time()

    def answer(self, w):
        """Answers one input request (a no-op when it is not due)."""
        HANDLERS[w.action](self, w)

    def chat(self, w):
        """Types the chat line once."""
        if w.phase in self.handled:
            return
        self.handled.add(w.phase)
        log(f"phase {w.phase}: chat {w.arg!r}")
        self.c.chat(self.win, w.arg)
        time.sleep(1.5)
        self.c.screenshot(self.win, self.out / f"chat-{w.phase}.png")

    def key(self, w):
        """Presses the key once."""
        if w.phase in self.handled:
            return
        self.handled.add(w.phase)
        log(f"phase {w.phase}: key {w.arg}")
        self.c.press(self.win, w.arg)
        time.sleep(1.5)
        self.c.screenshot(self.win, self.out / f"key-{w.phase}.png")

    def click(self, w):
        """Clicks a dialog button; a dialog pauses the game, so it is clicked again until the map drops the row."""
        now = time.time()
        if now - self.start < CLICK_AFTER_S or now - self.clicked.get(w.phase, 0) < CLICK_REPEAT_S:
            return
        if w.phase not in self.clicked:
            log(f"phase {w.phase}: click {w.arg} (dialog)")
        self.clicked[w.phase] = now
        x, y = map(float, w.arg.split())
        self.c.click(self.win, x, y)
        time.sleep(1)
        self.c.screenshot(self.win, self.out / f"click-{w.phase}.png")

    def seq(self, w):
        """Runs a series of inputs once, with a screenshot after each key, click and `shot`."""
        if w.phase in self.handled:
            return
        self.handled.add(w.phase)
        log(f"phase {w.phase}: seq {w.arg}")
        for i, step in enumerate(st.strip() for st in w.arg.split(";")):
            what, *args = step.split()
            if what == "wait":
                time.sleep(float(args[0]))
                continue
            if what == "key":
                self.c.press(self.win, args[0])
            elif what == "tap":
                self.c.click(self.win, float(args[0]), float(args[1]))
            time.sleep(1)
            self.c.screenshot(self.win, self.out / f"seq-{w.phase}-{i}.png")

    def play(self, done_file, marker, timeout):
        """Answers requests until `done_file` ends with `marker`.

        Returns:
            `done` when the marker appeared, `crash` when the game crashed, `timeout` otherwise.
        """
        end = time.time() + timeout
        while time.time() < end:
            for row in read_rows(self.c.data / PHASE_FILE) or []:
                w = Wait.parse(row)
                if w:
                    self.answer(w)
            rows = read_rows(self.c.data / done_file)
            if rows and rows[-1] == marker:
                return "done"
            if self.c.wc3_crashed():
                self.record_crash(rows)
                return "crash"
            time.sleep(2)
        return "timeout"

    def record_crash(self, rows):
        """Writes crash.txt (seconds into the game, the done file's last record) and copies WC3's new crash reports
        (a folder each: Crash.txt, War3Log.txt, War3.dmp)."""
        last = rows[-1] if rows else "(none)"
        log(f"the game crashed after {int(time.time() - self.start)}s; last record: {last}")
        (self.out / CRASH_FILE).write_text(f"after={int(time.time() - self.start)}s\nlast={last}\n")
        time.sleep(5)  # the reporter writes its folder a moment after the crash
        errors = self.c.docs / "Errors"
        for d in sorted(errors.iterdir()) if errors.is_dir() else []:
            if d.is_dir() and d.stat().st_mtime >= self.start:
                shutil.copytree(d, self.out / "Errors" / d.name, dirs_exist_ok=True)


HANDLERS = {"chat": Session.chat, "key": Session.key, "click": Session.click, "seq": Session.seq}


def matches(name, patterns):
    """Whether a file name matches any of the glob patterns."""
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def data_files(c, patterns):
    """The CustomMapData files matching the patterns, sorted."""
    return sorted(f for f in c.data.iterdir() if matches(f.name, patterns)) if c.data.is_dir() else []


def game_started(c, patterns):
    """Whether game-time code wrote a file (the phase file does not count: the map writes it while loading)."""
    return any(f.name != PHASE_FILE for f in data_files(c, patterns))


def load_problem(rss_kb, ceiling_kb=LOAD_RSS_MAX_KB):
    """Why a map that is still loading has failed for good, or None while it may still load.

    Args:
        rss_kb: The game's resident memory in kB; None when the game no longer runs.
        ceiling_kb: The most memory a load may take.

    Returns:
        The reason, or None.
    """
    if rss_kb is None:
        return "WC3 exited while the map loaded"
    if rss_kb > ceiling_kb:
        return f"WC3 took {rss_kb / 2**20:.1f} GB while the map loaded (limit {ceiling_kb / 2**20:.1f} GB)"
    return None


def menu_px(c, win, point):
    """A MENU point in the actual window's pixels."""
    g = c.geometry(win)
    w, h = int(g.get("WIDTH", MENU_SIZE[0])), int(g.get("HEIGHT", MENU_SIZE[1]))
    return round(point[0] * w / MENU_SIZE[0]), round(point[1] * h / MENU_SIZE[1])


def is_main_menu(colours):
    """Whether the sampled MAIN_MENU_POINTS show the main menu's teal buttons."""
    return all(px and px[0] < 20 and 35 <= px[1] <= 70 and 35 <= px[2] <= 70 for px in colours)


def is_login(colours):
    """Whether the sampled LOGIN_POINTS show WC3's own Battle.net login (a blue panel)."""
    return all(px and px[2] - px[0] >= 60 for px in colours)


def wait_main_menu(c, win, out):
    """Waits for WC3's main menu.

    Raises:
        SystemExit: EXIT_MANUAL when WC3 shows its own login instead, 1 when the menu doesn't show up.
    """
    end = time.time() + MENU_WAIT_S
    while time.time() < end:
        if is_main_menu([c.pixel(win, *menu_px(c, win, p)) for p in MAIN_MENU_POINTS]):
            return
        if is_login([c.pixel(win, *menu_px(c, win, p)) for p in LOGIN_POINTS]):
            c.screenshot(win, out / "wc3-login.png")
            log("WC3 shows its own Battle.net login: the Battle.net session didn't reach the game (log in once by "
                "hand, then re-run)")
            sys.exit(bnet_login.EXIT_MANUAL)
        time.sleep(3)
    c.screenshot(win, out / "no-menu.png")
    sys.exit(f"e2e: WC3's main menu didn't show up within {MENU_WAIT_S}s (see no-menu.png)")


def start_from_menu(c, win, lobby, out):
    """Clicks from the main menu into a single-player game of the map named `lobby` in Maps/Test."""
    def click(name, wait):
        c.click_px(win, *menu_px(c, win, MENU[name]))
        time.sleep(wait)

    def filter_for(text):
        # a click right after a list change is sometimes lost; the box keeps its text between folders
        click("quick_filter", 1)
        click("quick_filter", 0.5)
        c.xdo("key", "ctrl+a", "BackSpace")
        c.type_text(text)
        time.sleep(3)

    wait_main_menu(c, win, out)
    click("single_player", 3)
    click("custom_games", 4)
    click("custom_games", 6)  # the first click is lost while the menu slides in
    filter_for("Test")
    click("first_row", 1.5)
    click("open", 6)  # Open Folder
    filter_for(lobby)
    click("first_match", 1.5)
    c.screenshot(win, out / "menu-map.png")
    click("open", 6)  # Create
    c.screenshot(win, out / "menu-lobby.png")
    click("open", 2)  # Start Game


def open_game_window(c):
    """Launches WC3 through Battle.net, logging Battle.net in first when its session is gone.

    Returns:
        The game window.

    Raises:
        SystemExit: Code 2 when the login needs manual help, 1 when no game window shows up.
    """
    c.run_bg(BNET, "--exec=launch W3")
    win = c.wc3_window(120)
    if win:
        return win
    # Battle.net shows its login window instead of starting the game: log in, then launch once more
    if bnet_login.login_window(c) is not None:
        if not bnet_login.login(c):
            log("the Battle.net login needs manual help (see the client's logs)")
            sys.exit(bnet_login.EXIT_MANUAL)
        c.run_bg(BNET, "--exec=launch W3")
        win = c.wc3_window(120)
    if not win:
        sys.exit("e2e: no WC3 window (is the client logged in? see ~/wc3-test/logs)")
    return win


def launch(c, src, out, patterns, lobby):
    """Starts the map (through the menus, `start_from_menu`) and gets past its loading screen.

    The loading screen sometimes hangs at ~85 %: when the map writes nothing within 5 minutes, the game is closed
    and launched once more. A game that exits or runs out of memory while loading (`load_problem`) is not retried.

    Returns:
        The game window.

    Raises:
        SystemExit: When the map did not start in LAUNCH_ATTEMPTS attempts (code 1), or crashed while loading
            (EXIT_LOAD_CRASH).
    """
    for attempt in range(1, LAUNCH_ATTEMPTS + 1):
        c.close_bnet()
        c.set_args("-nowfpause -windowmode windowed")
        c.start_bnet()
        win = open_game_window(c)
        c.set_args(None)
        start_from_menu(c, win, lobby, out)
        # "Press any key to continue": a key sent while the map still loads is lost, and space in the game only
        # moves the camera, so space is pressed until the map writes a file
        for _ in range(LOAD_POLLS):
            time.sleep(LOAD_POLL_S)
            if game_started(c, patterns):
                return win
            problem = load_problem(c.wc3_rss_kb())
            if problem:
                c.screenshot(win, out / "loadcrash.png")
                log(f"{problem}: object data WC3 misreads? (runner `object-layout <map>`)")
                c.close_wc3()
                sys.exit(EXIT_LOAD_CRASH)
            c.press(win, "space")
        c.screenshot(win, out / f"loadhang-{attempt}.png")
        log(f"the map did not start within {LOAD_POLLS * LOAD_POLL_S}s (load hang, attempt {attempt})")
        c.close_wc3()
    sys.exit(f"e2e: the map did not start {LAUNCH_ATTEMPTS} times in a row")


def prepare(c, src, out, patterns):
    """Empties the out dir, removes stale outputs (they would pass a check the game never reached), and makes the map
    the only one in Maps/Test (the runner's folder): a map whose name the list can't show is then still the one row."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for f in data_files(c, patterns):
        f.unlink()
    maps = c.docs / "Maps" / "Test"
    maps.mkdir(parents=True, exist_ok=True)
    for old in maps.glob("*.w3x"):
        old.unlink()
    shutil.copy2(src, maps / src.name)


def main(argv=None):
    """Plays the map and collects its files.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        0 when the done marker appeared, 1 on the timeout or a crash.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lobby", default="", help="the map's lobby name (its FF_MAP_NAME), to find it in the menu; "
                    "empty: the only map in Maps/Test (for a map the list shows without a name)")
    ap.add_argument("--done", required=True, help="CustomMapData file[:marker] that ends the run")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--collect", nargs="*", default=[], help="CustomMapData globs to copy out")
    ap.add_argument("--client", type=Path, default=default_client())
    a = ap.parse_args(argv)

    c = Client(a.client)
    src = a.map.resolve()
    done_file, _, marker = a.done.partition(":")
    marker = marker or "END"
    patterns = [done_file, PHASE_FILE, *a.collect]
    log(f"client {c.root} (WC3 {c.build_version()}), map {src.name}")
    prepare(c, src, a.out, patterns)
    outcome, win, t0 = "timeout", None, time.time()
    try:
        win = launch(c, src, a.out, patterns, a.lobby)
        c.screenshot(win, a.out / "start.png")
        outcome = Session(c, win, a.out).play(done_file, marker, a.timeout)
        c.screenshot(win, a.out / ("end.png" if outcome == "done" else f"{outcome}.png"))
    finally:
        c.set_args(None)
        if win or c.pids(WC3_PROC):
            c.close_wc3()
        for f in data_files(c, patterns):
            shutil.copy2(f, a.out / f.name)
        log(f"{outcome.upper() if outcome != 'done' else 'done'} after {int(time.time() - t0)}s -> {a.out}")
    return 0 if outcome == "done" else 1


if __name__ == "__main__":
    sys.exit(main())

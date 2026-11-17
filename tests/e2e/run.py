#!/usr/bin/env python3
"""Plays one map in the real WC3 client (the ~/wc3-test Proton prefix) and collects what it wrote.

    tests/e2e/run.py <map.w3x> <out dir> --done <file>[:<marker>] [--timeout s] [--collect glob ...]

How a map is started (docs/testing-plan.md, "launch route"): with Battle.net closed, WC3's extra launch arguments
in Battle.net.config get `-loadfile <map>`. Battle.net (auto-login) is started and asked to launch WC3, which loads
straight into a single-player game of the map; Battle.net exits by itself once the game runs. The arguments are
removed again in every case.

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
credentials. Exit codes: 0 done, 1 timeout, crash or no game, 2 the login needs manual help.
"""
import argparse
import fnmatch
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
from tests.e2e.client import BNET, WC3_PROC, WIN_DOCS, Client, log  # noqa: E402

PHASE_FILE = "ff_e2e_phase.txt"
LOAD_POLLS, LOAD_POLL_S = 60, 5
CLICK_AFTER_S, CLICK_REPEAT_S = 4, 6
LAUNCH_ATTEMPTS = 2
CRASH_FILE = "crash.txt"
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


def launch(c, src, out, patterns):
    """Starts the map and gets past its loading screen.

    The loading screen sometimes hangs at ~85 %: when the map writes nothing within 5 minutes, the game is closed
    and launched once more.

    Returns:
        The game window.

    Raises:
        SystemExit: When the map did not start in LAUNCH_ATTEMPTS attempts.
    """
    for attempt in range(1, LAUNCH_ATTEMPTS + 1):
        c.close_bnet()
        c.set_args(f'-loadfile "{WIN_DOCS}\\Maps\\Test\\{src.name}" -nowfpause -windowmode windowed')
        c.start_bnet()
        win = open_game_window(c)
        c.set_args(None)
        # "Press any key to continue": a key sent while the map still loads is lost, and space in the game only
        # moves the camera, so space is pressed until the map writes a file
        for _ in range(LOAD_POLLS):
            time.sleep(LOAD_POLL_S)
            if game_started(c, patterns):
                return win
            c.press(win, "space")
        c.screenshot(win, out / f"loadhang-{attempt}.png")
        log(f"the map did not start within {LOAD_POLLS * LOAD_POLL_S}s (load hang, attempt {attempt})")
        c.close_wc3()
    sys.exit(f"e2e: the map did not start {LAUNCH_ATTEMPTS} times in a row")


def prepare(c, src, out, patterns):
    """Empties the out dir, removes stale outputs (they would pass a check the game never reached), copies the map."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for f in data_files(c, patterns):
        f.unlink()
    maps = c.docs / "Maps" / "Test"
    maps.mkdir(parents=True, exist_ok=True)
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
        win = launch(c, src, a.out, patterns)
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

"""The WC3 test client: a Proton prefix with Battle.net and Warcraft III, driven with real X11 input.

WC3 and Battle.net run under Wine, which ignores input sent to a window directly (xdotool's --window keys), so
every key and click goes to the focused window, like real keyboard and mouse input.
"""
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.paths import WC3_INSTALL, refuse_stage  # noqa: E402

WIN_DOCS = r"C:\users\steamuser\Documents\Warcraft III"
BNET = "C:/Program Files (x86)/Battle.net/Battle.net.exe"
LAUNCHER = "C:/Program Files (x86)/Battle.net/Battle.net Launcher.exe"
WC3_PROC = re.compile(r"_retail_.x86_64.Warcraft III\.exe")
CRASH_PROC = re.compile(r"BlizzardError\.exe")
BNET_PROC = re.compile(r"Battle\.net\.exe")
BNET_MAIN_PROC = re.compile(r"Battle\.net\.exe --in-process")
AUTO_LOGIN_WAIT_S = 25
TYPE_DELAY_MS = "40"


def log(msg):
    """Prints a progress line of the e2e runner."""
    print(f"e2e: {msg}", flush=True)



def ui_point(width, height, fx, fy):
    """The window pixel of a point in WC3's UI area.

    WC3 lays its menus and dialogs out on a 4:3 area as tall as the window and centred in it; a wider window only
    adds empty margins left and right. A position measured as a fraction of that area stays on the same button at
    any window size.

    Args:
        width: The window's width in pixels.
        height: The window's height in pixels.
        fx: The x position as a fraction of the UI area's width (0 = its left edge).
        fy: The y position as a fraction of the window's height (0 = the top).

    Returns:
        The (x, y) pixel inside the window.
    """
    ui_width = height * 4 / 3
    return round((width - ui_width) / 2 + fx * ui_width), round(height * fy)

class Client:
    """One test client folder (~/wc3-test): its prefix, Battle.net, the game window and the X11 input to it.

    Attributes:
        root: The client folder.
        pfx: The Proton prefix.
        docs: WC3's Documents folder in the prefix (maps, CustomMapData).
        cfg: Battle.net's config file (holds WC3's extra launch arguments).
        data: WC3's CustomMapData folder, where the maps write their files.
        proton: The Proton launcher used to start programs in the prefix.
        logs: Where program output and screenshots of the login go.
        env: The environment every program is started with (display, prefix).
    """

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        refuse_stage(self.root, "e2e")
        self.pfx = self.root / "compat" / "pfx"
        users = self.pfx / "drive_c" / "users" / "steamuser"
        self.docs = users / "Documents" / "Warcraft III"
        self.cfg = users / "AppData" / "Roaming" / "Battle.net" / "Battle.net.config"
        self.data = self.docs / "CustomMapData"
        protons = sorted((self.root / "proton").glob("*/proton"))
        if not (self.cfg.is_file() and protons):
            sys.exit(f"e2e: no logged-in test client at {self.root} (set FF_WC3_PREFIX)")
        self.proton = protons[-1]
        self.logs = self.root / "logs"
        self.logs.mkdir(exist_ok=True)
        uid = os.getuid()
        xauth = sorted(glob.glob(f"/run/user/{uid}/.mutter-Xwaylandauth.*"))
        self.env = dict(os.environ,
                        DISPLAY=os.environ.get("DISPLAY", ":0"),
                        XAUTHORITY=os.environ.get("XAUTHORITY", xauth[0] if xauth else ""),
                        WAYLAND_DISPLAY=os.environ.get("WAYLAND_DISPLAY", "wayland-0"),
                        DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{uid}/bus",
                        STEAM_COMPAT_CLIENT_INSTALL_PATH=str(self.root / "steam-stub"),
                        STEAM_COMPAT_DATA_PATH=str(self.root / "compat"),
                        WINEDLLOVERRIDES="locationapi=d", WINEDEBUG="-all")

    def build_version(self):
        """WC3's build number (e.g. `3.0.0.12345`) from the install's .build.info, or `?`."""
        info = self.root / WC3_INSTALL / ".build.info"
        m = re.search(r"\|(\d+\.\d+\.\d+\.\d+)\|", info.read_text()) if info.is_file() else None
        return m.group(1) if m else "?"

    # processes

    def run_bg(self, exe, *args, logname="wc3.log"):
        """Starts a Windows program in the prefix, detached, its output appended to logs/<logname>."""
        with open(self.logs / logname, "a") as out:
            return subprocess.Popen([str(self.proton), "run", exe, *args], env=self.env, stdout=out,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)

    @staticmethod
    def pids(pattern):
        """The process ids whose command line matches `pattern` (Steam's own wrapper excluded)."""
        res = []
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                args = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if pattern.search(args) and "steam.exe" not in args.split(" ")[0]:
                res.append(int(d.name))
        return res

    @staticmethod
    def terminate(pids, sig=signal.SIGTERM):
        """Sends `sig` (default SIGTERM) to each process that still runs."""
        for p in pids:
            try:
                os.kill(p, sig)
            except ProcessLookupError:
                pass

    def bnet_running(self):
        """Whether Battle.net runs."""
        return bool(self.pids(BNET_PROC))

    # X11

    def xdo(self, *args, stdin=None):
        """Runs xdotool with the client's display.

        Args:
            *args: xdotool's arguments.
            stdin: Text passed on standard input (for `type --file -`), or None.

        Returns:
            xdotool's output, split into words.
        """
        r = subprocess.run(["xdotool", *args], env=self.env, capture_output=True, text=True, input=stdin)
        return r.stdout.split()

    def windows(self, name):
        """The ids of the windows whose title matches the regex `name`."""
        return self.xdo("search", "--name", name)

    def geometry(self, win):
        """A window's geometry: a dict with WIDTH, HEIGHT, X, Y (as text)."""
        r = subprocess.run(["xdotool", "getwindowgeometry", "--shell", str(win)], env=self.env,
                           capture_output=True, text=True)
        return dict(line.split("=", 1) for line in r.stdout.split() if "=" in line)

    def viewable(self, win):
        """Whether a window is mapped on screen (Battle.net keeps hidden windows around)."""
        r = subprocess.run(["xwininfo", "-id", str(win)], env=self.env, capture_output=True, text=True)
        return "IsViewable" in r.stdout

    def screenshot(self, win, path):
        """Saves a screenshot of a window."""
        subprocess.run(["import", "-window", str(win), str(path)], env=self.env, capture_output=True)

    def press(self, win, *keys):
        """Focuses a window and presses keys in it."""
        self.xdo("windowactivate", "--sync", str(win))
        self.xdo("key", *keys)

    def type_text(self, text):
        """Types text into the focused window; the text goes through stdin, never onto a command line."""
        self.xdo("type", "--delay", TYPE_DELAY_MS, "--file", "-", stdin=text)

    def click(self, win, fx, fy):
        """A left click at (fx, fy), as fractions of the game's UI area (see ui_point)."""
        g = self.geometry(win)
        x, y = ui_point(int(g["WIDTH"]), int(g["HEIGHT"]), fx, fy)
        self.xdo("windowactivate", "--sync", str(win))
        self.xdo("mousemove", "--window", str(win), str(x), str(y))
        # a click right after the move is sometimes lost: let the game see the pointer there first
        time.sleep(0.4)
        self.xdo("mousedown", "1")
        time.sleep(0.1)
        self.xdo("mouseup", "1")

    def chat(self, win, text):
        """Sends a chat line in the game: Return, the text, Return."""
        self.press(win, "Return")
        time.sleep(0.4)
        self.type_text(text)
        time.sleep(0.2)
        self.xdo("key", "Return")

    # Battle.net

    def close_bnet(self):
        """Closes Battle.net cleanly, also when it hides in the tray.

        Raises:
            SystemExit: When it does not close.
        """
        if not self.bnet_running():
            return
        # closing its main window (the big one) exits Battle.net without damaging the saved session
        for w in self.windows("^Battle.net$"):
            if int(self.geometry(w).get("WIDTH", 0)) > 800:
                self.xdo("windowclose", w)
        if self.wait_until(lambda: not self.bnet_running(), 20):
            return
        # in the tray instead (a fresh login does that): launching the game makes it exit cleanly
        # (GameLaunchWindowBehavior), then the game is closed again
        log("Battle.net hid in the tray; launching WC3 once to make it exit")
        self.run_bg(BNET, "--exec=launch W3")
        if self.wc3_window(120):
            self.wait_until(lambda: not self.bnet_running(), 40)
            time.sleep(5)
            self.close_wc3()
        if self.bnet_running():
            sys.exit("e2e: Battle.net did not close (close it, then re-run)")

    def set_args(self, args):
        """Sets WC3's extra launch arguments in Battle.net's config, or removes them (None)."""
        cfg = json.loads(self.cfg.read_text())
        w3 = cfg.setdefault("Games", {}).setdefault("w3", {})
        if args:
            w3["AdditionalLaunchArguments"] = args
        else:
            w3.pop("AdditionalLaunchArguments", None)
        self.cfg.write_text(json.dumps(cfg, indent=4))

    def start_bnet(self):
        """Starts Battle.net and gives its auto-login time to finish.

        Raises:
            SystemExit: When Battle.net does not start.
        """
        self.run_bg(LAUNCHER, logname="battlenet.log")
        if not self.wait_until(lambda: self.pids(BNET_MAIN_PROC), 90):
            sys.exit("e2e: Battle.net didn't start")
        time.sleep(AUTO_LOGIN_WAIT_S)

    # WC3

    def wc3_window(self, timeout):
        """Waits for the game window.

        Returns:
            Its id, or None after `timeout` seconds.
        """
        end = time.time() + timeout
        while time.time() < end:
            w = self.windows("^Warcraft III$")
            if w:
                return w[0]
            time.sleep(3)
        return None

    def wc3_crashed(self):
        """Whether the game is gone or its crash reporter (BlizzardError.exe) is up."""
        return not self.pids(WC3_PROC) or bool(self.pids(CRASH_PROC))

    def close_wc3(self):
        """Closes the game; a process that lingers after its window closed (Proton) is terminated, and so is a
        crash reporter."""
        for w in self.windows("^Warcraft III$"):
            self.xdo("windowclose", w)
        # the crash reporter's dialog ignores the close and SIGTERM
        self.terminate(self.pids(CRASH_PROC), signal.SIGKILL)
        pids = self.pids(WC3_PROC)
        if not self.wait_until(lambda: not any(Path(f"/proc/{p}").exists() for p in pids), 30):
            self.terminate(pids)
            time.sleep(3)

    @staticmethod
    def wait_until(cond, seconds, step=2):
        """Polls `cond` every `step` seconds for up to `seconds`; returns whether it became true."""
        for _ in range(max(1, seconds // step)):
            if cond():
                return True
            time.sleep(step)
        return bool(cond())

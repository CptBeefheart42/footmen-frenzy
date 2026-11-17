#!/usr/bin/env python3
"""Logs the e2e test client's Battle.net back in when its saved session is gone (a visible "Battle.net Login"
window and no game starting). tests/e2e/run.py calls it by itself; by hand:

    python3 tests/e2e/bnet_login.py [--client ~/wc3-test]

The credentials come from ~/.config/footmen-frenzy/e2e-bnet.env (FF_E2E_BNET_EMAIL / FF_E2E_BNET_PASSWORD; the test
account only, never in git). The file must be readable by its owner only. The credentials are never printed,
logged or put on a command line (xdotool reads them from stdin).

The login is real input, like the rest of the runner: close a stale login window, start Battle.net fresh, focus the
login window, click the email field, select all, type the email, Tab, the password, Return. A screenshot of each
step (taken before anything is typed) goes to <client>/logs/. A fresh login may ask for an e-mail security code;
that needs manual entry (exit 2, said so).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.paths import default_client  # noqa: E402
from tests.e2e.client import BNET_PROC, Client, log  # noqa: E402

ENV = Path.home() / ".config" / "footmen-frenzy" / "e2e-bnet.env"
EMAIL_KEY, PASSWORD_KEY = "FF_E2E_BNET_EMAIL", "FF_E2E_BNET_PASSWORD"
# the email field, relative to the 362x719 login window (the password field is the next Tab stop)
EMAIL_AT = (0.5, 0.40)
EXIT_MANUAL = 2


def parse_env(text):
    """Parses a shell-style env file: `KEY=value` lines, `export ` allowed, quotes stripped, `#` comments.

    Args:
        text: The file's content.

    Returns:
        A dict of key to value.
    """
    vals = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, eq, v = line.partition("=")
        if not eq:
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        vals[k.strip()] = v
    return vals


def creds(env=ENV):
    """Reads the test account's credentials.

    Args:
        env: The env file.

    Returns:
        (email, password).

    Raises:
        SystemExit: When the file is readable by others, or lacks either value.
    """
    env = Path(env)
    if not env.is_file():
        sys.exit(f"bnet_login: no credentials file {env}")
    if env.stat().st_mode & 0o077:
        sys.exit(f"bnet_login: {env} is readable by others; chmod 600 it")
    vals = parse_env(env.read_text())
    email, pw = vals.get(EMAIL_KEY), vals.get(PASSWORD_KEY)
    if not (email and pw):
        sys.exit(f"bnet_login: no credentials in {env}")
    return email, pw


def login_window(c):
    """The visible "Battle.net Login" window, or None (a logged-in Battle.net keeps a hidden one around)."""
    return next((w for w in c.windows("^Battle.net Login$") if c.viewable(w)), None)


def login(c, wait=60):
    """Types the credentials into the login window.

    Args:
        c: The client.
        wait: Seconds to wait for the login window to go away.

    Returns:
        True once logged in (the window is gone); False when it stays (a security code or a captcha is asked).
    """
    email, pw = creds()
    w = login_window(c)
    if w is None:
        log("bnet_login: no login window (already logged in?)")
        return True
    c.xdo("windowactivate", "--sync", w)
    time.sleep(1)
    c.screenshot(w, c.logs / "login-0.png")
    c.click(w, *EMAIL_AT)
    time.sleep(0.5)
    c.xdo("key", "ctrl+a")
    c.type_text(email)
    time.sleep(0.3)
    c.xdo("key", "Tab")
    time.sleep(0.3)
    c.type_text(pw)
    time.sleep(0.3)
    c.xdo("key", "Return")
    log("bnet_login: credentials entered; waiting for the login to finish")
    for _ in range(wait // 2):
        time.sleep(2)
        if login_window(c) is None or not c.bnet_running():
            log("bnet_login: logged in")
            return True
    c.screenshot(w, c.logs / "login-2.png")
    log(f"bnet_login: the login window is still there — a security code or a captcha? (see {c.logs}/login-2.png; "
        "an e-mail security code needs manual entry)")
    return False


def restart_bnet(c):
    """Starts Battle.net fresh, so its login page is clean.

    A running Battle.net gets its login window closed; one that only hides in the tray (a dead session does) is
    terminated, which is safe because it is logged out and has no session left to damage.
    """
    if c.bnet_running():
        w = login_window(c)
        if w is not None:
            c.xdo("windowclose", w)
        if not c.wait_until(lambda: not c.bnet_running(), 30):
            c.terminate(c.pids(BNET_PROC))
            c.wait_until(lambda: not c.bnet_running(), 30)
    if not c.bnet_running():
        c.start_bnet()
        c.wait_until(lambda: login_window(c) is not None or c.windows("^Battle.net$"), 90)
        time.sleep(5)


def main(argv=None):
    """Logs the client in.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        0 when logged in, 2 when the login needs manual help (no window, a security code).
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", type=Path, default=default_client())
    a = ap.parse_args(argv)
    c = Client(a.client)
    restart_bnet(c)
    if login_window(c) is None and not c.windows("^Battle.net$"):
        log("bnet_login: Battle.net showed neither its login nor its main window")
        return EXIT_MANUAL
    return 0 if login(c) else EXIT_MANUAL


if __name__ == "__main__":
    sys.exit(main())

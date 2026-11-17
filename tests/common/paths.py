"""Where things are: the repository, the e2e folder and the WC3 test client."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E2E_DIR = REPO / "tests" / "e2e"
DOCS_DIR = REPO / "docs"
WC3_INSTALL = Path("compat", "pfx", "drive_c", "Program Files (x86)", "Warcraft III")


def default_client():
    """The test client's root folder: $FF_WC3_PREFIX, else ~/wc3-test.

    Returns:
        The path (not checked for existence).
    """
    return Path(os.environ.get("FF_WC3_PREFIX", str(Path.home() / "wc3-test"))).expanduser()


def refuse_stage(path, tool):
    """Stops a tool that was pointed at the pre-3.0 reference install (~/wc3-stage), which is never touched.

    Args:
        path: The client path the tool was given.
        tool: The tool's name, for the message.

    Raises:
        SystemExit: When the path lies in ~/wc3-stage.
    """
    if "wc3-stage" in str(path):
        sys.exit(f"{tool}: refusing ~/wc3-stage (the pre-3.0 reference install is never touched); "
                 "point it at the test client")

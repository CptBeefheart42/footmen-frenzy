"""PASS/FAIL bookkeeping shared by the test tools."""
from dataclasses import dataclass, field


@dataclass
class Result:
    """One named check's outcome.

    Attributes:
        name: What was checked, in words.
        ok: Whether it held.
        detail: What was seen instead (printed on failure only).
    """

    name: str
    ok: bool
    detail: str = ""


@dataclass
class Checks:
    """A list of named checks, printed as one `PASS <name>` / `FAIL <name> — <detail>` line each.

    Attributes:
        label: The summary line's prefix, e.g. `e2e check`.
        results: Every check recorded so far, in order.
    """

    label: str
    results: list = field(default_factory=list)

    def check(self, name, ok, detail=""):
        """Records a check.

        Args:
            name: What was checked.
            ok: Whether it held (any truthy value passes).
            detail: What was seen, shown when it failed.
        """
        self.results.append(Result(name, bool(ok), str(detail)))

    def eq(self, name, got, want):
        """Records a check that `got` equals `want`.

        Args:
            name: What was checked.
            got: The value found.
            want: The value expected.
        """
        self.check(name, got == want, f"got {got!r}, want {want!r}")

    def between(self, name, got, lo, hi):
        """Records a check that `got` is an integer within lo..hi (inclusive).

        Args:
            name: What was checked.
            got: The value found (an int or its text; anything else fails).
            lo: The lowest accepted value.
            hi: The highest accepted value.
        """
        try:
            v = int(got)
        except (TypeError, ValueError):
            self.check(name, False, f"got {got!r}, want an integer in {lo}..{hi}")
            return
        self.check(name, lo <= v <= hi, f"got {v}, want {lo}..{hi}")

    @property
    def failed(self):
        """The failed checks."""
        return [r for r in self.results if not r.ok]

    def report(self, show_pass=True):
        """Prints every check and a summary line.

        Args:
            show_pass: False prints the failures only (for tools with many routine checks).

        Returns:
            The exit code: 1 when any check failed, else 0.
        """
        for r in self.results:
            if r.ok and show_pass:
                print(f"PASS {r.name}")
            elif not r.ok:
                print(f"FAIL {r.name}" + (f" — {r.detail}" if r.detail else ""))
        n_failed = len(self.failed)
        print(f"{self.label}: {len(self.results) - n_failed} passed, {n_failed} failed")
        return 1 if n_failed else 0

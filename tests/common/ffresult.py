"""The files the map writes for the league bot, as Python objects: the result file and the kill log.

The record formats are described in docs/result-contract.md; docs/ff_result-sample.txt is a complete example.
"""
from dataclasses import dataclass, field

from tests.common.kv import as_int, parse_kv

STATS_KEYS = ("given recv pool_out pool_in inh_out inh_in mined tech ukills hkills razed food deny_own deny_ally "
              "tm_casts tm_hits tm_creeps tm_denied tm_saves creeps creep_gold atk_lvl def_lvl race_lvl team_res koth_gold "
              "dmg_out dmg_bld dmg_in hero_lvl").split()
RESULT_EVENTS = ("afk", "sub", "out", "sidedead", "winner", "placement", "gameend")
MAP_EVENTS = ("pick", "baseup", "buy", "used")
USE_CATS = ("item", "unit", "tech", "tower", "spell", "cmd", "pawn", "rsch", "rlvl")
STATES = ("alive", "out", "left")
KNOWN_OTHER = ("format", "modes", "koth")
KILLLOG_HEADER = "owner,unit,hero,unit_died,hero_died"


class FormatError(ValueError):
    """A row that does not have the shape its record kind requires."""


@dataclass(frozen=True)
class Event:
    """A result or map event row: `<kind>,<head>,<subject>,<extra>...`.

    Attributes:
        kind: The record kind (`afk`, `out`, `sidedead`, `winner`, `placement`, `gameend`, `pick`, `baseup`, `buy`,
            `used`).
        head: The game time (mm:ss); for a `placement` the place number.
        subject: The slot (`afk`, `out`, `pick`, `baseup`, `buy`, `used`) or the side (`sidedead`, `winner`,
            `placement`); empty for `gameend`.
        extra: The remaining fields (a name, the members, a hero, base or item code, how a hero was picked).
    """

    kind: str
    head: str
    subject: str = ""
    extra: tuple = ()

    @classmethod
    def parse(cls, kind, rest):
        """Builds an event from a row's kind and the text after its first comma."""
        fields = rest.split(",")
        return cls(kind, fields[0], fields[1] if len(fields) > 1 else "", tuple(fields[2:]))


@dataclass
class StatsRow:
    """One participant's `stats` numbers (the two rows of a write merged).

    Attributes:
        slot: The participant's slot (1-based, as in the roster).
        values: Every `key=value` field of the rows, as text (`t` and `state` included).
    """

    slot: int
    values: dict = field(default_factory=dict)

    @property
    def t(self):
        """The game time (mm:ss) of the write the rows belong to."""
        return self.values.get("t")

    @property
    def state(self):
        """`alive`, `out` or `left`."""
        return self.values.get("state")

    def int(self, key):
        """A key's value as an integer, or None when it is missing or not an integer."""
        return as_int(self.values.get(key))

    def merge(self, other):
        """Adds a row of the same write (same `t=`); a row of a later write replaces this one.

        Args:
            other: The next `stats` row of this slot.

        Returns:
            The merged row.
        """
        if other.t == self.t:
            return StatsRow(self.slot, {**self.values, **other.values})
        return other


@dataclass
class FFResultFile:
    """A parsed `ff_result*.txt`.

    Attributes:
        rows: Every row, in file order.
        mode: The `mode` row's value (`ffa` / `6v6`), or None.
        roster: Slot to player name, from `roster` and `roster_more`.
        stats: Slot to the participant's merged `stats` row.
        events: The result and map events, in file order.
        use: (slot, category) to {code: count}, from the `use` rows.
        skills: (slot, hero code) to the skill order, from the `skills` rows.
        other: Every other row (`format`, `modes`, `koth` and anything unknown), raw.
    """

    rows: list = field(default_factory=list)
    mode: str = None
    roster: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    use: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    other: list = field(default_factory=list)

    @classmethod
    def parse(cls, rows):
        """Parses the rows of a result file.

        Args:
            rows: The file's rows (tests.common.preload.read_rows).

        Returns:
            The parsed file.

        Raises:
            FormatError: When a row's slot or count is not an integer, or a row lacks a required field.
        """
        res = cls(rows=list(rows))
        for row in res.rows:
            try:
                res._add(row)
            except (ValueError, IndexError) as e:
                raise FormatError(f"{row!r}: {e}") from e
        return res

    def _add(self, row):
        kind, _, rest = row.partition(",")
        if kind == "mode":
            self.mode = rest
        elif kind in ("roster", "roster_more"):
            for entry in filter(None, rest.split(";")):
                slot, _, name = entry.partition(":")
                self.roster[int(slot)] = name
        elif kind == "stats":
            slot, *pairs = rest.split(",")
            new = StatsRow(int(slot), parse_kv(pairs))
            old = self.stats.get(new.slot)
            self.stats[new.slot] = old.merge(new) if old else new
        elif kind in RESULT_EVENTS or kind in MAP_EVENTS:
            self.events.append(Event.parse(kind, rest))
        elif kind == "use":
            slot, cat, *pairs = rest.split(",")
            counts = self.use.setdefault((int(slot), cat), {})
            counts.update({k: int(v) for k, v in parse_kv(pairs).items()})
        elif kind == "skills":
            slot, hero, order = rest.split(",", 2)
            self.skills.setdefault((int(slot), hero), []).extend(order.split(";"))
        else:
            self.other.append(row)

    def events_of(self, kind):
        """The events of one kind, in file order."""
        return [e for e in self.events if e.kind == kind]

    @property
    def result_kinds(self):
        """The kinds of the result events, in file order (what `gameend` must come last in)."""
        return [e.kind for e in self.events if e.kind in RESULT_EVENTS]

    @property
    def winner(self):
        """The winning side (`team1`, `west`, ...), or None."""
        win = self.events_of("winner")
        return win[0].subject if win else None

    @property
    def placement_sides(self):
        """The sides in placement order."""
        return [e.subject for e in self.events_of("placement")]

    @property
    def places(self):
        """The placement numbers in file order (1..N without ties when the file is right)."""
        return [as_int(e.head) for e in self.events_of("placement")]

    def stat(self, slot, key):
        """A participant's stats value as an integer, or None (no row, no key or not an integer)."""
        row = self.stats.get(slot)
        return row.int(key) if row else None

    def other_rows(self, kind):
        """The raw rows of a kind kept in `other` (`modes`, `koth`, `format`)."""
        return [r for r in self.other if r.startswith(kind + ",")]

    @property
    def unknown(self):
        """Rows of a kind this model does not know."""
        return [r for r in self.other if r.partition(",")[0] not in KNOWN_OTHER]


@dataclass(frozen=True)
class OwnerRow:
    """A kill log owner row: one player's kills and deaths."""

    unit: int
    hero: int
    unit_died: int
    hero_died: int


@dataclass
class KillLog:
    """A parsed `ff_killlog_<token>.txt`.

    Attributes:
        header: The first row (KILLLOG_HEADER when the file is right).
        owner_rows: The raw owner rows (`<name>,<unit>,<hero>,<unit_died>,<hero_died>`).
        feed: The hero kill rows (`herokill,...`), split.
    """

    header: str = ""
    owner_rows: list = field(default_factory=list)
    feed: list = field(default_factory=list)

    @classmethod
    def parse(cls, rows):
        """Parses the rows of a kill log.

        Args:
            rows: The file's rows.

        Returns:
            The parsed kill log.
        """
        log = cls(header=rows[0] if rows else "")
        for row in rows[1:]:
            if row.startswith("herokill,"):
                log.feed.append(row.split(","))
            else:
                log.owner_rows.append(row)
        return log

    @staticmethod
    def _owner_ok(row):
        parts = row.split(",")
        return len(parts) == 5 and all(as_int(x) is not None for x in parts[1:])

    @property
    def bad_owner_rows(self):
        """Owner rows without exactly 5 fields or with a non-integer count."""
        return [r for r in self.owner_rows if not self._owner_ok(r)]

    @property
    def bad_feed_rows(self):
        """Feed rows without exactly 6 fields."""
        return [",".join(f) for f in self.feed if len(f) != 6]

    @property
    def owners(self):
        """Player name to their OwnerRow, from the well-formed owner rows."""
        out = {}
        for row in self.owner_rows:
            if self._owner_ok(row):
                name, *counts = row.split(",")
                out[name] = OwnerRow(*map(int, counts))
        return out

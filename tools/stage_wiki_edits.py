"""Prepare changed map payloads from a balance wiki proposal for review."""
import argparse
from collections import defaultdict
from contextlib import ExitStack
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory

from export_wiki import ROOT, add_inputs, family_name, open_source
from wiki.atlas import GROUPS
from wiki.map_values import WTS_ENTRY, decode_objects


def object_edits(data, name, changes):
    valid = {}
    def remember(uid, field, level, pointer, value, entry, kind, offset, token):
        valid[offset] = (uid, field, level, pointer, kind, value)
    ext = name.rsplit(".", 1)[1]
    list(decode_objects(data, name, ext in {"w3a", "w3q", "w3d"}, {}, remember))
    out = bytearray(data)
    # A longer ability list shifts subsequent byte offsets. Apply edits from
    # the end of the original payload so every recorded offset stays valid.
    for change in sorted(changes, key=lambda c: c["offset"], reverse=True):
        offset = change["offset"]
        expected = tuple(change[k] for k in ("id", "field", "level", "pointer", "kind", "original"))
        if valid.pop(offset, None) != expected:
            raise ValueError(f"Object identity or original value differs at {name} byte {offset}")
        value = change["value"]
        if expected[4] == 3:
            if not isinstance(value, str) or "\0" in value:
                raise ValueError("Expected an object string without NUL bytes")
            end = data.index(b"\0", offset)
            try:
                data[offset:end].decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                encoding = "cp1252"
            out[offset:end] = value.encode(encoding)
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Expected a finite numeric value")
        if expected[4] == 0 and type(value) is not int:
            raise ValueError("Integer fields require whole numbers")
        struct.pack_into("<i" if expected[4] == 0 else "<f", out, offset, value)
    return bytes(out)


def wts_edits(data, name, changes):
    source = data.decode("utf-8-sig")
    pending = {c["id"]: c for c in changes}
    if len(pending) != len(changes):
        raise ValueError("Duplicate string table edit")
    def replace(match):
        change = pending.pop(int(match["id"]), None)
        if change is None:
            return match[0]
        original = match["body"].replace("\r\n", "\n")
        if original != change["original"]:
            raise ValueError(f'Original WTS string differs at {change["id"]}')
        value = change["value"]
        if not isinstance(value, str) or "\0" in value or re.search(r"(?m)^\}\s*$", value):
            raise ValueError("Invalid WTS string content")
        ending = "\r\n" if match["header"].endswith("\r\n") else "\n"
        footer = match["footer"]
        if value and footer.startswith("}"):
            footer = ending + footer
        return match["header"] + value.replace("\r\n", "\n").replace("\n", ending) + footer
    updated = WTS_ENTRY.sub(replace, source)
    if pending:
        raise ValueError(f"Missing string table entries {list(pending)}")
    return (b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b"") + updated.encode("utf-8")


def line_edits(data, name, changes):
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    data = data[len(bom):]
    try:
        lines = data.decode("utf-8").splitlines(keepends=True)
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "cp1252"
        lines = data.decode(encoding).splitlines(keepends=True)
    seen = set()
    for change in changes:
        n = change["line"]
        if type(n) is not int or not 1 <= n <= len(lines) or n in seen:
            raise ValueError(f"Invalid or duplicate {name} line {n}")
        seen.add(n)
        original = lines[n-1].rstrip("\r\n")
        if original != change["original"]:
            raise ValueError(f"Original line differs at {name}:{n}")
        new = change["value"]
        if not isinstance(new, str) or any(c in new for c in "\0\r\n"):
            raise ValueError("Expected one source line")
        lines[n-1] = new + lines[n-1][len(original):]
    return bom + "".join(lines).encode(encoding)


def stage(args):
    raw = args.proposal.read_bytes()
    proposal = json.loads(raw)
    family = family_name(args.project)
    if proposal["schema"] != 1 or proposal["family"] != family or not proposal["changes"]:
        raise ValueError("Expected a nonempty proposal for the selected map family")
    objects = {f"{p}.{ext}" for ext in GROUPS.values() for p in ("war3map", "war3mapSkin")}
    line_sources = {"war3map.j", "war3mapMisc.txt", "war3mapSkin.txt", "war3mapExtra.txt"}
    grouped = defaultdict(list)
    for change in proposal["changes"]:
        name = change["entry"]
        if not ((name in objects and change["type"] == "object") or
                (name in line_sources and change["type"] == "line") or
                (name == "war3map.wts" and change["type"] == "wts")):
            raise ValueError(f"Unsupported edit target {name}")
        grouped[name].append(change)
    expected = proposal["source"]
    result = {}
    with ExitStack() as stack:
        read, source = open_source(args, stack)
        if "sha256" in source:
            if source["sha256"] != expected.get("sha256"):
                raise ValueError("Proposal and selected archive have different SHA256s")
        elif expected.get("input") != source["input"] or not expected.get("entries"):
            raise ValueError("Select the same input used to generate this wiki")
        for name, changes in grouped.items():
            data = read(name)
            if data is None or ("entries" in source and source["entries"][name] != expected["entries"].get(name)):
                raise ValueError(f"Source data changed for {name}")
            edit = object_edits if name in objects else wts_edits if name == "war3map.wts" else line_edits
            result[name] = edit(data, name, changes)
    root = ROOT / "build/wiki-edits" / args.project
    root.mkdir(parents=True, exist_ok=True)
    target = root / sha256(raw).hexdigest()[:16]
    with TemporaryDirectory(dir=root) as tmp:
        work = Path(tmp) / "payloads"
        work.mkdir()
        for name, data in result.items():
            (work / name).write_bytes(data)
        (work / "proposal.json").write_bytes(raw)
        if target.exists():
            if any((target / name).read_bytes() != data for name, data in {**result, "proposal.json": raw}.items()):
                raise ValueError(f"Existing staged files changed in {target}")
        else:
            work.rename(target)
    print(f"Staged {len(result)} changed payload(s) for review in {target}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("project", choices=["799x", "solo", "ffa"])
    cli.add_argument("proposal", type=Path)
    add_inputs(cli)
    try:
        stage(cli.parse_args())
    except (ValueError, KeyError, OSError, TypeError, OverflowError, struct.error, RuntimeError) as error:
        cli.exit(1, f"Could not stage wiki edits: {error}\n")

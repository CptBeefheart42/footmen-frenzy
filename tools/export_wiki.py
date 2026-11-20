"""Export repeatable, source-attributed Warcraft map tables for the Footmen Frenzy wiki."""
import argparse
from contextlib import ExitStack
from functools import lru_cache
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from wiki.archive import Archive
from wiki.atlas import atlas
from wiki.portraits import attach_portraits
from wiki.reachability import trace
from wiki.asset_review import review
from wiki.map_values import object_rows, object_table, script_rows, string_table, text


ROOT = Path(__file__).resolve().parents[1]
REPORTS = json.loads((ROOT / "tools/wiki/reports.json").read_text(encoding="utf-8"))
OBJECT_NOTE = ("Map object fields, including values from map-defined parents. A dash means the "
               "selected input supplies no value for that field at this level and data pointer. "
               "Game-install defaults and later trigger changes are outside this table.")
SCRIPT_NOTE = ("Literal values assigned by the map’s initialization functions. A dash marks an "
               "absent assignment. Game modes and later triggers can change these settings.")


def family_name(project):
    """Return the family used to label an export or match an edit proposal."""
    if project == "ffa":
        return "FFA Foots"
    return json.loads((ROOT / "projects" / project / "project.json").read_text(encoding="utf-8"))["map_type"]


def open_source(args, stack):
    if args.project == "ffa" and not (args.map or args.directory):
        raise ValueError("Select an external FFA archive with --map or extracted data with --directory.")
    project = ROOT / "projects" / args.project
    if args.directory:
        directory = args.directory.resolve(strict=True)
        source = {"input": directory.name, "entries": {}}

        def read(name):
            path = (directory / name.replace("\\", "/")).resolve()
            if not path.is_relative_to(directory) or not path.is_file():
                return None
            data = path.read_bytes()
            source["entries"][name] = sha256(data).hexdigest()
            return data
        return read, source
    if args.map:
        path = args.map
    elif args.source == "built":
        path = ROOT / "build" / args.project / (args.project + "-dev.w3x")
    else:
        path = project / "base.w3x"
    digest = sha256(path.read_bytes()).hexdigest()
    archive = stack.enter_context(Archive(path))

    def read(name):
        try:
            return archive.read(name)
        except KeyError:
            return None
    return read, {"input": path.name, "sha256": digest}


def collect(args, read):
    strings = string_table(read("war3map.wts") or b"")

    @lru_cache(None)
    def objects(extension):
        return object_table(read, extension, strings)

    @lru_cache(None)
    def script():
        data = read("war3map.j")
        if data is None:
            raise ValueError("Missing war3map.j")
        return text(data)

    tables = []
    for key in REPORTS if args.report == "all" else [args.report]:
        report = REPORTS[key]
        selected = args.fields or list(report["fields"])
        columns = {"id": "ID", "name": "Name"}
        if "extension" in report:
            if any(len(f) != 4 or not f.isascii() for f in selected):
                raise ValueError("Object fields must be four-character, case-sensitive rawcodes.")
            if report["extension"] in {"w3a", "w3q", "w3d"}:
                columns.update(level="Level", pointer="Data pointer")
            rows = object_rows(objects(report["extension"]), report, selected)
            note = OBJECT_NOTE
        else:
            if any(not re.fullmatch(r"udg_\w+", f) for f in selected):
                raise ValueError("Script fields must be udg_ array names from the report functions.")
            columns["index"] = "Index"
            rows = script_rows(script(), objects("w3u"), report, selected)
            note = SCRIPT_NOTE
        columns.update({f: report["fields"].get(f, f) for f in selected})
        if args.ids:
            rows = [row for row in rows if "id" in row and row["id"].value in args.ids]
            missing = set(args.ids) - {row["id"].value for row in rows}
            if missing:
                raise ValueError(f"No matching {key} records with selected fields for {', '.join(sorted(missing))}")
        if args.fields:
            missing = [f for f in selected if not any(f in row for row in rows)]
            if missing:
                raise ValueError(f"No recorded values for {', '.join(missing)} in this selection")
        if not rows:
            raise ValueError(f"No matching rows for {key}")
        tables.append(dict(key=key, title=report["title"], note=note, columns=columns,
                           rows=[{k: vars(row[k]) if k in row else None for k in columns} for row in rows]))
    return tables


def render(data, fragment):
    source = data["source"]
    fingerprint = source.get("sha256") or sha256(json.dumps(source["entries"], sort_keys=True).encode()).hexdigest()
    title = escape(data["family"] + " wiki values")
    body = [f'<header><h1>{title}</h1><p>{escape(source["input"])}<br><small>'
            f'{"Map" if "sha256" in source else "Input manifest"} SHA256 <code>{fingerprint}</code></small></p></header>']
    if len(data["reports"]) > 1:
        links = [f'<a href="#{r["key"]}">{escape(r["title"])}</a>' for r in data["reports"]]
        body.append('<nav aria-label="Reports">' + " · ".join(links) + "</nav>")
    for report in data["reports"]:
        cols = report["columns"]
        body.append(f'<section id="{report["key"]}"><h2>{escape(report["title"])}</h2>'
                    f'<p>{escape(report["note"])}</p><div class="scroll"><table><thead><tr>')
        for key, label in cols.items():
            body.append(f'<th scope="col" title="{escape(key)}">{escape(label)}</th>')
        body.append("</tr></thead><tbody>")
        for row in report["rows"]:
            body.append("<tr>")
            for key in cols:
                cell = row[key]
                body.append('<td>—</td>' if cell is None else
                            f'<td title="{escape(cell["source"])}">{escape(str(cell["value"]))}</td>')
            body.append("</tr>")
        body.append("</tbody></table></div></section>")
    contents = "\n".join(body)
    if fragment:
        return contents + "\n"
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font:1rem/1.45 system-ui,sans-serif;color:#20372f;max-width:95rem;margin:2rem auto;padding:0 2vw}}
h1,h2{{font-family:Georgia,serif}} h2{{margin:2rem 0 .3rem}} code{{overflow-wrap:anywhere}}
nav,a{{color:#235e47}} .scroll{{overflow:auto}}table{{border-collapse:collapse;font-variant-numeric:tabular-nums}}
td,th{{padding:.36rem .65rem;text-align:left;border-bottom:1px solid #dbe4df}} th{{background:#e8f0eb}}
</style><main>{contents}</main></html>
"""


def add_inputs(parser):
    """Select one complete archive or an extracted map directory."""
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--source", choices=["base", "built"], default="base")
    inputs.add_argument("--map", type=Path, help="Exact .w3x or .w3m archive")
    inputs.add_argument("--directory", type=Path, help="Directory with extracted binary object data and script")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=["799x", "solo", "ffa"])
    add_inputs(parser)
    parser.add_argument("--report", choices=["wiki", "all", *REPORTS], default="wiki")
    parser.add_argument("--fields", nargs="+", help="Object field IDs or JASS array names")
    parser.add_argument("--id", dest="ids", nargs="+", help="One or more case-sensitive object IDs")
    parser.add_argument("--format", choices=["html", "fragment", "json"], default="html")
    parser.add_argument("--output", type=Path, help="Destination file (default under build/wiki-exports)")
    args = parser.parse_args()
    if args.report in {"all", "wiki"} and (args.fields or args.ids):
        parser.error("Choose a single --report when using --fields or --id.")
    if args.report == "wiki" and args.format == "fragment":
        parser.error("Use a table report for a pasteable HTML fragment.")
    if args.map and args.map.suffix.lower() not in {".w3x", ".w3m"}:
        parser.error("--map expects a .w3x or .w3m archive.")
    ext = ".json" if args.format == "json" else ".html"
    if args.output and args.output.suffix.lower() != ext:
        parser.error(f"Use a {ext} destination for --format {args.format}.")
    try:
        with ExitStack() as stack:
            read, source = open_source(args, stack)
            if args.report == "wiki":
                index = atlas(read)
                index["tables"] = []
                index["table_errors"] = {}
                for preset in ("heroes", "spawns"):
                    try:
                        index["tables"].extend(collect(argparse.Namespace(report=preset, fields=None, ids=None), read))
                    except ValueError as error:
                        index["table_errors"][preset] = str(error)
                index["trace"] = trace(index)
                attach_portraits(index, read)
                index["imports"] = review(index, read)
            else:
                tables = collect(args, read)
        family = family_name(args.project)
        data = dict(schema=1, family=family, source=source)
        if args.report == "wiki":
            data.update(index)
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            template = Path(__file__).with_name("wiki") / "browser.html"
            content = payload if args.format == "json" else template.read_text(encoding="utf-8").replace(
                "/* PLAYER_STYLES */", template.with_name("player.css").read_text(encoding="utf-8")).replace(
                "/* PLAYER_SCRIPT */", template.with_name("player.js").read_text(encoding="utf-8")).replace(
                "<!--WIKI_DATA-->", payload.replace("<", "\\u003c"))
        else:
            data["reports"] = tables
            content = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                       if args.format == "json" else render(data, args.format == "fragment"))
        scope = args.report
        if args.ids or args.fields:
            selection = json.dumps([args.ids, args.fields]).encode()
            scope += "-" + sha256(selection).hexdigest()[:12]
        if args.format == "fragment":
            scope += "-fragment"
        folder = args.map.stem if args.map else "extracted" if args.directory else args.source
        output = args.output or ROOT / "build/wiki-exports" / args.project / folder / (scope + ext)
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, delete=False) as temp:
            pending = Path(temp.name)
        try:
            pending.write_bytes(content.encode("utf-8"))
            pending.replace(output)
        finally:
            pending.unlink(missing_ok=True)
        print(output.resolve())
        if args.report == "wiki":
            print(f'{len(index["objects"])} objects, {len(index["functions"])} JASS functions')
        else:
            print(", ".join(f'{r["key"]} ({len(r["rows"])} rows)' for r in tables))
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Wiki export failed: {error}\n")


if __name__ == "__main__":
    main()

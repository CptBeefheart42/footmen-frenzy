"""Build one standalone NorthStar port with the repository's object compiler and MPQ packer."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from urllib.parse import quote
from urllib.request import urlopen

PORTS = Path(__file__).resolve().parent
ROOT = PORTS.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ff"))
from build import check_reachable, check_script, stage_sources
from repo import BUILD, Project
import toolchain

REVISION = "e40cb50fd2394500a4d60ff9b6797bbc8c5061c0"
MEDIA = "https://media.githubusercontent.com/media/NorthStarEnergy/Footmen-Frenzy"


class Port(Project):
    """A standalone project kept outside the set of league builds."""

    @property
    def folder(self):
        return PORTS / self.name


def checked_base(project, sha, local, cache):
    """Read the exact complete map, downloading it once when no local copy is supplied."""
    path = local or cache
    if not local and not path.is_file():
        url = f"{MEDIA}/{REVISION}/projects/{project.name}/release/{quote(project.start_name)}"
        with TemporaryDirectory(dir=cache.parent) as temp:
            fresh = Path(temp) / "map.w3x"
            with urlopen(url, timeout=120) as source, fresh.open("wb") as target:
                shutil.copyfileobj(source, target)
            if hashlib.sha256(fresh.read_bytes()).hexdigest() != sha:
                raise ValueError("Downloaded starting map failed SHA-256 verification")
            fresh.replace(cache)
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise ValueError(f"Starting map failed SHA-256 verification: {path}")
    return path.resolve()


def build_port(slug, local):
    """Compile object text, pack the editable files, and verify names and JASS."""
    meta = json.loads((PORTS / slug / "project.json").read_bytes())
    start = meta["start_map"]
    project = Port(slug, meta["map_type"], start["name"])
    out = BUILD / "northstar" / slug
    out.mkdir(parents=True, exist_ok=True)
    base = checked_base(project, start["sha256"], local, out / "base.w3x")
    final = out / project.start_name
    if final.resolve() == base:
        raise ValueError("Choose an input outside the output path")
    with TemporaryDirectory(dir=out) as stage:
        stage = Path(stage)
        sources = stage_sources(project, stage / "src")
        check_script(sources / "war3map.j")
        packed = stage / "packed.w3x"
        with base.open("rb") as original:
            header = original.read(512)
            archive = base
            if header.startswith(b"HM3W"):
                if original.read(4) != b"MPQ\x1a":
                    raise ValueError("Expected the MPQ archive after the 512-byte lobby header")
                archive = stage / "base.mpq"
                original.seek(512)
                with archive.open("wb") as target:
                    shutil.copyfileobj(original, target)
        args = ["pack", str(archive), str(sources), str(packed), "--binaries", str(project.binaries)]
        if toolchain.run_dotnet_tool("tools/runner", args):
            raise RuntimeError("The native packer could not reproduce the port")
        if toolchain.run_dotnet_tool("tools/runner", ["objects", "check", str(packed), str(project.objects)]):
            raise RuntimeError("Packed object data differs from its editable text")
        if header.startswith(b"HM3W"):
            headed = stage / "headed.w3x"
            with headed.open("wb") as target, packed.open("rb") as rebuilt:
                target.write(header)
                shutil.copyfileobj(rebuilt, target)
            packed = headed
        check_reachable(project, packed)
        packed.replace(final)
    print(final)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=("799x", "solo", "ffa"))
    parser.add_argument("--base", type=Path, help="verified local .w3x to use in place of the download")
    args = parser.parse_args()
    build_port(args.project, args.base)

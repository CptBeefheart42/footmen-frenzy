"""Inventory imports referenced by the trace, including model textures and UI includes."""
from collections import defaultdict, deque
from pathlib import PureWindowsPath
import re
import struct


def review(db, read):
    data = read("war3map.imp")
    if not data:
        return {}
    version, count = struct.unpack_from("<II",data)
    if version != 1:
        raise ValueError(f"Unsupported import table version {version}")
    names = {}
    pos = 8
    def canonical(name):
        return name.replace("/", "\\").replace("\\\\","\\").strip(' "\0').lower()
    for _ in range(count):
        flag = data[pos]
        end = data.index(0,pos+1)
        name = data[pos+1:end].decode("utf-8",errors="replace")
        pos = end+1
        if flag in (5,8):
            name = "war3mapImported\\"+name
        names[canonical(name)] = name
    if pos != len(data):
        raise ValueError("Trailing import table data")
    refs = defaultdict(set)
    def mention(path, source):
        p = canonical(path)
        if p.endswith(".mdl"):
            p = p[:-4]+".mdx"
        if p in names:
            refs[p].add(source)
    trace = db["trace"]
    for key in set(trace["via"]) | set(trace["parents"]) | set(trace["support"]):
        obj = db["objects"][key]
        mention(obj.get("art_file",""),key)
        for f in obj["fields"]:
            if isinstance(f[3],str):
                for v in f[3].split(","):
                    mention(v,key)
        for row in obj["stock"].values():
            for value in row.values():
                for v in value.split(","):
                    mention(v,key)
    for n in trace["functions"]:
        for value in re.findall(r'"([^"\n]+)"',db["functions"][n]["body"]):
            mention(value,"fn/"+n)
    for name,body in db["config"].items():
        if name.startswith("war3map"):
            for line in body.splitlines():
                for v in line.partition("=")[2].split(","):
                    mention(v,"cfg/"+name)
    queue,seen = deque(refs),set()
    while queue:
        p = queue.popleft()
        if p in seen:
            continue
        seen.add(p)
        ext = PureWindowsPath(p).suffix
        if ext not in {".mdx",".fdf",".toc"}:
            continue
        if ".." in PureWindowsPath(p).parts or PureWindowsPath(p).anchor:
            continue
        children = []
        blob = read(names[p]) or b""
        if ext==".mdx":
            children.append(p[:-4]+"_portrait.mdx")
            children.extend(s.decode("latin1") for s in re.findall(rb"[\x20-\x7e]{1,260}\.(?:blp|dds|tga)\x00",blob,re.I))
        else:
            for line in blob.decode("utf-8",errors="replace").splitlines():
                children.extend(re.findall(r'"([^"]+)"',line))
                children.append(line.strip())
        for child in children:
            mention(child,"asset/"+p)
            k = canonical(child)
            if k in refs and k not in seen:
                queue.append(k)
    return {name:sorted(refs.get(key,())) for key,name in sorted(names.items())}

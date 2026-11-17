#!/usr/bin/env bash
# Simulation tests: runs every scenario (tests/simulation/scenarios/*.lua, or the ones given) in a
# fresh Lua state against the transpiled scripts in <lua dir> (common.lua, Blizzard.lua, main.lua,
# solo.lua — `make test-sim` makes them). main_* scenarios run on the main map, solo_* on Solo,
# the rest on both. Prints PASS/FAIL per check (XFAIL for a known bug of the map, T.knownBug), exits
# non-zero on any failure.
#   tests/simulation/run.sh <lua dir> [scenario.lua ...]
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
dir=${1:?usage: run.sh <lua dir> [scenario.lua ...]}
shift
lua=$(command -v texlua || command -v lua5.3 || true)
[ -n "$lua" ] || { echo "simulation: no Lua 5.3 (texlua or lua5.3)" >&2; exit 2; }
for f in common Blizzard; do
	[ -f "$dir/$f.lua" ] || { echo "simulation: $dir/$f.lua missing (make test-sim)" >&2; exit 2; }
done
if [ $# -gt 0 ]; then scenarios=("$@"); else scenarios=("$here"/scenarios/*.lua); fi

pass=0; fail=0; xfail=0; broken=()
for s in "${scenarios[@]}"; do
	b=$(basename "$s" .lua)
	case "$b" in main_*) maps=main ;; solo_*) maps=solo ;; *) maps="main solo" ;; esac
	for m in $maps; do
		if [ ! -f "$dir/$m.lua" ]; then
			echo "FAIL [$m] $b :: $dir/$m.lua missing"; fail=$((fail + 1)); broken+=("$m/$b"); continue
		fi
		out=$("$lua" "$here/run.lua" "$repo/common.j" "$dir" "$m" "$s" 2>&1); rc=$?
		printf '%s\n' "$out" | sed -E "s/^(PASS|FAIL|XFAIL) /\1 [$m] /"
		pass=$((pass + $(printf '%s\n' "$out" | grep -c '^PASS ')))
		fail=$((fail + $(printf '%s\n' "$out" | grep -c '^FAIL ')))
		xfail=$((xfail + $(printf '%s\n' "$out" | grep -c '^XFAIL ')))
		if [ $rc -ne 0 ]; then broken+=("$m/$b"); fi
	done
done
echo "simulation: $pass passed, $fail failed, $xfail known bugs"
[ ${#broken[@]} -eq 0 ] || { echo "simulation: failing scenarios: ${broken[*]}"; exit 1; }

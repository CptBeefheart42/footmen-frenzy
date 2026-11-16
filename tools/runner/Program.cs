using CSharpLua;
using Microsoft.CodeAnalysis;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using War3Net.Build;
using War3Net.Build.Extensions;
using War3Net.Build.Info;
using War3Net.Build.Object;
using War3Net.CodeAnalysis.Jass;
using War3Net.CodeAnalysis.Transpilers;
using War3Net.IO.Mpq;
using FootmenFrenzy.Shared;

// In-repo, non-interactive build runner for the C#-scripted gameplay.
// Compiles the Source project (C# -> Lua via CSharpLua), merges it with the base map's GUI
// triggers, and repacks a playable .w3x. A generalised replica of the parked rework's
// Launcher.Build(launch:false, protect:false), driven entirely by env vars so nothing is
// hardcoded:
//
//   FF_SOURCE      folder containing the Source .csproj         (default: lua/Source)
//   FF_BASEMAP     base map: a .w3x MPQ file OR an extracted folder
//   FF_OUTPUT      output folder                                (default: build)
//   FF_OUTPUT_MAP  output map filename                          (default: target.w3x)
//   FF_MAP_VERSION version stamp for war3map.wts, empty = leave as-is. Replaces every match of
//                  FF_VERSION_PATTERN (a .NET regex; default `7\.9\.9[A-Z](?:-rc\d+)?`, the main
//                  map's token) — the Solo map passes its own, e.g. `(?<=_v)1\.7(?:-\d+)?(?![0-9.])`
//   FF_JASS_ADDONS folder of *.j addons -> the minimal-delta JASS build instead (see below);
//                  FF_JASS_STUB_FUNCS optionally no-ops named base-script functions,
//                  FF_JASS_ANCHORS optionally inserts lines into named base-script functions (see ApplyJassAnchors)
//                  FF_SLOT_CONTROLLERS=computer:0-11 (e2e builds only) makes those players Computer slots
//   FF_LEVEL_DEFAULTS optional path to ability_level_defaults.csv (default: data/ability_level_defaults.csv).
//   FF_MAP_NAME / FF_LOADING_TITLE / FF_CREDITS_LINE  release branding stamped into war3map.wts (lobby name,
//                  loading-screen title, a line appended to the in-game Credits quest); empty = leave as-is
//
//   `verify-map <w3x> [--name S] [--author S] [--loading-title S] [--credits S] [--funcs a,b] [--stubs a,b] [--imports a,b] [--overrides csv] [--anchors txt]`
//                  release gate for a BUILT map (see VerifyMap)
//   `check-anchors <w3x> <anchors.txt>`  dry-runs the anchor hooks on a base map's script (exit 1 if one doesn't apply)
//   `pack <start.w3x> <src dir> <out.w3x> [--script j] [--lfs-cache dir] [--missing file]`  a project's starting map
//                  plus its source files -> a complete map (see Pack)
//                  Every build applies the WC3 3.0 level fill (tools/shared/AbilityLevelFill.cs) to war3map.w3a.
//
// When FF_BASEMAP is a .w3x file it is first extracted to a temp folder, so the same proven
// folder-based AddFiles path is used regardless of input form (preserves imported media).

string repoRoot = Repo.Root;
string sourceFolder = Environment.GetEnvironmentVariable("FF_SOURCE")
    ?? Path.Combine(repoRoot, "lua", "Source");
string baseMapInput = Environment.GetEnvironmentVariable("FF_BASEMAP")
    ?? "";
string outputFolder = Environment.GetEnvironmentVariable("FF_OUTPUT")
    ?? Path.Combine(repoRoot, "build");
string outputMapName = Environment.GetEnvironmentVariable("FF_OUTPUT_MAP") ?? "target.w3x";
const string OUTPUT_SCRIPT_NAME = "war3map.lua";
const bool IS_USING_GUI_TRIGGER_EDITOR = true;

Directory.CreateDirectory(outputFolder);

var blizzardJ = Repo.Data("Blizzard.j");
var commonJ = Repo.Data("common.j");

// Minimal-delta JASS build (FF_JASS_ADDONS = folder of *.j addon files): keeps the base map's
// ORIGINAL war3map.j as the engine script and only injects the plain-JASS addon systems
// (scripting/jass). No transpile, no CSharpLua, no MapBuilder — every other archive entry is
// carried over as-is, so the shipped map differs from the base only by the injected functions
// (and the version stamp). Works on a listfile-less ("protected") base too, since entries are
// addressed by hash, not name; that is why this runs BEFORE the name-based extraction below.
//   FF_JASS_STUB_FUNCS  optional, comma-separated `returns nothing` functions of the base script
//                       to turn into no-ops (a base map's own, incompatible writers of the same
//                       output files — e.g. the Solo map's SoloFootsFFWrite*).
//   FF_JASS_MAP_ADDONS  optional folder of addons for THIS map only (e.g. scripting/jass-solo): its *.j are
//                       injected after the common ones, `call FF_MapInit()` after `call FF_Init()`, and every
//                       file under <folder>/imports is added to the archive under its relative path.
// Every JASS build also applies the WC3 3.0 fixes: the ability level fill and the dotted asset file names
// (see AssetPaths).
// Release gate for a built map (names, credits, addon hooks, 3.0 level fill) — no base map needed.
if (args.Length > 0 && args[0] == "verify-map")
    return VerifyMap(args.Skip(1).ToArray());
if (args.Length > 0 && args[0] == "check-anchors")
    return CheckAnchors(args.Skip(1).ToArray());
if (args.Length > 0 && args[0] == "jass-to-lua")
    return JassToLua(args.Skip(1).ToArray(), commonJ, blizzardJ);
if (args.Length > 0 && args[0] == "pack")
    return Pack.Run(args.Skip(1).ToArray());

string jassAddonsDir = Environment.GetEnvironmentVariable("FF_JASS_ADDONS");
if (!string.IsNullOrEmpty(jassAddonsDir))
{
    if (!File.Exists(baseMapInput))
    {
        Console.WriteLine($"FF_BASEMAP must be a .w3x file for the JASS addons build: {baseMapInput}");
        return 1;
    }
    return BuildJassAddons(baseMapInput, jassAddonsDir, outputFolder, outputMapName,
        Environment.GetEnvironmentVariable("FF_MAP_VERSION"), VersionPattern(),
        Environment.GetEnvironmentVariable("FF_JASS_STUB_FUNCS"), commonJ, blizzardJ,
        Environment.GetEnvironmentVariable("FF_JASS_MAP_ADDONS"), Environment.GetEnvironmentVariable("FF_JASS_ANCHORS"));
}

// A .w3x file is extracted to a temp folder so AddFiles can pull in all imported media.
string baseMapFolder = baseMapInput;
if (File.Exists(baseMapInput))
{
    baseMapFolder = ExtractMpq(baseMapInput);
}
else if (!Directory.Exists(baseMapInput))
{
    Console.WriteLine($"FF_BASEMAP not found: {baseMapInput}");
    return 1;
}

// Migration tooling subcommands (read-only; reduce the per-slice cost of porting triggers to C#).
// Usage: dotnet run --project scripting/build -c Release -- <gen-globals|report|extract <name>>
if (args.Length > 0)
{
    var jassForTool = Path.Combine(baseMapFolder, "war3map.j");
    if (!File.Exists(jassForTool))
    {
        Console.WriteLine($"war3map.j not found in base map ({baseMapFolder}); tooling needs a JASS base.");
        return 1;
    }
    var jassText = File.ReadAllText(jassForTool);
    switch (args[0])
    {
        case "gen-globals":
            GenerateGlobals(jassText, Path.Combine(sourceFolder, "MapGlobals.g.cs"));
            return 0;
        case "report":
            MigrationReport(jassText);
            return 0;
        case "extract":
            if (args.Length < 2) { Console.WriteLine("usage: extract <triggerBaseName>"); return 1; }
            ExtractTrigger(jassText, args[1]);
            return 0;
        default:
            Console.WriteLine($"unknown subcommand '{args[0]}' (gen-globals | report | extract <name>)");
            return 1;
    }
}

var map = Map.Open(baseMapFolder);
// WC3 3.0 level fill — MapBuilder re-serializes war3map.w3a from map.AbilityObjectData below.
if (FillLevels(map.Info, map.AbilityObjectData) == null)
    return 1;
if (ApplyObjectOverrides(map.AbilityObjectData, Environment.GetEnvironmentVariable("FF_OBJECT_OVERRIDES")) < 0)
    return 1;

// The CSharpLua pipeline only runs on Lua maps. If the base ships a JASS script (war3map.j,
// no war3map.lua) we transpile its existing GUI script to Lua up-front, flip the map's declared
// language, and drop the .j so it isn't packed alongside the generated .lua. The transpiled Lua
// is spliced back in below (see the GUI-merge block) — exactly where a Lua base's war3map.lua
// would be used.
string transpiledGuiLua = null;
var jassScriptPath = Path.Combine(baseMapFolder, "war3map.j");
bool baseIsJass = File.Exists(jassScriptPath) && !File.Exists(Path.Combine(baseMapFolder, "war3map.lua"));
if (baseIsJass)
{
    Console.WriteLine("Base map is JASS — transpiling war3map.j -> Lua ...");
    transpiledGuiLua = TranspileJassToLua(jassScriptPath, commonJ, blizzardJ);
    File.Delete(jassScriptPath); // don't pack the stale JASS script next to the new Lua one
    if (map.Info != null)
        map.Info.ScriptLanguage = ScriptLanguage.Lua;
}

var builder = new MapBuilder(map);
AddFolderAsMpqFiles(builder, baseMapFolder);

// Bake the configurable admin list (scripting/admins.txt) into Admins.g.cs before compiling, so
// admins are managed from a plain text file in the repo instead of hardcoded battletags.
GenerateAdmins(Path.Combine(repoRoot, "lua", "admins.txt"), Path.Combine(sourceFolder, "Admins.g.cs"));

string csc = null;
var csproj = Directory.EnumerateFiles(sourceFolder, "*.csproj", SearchOption.TopDirectoryOnly).Single();
var compiler = new Compiler(csproj, outputFolder, string.Empty, null, "War3Api.*;WCSharp.*", "", csc, false, null, string.Empty)
{
    IsExportMetadata = true,
    IsModule = false,
    IsInlineSimpleProperty = false,
    IsPreventDebugObject = true,
    IsCommentsDisabled = true,
};

var coreSystemFiles = CSharpLua.CoreSystem.CoreSystemProvider.GetCoreSystemFiles(CSharpLua.CoreSystem.Wc3Api.WCSharp)
    .Select(p =>
    {
        // The provider returns Windows-style relative paths like ".\CoreSystem/Natives.lua".
        // Normalize separators and resolve against the bin dir where the files were copied.
        var rel = p.Replace('\\', '/').TrimStart('.', '/');
        return Path.Combine(AppContext.BaseDirectory, rel);
    })
    .ToList();
Console.WriteLine($"blizzardJ exists={File.Exists(blizzardJ)} : {blizzardJ}");
Console.WriteLine($"commonJ   exists={File.Exists(commonJ)} : {commonJ}");

var mapScriptBuilder = new MapScriptBuilder
{
    MaxPlayerSlots = 24,
    ForceGenerateGlobalUnitVariable = true,
    ForceGenerateGlobalDestructableVariable = false,
    ForceGenerateUnitWithSkin = false,
    ForceGenerateDestructableWithSkin = false,
    UseCSharpLua = true,
    UseLifeVariable = false,
    UseWeatherEffectVariable = false,
};

if (map.Triggers != null)
{
    map.Triggers.TriggerItems.RemoveAll(t =>
        t is War3Net.Build.Script.TriggerDefinition def &&
        def.Type == War3Net.Build.Script.TriggerItemType.Comment);
}

Console.WriteLine("Compiling C# -> Lua ...");
var compileResult = map.CompileScript(compiler, mapScriptBuilder, coreSystemFiles, blizzardJ, commonJ);
if (!compileResult.Success)
{
    Console.WriteLine("COMPILE FAILED:");
    foreach (var d in compileResult.Diagnostics.Where(x => x.Severity == DiagnosticSeverity.Error).Take(20))
        Console.WriteLine("  " + d.GetMessage());
    return 1;
}
Console.WriteLine("C# compiled OK.");

if (IS_USING_GUI_TRIGGER_EDITOR)
{
    string LoadGuiScript(string baseMap)
    {
        if (Directory.Exists(baseMap))
        {
            var path = Path.Combine(baseMap, "war3map.lua");
            return File.Exists(path) ? File.ReadAllText(path) : null;
        }
        if (File.Exists(baseMap))
        {
            using var archive = MpqArchive.Open(baseMap);
            var entry = archive.GetMpqEntries("war3map.lua").FirstOrDefault();
            if (entry != null)
            {
                using var stream = archive.OpenFile(entry);
                using var reader = new StreamReader(stream);
                return reader.ReadToEnd();
            }
        }
        return null;
    }

    string guiScript = transpiledGuiLua ?? LoadGuiScript(baseMapFolder) ?? string.Empty;

    // For a transpiled JASS base: the JASS `globals` initializers became top-level Lua statements
    // that run at chunk-load — but they call engine natives (InitHashtable/CreateTimer/Location/…)
    // before the engine is ready, which instantly crashes WC3. Hoist that leading block into a
    // function invoked at the start of main() (mirrors how a clean Lua map / JASS engine does it).
    if (baseIsJass && !string.IsNullOrEmpty(guiScript))
    {
        guiScript = HoistGlobalsToInit(guiScript);
        // Remove the transpiled Lua for systems we've re-authored in C# (see MigratedTriggers), so
        // only our version runs. The C# module re-publishes each trigger's gg_trg_* handle, so the
        // rest of the still-Lua map keeps interoperating with it.
        guiScript = StripMigratedTriggers(guiScript);
        // JASS silently kills any thread that exceeds ~300k operations, so the original map relies
        // on that to truncate runaway loops (e.g. an off-by-one in playernameandtag's battletag
        // parser that oscillates forever). Lua has no such limit, so those loops hang the game.
        // Reproduce the engine's behaviour: cap every transpiled loop with an iteration guard.
        guiScript = EmulateOpLimit(guiScript);
        // FileIO reads return Lua nil for a missing file (s__File_readPreload), where JASS yields "".
        // Downstream string natives (SubString/S2I) then crash on nil — and because this runs in
        // init (zoom_Init reading a saved-zoom file), it aborts main() on clients without the file,
        // desyncing them from clients that have it. Coalesce the read to "" to match JASS semantics.
        guiScript = PatchFileIoReadNil(guiScript);
        // The zoom system restores a per-player saved camera distance by reading a file inside a
        // GetLocalPlayer() gate (zoom__RestoreFromFile). That read uses Preloader + BlzSetAbilityTooltip,
        // which then run on only ONE client per player — asymmetric engine ops that desync at init
        // (zoom_Init) and on per-player restore. Neuter the read (cosmetic: no zoom-restore-on-load).
        guiScript = PatchZoomRestore(guiScript);
    }

    if (!string.IsNullOrEmpty(guiScript))
    {
        string oldValue = "InitCustomTriggers()";
        string newValue = "InitCustomTriggers()\nInitCSharp()";
        int lastIndex = guiScript.LastIndexOf(oldValue);
        if (lastIndex != -1)
            guiScript = guiScript.Substring(0, lastIndex) + newValue + guiScript.Substring(lastIndex + oldValue.Length);
        int lastCSharpIndex = map.Script.IndexOf("Source.Program.Main()") + 26;
        map.Script = string.Concat(map.Script.AsSpan(0, lastCSharpIndex), "\n\n", guiScript);
    }
    else
    {
        Console.WriteLine("No GUI found in base map.");
    }
}

// Optional: instrument map init with a boot-log so a hang/crash can be pinpointed by reading the
// last checkpoint written to disk (WC3 can't be launched here — the user runs the test build).
if (Environment.GetEnvironmentVariable("FF_DEBUG_BOOT") == "1")
{
    map.Script = InstrumentBootLog(map.Script);
    map.Script = InstrumentCallbacks(map.Script);
    Console.WriteLine("BOOT: injected init checkpoints (FF_DEBUG_BOOT=1) -> CustomMapData/ff_boot.txt");
    Console.WriteLine("BOOT: injected callback tracer -> CustomMapData/ff_trace.txt (last line = the hanging callback)");
}

File.WriteAllText(Path.Combine(outputFolder, OUTPUT_SCRIPT_NAME), map.Script);

var archiveCreateOptions = new MpqArchiveCreateOptions
{
    ListFileCreateMode = MpqFileCreateMode.Overwrite,
    AttributesCreateMode = MpqFileCreateMode.Prune,
    BlockSize = 3,
};
string normalMapPath = Path.Combine(outputFolder, outputMapName);
builder.Build(normalMapPath, archiveCreateOptions);

// MapBuilder re-serializes the trigger/text source files (it owns those filenames, so a raw copy
// can't override them). Its war3map.wts writer drops the UTF-8 BOM and rewrites CRLF->LF, which
// makes WC3 mis-parse labels with extended characters (missing button text). war3map.wtg/.wct are
// editor-only and re-serialized lossily too. Overlay the originals back byte-for-byte — we only
// ever meant to change the script (war3map.lua) and the script-language flag (war3map.w3i).
if (baseIsJass)
    OverlayOriginalFiles(normalMapPath, baseMapFolder, archiveCreateOptions,
        new[] { "war3map.wts", "war3map.wtg", "war3map.wct" }, map.Info, Path.Combine(outputFolder, OUTPUT_SCRIPT_NAME));

Console.WriteLine($"BUILD OK -> {normalMapPath}");
return 0;

// The FF_JASS_ADDONS build: injects the addon .j files (concatenated in filename order) into the
// base map's original war3map.j — globals into the map's globals block, functions right before
// main(), and `call FF_Init()` after main()'s InitCustomTriggers() — then repacks the archive with
// every other entry carried over unchanged (war3map.wts gets the FF_MAP_VERSION stamp, if it has a
// version token). Entries are taken straight from the source archive by hash, so a base without a
// (listfile) — a protected map, whose file names can't be recovered — repacks just as faithfully.
// The injected script is verified by a full parse and, when common.j/Blizzard.j are available, a
// JASS->Lua transpile smoke test (catches unknown identifiers, not just syntax) — the result of
// that transpile is discarded; the map ships the JASS.
// `jass-to-lua <in.j> <out.lua> [...]`: each JASS file as Lua, for the simulation tests (tests/simulation), which
// run a built map's script against a modelled engine.
static int JassToLua(string[] a, string commonJ, string blizzardJ)
{
    if (a.Length < 2 || a.Length % 2 != 0)
    {
        Console.WriteLine("usage: jass-to-lua <in.j> <out.lua> [<in.j> <out.lua> ...]");
        return 1;
    }
    for (var i = 0; i < a.Length; i += 2)
    {
        File.WriteAllText(a[i + 1], TranspileJassToLua(a[i], commonJ, blizzardJ), new UTF8Encoding(false));
        Console.WriteLine($"LUA: {a[i + 1]}");
    }
    return 0;
}

// FF_SLOT_CONTROLLERS: "computer:0-11" (or "computer:0,3,5"), player ids 0..23. Empty = no change. null = malformed.
static HashSet<int> ParseSlotControllers(string spec)
{
    var res = new HashSet<int>();
    if (string.IsNullOrWhiteSpace(spec))
        return res;
    var m = Regex.Match(spec.Trim(), @"^computer:(\d{1,2}(?:-\d{1,2})?(?:,\d{1,2}(?:-\d{1,2})?)*)$");
    if (!m.Success)
    {
        Console.WriteLine($"SLOTS: FF_SLOT_CONTROLLERS must look like computer:0-11, got '{spec}'.");
        return null;
    }
    foreach (var part in m.Groups[1].Value.Split(','))
    {
        var r = part.Split('-').Select(int.Parse).ToArray();
        if (r[0] > r[^1] || r[^1] > 23)
        {
            Console.WriteLine($"SLOTS: '{part}' in FF_SLOT_CONTROLLERS is not an ascending range of player ids 0-23.");
            return null;
        }
        for (int i = r[0]; i <= r[^1]; i++)
            res.Add(i);
    }
    return res;
}

// The named players become Computer slots in config()'s SetPlayerController calls; false if one isn't there.
static bool SetComputerSlotsInScript(ref string jass, HashSet<int> slots)
{
    int swapped = 0;
    jass = Regex.Replace(jass, @"SetPlayerController\(Player\((\d+)\), MAP_CONTROL_USER\)", m =>
    {
        if (!slots.Contains(int.Parse(m.Groups[1].Value)))
            return m.Value;
        swapped++;
        return $"SetPlayerController(Player({m.Groups[1].Value}), MAP_CONTROL_COMPUTER)";
    });
    if (swapped == slots.Count)
        return true;
    Console.WriteLine($"SLOTS: {swapped} of {slots.Count} SetPlayerController calls found in config().");
    return false;
}

// The named players become Computer slots in the lobby data (war3map.w3i); false if one is missing or no User
// slot is left for the client.
static bool SetComputerSlotsInMapInfo(MapInfo mapInfo, HashSet<int> slots, Dictionary<ulong, MpqFile> replacements)
{
    var players = mapInfo.Players.Where(pl => slots.Contains(pl.Id)).ToList();
    if (players.Count != slots.Count || mapInfo.Players.All(pl => slots.Contains(pl.Id) || pl.Controller != PlayerController.User))
    {
        Console.WriteLine("SLOTS: FF_SLOT_CONTROLLERS names a slot the map lacks, or leaves no User slot for the client.");
        return false;
    }
    foreach (var pl in players)
        pl.Controller = PlayerController.Computer;
    using var w3iOut = new MemoryStream();
    using (var writer = new BinaryWriter(w3iOut, new UTF8Encoding(false), true))
        writer.Write(mapInfo);
    replacements[MpqHash.GetHashedFileName("war3map.w3i")] = MpqFile.New(new MemoryStream(w3iOut.ToArray()), "war3map.w3i", false);
    Console.WriteLine($"SLOTS: players {string.Join(",", slots.OrderBy(x => x))} are Computer slots (e2e build).");
    return true;
}

static int BuildJassAddons(string baseMapPath, string addonsDir, string outputFolder, string outputMapName, string version, string versionPattern, string stubFuncs, string commonJPath, string blizzardJPath, string mapAddonsDir, string anchorsPath)
{
    var addonFiles = Directory.EnumerateFiles(addonsDir, "*.j").OrderBy(Path.GetFileName, StringComparer.Ordinal).ToArray();
    if (addonFiles.Length == 0)
    {
        Console.WriteLine($"JASS: no *.j addon files found in {addonsDir}.");
        return 1;
    }
    bool hasMapAddons = !string.IsNullOrEmpty(mapAddonsDir);
    var mapAddonFiles = Array.Empty<string>();
    if (hasMapAddons)
    {
        if (!Directory.Exists(mapAddonsDir))
        {
            Console.WriteLine($"JASS: FF_JASS_MAP_ADDONS folder not found: {mapAddonsDir}");
            return 1;
        }
        mapAddonFiles = Directory.EnumerateFiles(mapAddonsDir, "*.j").OrderBy(Path.GetFileName, StringComparer.Ordinal).ToArray();
    }

    // Split each addon into its top-level globals block(s) and everything else, preserving
    // filename order so shared helpers precede their callers.
    var globalsSb = new StringBuilder();
    var fnSb = new StringBuilder();
    foreach (var f in addonFiles.Concat(mapAddonFiles))
    {
        bool inGlobals = false;
        foreach (var line in File.ReadAllLines(f))
        {
            var t = line.Trim();
            if (t == "globals") { inGlobals = true; continue; }
            if (t == "endglobals") { inGlobals = false; continue; }
            if (inGlobals)
                globalsSb.Append(line).Append('\n');
            else
                fnSb.Append(line).Append('\n');
        }
        fnSb.Append('\n');
        Console.WriteLine($"JASS: {(Array.IndexOf(mapAddonFiles, f) >= 0 ? "map addon" : "addon")} {Path.GetFileName(f)}");
    }

    using var archive = MpqArchive.Open(baseMapPath, true); // true = name what the (listfile) knows, if any
    // Lookup-only twin of `archive`. TryOpenFile/FileExists NAME the entries of the instance they run on, and
    // a named entry is re-placed by probing in the repack — harmless for the few files `archive` itself reads
    // (they sit in their start slots), but it would move entries stored off their start slot in a protected
    // map. Every other lookup/read goes through `probe`, which must stay open until the archive is written.
    using var probe = MpqArchive.Open(baseMapPath, true);
    if (!archive.TryOpenFile("war3map.j", out var jassStream))
    {
        Console.WriteLine($"JASS: war3map.j not found in base map ({baseMapPath}) — the addons build needs a JASS base.");
        return 1;
    }
    string jass;
    using (jassStream)
    using (var reader = new StreamReader(jassStream, new UTF8Encoding(false)))
        jass = reader.ReadToEnd();

    // Every FF_ global/function we inject must be new to the base script.
    var declared = new List<string>();
    foreach (Match m in Regex.Matches(globalsSb.ToString(), @"^\s*\w+\s+(?:array\s+)?(FF_\w+)", RegexOptions.Multiline))
        declared.Add(m.Groups[1].Value);
    foreach (Match m in Regex.Matches(fnSb.ToString(), @"^function (FF_\w+)", RegexOptions.Multiline))
        declared.Add(m.Groups[1].Value);
    foreach (var name in declared)
    {
        if (Regex.IsMatch(jass, $@"\b{Regex.Escape(name)}\b"))
        {
            Console.WriteLine($"JASS: identifier collision — {name} already exists in war3map.j; rename the addon symbol.");
            return 1;
        }
    }

    if (hasMapAddons && !Regex.IsMatch(fnSb.ToString(), @"^function FF_MapInit takes nothing returns nothing", RegexOptions.Multiline))
    {
        Console.WriteLine("JASS: FF_JASS_MAP_ADDONS is set but no map addon defines `function FF_MapInit takes nothing returns nothing`.");
        return 1;
    }

    if (!string.IsNullOrWhiteSpace(stubFuncs))
    {
        jass = StubJassFunctions(jass, stubFuncs);
        if (jass == null)
            return 1;
    }
    if (!string.IsNullOrWhiteSpace(anchorsPath))
    {
        var hooks = ReadAnchors(anchorsPath);
        jass = hooks == null ? null : ApplyJassAnchors(jass, hooks);
        if (jass == null)
            return 1;
    }
    // e2e builds only (tests/e2e; never set for a release): FF_SLOT_CONTROLLERS=computer:<from>-<to> turns those
    // players into Computer slots — in the lobby data (war3map.w3i, below) and in config()'s SetPlayerController —
    // so a single-player game started with -loadfile seats the one test client in the first slot still a User one.
    var computerSlots = ParseSlotControllers(Environment.GetEnvironmentVariable("FF_SLOT_CONTROLLERS"));
    if (computerSlots == null || (computerSlots.Count > 0 && !SetComputerSlotsInScript(ref jass, computerSlots)))
        return 1;

    int endGlobals = jass.IndexOf("\nendglobals", StringComparison.Ordinal);
    int mainIdx = jass.IndexOf("\nfunction main takes nothing returns nothing", StringComparison.Ordinal);
    if (endGlobals < 0 || mainIdx < 0 || endGlobals > mainIdx)
    {
        Console.WriteLine("JASS: could not locate the globals block and main() — unexpected script layout.");
        return 1;
    }
    int initCall = jass.IndexOf("call InitCustomTriggers()", mainIdx, StringComparison.Ordinal);
    if (initCall < 0)
    {
        Console.WriteLine("JASS: 'call InitCustomTriggers()' not found in main() — no init hook point.");
        return 1;
    }
    int initLineEnd = jass.IndexOf('\n', initCall);
    int initLineStart = jass.LastIndexOf('\n', initCall) + 1;
    // An addon may define FF_EarlyInit: called right BEFORE the map's InitCustomTriggers, so its triggers fire ahead
    // of the map's own on the same event (e.g. counting a bought item before the map's handler removes it).
    bool earlyInit = Regex.IsMatch(fnSb.ToString(), @"^function FF_EarlyInit takes nothing returns nothing", RegexOptions.Multiline);

    const string banner = "// === FF addons (injected by the build; sources: scripting/jass) ===\n";
    var sb = new StringBuilder(jass.Length + globalsSb.Length + fnSb.Length + 256);
    sb.Append(jass, 0, endGlobals + 1);                                    // ..incl. '\n' before endglobals
    sb.Append(banner).Append(globalsSb);
    sb.Append(jass, endGlobals + 1, mainIdx + 1 - (endGlobals + 1));       // endglobals .. incl. '\n' before main
    sb.Append(banner).Append(fnSb);
    if (earlyInit)
    {
        sb.Append(jass, mainIdx + 1, initLineStart - (mainIdx + 1));       // main .. up to the InitCustomTriggers line
        sb.Append("    call FF_EarlyInit()\n");
        sb.Append(jass, initLineStart, initLineEnd + 1 - initLineStart);  // the InitCustomTriggers line
    }
    else
        sb.Append(jass, mainIdx + 1, initLineEnd + 1 - (mainIdx + 1));     // main .. incl. InitCustomTriggers line
    sb.Append("    call FF_Init()\n");
    if (hasMapAddons)
        sb.Append("    call FF_MapInit()\n");
    // e2e test addons (tests/e2e, scripting/jass-e2e) start after everything else; release maps never define it.
    if (Regex.IsMatch(fnSb.ToString(), @"^function FF_E2E_Init takes nothing returns nothing", RegexOptions.Multiline))
        sb.Append("    call FF_E2E_Init()\n");
    sb.Append(jass, initLineEnd + 1, jass.Length - (initLineEnd + 1));
    var injected = sb.ToString();
    Console.WriteLine($"JASS: injected {declared.Count} FF_ symbols; init hook after InitCustomTriggers()" + (earlyInit ? ", FF_EarlyInit() before it." : "."));

    // WC3 3.0 asset paths (see AssetPaths): imported files the map references with a dotted file name are
    // renamed and every reference rewritten. Planned before the parse so the script's literals are checked in
    // their final form; object-data edits are collected here and composed with the level fill below.
    var objectFileBytes = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
    foreach (var name in AssetPaths.ObjectFiles)
        if (probe.TryOpenFile(name, out var objStream))
            objectFileBytes[name] = AssetPaths.ReadAll(objStream);
    var objectEdits = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
    SortedDictionary<string, string> renames;
    byte[] impEdit = null;
    try
    {
        renames = AssetPaths.PlanRenames(probe, objectFileBytes, injected);
        int assetRefs = 0;
        if (renames.Count > 0)
        {
            injected = AssetPaths.RewriteScript(injected, probe, renames, ref assetRefs);
            foreach (var (name, bytes) in objectFileBytes)
            {
                var edited = AssetPaths.RewriteObjectFile(name, bytes, probe, renames, ref assetRefs);
                if (edited != null)
                    objectEdits[name] = edited;
            }
            if (probe.TryOpenFile("war3map.imp", out var impStream))
                impEdit = AssetPaths.RewriteImportedFiles(AssetPaths.ReadAll(impStream), renames, ref assetRefs);
            foreach (var (from, to) in renames)
                Console.WriteLine($"ASSETS: rename {from} -> {to}");
        }
        Console.WriteLine($"ASSETS: renamed {renames.Count} file(s), rewrote {assetRefs} reference(s) (WC3 3.0 dotted file names).");
    }
    catch (InvalidDataException e)
    {
        Console.WriteLine($"ASSETS: FAILED — {e.Message}");
        return 1;
    }

    var injectedPath = Path.Combine(outputFolder, "war3map.j");           // for inspection + the smoke test
    File.WriteAllText(injectedPath, injected, new UTF8Encoding(false));
    try
    {
        JassSyntaxFactory.ParseCompilationUnit(injected);
        Console.WriteLine("JASS: parse OK.");
    }
    catch (Exception e)
    {
        Console.WriteLine($"JASS: PARSE FAILED — {e.Message} (script: {injectedPath}; pjass names the line)");
        return 1;
    }
    // per map too (bin/<map>.j): the simulation tests run each map's own script
    File.WriteAllText(Path.Combine(outputFolder, Path.GetFileNameWithoutExtension(outputMapName) + ".j"), injected, new UTF8Encoding(false));
    if (File.Exists(commonJPath) && File.Exists(blizzardJPath))
    {
        try
        {
            TranspileJassToLua(injectedPath, commonJPath, blizzardJPath);
            Console.WriteLine("JASS: transpile smoke test OK (identifiers resolve).");
        }
        catch (Exception e)
        {
            Console.WriteLine($"JASS: TRANSPILE CHECK FAILED — {e.Message}");
            return 1;
        }
    }
    else
    {
        Console.WriteLine("JASS: WARNING — common.j/Blizzard.j not found; skipped the identifier smoke test.");
    }

    // Repack: every source entry as-is (named or not), minus the archive-internal files, with
    // war3map.j (and a stamped war3map.wts) swapped in by hash. A base that shipped a (listfile)
    // gets one regenerated from the names it had; a protected base stays without one.
    var replacements = new Dictionary<ulong, MpqFile>
    {
        [MpqHash.GetHashedFileName("war3map.j")] = MpqFile.New(new MemoryStream(Encoding.UTF8.GetBytes(injected)), "war3map.j", false),
    };
    // WC3 3.0 level fill: war3map.w3a gets its unset ability levels 5+. Read and swapped in by hash like
    // war3map.j/.wts, so a protected base keeps its hash-table layout.
    if (!archive.TryOpenFile("war3map.w3i", out var w3iStream) || !objectFileBytes.ContainsKey("war3map.w3a"))
    {
        Console.WriteLine("LEVELFILL: the base map lacks war3map.w3i or war3map.w3a.");
        return 1;
    }
    MapInfo mapInfo;
    using (w3iStream) mapInfo = new BinaryReader(w3iStream).ReadMapInfo();
    if (computerSlots.Count > 0 && !SetComputerSlotsInMapInfo(mapInfo, computerSlots, replacements))
        return 1;
    var w3aBytes = objectEdits.TryGetValue("war3map.w3a", out var assetEditedW3a) ? assetEditedW3a : objectFileBytes["war3map.w3a"];
    var abilityData = new BinaryReader(new MemoryStream(w3aBytes)).ReadAbilityObjectData();
    var fill = FillLevels(mapInfo, abilityData);
    if (fill == null)
        return 1;
    int overridden = ApplyObjectOverrides(abilityData, Environment.GetEnvironmentVariable("FF_OBJECT_OVERRIDES"));
    if (overridden < 0)
        return 1;
    if (fill.Cells > 0 || overridden > 0)
    {
        using var w3aOut = new MemoryStream();
        using (var writer = new BinaryWriter(w3aOut, new UTF8Encoding(false), true))
            writer.Write(abilityData);
        objectEdits["war3map.w3a"] = w3aOut.ToArray();
    }
    foreach (var (name, bytes) in objectEdits)
        replacements[MpqHash.GetHashedFileName(name)] = MpqFile.New(new MemoryStream(bytes), name, false);
    if (impEdit != null)
        replacements[MpqHash.GetHashedFileName("war3map.imp")] = MpqFile.New(new MemoryStream(impEdit), "war3map.imp", false);

    // war3map.wts: the version stamp, then the release branding. A requested stamp or branding that
    // can't be applied is a build error, not a warning: CI would otherwise ship a map that claims the
    // wrong version, name or credits.
    bool stamped = false, branded = false;
    var branding = Branding.FromEnvironment();
    if (!string.IsNullOrWhiteSpace(version) || branding.Requested)
    {
        if (!archive.TryOpenFile("war3map.wts", out var wtsStream))
        {
            Console.WriteLine("VERSION: FF_MAP_VERSION/branding given but the base has no war3map.wts.");
            return 1;
        }
        byte[] wtsBytes;
        using (wtsStream)
        using (var ms = new MemoryStream())
        {
            wtsStream.CopyTo(ms);
            wtsBytes = ms.ToArray();
        }
        if (!string.IsNullOrWhiteSpace(version))
        {
            var restamped = StampMapVersion(wtsBytes, version.Trim(), versionPattern);
            if (restamped == null)
            {
                Console.WriteLine($"VERSION: no token matching /{versionPattern}/ in war3map.wts — cannot stamp {version.Trim()}.");
                return 1;
            }
            wtsBytes = restamped;
            stamped = true;
            Console.WriteLine($"VERSION: stamped war3map.wts -> {version.Trim()}");
        }
        if (branding.Requested)
        {
            wtsBytes = ApplyBranding(wtsBytes, mapInfo, injected, branding);
            if (wtsBytes == null)
                return 1;
            branded = true;
        }
        replacements[MpqHash.GetHashedFileName("war3map.wts")] = MpqFile.New(new MemoryStream(wtsBytes), "war3map.wts", false);
    }
    // Entries appended after the carried ones (named, placed by probing into free slots): the renamed asset
    // copies (their compressed data passed through from `probe`) and the map addons' imports.
    var newEntries = new List<MpqFile>();
    foreach (var (from, to) in renames)
        newEntries.Add(MpqFile.New(probe.OpenFile(from), to, false));
    if (hasMapAddons && Directory.Exists(Path.Combine(mapAddonsDir, "imports")))
    {
        var importsDir = Path.Combine(mapAddonsDir, "imports");
        foreach (var importPath in Directory.EnumerateFiles(importsDir, "*", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.Ordinal))
        {
            var importName = Path.GetRelativePath(importsDir, importPath).Replace('/', '\\');
            if (probe.FileExists(importName))
            {
                Console.WriteLine($"JASS: map addon import {importName} already exists in the base map.");
                return 1;
            }
            newEntries.Add(MpqFile.New(new MemoryStream(File.ReadAllBytes(importPath)), importName, false));
            Console.WriteLine($"JASS: map addon import {importName}");
        }
    }
    // The originals of renamed assets are dropped only from a fully named base: in a protected map (unnamed
    // entries pinned to their slots) removing one could vacate a slot inside a probe chain.
    bool protectedBase = archive.GetMpqFiles().Any(f => f is not MpqKnownFile);
    var renamedFrom = protectedBase ? new HashSet<ulong>() : renames.Keys.Select(MpqHash.GetHashedFileName).ToHashSet();
    string outPath = Path.Combine(outputFolder, outputMapName);
    var packed = MpqRepack.Write(archive, baseMapPath, replacements, newEntries, renamedFrom, outPath);
    if (packed == null)
        return 1;
    Console.WriteLine($"PACK: {packed.Value.Total} entries — {packed.Value.Carried} carried over unchanged" +
        (packed.Value.Unnamed > 0 ? $" ({packed.Value.Unnamed} unnamed, no listfile)" : "") +
        $", replaced war3map.j{(stamped ? " + the war3map.wts version stamp" : "")}{(branded ? " + branding" : "")}{(fill.Cells > 0 ? " + the war3map.w3a level fill" : "")}" +
        $"{(renames.Count > 0 ? " + asset-path rewrites" : "")}" +
        $"{(newEntries.Count > 0 ? $"; added {newEntries.Count} new entr{(newEntries.Count == 1 ? "y" : "ies")}" : "")}{(packed.Value.Dropped > 0 ? $", dropped {packed.Value.Dropped} renamed original(s)" : "")}.");
    Console.WriteLine($"BUILD OK -> {outPath}");
    return 0;
}

// Turns the named `returns nothing` functions of the base script into no-ops by inserting a
// `return` right after their local declarations (JASS has no unreachable-code check, and leaving
// the body in place keeps the delta reviewable). Every name must exist — a base map that renames
// or drops one of them should fail the build, not silently keep a writer alive. Returns null on
// failure.
static string StubJassFunctions(string jass, string csv)
{
    foreach (var raw in csv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
    {
        var header = Regex.Match(jass, $@"^function {Regex.Escape(raw)} takes [^\n]*returns (\w+)[ \t]*\r?\n", RegexOptions.Multiline);
        if (!header.Success)
        {
            Console.WriteLine($"JASS: stub target '{raw}' not found in war3map.j.");
            return null;
        }
        if (header.Groups[1].Value != "nothing")
        {
            Console.WriteLine($"JASS: stub target '{raw}' returns {header.Groups[1].Value} — only `returns nothing` functions can be stubbed.");
            return null;
        }
        int at = header.Index + header.Length;
        var locals = Regex.Match(jass.Substring(at), @"\A(?:[ \t]*local [^\n]*\n)*");
        at += locals.Length;
        jass = jass.Substring(0, at) + "    return // stubbed by the FF addons build (FF_JASS_STUB_FUNCS)\n" + jass.Substring(at);
        Console.WriteLine($"JASS: stubbed {raw}() (no-op).");
    }
    return jass;
}

// FF_JASS_ANCHORS=<txt>: lines inserted into or replaced in the base script's own functions (e.g.
// scripting/jass-main/anchors.txt, the stats hooks after the map's gold transfers). Format, `#` comments:
//   function <name>   the function the following anchors are scoped to (identical lines in two functions stay apart)
//   after <line>      optional, before an anchor: a line occurring EXACTLY ONCE in the function; the anchor is then
//                     the first match after it (for a line the function repeats, e.g. in both branches of an if)
//   anchor <line>     a whole line of that function, whitespace-trimmed; it must occur there EXACTLY ONCE
//   replace <line>    optional: the anchor line itself becomes <line>
//   insert <line>     one or more lines added right after the anchor, with the anchor's indentation
// Every anchor needs a replace or at least one insert. A base map whose hooked function is gone or changed fails
// the build instead of silently losing the hook.
static List<AnchorHook> ReadAnchors(string path)
{
    if (!File.Exists(path))
    {
        Console.WriteLine($"JASS: anchors file not found: {path}");
        return null;
    }
    var hooks = new List<AnchorHook>();
    string fn = null, after = null;
    int n = 0;
    foreach (var raw in File.ReadAllLines(path))
    {
        n++;
        var line = raw.Trim();
        if (line.Length == 0 || line.StartsWith('#'))
            continue;
        int sp = line.IndexOf(' ');
        var key = sp < 0 ? line : line.Substring(0, sp);
        var val = sp < 0 ? "" : line.Substring(sp + 1).Trim();
        bool inHook = hooks.Count > 0 && hooks[^1].Function == fn && after == null;
        if (key == "function" && val.Length > 0 && after == null)
            fn = val;
        else if (key == "after" && val.Length > 0 && fn != null && after == null)
            after = val;
        else if (key == "anchor" && val.Length > 0 && fn != null)
        {
            hooks.Add(new AnchorHook(fn, val, new List<string>(), after));
            after = null;
        }
        else if (key == "replace" && val.Length > 0 && inHook && hooks[^1].Replace == null && hooks[^1].Inserts.Count == 0)
            hooks[^1] = hooks[^1] with { Replace = val };
        else if (key == "insert" && val.Length > 0 && inHook)
            hooks[^1].Inserts.Add(val);
        else
        {
            Console.WriteLine($"JASS: {Path.GetFileName(path)}:{n}: expected `function <name>`, then [`after <line>`] `anchor <line>`, then `replace <line>` and/or `insert <line>`");
            return null;
        }
    }
    var empty = hooks.FirstOrDefault(h => h.Inserts.Count == 0 && h.Replace == null);
    if (empty != null || after != null)
    {
        Console.WriteLine(empty != null
            ? $"JASS: {Path.GetFileName(path)}: anchor without a replace or an insert in {empty.Function}: {empty.Anchor}"
            : $"JASS: {Path.GetFileName(path)}: `after` without an anchor: {after}");
        return null;
    }
    return hooks;
}

// The lines of `fn` in `jass` whose trimmed text equals `text`, as (line start, index past its newline).
// Null when the function itself is missing.
static List<(int Start, int End)> FindJassLines(string jass, string fn, string text)
{
    var header = Regex.Match(jass, $@"^function {Regex.Escape(fn)} takes [^\n]*\n", RegexOptions.Multiline);
    if (!header.Success)
        return null;
    int end = jass.IndexOf("\nendfunction", header.Index, StringComparison.Ordinal);
    if (end < 0)
        end = jass.Length;
    var hits = new List<(int, int)>();
    for (int at = header.Index + header.Length; at <= end;)
    {
        int nl = jass.IndexOf('\n', at);
        int next = nl < 0 ? jass.Length : nl + 1;
        if (jass.Substring(at, next - at).Trim() == text)
            hits.Add((at, next));
        at = next;
    }
    return hits;
}

// Where hook `h` matches `line` in `jass`: the only match in its function, or with `after` the first match after
// its context line. Null and a reason when the function is missing or the match isn't unique.
static (int Start, int End)? LocateHookLine(string jass, AnchorHook h, string line, out string why)
{
    why = null;
    var hits = FindJassLines(jass, h.Function, line);
    if (hits == null)
    {
        why = $"anchor function '{h.Function}' not found in war3map.j.";
        return null;
    }
    if (h.After == null)
    {
        if (hits.Count == 1)
            return hits[0];
        why = $"anchor in {h.Function} matched {hits.Count} lines (must be exactly 1): {line}";
        return null;
    }
    var ctx = FindJassLines(jass, h.Function, h.After);
    if (ctx.Count != 1)
    {
        why = $"`after` line in {h.Function} matched {ctx.Count} lines (must be exactly 1): {h.After}";
        return null;
    }
    foreach (var hit in hits)
        if (hit.Start >= ctx[0].End)
            return hit;
    why = $"anchor in {h.Function} matched no line after `{Shorten(h.After)}`: {line}";
    return null;
}

// The script with every hook applied; null (and a message) when an anchor doesn't match exactly once.
static string ApplyJassAnchors(string jass, List<AnchorHook> hooks)
{
    foreach (var h in hooks)
    {
        var hit = LocateHookLine(jass, h, h.Anchor, out var why);
        if (hit == null)
        {
            Console.WriteLine("JASS: " + why);
            return null;
        }
        var (start, next) = hit.Value;
        var anchorLine = jass.Substring(start, next - start);
        var indent = anchorLine.Substring(0, anchorLine.Length - anchorLine.TrimStart().Length);
        var nl = anchorLine.EndsWith("\r\n", StringComparison.Ordinal) ? "\r\n" : "\n";
        var add = string.Concat(h.Inserts.Select(i => indent + i + nl));
        if (h.Replace != null)
        {
            jass = jass.Substring(0, start) + indent + h.Replace + nl + add + jass.Substring(next);
            Console.WriteLine($"JASS: hooked {h.Function} (replaced `{Shorten(h.Anchor)}`, +{h.Inserts.Count} line(s)).");
            continue;
        }
        if (!anchorLine.EndsWith('\n'))
            add = nl + add;
        jass = jass.Substring(0, next) + add + jass.Substring(next);
        Console.WriteLine($"JASS: hooked {h.Function} (+{h.Inserts.Count} line(s) after `{Shorten(h.Anchor)}`).");
    }
    return jass;
}

// Head and tail of a long line for the log: hooked lines tend to differ only near the end (ally_1 / ally_2).
static string Shorten(string s) => s.Length <= 72 ? s : s.Substring(0, 28) + "..." + s.Substring(s.Length - 41);

// True if the hook is in place in a built script: its anchor (or its replacement) is where the hook puts it and is
// followed by exactly its insert lines.
static bool AnchorHookApplied(string jass, AnchorHook h)
{
    var hit = LocateHookLine(jass, h, h.Replace ?? h.Anchor, out _);
    if (hit == null)
        return false;
    int at = hit.Value.End;
    foreach (var ins in h.Inserts)
    {
        int nl = jass.IndexOf('\n', at);
        int next = nl < 0 ? jass.Length : nl + 1;
        if (jass.Substring(at, next - at).Trim() != ins)
            return false;
        at = next;
    }
    return true;
}

// `check-anchors <w3x> <anchors.txt>`: applies the hooks to the map's war3map.j in memory only.
static int CheckAnchors(string[] a)
{
    if (a.Length != 2)
    {
        Console.WriteLine("usage: check-anchors <map.w3x> <anchors.txt>");
        return 2;
    }
    using var archive = MpqArchive.Open(a[0], true);
    if (!archive.TryOpenFile("war3map.j", out var st))
    {
        Console.WriteLine($"JASS: war3map.j not found in {a[0]}");
        return 1;
    }
    string jass;
    using (st)
    using (var reader = new StreamReader(st, new UTF8Encoding(false)))
        jass = reader.ReadToEnd();
    var hooks = ReadAnchors(a[1]);
    if (hooks == null || ApplyJassAnchors(jass, hooks) == null)
        return 1;
    Console.WriteLine($"ANCHORS OK: {hooks.Count} hook(s) apply to {Path.GetFileName(a[0])}");
    return 0;
}

// Wraps a transpiled JASS map's leading top-level globals-init block (everything before the first
// function definition) into __ff_globals_init() and calls it as the first statement of main().
// JASS global initializers can call natives; running them at Lua chunk-load (before the engine is
// ready) crashes WC3, so they must run from main() like the engine does.
static string HoistGlobalsToInit(string guiScript)
{
    int firstFn = guiScript.IndexOf("\nfunction ", StringComparison.Ordinal);
    if (firstFn <= 0)
    {
        Console.WriteLine("HOIST: no leading globals block found — skipping.");
        return guiScript;
    }
    string globalsBlock = guiScript.Substring(0, firstFn);
    string rest = guiScript.Substring(firstFn); // begins with "\nfunction ..."

    const string mainMarker = "function main()";
    int mainIdx = rest.IndexOf(mainMarker, StringComparison.Ordinal);
    if (mainIdx < 0)
    {
        Console.WriteLine("HOIST: main() not found — skipping (globals would crash at load).");
        return guiScript;
    }
    // Insert the init call as the first statement inside main().
    int insertAt = mainIdx + mainMarker.Length;
    rest = rest.Substring(0, insertAt) + "\n    __ff_globals_init()" + rest.Substring(insertAt);

    int lines = globalsBlock.Split('\n').Length;
    Console.WriteLine($"HOIST: moved {lines} top-level globals-init lines into __ff_globals_init() (called from main()).");
    return "function __ff_globals_init()\n" + globalsBlock + "\nend\n" + rest;
}

// Neuters zoom__RestoreFromFile (early `do return end`) so the GetLocalPlayer-gated FileIO read
// never runs. That read (Preloader + BlzSetAbilityTooltip) executes on only one client per player,
// an asymmetric engine operation that desyncs init. Lua requires `return` to be a block's last
// statement, so we wrap it as `do return end` ahead of the now-dead body.
static string PatchZoomRestore(string script)
{
    const string needle = "function zoom__RestoreFromFile()\n";
    if (script.Contains(needle))
    {
        Console.WriteLine("ZOOM: neutered zoom__RestoreFromFile (skip GetLocalPlayer-gated FileIO read — desync fix).");
        return script.Replace(needle, needle + "    do return end\n");
    }
    Console.WriteLine("ZOOM: WARNING — zoom__RestoreFromFile not found; no patch applied.");
    return script;
}

// Makes the transpiled FileIO read return "" instead of nil for a missing/empty file, matching
// JASS string semantics. s__File_readEx returns `buf` (which is nil when the file doesn't exist);
// nil then flows into SubString/S2I and crashes the thread. This desyncs init (zoom_Init reads a
// saved-zoom file at startup) between clients that have the file and those that don't.
static string PatchFileIoReadNil(string script)
{
    const string needle = "    if (output == nil) then\n        return buf\n    end";
    const string repl = "    if (output == nil) then\n        return buf or \"\"\n    end";
    if (script.Contains(needle))
    {
        Console.WriteLine("FILEIO: patched s__File_readEx to return \"\" instead of nil (desync fix).");
        return script.Replace(needle, repl);
    }
    // Fallback: tolerate CRLF / different spacing by normalizing the search on the readEx body.
    int idx = script.IndexOf("function s__File_readEx(", StringComparison.Ordinal);
    if (idx >= 0)
    {
        int rb = script.IndexOf("return buf", idx, StringComparison.Ordinal);
        if (rb >= 0 && !script.Substring(rb, Math.Min(20, script.Length - rb)).Contains("or"))
        {
            Console.WriteLine("FILEIO: patched s__File_readEx 'return buf' -> 'return buf or \"\"' (fallback).");
            return script.Substring(0, rb) + "return buf or \"\"" + script.Substring(rb + "return buf".Length);
        }
    }
    Console.WriteLine("FILEIO: WARNING — s__File_readEx nil-return pattern not found; no patch applied.");
    return script;
}

// Injects a Preload-based checkpoint emitter (__ffboot) and a checkpoint before every statement
// in the map's main(), so the last line written to CustomMapData/FootmenFrenzy/boot.txt reveals
// exactly which init call hangs. A top-level "Z00" checkpoint just before main() distinguishes a
// chunk-load (globals) hang from a main()-time hang.
static string InstrumentBootLog(string script)
{
    const string marker = "function main()";
    int mainStart = script.IndexOf(marker, StringComparison.Ordinal);
    if (mainStart < 0)
    {
        Console.WriteLine("BOOT: main() not found — skipping instrumentation.");
        return script;
    }
    int bodyStart = mainStart + marker.Length;

    // main()'s closing 'end' is at column 0 (body statements are indented).
    int endIdx = script.IndexOf("\nend", bodyStart, StringComparison.Ordinal);
    while (endIdx >= 0)
    {
        int after = endIdx + 4;
        if (after >= script.Length || script[after] == '\n' || script[after] == '\r')
            break;
        endIdx = script.IndexOf("\nend", endIdx + 1, StringComparison.Ordinal);
    }
    if (endIdx < 0)
    {
        Console.WriteLine("BOOT: main() end not found — skipping instrumentation.");
        return script;
    }

    string body = script.Substring(bodyStart, endIdx - bodyStart);
    var pieces = body.Split('\n');
    var sb = new StringBuilder();
    int n = 0;
    for (int i = 0; i < pieces.Length; i++)
    {
        var line = pieces[i];
        if (i > 0)
            sb.Append('\n');
        var trimmed = line.Trim();
        if (trimmed.Length > 0 && !trimmed.StartsWith("--", StringComparison.Ordinal))
        {
            string indent = line.Substring(0, line.Length - line.TrimStart().Length);
            n++;
            string label = $"M{n:D2} {trimmed.Replace("\\", "").Replace("\"", "'")}";
            if (label.Length > 80)
                label = label.Substring(0, 80);
            sb.Append(indent).Append("__ffboot(\"").Append(label).Append("\")\n");
        }
        sb.Append(line);
    }

    Console.WriteLine($"BOOT: instrumented {n} statements in main().");
    string instrumentedMain = BootEmitterLua() + "\n" + marker + sb;
    return script.Substring(0, mainStart) + instrumentedMain + script.Substring(endIdx);
}

// The injected Lua checkpoint emitter. Rewrites the whole boot-log on every call (Preload can't
// append), so the file on disk is always current right up to the statement that hangs.
static string BootEmitterLua() =>
@"__ffboot_log = {}
function __ffboot(s)
  __ffboot_log[#__ffboot_log + 1] = s
  PreloadGenClear()
  PreloadGenStart()
  local i = 1
  while i <= #__ffboot_log do
    Preload(__ffboot_log[i])
    i = i + 1
  end
  PreloadGenEnd(""ff_boot.txt"")
end
__ffmark_n = 0
function __ffmark(s)
  __ffmark_n = __ffmark_n + 1
  PreloadGenClear()
  PreloadGenStart()
  Preload(tostring(__ffmark_n) .. "" "" .. s)
  PreloadGenEnd(""ff_trace.txt"")
end
__ffboot(""Z00 chunkload_reached_main_def"")";

// Strips the transpiled Lua for every trigger in the migration manifest: drops its
// `InitTrig_<name>()` call from InitCustomTriggers and deletes its `function Trig_<name>_*` /
// `function InitTrig_<name>` blocks. The `gg_trg_<name>` handle global (declared in the globals
// block) is intentionally kept — the C# replacement re-publishes the handle to it, and other
// still-Lua triggers reference it.
static string StripMigratedTriggers(string guiScript)
{
    var MigratedTriggers = MigratedTriggerNames();

    if (MigratedTriggers.Length == 0)
        return guiScript;

    var lines = guiScript.Split('\n');
    var sb = new StringBuilder();
    int strippedFns = 0, strippedCalls = 0;
    bool skipping = false;
    foreach (var line in lines)
    {
        if (skipping)
        {
            // A transpiled top-level function ends at a column-0 'end'; nested ends are indented.
            var t = line.TrimEnd();
            if (t == "end")
                skipping = false;
            continue;
        }

        bool isMigratedFn = MigratedTriggers.Any(n =>
            line.StartsWith("function Trig_" + n + "_", StringComparison.Ordinal) ||
            line.StartsWith("function InitTrig_" + n + "(", StringComparison.Ordinal));
        if (isMigratedFn)
        {
            skipping = true;
            strippedFns++;
            continue;
        }

        bool isMigratedCall = MigratedTriggers.Any(n => line.Trim() == "InitTrig_" + n + "()");
        if (isMigratedCall)
        {
            strippedCalls++;
            continue;
        }

        sb.Append(line).Append('\n');
    }
    if (sb.Length > 0) sb.Length -= 1;
    Console.WriteLine($"STRIP: removed {strippedFns} function(s) + {strippedCalls} init call(s) for migrated triggers: {string.Join(", ", MigratedTriggers)}");
    return sb.ToString();
}

// Emulates the JASS thread operation-limit by bounding every transpiled loop. The transpiler
// renders every JASS `loop ... endloop` as `while true do ... end`, so we inject a per-loop
// counter that breaks after LIMIT iterations — well above any legitimate loop (the largest in S
// is ~8190), low enough that a true infinite loop trips in a fraction of a second. This makes the
// converted Lua runtime-faithful to JASS: a runaway loop is cut and the game keeps running,
// instead of hanging the whole process. Each guard is a fresh local, so nested loops are safe.
static string EmulateOpLimit(string script)
{
    const long LIMIT = 200_000;
    var lines = script.Split('\n');
    // Counters live in one global table keyed per loop, NOT in per-loop locals: Lua caps a function
    // at 200 locals, and a fat function like InitGlobals has 500+ loops, so locals overflow that
    // limit and the script fails to compile ("map corrupted"). A table key adds zero locals and is
    // nesting-safe (each loop has a unique key; the key is reset on entry so re-runs start fresh).
    var sb = new StringBuilder("__lgc = {}\n");
    int guards = 0;
    foreach (var line in lines)
    {
        if (line.Trim() == "while true do")
        {
            string indent = line.Substring(0, line.Length - line.TrimStart().Length);
            guards++;
            string c = $"__lgc[{guards}]";
            sb.Append(indent).Append(c).Append(" = 0\n");
            sb.Append(line).Append('\n');
            sb.Append(indent).Append("    ").Append(c).Append(" = ").Append(c)
              .Append(" + 1 if ").Append(c).Append(" > ").Append(LIMIT).Append(" then break end\n");
        }
        else
        {
            sb.Append(line).Append('\n');
        }
    }
    if (sb.Length > 0) sb.Length -= 1; // drop the trailing '\n' we added
    Console.WriteLine($"OPLIMIT: guarded {guards} transpiled loops (cap {LIMIT:N0} iterations).");
    return sb.ToString();
}

// Marks the entry of every asynchronous callback the engine invokes post-main — GUI trigger
// actions plus the periodic timer callbacks — by overwriting ff_trace.txt with a counter + the
// callback's name. main() is already covered by InstrumentBootLog; once main() returns the only
// code that runs is these callbacks, so when the game hangs the LAST name left in ff_trace.txt is
// the callback that infinite-looped. (Helpers/conditions are intentionally NOT marked — they run
// in tight loops and would turn the trace into an I/O storm without naming the real culprit.)
static string InstrumentCallbacks(string script)
{
    // Callback boundaries the engine fires asynchronously: GUI trigger actions (Trig_*_Actions)
    // and the hand-written vJASS timer callbacks that S registers at game start.
    var rx = new System.Text.RegularExpressions.Regex(
        @"^function (Trig_[A-Za-z0-9_]*_Actions|MMD___tick|MMD___init2|s__Missiles_move|sc__Missiles_move|s__Missiles_period|sc__Missiles_period)\(");

    var lines = script.Split('\n');
    var sb = new StringBuilder();
    int marked = 0;
    for (int i = 0; i < lines.Length; i++)
    {
        if (i > 0)
            sb.Append('\n');
        sb.Append(lines[i]);
        var m = rx.Match(lines[i]);
        if (m.Success)
        {
            sb.Append("\n    __ffmark(\"").Append(m.Groups[1].Value).Append("\")");
            marked++;
        }
    }
    Console.WriteLine($"BOOT: instrumented {marked} callback entries.");
    return sb.ToString();
}

// Transpiles a JASS map script to Lua using the same recipe War3Net's CompileScript uses
// internally for generated GUI. common.j / Blizzard.j are registered so native and BJ return
// types are known; the map's own script is registered too so its custom functions resolve.
/// <summary>
/// Prefixes every JASS identifier that is a Lua keyword with `lua_` (`end` -> `lua_end`), leaving string
/// literals, object codes and comments untouched, so the transpiled script is valid Lua. JASS allows these names
/// (`function SubStringBJ takes string source, integer start, integer end`), and War3Net's JASS-to-Lua transpiler
/// (6.1.x) writes identifiers unescaped. JASS names start and end with a letter or digit, hence a prefix.
/// </summary>
static string EscapeLuaKeywords(string jass) => Regex.Replace(jass,
    @"(""(?:\\.|[^""\\])*""|'(?:\\.|[^'\\])*'|//[^\n]*)|\b(break|do|end|for|goto|in|repeat|until|while)\b",
    m => m.Groups[1].Success ? m.Value : "lua_" + m.Value);

static string TranspileJassToLua(string jassPath, string commonJPath, string blizzardJPath)
{
    var transpiler = new JassToLuaTranspiler
    {
        IgnoreComments = true,
        IgnoreEmptyDeclarations = true,
        IgnoreEmptyStatements = true,
        KeepFunctionsSeparated = true,
    };
    // common.j / Blizzard.j themselves are transpiled too (simulation tests): each registers only what it builds on.
    var name = Path.GetFileName(jassPath);
    if (name != "common.j")
        transpiler.RegisterJassFile(JassSyntaxFactory.ParseCompilationUnit(EscapeLuaKeywords(File.ReadAllText(commonJPath))));
    if (name != "common.j" && name != "Blizzard.j")
        transpiler.RegisterJassFile(JassSyntaxFactory.ParseCompilationUnit(EscapeLuaKeywords(File.ReadAllText(blizzardJPath))));

    // Do not RegisterJassFile the unit we're about to transpile — Transpile re-registers its
    // globals, and pre-registering would collide (duplicate key on the map's library globals).
    var mapUnit = JassSyntaxFactory.ParseCompilationUnit(EscapeLuaKeywords(File.ReadAllText(jassPath)));
    var luaUnit = transpiler.Transpile(mapUnit);

    var sb = new StringBuilder();
    using (var writer = new StringWriter(sb))
    {
        new LuaRenderer(new LuaSyntaxGenerator.SettingInfo { Indent = 4 }, writer).RenderCompilationUnit(luaUnit);
    }
    return sb.ToString();
}

// Adds every file under `folder` to the builder as an MpqFile whose archive name uses BACKSLASH
// separators. War3Net's AddFiles(folder, ...) names entries with the OS path separator, so on Linux
// imported assets get packed as "ReplaceableTextures/CommandButtons/BTNx.blp" (forward slashes)
// while WC3 (and the map's object data) looks them up with backslashes — making every subfoldered
// icon/model silently unresolvable (missing custom hero icons, etc.). We re-derive each entry name
// from its relative path and normalise '/' -> '\' so it matches what WC3/MPQ expects.
static void AddFolderAsMpqFiles(MapBuilder builder, string folder)
{
    var files = Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories)
        .Select(path => MpqFile.New(
            new MemoryStream(File.ReadAllBytes(path)),          // own copy; MpqFile disposes it post-Build
            Path.GetRelativePath(folder, path).Replace('/', '\\'),
            false))                                             // leaveOpen=false
        .ToArray();
    builder.AddFiles(files);
    Console.WriteLine($"PACK: added {files.Length} base-map files with backslash MPQ names.");
}

// ---------------------------------------------------------------------------------------------
// Migration manifest + tooling (Phase 0 of the mostly-C# roadmap). Shared source of truth for which
// GUI triggers have been re-authored in C#; the strip pass and the report both read it.
// ---------------------------------------------------------------------------------------------

// Generates scripting/Source/Admins.g.cs from a plain-text admin list (one battletag per line,
// '#' comments). Lets the admin roster be edited in the repo and baked in at build time, instead of
// hardcoded names in the trigger logic. Falls back to the historical default if the file is absent.
static void GenerateAdmins(string adminsTxtPath, string outPath)
{
    var names = new List<string>();
    if (File.Exists(adminsTxtPath))
    {
        foreach (var raw in File.ReadAllLines(adminsTxtPath))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
            names.Add(line);
        }
    }
    if (names.Count == 0) names.Add("miRaculix#1853"); // historical default keeps behaviour if file missing/empty

    var sb = new StringBuilder();
    sb.AppendLine("// <auto-generated> Generated by the build from scripting/admins.txt. Do not edit.");
    sb.AppendLine("namespace Source");
    sb.AppendLine("{");
    sb.AppendLine("\t/// <summary>The admin roster, baked from scripting/admins.txt at build time.</summary>");
    sb.AppendLine("\tinternal static class Admins");
    sb.AppendLine("\t{");
    sb.Append("\t\tprivate static readonly string[] Names = { ");
    sb.Append(string.Join(", ", names.Select(n => "\"" + n.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"")));
    sb.AppendLine(" };");
    sb.AppendLine();
    sb.AppendLine("\t\t/// <summary>True if the given player (account) name is an admin.</summary>");
    sb.AppendLine("\t\tpublic static bool Is(string name)");
    sb.AppendLine("\t\t{");
    sb.AppendLine("\t\t\tforeach (var n in Names)");
    sb.AppendLine("\t\t\t{");
    sb.AppendLine("\t\t\t\tif (n == name) return true;");
    sb.AppendLine("\t\t\t}");
    sb.AppendLine("\t\t\treturn false;");
    sb.AppendLine("\t\t}");
    sb.AppendLine("\t}");
    sb.AppendLine("}");
    File.WriteAllText(outPath, sb.ToString());
    Console.WriteLine($"ADMINS: baked {names.Count} admin(s) -> {Path.GetFileName(outPath)}");
}

// Base names of GUI triggers re-authored in C# (scripting/Source). Add a name when you migrate it.
static string[] MigratedTriggerNames() => new[]
{
    "repick_command",
    // game-mode (MODE) system
    "MODE_GUI_show", "MODE_GUI_execute",
    "MODE_set_pub_game_default", "MODE_set_pub_game_custom", "MODE_set_pro_mode", "MODE_set_inhouse",
    "MODE_colossal_GUI_execute", "MODE_colossal_amount_GUI_execute",
    "MODE_new", "MODE_set_standard_units", "MODE_set_bounties",
    "MODE_1v1_check", "MODE_1v1", "MODE_King_Of_The_Hill", "MODE_777",
    // Phase 1 leaf systems
    "kill_blink_shop_t1", "kill_blink_shop_t2", "kill_blink_shop_t3", "kill_blink_shop_t4",
    "block_from_shop_t1", "block_from_shop_t2", "block_from_shop_t3", "block_from_shop_t4",
    "show_commands", "show_players",
    "turn_off_mh", "turn_on_mh", "turn_trading_ON",
    // Phase 1 wait pilot
    "suicide", "suicide_pressed", "suicide_after_10_seconds",
    "Tech_Delay_T1", "Tech_Delay_T2", "Tech_Delay_T3",
    "Vote_SD_button", "Vote_AP_button", "Vote_AR_button", "Vote_Timer_Expires",
};

// Parses every `globals`..`endglobals` block; returns (name, csharpType, isArray) for each
// non-constant global whose type is mapped. Keyed/deduped by name.
static List<(string Name, string Type, bool IsArray)> ParseGlobals(string jass)
{
    // JASS handle/primitive type -> WCSharp.Api C# type. Globals of unmapped types are skipped.
    var JassTypeMap = new Dictionary<string, string>
    {
        ["integer"] = "int", ["real"] = "float", ["boolean"] = "bool", ["string"] = "string",
        ["unit"] = "unit", ["item"] = "item", ["destructable"] = "destructable", ["timer"] = "timer",
        ["trigger"] = "trigger", ["triggeraction"] = "triggeraction", ["triggercondition"] = "triggercondition",
        ["group"] = "group", ["force"] = "force", ["player"] = "player", ["location"] = "location",
        ["rect"] = "rect", ["region"] = "region", ["dialog"] = "dialog", ["button"] = "button",
        ["sound"] = "sound", ["effect"] = "effect", ["lightning"] = "lightning", ["texttag"] = "texttag",
        ["quest"] = "quest", ["questitem"] = "questitem", ["timerdialog"] = "timerdialog",
        ["leaderboard"] = "leaderboard", ["multiboard"] = "multiboard", ["multiboarditem"] = "multiboarditem",
        ["trackable"] = "trackable", ["gamecache"] = "gamecache", ["hashtable"] = "hashtable",
        ["unitpool"] = "unitpool", ["itempool"] = "itempool", ["image"] = "image",
        ["ubersplat"] = "ubersplat", ["fogmodifier"] = "fogmodifier", ["weathereffect"] = "weathereffect",
        ["boolexpr"] = "boolexpr", ["abilcode"] = "int", ["unitcode"] = "int", ["itemcode"] = "int",
    };
    var rx = new System.Text.RegularExpressions.Regex(
        @"^\s*(constant\s+)?([A-Za-z]+)\s+(array\s+)?(\w+)\b");
    var result = new List<(string, string, bool)>();
    var seen = new HashSet<string>(StringComparer.Ordinal);
    bool inGlobals = false;
    foreach (var raw in jass.Split('\n'))
    {
        var line = raw.TrimEnd();
        var t = line.Trim();
        if (!inGlobals) { if (t == "globals") inGlobals = true; continue; }
        if (t == "endglobals") { inGlobals = false; continue; }
        var m = rx.Match(line);
        if (!m.Success) continue;
        if (m.Groups[1].Success) continue;                 // skip constants
        if (!JassTypeMap.TryGetValue(m.Groups[2].Value, out var cs)) continue;
        var name = m.Groups[4].Value;
        if (seen.Add(name)) result.Add((name, cs, m.Groups[3].Success));
    }
    return result;
}

// Generates scripting/Source/MapGlobals.g.cs: a `G` class of CSharpLua code-template accessors for
// every shared global (getter + setter, overloaded by signature; arrays take an index). This is the
// scaling enabler — migrated systems reference G.<global>(...) instead of hand-written bindings.
static void GenerateGlobals(string jass, string outPath)
{
    var globals = ParseGlobals(jass);
    var sb = new StringBuilder();
    sb.AppendLine("// <auto-generated> Generated by `make mig-globals` from war3map.j globals. Do not edit.");
    sb.AppendLine("#pragma warning disable CS0626 // extern method has no attribute (CSharpLua code templates)");
    sb.AppendLine("using WCSharp.Api;");
    sb.AppendLine();
    sb.AppendLine("namespace Source");
    sb.AppendLine("{");
    sb.AppendLine("\t/// <summary>Typed accessors for the map's shared Lua globals (udg_* and gg_*), auto-generated");
    sb.AppendLine("\t/// from war3map.j. Each is a CSharpLua code template emitting the raw global at the call site.</summary>");
    sb.AppendLine("\tinternal static class G");
    sb.AppendLine("\t{");
    foreach (var (name, type, isArray) in globals)
    {
        if (isArray)
        {
            sb.AppendLine($"\t\t/// <summary>\n\t\t/// @CSharpLua.Template = {name}[{{0}}]\n\t\t/// </summary>");
            sb.AppendLine($"\t\tpublic static extern {type} {name}(int index);");
            sb.AppendLine($"\t\t/// <summary>\n\t\t/// @CSharpLua.Template = {name}[{{0}}] = {{1}}\n\t\t/// </summary>");
            sb.AppendLine($"\t\tpublic static extern void {name}(int index, {type} value);");
        }
        else
        {
            sb.AppendLine($"\t\t/// <summary>\n\t\t/// @CSharpLua.Template = {name}\n\t\t/// </summary>");
            sb.AppendLine($"\t\tpublic static extern {type} {name}();");
            sb.AppendLine($"\t\t/// <summary>\n\t\t/// @CSharpLua.Template = {name} = {{0}}\n\t\t/// </summary>");
            sb.AppendLine($"\t\tpublic static extern void {name}({type} value);");
        }
    }
    sb.AppendLine("\t}");
    sb.AppendLine("}");
    File.WriteAllText(outPath, sb.ToString());
    Console.WriteLine($"GEN: wrote {globals.Count} global accessors -> {outPath}");
}

// Prints a self-contained migration bundle for one GUI trigger: its full JASS functions plus the
// shared globals it references (with C# types + the G.<name> accessor to use). One command per slice
// instead of re-reading/grepping the 53k-line script.
static void ExtractTrigger(string jass, string name)
{
    var lines = jass.Split('\n');
    var globals = ParseGlobals(jass).ToDictionary(g => g.Name, g => g);
    var body = new StringBuilder();
    var refs = new SortedSet<string>(StringComparer.Ordinal);
    var fnRx = new System.Text.RegularExpressions.Regex(
        $@"^\s*(constant\s+)?function (Trig_{System.Text.RegularExpressions.Regex.Escape(name)}_|InitTrig_{System.Text.RegularExpressions.Regex.Escape(name)}\b)");
    var refRx = new System.Text.RegularExpressions.Regex(@"\b(udg_\w+|gg_\w+)\b");
    bool inFn = false; int fnCount = 0;
    foreach (var line in lines)
    {
        if (!inFn && fnRx.IsMatch(line)) { inFn = true; fnCount++; }
        if (inFn)
        {
            body.Append(line).Append('\n');
            foreach (System.Text.RegularExpressions.Match mm in refRx.Matches(line)) refs.Add(mm.Groups[1].Value);
            if (line.Trim() == "endfunction") { inFn = false; body.Append('\n'); }
        }
    }
    if (fnCount == 0) { Console.WriteLine($"No functions found for trigger '{name}' (Trig_{name}_* / InitTrig_{name})."); return; }
    Console.WriteLine($"==== JASS for trigger '{name}' ({fnCount} functions) ====");
    Console.Write(body.ToString());
    Console.WriteLine("==== shared globals referenced (use the G.<accessor>) ====");
    foreach (var r in refs)
    {
        if (globals.TryGetValue(r, out var g))
            Console.WriteLine($"  {r,-34} {g.Type}{(g.IsArray ? "[]" : "")}   ->  G.{r}({(g.IsArray ? "i" : "")})");
        else
            Console.WriteLine($"  {r,-34} (object/handle global or constant — not in G; reference directly or add)");
    }
}

// Prints migration progress: total GUI triggers, migrated, and the largest remaining clusters.
static void MigrationReport(string jass)
{
    var all = new List<string>();
    foreach (var raw in jass.Split('\n'))
    {
        var m = System.Text.RegularExpressions.Regex.Match(raw, @"^function InitTrig_(\w+) takes");
        if (m.Success) all.Add(m.Groups[1].Value);
    }
    var migrated = new HashSet<string>(MigratedTriggerNames(), StringComparer.Ordinal);
    var remaining = all.Where(t => !migrated.Contains(t)).ToList();
    Console.WriteLine($"MIGRATION STATUS: {migrated.Count}/{all.Count} GUI triggers migrated, {remaining.Count} remaining.");
    Console.WriteLine("Largest remaining clusters (by name prefix):");
    foreach (var grp in remaining.GroupBy(t => t.Split('_')[0]).OrderByDescending(g => g.Count()).Take(20))
        Console.WriteLine($"  {grp.Count(),4}  {grp.Key}");
    Console.WriteLine($"Migrated: {string.Join(", ", MigratedTriggerNames())}");
}

// Re-packs the built map, replacing the named entries with their byte-for-byte originals from the
// extracted base folder. Used to undo MapBuilder's lossy re-serialization of map-owned text/trigger
// files (war3map.wts/.wtg/.wct) — those filenames can't be overridden via AddFiles, so the only way
// to preserve them is to rewrite the archive after Build. Every other entry is copied through as-is.
static void OverlayOriginalFiles(string builtMapPath, string baseMapFolder, MpqArchiveCreateOptions options, string[] names, MapInfo info, string scriptPath)
{
    var overlays = names
        .Where(n => File.Exists(Path.Combine(baseMapFolder, n)))
        .ToDictionary(n => n, n => File.ReadAllBytes(Path.Combine(baseMapFolder, n)), StringComparer.OrdinalIgnoreCase);

    // The base map's war3map.wts carries the displayed version (loading screen + in-game text). Restamp
    // it to FF_MAP_VERSION so the map shows the release we're actually shipping, not the base map's letter.
    var version = Environment.GetEnvironmentVariable("FF_MAP_VERSION");
    if (!string.IsNullOrWhiteSpace(version) && overlays.TryGetValue("war3map.wts", out var wts))
    {
        var stamped = StampMapVersion(wts, version.Trim(), VersionPattern());
        if (stamped != null)
        {
            overlays["war3map.wts"] = stamped;
            Console.WriteLine($"VERSION: stamped war3map.wts -> {version.Trim()}");
        }
    }
    var branding = Branding.FromEnvironment();
    if (branding.Requested && overlays.TryGetValue("war3map.wts", out var wtsToBrand))
    {
        var script = File.Exists(scriptPath) ? File.ReadAllText(scriptPath) : "";
        overlays["war3map.wts"] = ApplyBranding(wtsToBrand, info, script, branding)
            ?? throw new InvalidDataException("branding failed (see BRAND: above)");
    }

    var files = new List<MpqFile>();
    using (var archive = MpqArchive.Open(builtMapPath, true))
    {
        foreach (var entry in archive)
        {
            var name = entry.FileName;
            if (string.IsNullOrEmpty(name) || name is "(listfile)" or "(attributes)" or "(signature)")
                continue; // skip MPQ metadata; Create regenerates it from options
            byte[] bytes;
            if (!overlays.TryGetValue(name, out bytes))
            {
                using var s = archive.OpenFile(entry);
                using var ms = new MemoryStream();
                s.CopyTo(ms);
                bytes = ms.ToArray();
            }
            files.Add(MpqFile.New(new MemoryStream(bytes), name, false));
        }
    }

    var tmp = builtMapPath + ".tmp";
    using (MpqArchive.Create(tmp, files, options)) { }
    File.Delete(builtMapPath);
    File.Move(tmp, builtMapPath);
    Console.WriteLine($"OVERLAY: restored {overlays.Count} original file(s) byte-for-byte: {string.Join(", ", overlays.Keys)}");
}

// Replaces the "7.9.9<letter>[-rcN]" version token in a war3map.wts with newVersion. The .wts is a
// The version token to stamp over: FF_VERSION_PATTERN, or the main map's `7.9.9X[-rcN]`.
static string VersionPattern()
{
    var p = Environment.GetEnvironmentVariable("FF_VERSION_PATTERN");
    return string.IsNullOrWhiteSpace(p) ? @"7\.9\.9[A-Z](?:-rc\d+)?" : p.Trim();
}

// UTF-8 (BOM) text file whose strings are TRIGSTR-indexed, so changing the token's length is safe. We
// work in string space but preserve the BOM by hand (the UTF-8 encoder must not emit its own). Returns
// null when nothing matched, so a base map with an unexpected version format is left untouched.
// `pattern` is the regex for the token to replace (see FF_VERSION_PATTERN).
static byte[] StampMapVersion(byte[] bytes, string newVersion, string pattern)
{
    var hasBom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
    var utf8 = new UTF8Encoding(false);
    var text = utf8.GetString(bytes, hasBom ? 3 : 0, bytes.Length - (hasBom ? 3 : 0));

    var replaced = Regex.Replace(text, pattern, newVersion);
    if (replaced == text)
        return null; // no version token found — don't touch the file

    var body = utf8.GetBytes(replaced);
    if (!hasBom)
        return body;
    var withBom = new byte[body.Length + 3];
    withBom[0] = 0xEF; withBom[1] = 0xBB; withBom[2] = 0xBF;
    Array.Copy(body, 0, withBom, 3, body.Length);
    return withBom;
}

// Stamps the release branding into war3map.wts: the lobby map name and loading-screen title (the STRING
// blocks the w3i references) and a credits line appended to the in-game Credits quest (the quest whose
// title string reads "Credits", found in the map script). Nothing else in the file is touched. Returns
// null (after printing why) when a requested part can't be applied.
static byte[] ApplyBranding(byte[] wtsBytes, MapInfo info, string script, Branding b)
{
    var (text, bom) = Wts.Decode(wtsBytes);
    try
    {
        int nameId = -1;
        if (!string.IsNullOrEmpty(b.MapName))
        {
            nameId = Wts.TrigStrId(info.MapName);
            if (nameId < 0) throw new InvalidDataException($"the w3i map name is a literal ('{info.MapName}'), not a TRIGSTR reference");
            text = Wts.SetString(text, nameId, b.MapName);
            Console.WriteLine($"BRAND: map name (STRING {nameId}) -> {b.MapName}");
        }
        if (!string.IsNullOrEmpty(b.LoadingTitle))
        {
            int titleId = Wts.TrigStrId(info.LoadingScreenTitle);
            if (titleId < 0) throw new InvalidDataException($"the w3i loading-screen title is a literal ('{info.LoadingScreenTitle}'), not a TRIGSTR reference");
            if (titleId == nameId && b.LoadingTitle != b.MapName) throw new InvalidDataException($"map name and loading title share STRING {titleId} but were asked to differ");
            text = Wts.SetString(text, titleId, b.LoadingTitle);
            Console.WriteLine($"BRAND: loading title (STRING {titleId}) -> {b.LoadingTitle}");
        }
        if (!string.IsNullOrEmpty(b.CreditsLine))
        {
            var strings = Wts.Strings(text);
            var quests = Wts.CreditsQuests(script, strings);
            if (quests.Count != 1) throw new InvalidDataException($"expected exactly one Credits quest in the map script, found {quests.Count}");
            int descId = quests[0];
            if (!strings.TryGetValue(descId, out var desc)) throw new InvalidDataException($"Credits quest text STRING {descId} is missing from war3map.wts");
            if (desc.Contains(b.CreditsLine, StringComparison.Ordinal))
                Console.WriteLine($"BRAND: Credits quest (STRING {descId}) already has the credits line");
            else
            {
                var nl = desc.Contains("\r\n") || text.Contains("\r\n") ? "\r\n" : "\n";
                text = Wts.SetString(text, descId, desc + nl + nl + b.CreditsLine);
                Console.WriteLine($"BRAND: Credits quest (STRING {descId}) += {b.CreditsLine}");
            }
        }
    }
    catch (InvalidDataException e)
    {
        Console.WriteLine($"BRAND: FAILED — {e.Message}");
        return null;
    }
    return Wts.Encode(text, bom);
}

// The bot lists of a script (the FF_IsHostBotName and FF_IsBotName functions), line endings normalized; null if it
// lacks either.
static string BotList(string src)
{
    var lists = new[] { "FF_IsHostBotName", "FF_IsBotName" }
        .Select(f => Regex.Match(src, $@"^function {f} takes.*?^endfunction", RegexOptions.Multiline | RegexOptions.Singleline))
        .ToList();
    return lists.All(m => m.Success) ? string.Join("\n", lists.Select(m => m.Value.Replace("\r", ""))) : null;
}

// `verify-map <w3x> [--name S] [--author S] [--loading-title S] [--credits S] [--funcs a,b] [--stubs a,b] [--imports a,b] [--anchors txt]`:
// the release gate for a BUILT map. Reads war3map.w3i/.wts/.w3a and the script by hash (so it works on a
// protected map) and checks the lobby name, author, loading title, the Credits-quest line, that the addon
// init functions exist and main() calls FF_Init, that the named base functions are stubbed, the TFT/Custom
// game data, that the named files exist in the archive, and that the WC3 3.0 fixes are complete: a fresh
// level fill would add nothing and no referenced import has a dotted file name.
static int VerifyMap(string[] a)
{
    if (a.Length == 0 || a[0].StartsWith("--", StringComparison.Ordinal))
    {
        Console.WriteLine("usage: verify-map <map.w3x> [--name S] [--author S] [--loading-title S] [--credits S] [--funcs a,b] [--stubs a,b] [--imports a,b] [--overrides csv[;csv]] [--anchors txt]");
        return 2;
    }
    var opt = new Dictionary<string, string>(StringComparer.Ordinal);
    for (int i = 1; i < a.Length; i++)
    {
        if (!a[i].StartsWith("--", StringComparison.Ordinal) || i + 1 >= a.Length)
        {
            Console.WriteLine($"verify-map: bad argument '{a[i]}'");
            return 2;
        }
        opt[a[i]] = a[++i];
    }
    string path = a[0];
    if (!File.Exists(path))
    {
        Console.WriteLine($"VERIFY: FAIL map not found: {path}");
        return 1;
    }
    int failures = 0;
    void Check(bool ok, string what)
    {
        Console.WriteLine($"VERIFY: {(ok ? "PASS" : "FAIL")} {what}");
        if (!ok) failures++;
    }

    using var archive = MpqArchive.Open(path, true);
    byte[] Read(string name)
    {
        if (!archive.TryOpenFile(name, out var st)) return null;
        using (st)
        using (var ms = new MemoryStream())
        {
            st.CopyTo(ms);
            return ms.ToArray();
        }
    }
    var w3i = Read("war3map.w3i");
    var wtsBytes = Read("war3map.wts");
    var w3a = Read("war3map.w3a");
    var jassBytes = Read("war3map.j");
    var scriptBytes = jassBytes ?? Read("war3map.lua");
    if (w3i == null || wtsBytes == null || w3a == null || scriptBytes == null)
    {
        Console.WriteLine("VERIFY: FAIL the map lacks war3map.w3i, war3map.wts, war3map.w3a or a script");
        return 1;
    }
    var info = new BinaryReader(new MemoryStream(w3i)).ReadMapInfo();
    var strings = Wts.Strings(Wts.Decode(wtsBytes).text);
    var script = Encoding.UTF8.GetString(scriptBytes);
    string Resolve(string v)
    {
        int id = Wts.TrigStrId(v);
        return id < 0 ? v : strings.TryGetValue(id, out var str) ? str : $"<missing STRING {id}>";
    }

    if (opt.TryGetValue("--name", out var name))
        Check(Resolve(info.MapName) == name, $"map name '{Resolve(info.MapName)}' == '{name}'");
    if (opt.TryGetValue("--author", out var author))
        Check(Resolve(info.MapAuthor) == author, $"author '{Resolve(info.MapAuthor)}' == '{author}'");
    if (opt.TryGetValue("--loading-title", out var title))
        Check(Resolve(info.LoadingScreenTitle) == title, $"loading title '{Resolve(info.LoadingScreenTitle)}' == '{title}'");
    if (opt.TryGetValue("--credits", out var credits))
    {
        var quests = Wts.CreditsQuests(script, strings);
        bool has = quests.Count == 1 && strings.TryGetValue(quests[0], out var desc) && desc.Contains(credits, StringComparison.Ordinal);
        Check(has, $"Credits quest contains '{credits}'");
    }
    if (opt.TryGetValue("--funcs", out var funcs) && jassBytes == null)
        Console.WriteLine("VERIFY: SKIP addon hooks — Lua flavor (its bot features are C#, not the JASS addons)");
    else if (funcs != null)
    {
        foreach (var f in funcs.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            Check(Regex.IsMatch(script, $@"^function {Regex.Escape(f)} takes", RegexOptions.Multiline), $"script defines {f}");
        Check(script.Contains("call FF_Init()", StringComparison.Ordinal), "main() calls FF_Init()");
        if (funcs.Split(',').Any(f => f.Trim() == "FF_MapInit"))
            Check(script.Contains("call FF_MapInit()", StringComparison.Ordinal), "main() calls FF_MapInit()");
        if (funcs.Split(',').Any(f => f.Trim() == "FF_EarlyInit"))
        {
            int early = script.IndexOf("call FF_EarlyInit()", StringComparison.Ordinal);
            int custom = early < 0 ? -1 : script.IndexOf("call InitCustomTriggers()", early, StringComparison.Ordinal);
            Check(early >= 0 && custom >= 0, "main() calls FF_EarlyInit() before InitCustomTriggers()");
        }
    }
    if (jassBytes != null)
    {
        // e2e builds (tests/e2e) carry a test addon and a test account on the bot list — never a release.
        Check(!script.Contains("FF_E2E_", StringComparison.Ordinal), "no e2e test addon (FF_E2E_)");
        try
        {
            var e2eObjs = new BinaryReader(new MemoryStream(w3a)).ReadAbilityObjectData();
            // the e2e addon's own abilities (scripting/jass-e2e/core/object_overrides.csv) are named E2xx
            var e2eAbil = e2eObjs.NewAbilities.Where(x => AbilityLevelFill.Code(x.NewId).StartsWith("E2", StringComparison.Ordinal)).ToList();
            Check(e2eAbil.Count == 0, "no e2e test abilities (E2xx) in the object data");
        }
        catch (Exception e) when (e is IOException or InvalidDataException)
        {
            Check(false, "e2e test abilities: " + e.Message);
        }
        var repoCommon = Path.Combine(Repo.Root, "league", "00-common.j");
        if (File.Exists(repoCommon) && script.Contains("function FF_IsBotName", StringComparison.Ordinal))
            Check(BotList(script) == BotList(File.ReadAllText(repoCommon)), "bot lists (FF_IsHostBotName, FF_IsBotName) as in scripting/jass/00-common.j");
    }
    if (opt.TryGetValue("--imports", out var imports))
        foreach (var f in imports.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            Check(archive.FileExists(f), $"archive contains {f}");
    if (jassBytes == null)
        Console.WriteLine("VERIFY: SKIP asset paths — Lua flavor (the dotted-file-name fix runs in the JASS build)");
    else
    {
        try
        {
            var objBytes = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
            foreach (var n in AssetPaths.ObjectFiles)
                if (archive.TryOpenFile(n, out var os))
                    objBytes[n] = AssetPaths.ReadAll(os);
            var pending = AssetPaths.PlanRenames(archive, objBytes, script);
            Check(pending.Count == 0, "no referenced import has a dotted file name (WC3 3.0)" + (pending.Count > 0 ? ": " + string.Join(", ", pending.Keys) : ""));
        }
        catch (InvalidDataException e)
        {
            Check(false, "asset paths: " + e.Message);
        }
    }
    if (opt.TryGetValue("--stubs", out var stubs))
        foreach (var f in stubs.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            Check(Regex.IsMatch(script, $@"^function {Regex.Escape(f)} takes[^\n]*\n(?:[ \t]*(?:local\b[^\n]*|//[^\n]*)?\r?\n)*[ \t]*return\b", RegexOptions.Multiline),
                $"{f} is stubbed (returns immediately)");
    if (opt.TryGetValue("--anchors", out var anchorsPath))
    {
        var hooks = ReadAnchors(anchorsPath);
        if (hooks == null)
            Check(false, $"anchor hooks: cannot read {anchorsPath}");
        else
        {
            var missing = hooks.Where(h => !AnchorHookApplied(script, h)).ToList();
            Check(missing.Count == 0, $"anchor hooks from {Path.GetFileName(anchorsPath)}: {hooks.Count - missing.Count}/{hooks.Count} in place"
                + (missing.Count > 0 ? " — missing: " + string.Join(", ", missing.Select(h => $"{h.Function} `{Shorten(h.Anchor)}`")) : ""));
        }
    }
    try
    {
        AbilityLevelFill.EnsureGameData(info);
        Check(true, "game data TFT/Custom");
        var defaults = AbilityLevelDefaults.Load(AbilityLevelDefaults.Resolve());
        var data = new BinaryReader(new MemoryStream(w3a)).ReadAbilityObjectData();
        var dry = AbilityLevelFill.Fill(data, defaults, dryRun: true);
        Check(dry.Cells == 0, $"WC3 3.0 level fill complete (a fresh fill would add {dry.Cells} cell(s))");
    }
    catch (Exception e) when (e is IOException or InvalidDataException)
    {
        Check(false, "game data / level fill: " + e.Message);
    }

    if (opt.TryGetValue("--overrides", out var overridePaths))
    {
        try
        {
            var objs = new BinaryReader(new MemoryStream(w3a)).ReadAbilityObjectData();
            var all = objs.BaseAbilities.Concat(objs.NewAbilities).ToList();
            foreach (var file in overridePaths.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                var rows = ReadObjectOverrides(file);
                var bad = new List<string>();
                foreach (var o in rows)
                {
                    int objId = AbilityLevelFill.FourCC(o.Obj), fieldId = AbilityLevelFill.FourCC(o.Field);
                    var obj = all.FirstOrDefault(x => (x.NewId != 0 ? x.NewId : x.OldId) == objId);
                    var cell = obj?.Modifications.FirstOrDefault(m => m.Id == fieldId && m.Level == o.Level);
                    bool ok = o.Value == "<unset>"
                        ? obj != null && cell == null
                        : cell != null && cell.Type.ToString() == o.Type && (cell.Type is ObjectDataType.Int
                            ? Convert.ToInt32(cell.Value, System.Globalization.CultureInfo.InvariantCulture) == int.Parse(o.Value, System.Globalization.CultureInfo.InvariantCulture)
                            : cell.Type is ObjectDataType.Real or ObjectDataType.Unreal
                                ? Math.Abs(Convert.ToSingle(cell.Value, System.Globalization.CultureInfo.InvariantCulture) - float.Parse(o.Value, System.Globalization.CultureInfo.InvariantCulture)) < 1e-4f
                                : (cell.Value as string ?? "") == o.Value);
                    if (!ok) bad.Add($"{o.Obj} {o.Field} L{o.Level}");
                }
                Check(bad.Count == 0, $"map fixes from {Path.GetFileName(file)}: {rows.Count - bad.Count}/{rows.Count} cell(s) as listed" + (bad.Count > 0 ? " — wrong: " + string.Join(", ", bad.Take(8)) : ""));
            }
        }
        catch (Exception e) when (e is IOException or InvalidDataException or FormatException)
        {
            Check(false, "map fixes: " + e.Message);
        }
    }

    Console.WriteLine(failures == 0 ? $"VERIFY OK -> {path}" : $"VERIFY FAILED ({failures} check(s)) -> {path}");
    return failures == 0 ? 0 : 1;
}

// WC3 3.0 level fill (tools/shared/AbilityLevelFill.cs): unset ability levels 5+ get the 2.0.4 level-4
// defaults from ability_level_defaults.csv. Returns null (after printing why) when it can't be applied —
// a build error, never a silent skip: shipping without it leaves free spells / zero cooldowns on 3.0.
// FF_OBJECT_OVERRIDES=<csv>[;<csv>...] sets or removes single ability cells after the level fill — lines
// `Object,Field,Level,Pointer,Type,Value` (Type Int/Real/Unreal/String, Value `<unset>` removes the cell; the value may
// contain commas; `#` comments). Release builds pass scripting/object_overrides.csv (map fixes agreed with the user, both
// maps; verify-map --overrides gates them); the probe build adds scripting/probe/object_overrides.csv (data variants the
// JASS natives can't write). Objects missing from a map's w3a are an error. Returns the cells touched, -1 on error.
static int ApplyObjectOverrides(War3Net.Build.Object.AbilityObjectData abilities, string paths)
{
    if (string.IsNullOrWhiteSpace(paths))
        return 0;
    int total = 0;
    foreach (var path in paths.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
    {
        int n = ApplyObjectOverrideFile(abilities, path);
        if (n < 0)
            return -1;
        total += n;
    }
    return total;
}

static List<(string Obj, string Field, int Level, int Pointer, string Type, string Value)> ReadObjectOverrides(string path)
{
    if (!File.Exists(path))
        throw new FileNotFoundException($"object overrides file not found: {path}");
    var rows = new List<(string, string, int, int, string, string)>();
    foreach (var raw in File.ReadLines(path))
    {
        var line = raw.Trim();
        if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal))
            continue;
        var c = line.Split(',', 6);
        if (c.Length != 6 || !int.TryParse(c[2], out var level) || !int.TryParse(c[3], out var pointer))
            throw new InvalidDataException($"{path}: malformed line '{line}'");
        rows.Add((c[0], c[1], level, pointer, c[4], c[5]));
    }
    return rows;
}

static int ApplyObjectOverrideFile(War3Net.Build.Object.AbilityObjectData abilities, string path)
{
    List<(string Obj, string Field, int Level, int Pointer, string Type, string Value)> rows;
    try
    {
        rows = ReadObjectOverrides(path);
    }
    catch (IOException e)
    {
        Console.WriteLine($"OVERRIDES: {e.Message}");
        return -1;
    }
    catch (InvalidDataException e)
    {
        Console.WriteLine($"OVERRIDES: {e.Message}");
        return -1;
    }
    int n = 0;
    foreach (var o in rows)
    {
        int objId = AbilityLevelFill.FourCC(o.Obj);
        var obj = abilities.BaseAbilities.Concat(abilities.NewAbilities).FirstOrDefault(x => (x.NewId != 0 ? x.NewId : x.OldId) == objId);
        if (o.Field == "<new>")
        {
            // `Obj,<new>,0,0,String,<base>`: a new custom ability Obj based on <base> (test builds only: the e2e
            // addon's own abilities; verify-map rejects them in a release)
            if (obj != null)
            {
                Console.WriteLine($"OVERRIDES: {o.Obj} already exists in war3map.w3a ({path})");
                return -1;
            }
            abilities.NewAbilities.Add(new LevelObjectModification { OldId = AbilityLevelFill.FourCC(o.Value), NewId = objId });
            n++;
            continue;
        }
        if (obj == null)
        {
            Console.WriteLine($"OVERRIDES: {o.Obj} is not in war3map.w3a ({path})");
            return -1;
        }
        int fieldId = AbilityLevelFill.FourCC(o.Field);
        for (int i = obj.Modifications.Count - 1; i >= 0; i--)
            if (obj.Modifications[i].Id == fieldId && obj.Modifications[i].Level == o.Level)
                obj.Modifications.RemoveAt(i);
        n++;
        if (o.Value == "<unset>")
            continue;
        var type = Enum.Parse<ObjectDataType>(o.Type);
        object value = type switch
        {
            ObjectDataType.Int => int.Parse(o.Value, System.Globalization.CultureInfo.InvariantCulture),
            ObjectDataType.Real or ObjectDataType.Unreal => float.Parse(o.Value, System.Globalization.CultureInfo.InvariantCulture),
            _ => o.Value,
        };
        var mod = new LevelObjectDataModification { Id = fieldId, Type = type, Level = o.Level, Pointer = o.Pointer, Value = value };
        AbilityLevelFill.CopySanityCheck(obj.Modifications.FirstOrDefault(), mod);
        obj.Modifications.Add(mod);
    }
    Console.WriteLine($"OVERRIDES: {n} ability cell(s) set/removed from {path}");
    return n;
}

static AbilityLevelFill.Result FillLevels(MapInfo info, War3Net.Build.Object.AbilityObjectData abilities)
{
    try
    {
        var path = AbilityLevelDefaults.Resolve();
        var defaults = AbilityLevelDefaults.Load(path);
        AbilityLevelFill.EnsureGameData(info);
        var r = AbilityLevelFill.Fill(abilities, defaults);
        Console.WriteLine($"LEVELFILL: +{r.Cells} cells on {r.Abilities} abilities (unset levels 5+ <- 2.0.4 level-4 defaults, {Path.GetFileName(path)})" +
            (r.UnknownBases.Count > 0 ? $"; {r.UnknownBases.Count} with a non-Blizzard base skipped" : ""));
        return r;
    }
    catch (Exception e) when (e is IOException or InvalidDataException)
    {
        Console.WriteLine($"LEVELFILL: FAILED — {e.Message}");
        return null;
    }
}

// Extracts every named file from a .w3x MPQ into a fresh temp folder and returns its path.
static string ExtractMpq(string mpqPath)
{
    var dest = Path.Combine(Path.GetTempPath(), "ff-basemap-" + Path.GetFileNameWithoutExtension(mpqPath));
    if (Directory.Exists(dest))
        Directory.Delete(dest, true);
    Directory.CreateDirectory(dest);

    using var archive = MpqArchive.Open(mpqPath, true); // true = resolve names from the (listfile)
    int written = 0, skipped = 0;
    foreach (var entry in archive)
    {
        var name = entry.FileName;
        if (string.IsNullOrEmpty(name))
        {
            skipped++; // not in (listfile) — can't recover its name
            continue;
        }
        if (name is "(listfile)" or "(attributes)" or "(signature)")
            continue;

        var outPath = Path.Combine(dest, name.Replace('\\', '/'));
        Directory.CreateDirectory(Path.GetDirectoryName(outPath));
        using var src = archive.OpenFile(entry);
        using var outFs = File.Create(outPath);
        src.CopyTo(outFs);
        written++;
    }
    Console.WriteLine($"Extracted {written} files from {Path.GetFileName(mpqPath)} -> {dest}" +
        (skipped > 0 ? $" ({skipped} unnamed entries skipped)" : ""));
    return dest;
}

// ---- MPQ hash table (read-only, for the layout post-condition) --------------------------------
// The table is a fixed-size open-addressing array of (nameA, nameB, locale, blockIndex) entries,
// encrypted with the key for "(hash table)"; the standard StormLib routines below decrypt it.
static class MpqTables
{
    public readonly record struct MpqHashSlot(uint NameA, uint NameB, uint BlockIndex)
    {
        public bool IsEmpty => BlockIndex == 0xFFFFFFFF;
        public bool IsDeleted => BlockIndex == 0xFFFFFFFE;
        public bool IsOccupied => !IsEmpty && !IsDeleted;
        public bool SameName(MpqHashSlot o) => NameA == o.NameA && NameB == o.NameB;
    }

    public static MpqHashSlot[] ReadHashTable(string mpqPath)
    {
        using var fs = File.OpenRead(mpqPath);
        var header = MpqHeader.Parse(fs, true);
        fs.Seek(header.HashTablePosition, SeekOrigin.Begin);
        var raw = new byte[header.HashTableSize * 16];
        int read = 0;
        while (read < raw.Length)
        {
            int n = fs.Read(raw, read, raw.Length - read);
            if (n <= 0) throw new InvalidDataException($"{mpqPath}: truncated hash table.");
            read += n;
        }
        var words = new uint[header.HashTableSize * 4];
        Buffer.BlockCopy(raw, 0, words, 0, raw.Length);
        Decrypt(words, HashString("(hash table)", 0x300));
        var slots = new MpqHashSlot[header.HashTableSize];
        for (int i = 0; i < slots.Length; i++)
            slots[i] = new MpqHashSlot(words[i * 4], words[i * 4 + 1], words[i * 4 + 3]);
        return slots;
    }

    // Slot-by-slot: an occupied source slot must hold the same name in the output, except the
    // archive-internal files, which may move or vanish as long as that doesn't open a gap inside a
    // chain (i.e. the vacated slot was the end of one). Duplicated names in the output are an error
    // too (a probe could stop at the wrong copy).
    public static List<string> CompareLayout(MpqHashSlot[] src, MpqHashSlot[] dst)
    {
        var problems = new List<string>();
        if (src.Length != dst.Length)
        {
            problems.Add($"hash table size changed {src.Length} -> {dst.Length}");
            return problems;
        }
        var internalNames = new[] { "(listfile)", "(attributes)", "(signature)" }
            .Select(n => (HashString(n, 0x100), HashString(n, 0x200))).ToHashSet();
        for (int i = 0; i < src.Length; i++)
        {
            if (!src[i].IsOccupied) continue;
            if (dst[i].IsOccupied && dst[i].SameName(src[i])) continue;
            bool isInternal = internalNames.Contains((src[i].NameA, src[i].NameB));
            bool chainEndsHere = !src[(i + 1) % src.Length].IsOccupied;
            if (isInternal && (dst[i].IsOccupied || chainEndsHere)) continue;
            problems.Add($"slot {i}: source entry {(isInternal ? "(internal file)" : $"{src[i].NameA:X8}{src[i].NameB:X8}")} " +
                (dst[i].IsOccupied ? "replaced by a different entry" : "vacated inside a probe chain"));
        }
        var seen = new HashSet<(uint, uint)>();
        for (int i = 0; i < dst.Length; i++)
            if (dst[i].IsOccupied && !seen.Add((dst[i].NameA, dst[i].NameB)))
                problems.Add($"slot {i}: duplicated name hash {dst[i].NameA:X8}{dst[i].NameB:X8}");
        return problems;
    }

    static readonly uint[] CryptTable = BuildCryptTable();
    static uint[] BuildCryptTable()
    {
        var table = new uint[0x500];
        uint seed = 0x00100001;
        for (uint index1 = 0; index1 < 0x100; index1++)
        {
            for (uint index2 = index1, i = 0; i < 5; i++, index2 += 0x100)
            {
                seed = (seed * 125 + 3) % 0x2AAAAB;
                uint temp1 = (seed & 0xFFFF) << 0x10;
                seed = (seed * 125 + 3) % 0x2AAAAB;
                uint temp2 = seed & 0xFFFF;
                table[index2] = temp1 | temp2;
            }
        }
        return table;
    }

    static uint HashString(string s, uint hashType)
    {
        uint seed1 = 0x7FED7FED, seed2 = 0xEEEEEEEE;
        foreach (var c in s.ToUpperInvariant())
        {
            seed1 = CryptTable[hashType + c] ^ (seed1 + seed2);
            seed2 = c + seed1 + seed2 + (seed2 << 5) + 3;
        }
        return seed1;
    }

    /// <summary>
    /// Lets <paramref name="edit"/> change an archive's decrypted hash table (four words per slot: name A, name B,
    /// locale and platform, block index) and returns the archive with the table re-encrypted, or the archive itself
    /// when nothing changed.
    /// </summary>
    /// <param name="archive">The whole archive file.</param>
    /// <param name="edit">Changes the words in place and returns how many slots it changed.</param>
    /// <param name="changed">The number <paramref name="edit"/> returned.</param>
    public static byte[] EditHashTable(byte[] archive, Func<uint[], int> edit, out int changed)
    {
        var copy = (byte[])archive.Clone();
        MpqHeader header;
        using (var stream = new MemoryStream(copy))
            header = MpqHeader.Parse(stream, true);
        var offset = (int)header.HashTablePosition;
        var words = new uint[header.HashTableSize * 4];
        Buffer.BlockCopy(copy, offset, words, 0, words.Length * 4);
        var key = HashString("(hash table)", 0x300);
        Decrypt(words, key);
        changed = edit(words);
        if (changed == 0)
            return archive;
        Encrypt(words, key);
        Buffer.BlockCopy(words, 0, copy, offset, words.Length * 4);
        return copy;
    }

    static void Encrypt(uint[] data, uint key)
    {
        uint seed = 0xEEEEEEEE;
        for (int i = 0; i < data.Length; i++)
        {
            seed += CryptTable[0x400 + (key & 0xFF)];
            uint plain = data[i];
            data[i] = plain ^ (key + seed);
            key = ((~key << 0x15) + 0x11111111) | (key >> 0x0B);
            seed = plain + seed + (seed << 5) + 3;
        }
    }

    static void Decrypt(uint[] data, uint key)
    {
        uint seed = 0xEEEEEEEE;
        for (int i = 0; i < data.Length; i++)
        {
            seed += CryptTable[0x400 + (key & 0xFF)];
            uint ch = data[i] ^ (key + seed);
            key = ((~key << 0x15) + 0x11111111) | (key >> 0x0B);
            seed = ch + seed + (seed << 5) + 3;
            data[i] = ch;
        }
    }
}

// One FF_JASS_ANCHORS hook (see ApplyJassAnchors).
sealed record AnchorHook(string Function, string Anchor, List<string> Inserts, string After = null, string Replace = null);

// Release branding stamped into war3map.wts (Makefile MAIN_MAP_NAME / SOLO_MAP_NAME / CREDITS_LINE).
sealed record Branding(string MapName, string LoadingTitle, string CreditsLine)
{
    public bool Requested => !string.IsNullOrEmpty(MapName) || !string.IsNullOrEmpty(LoadingTitle) || !string.IsNullOrEmpty(CreditsLine);

    public static Branding FromEnvironment() => new(
        Environment.GetEnvironmentVariable("FF_MAP_NAME"),
        Environment.GetEnvironmentVariable("FF_LOADING_TITLE"),
        Environment.GetEnvironmentVariable("FF_CREDITS_LINE"));
}

// ---- war3map.wts string table (TRIGSTR_n -> "STRING n { ... }") ------------------------------------
static class Wts
{
    static readonly Regex Block = new(@"^STRING (\d+)[ \t]*\r?\n(?:[ \t]*//[^\r\n]*\r?\n)*\{\r?\n(.*?)\r?\n\}[ \t]*(?=\r?\n|\z)",
        RegexOptions.Multiline | RegexOptions.Singleline | RegexOptions.CultureInvariant);
    static readonly Regex Quest = new(@"CreateQuestBJ\s*\([^,()]*,\s*""TRIGSTR_0*(\d+)""\s*,\s*""TRIGSTR_0*(\d+)""", RegexOptions.CultureInvariant);

    public static (string text, bool bom) Decode(byte[] bytes)
    {
        bool bom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
        return (new UTF8Encoding(false).GetString(bytes, bom ? 3 : 0, bytes.Length - (bom ? 3 : 0)), bom);
    }

    public static byte[] Encode(string text, bool bom)
    {
        var body = new UTF8Encoding(false).GetBytes(text);
        return bom ? new byte[] { 0xEF, 0xBB, 0xBF }.Concat(body).ToArray() : body;
    }

    public static int TrigStrId(string reference)
    {
        var m = Regex.Match(reference ?? "", @"^TRIGSTR_0*(\d+)$");
        return m.Success ? int.Parse(m.Groups[1].Value) : -1;
    }

    public static Dictionary<int, string> Strings(string text)
    {
        var d = new Dictionary<int, string>();
        foreach (Match m in Block.Matches(text))
            d.TryAdd(int.Parse(m.Groups[1].Value), m.Groups[2].Value);
        return d;
    }

    public static string SetString(string text, int id, string content)
    {
        var hits = Block.Matches(text).Where(m => int.Parse(m.Groups[1].Value) == id).ToList();
        if (hits.Count != 1) throw new InvalidDataException($"war3map.wts has {hits.Count} STRING {id} block(s), expected exactly 1");
        var g = hits[0].Groups[2];
        return text.Substring(0, g.Index) + content + text.Substring(g.Index + g.Length);
    }

    // Description string ids of the quests (JASS or Lua script) whose title string reads "Credits".
    public static List<int> CreditsQuests(string script, Dictionary<int, string> strings) =>
        Quest.Matches(script)
            .Select(m => (title: int.Parse(m.Groups[1].Value), desc: int.Parse(m.Groups[2].Value)))
            .Where(q => strings.TryGetValue(q.title, out var t)
                && Regex.Replace(t, @"\|[cC][0-9a-fA-F]{8}|\|[rR]", "").Trim().Equals("Credits", StringComparison.OrdinalIgnoreCase))
            .Select(q => q.desc).Distinct().ToList();
}

// ---- WC3 3.0 asset paths ------------------------------------------------------------------------------
// 3.0 takes a file's extension from the FIRST dot of its name, so an imported "FrostWyrmV2.01.mdx" is looked
// up as "FrostWyrmV2" + ".01.mdx" and the model renders invisible (shadow only). Every imported asset the map
// references with such a dotted file name is renamed ("FrostWyrmV201.mdx", plus the derived DISBTN icon /
// _portrait model the game finds by name) and its references are rewritten: object data + skin object data
// string values, JASS string literals and war3map.imp. References keep their own extension (a ".mdl"
// reference to an imported ".mdx" stays ".mdl").
static class AssetPaths
{
    public static readonly string[] ObjectFiles =
    {
        "war3map.w3u", "war3map.w3t", "war3map.w3b", "war3map.w3d", "war3map.w3a", "war3map.w3h", "war3map.w3q",
        "war3mapSkin.w3u", "war3mapSkin.w3t", "war3mapSkin.w3b", "war3mapSkin.w3d", "war3mapSkin.w3a", "war3mapSkin.w3h", "war3mapSkin.w3q",
    };

    static readonly HashSet<string> AssetExtensions = new(StringComparer.OrdinalIgnoreCase) { ".mdl", ".mdx", ".blp", ".dds", ".tga" };
    static readonly Regex JassString = new(@"""((?:[^""\\]|\\.)*)""", RegexOptions.CultureInvariant);

    public static byte[] ReadAll(Stream s)
    {
        using (s)
        using (var ms = new MemoryStream())
        {
            s.CopyTo(ms);
            return ms.ToArray();
        }
    }

    // An asset path whose file-name stem contains a dot, split into directory (with trailing '\'), stem, extension.
    static bool IsDotted(string token, out string dir, out string stem, out string ext)
    {
        dir = stem = ext = null;
        var t = token.Trim().Replace('/', '\\');
        int slash = t.LastIndexOf('\\');
        var file = t.Substring(slash + 1);
        int dot = file.LastIndexOf('.');
        if (dot <= 0 || !AssetExtensions.Contains(file.Substring(dot)))
            return false;
        stem = file.Substring(0, dot);
        if (!stem.Contains('.'))
            return false;
        dir = t.Substring(0, slash + 1);
        ext = file.Substring(dot);
        return true;
    }

    // The archive file a reference points at (.mdl and .mdx are interchangeable for models), or null.
    static string ResolveFile(MpqArchive archive, string dir, string stem, string ext)
    {
        var candidates = ext.Equals(".mdl", StringComparison.OrdinalIgnoreCase) ? new[] { ".mdl", ".mdx" }
            : ext.Equals(".mdx", StringComparison.OrdinalIgnoreCase) ? new[] { ".mdx", ".mdl" }
            : new[] { ext };
        foreach (var e in candidates)
            if (archive.FileExists(dir + stem + e))
                return dir + stem + e;
        return null;
    }

    static string Undotted(string archiveName)
    {
        int slash = archiveName.LastIndexOf('\\');
        var file = archiveName.Substring(slash + 1);
        int dot = file.LastIndexOf('.');
        return archiveName.Substring(0, slash + 1) + file.Substring(0, dot).Replace(".", "") + file.Substring(dot);
    }

    static void AddRename(MpqArchive archive, IDictionary<string, string> renames, string archiveName)
    {
        if (renames.ContainsKey(archiveName))
            return;
        var to = Undotted(archiveName);
        if (archive.FileExists(to))
            throw new InvalidDataException($"cannot rename {archiveName}: {to} already exists in the map");
        renames[archiveName] = to;
    }

    static IEnumerable<string> StringValues(object data) =>
        Modifications(data).Where(m => m.Type == ObjectDataType.String && m.Value is string).Select(m => (string)m.Value);

    // Imported files the map references with a dotted file name -> their new names.
    public static SortedDictionary<string, string> PlanRenames(MpqArchive archive, IReadOnlyDictionary<string, byte[]> objectFiles, string script)
    {
        var renames = new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        void Consider(string token)
        {
            if (!IsDotted(token, out var dir, out var stem, out var ext))
                return;
            var file = ResolveFile(archive, dir, stem, ext);
            if (file == null)
                return; // not a file of this map (a built-in asset, or a dangling reference) — nothing to rename
            AddRename(archive, renames, file);
            // Assets the game derives by name: the disabled twin of a command/passive icon, a model's portrait.
            var fileName = file.Substring(file.LastIndexOf('\\') + 1);
            if (Regex.IsMatch(file, @"^ReplaceableTextures\\(CommandButtons|PassiveButtons)\\", RegexOptions.IgnoreCase))
            {
                var disabled = @"ReplaceableTextures\CommandButtonsDisabled\DIS" + fileName;
                if (archive.FileExists(disabled))
                    AddRename(archive, renames, disabled);
            }
            var portrait = ResolveFile(archive, dir, stem + "_portrait", ext);
            if (portrait != null)
                AddRename(archive, renames, portrait);
        }
        foreach (var (name, bytes) in objectFiles)
            foreach (var value in StringValues(Read(name, bytes)))
                foreach (var token in value.Split(','))
                    Consider(token);
        foreach (Match m in JassString.Matches(script))
            Consider(m.Groups[1].Value.Replace(@"\\", @"\"));
        return renames;
    }

    static string RewriteToken(string token, MpqArchive archive, IReadOnlyDictionary<string, string> renames)
    {
        if (!IsDotted(token, out var dir, out var stem, out var ext))
            return token;
        var file = ResolveFile(archive, dir, stem, ext);
        if (file == null || !renames.ContainsKey(file))
            return token;
        int lead = token.Length - token.TrimStart().Length, trail = token.Length - token.TrimEnd().Length;
        return token.Substring(0, lead) + dir + stem.Replace(".", "") + ext + token.Substring(token.Length - trail);
    }

    public static string RewriteScript(string script, MpqArchive archive, IReadOnlyDictionary<string, string> renames, ref int count)
    {
        int n = 0;
        var result = JassString.Replace(script, m =>
        {
            var value = m.Groups[1].Value.Replace(@"\\", @"\");
            var rewritten = RewriteToken(value, archive, renames);
            if (rewritten == value)
                return m.Value;
            n++;
            return "\"" + rewritten.Replace(@"\", @"\\") + "\"";
        });
        count += n;
        return result;
    }

    // Rewrites the references in one object-data file; null when nothing references a renamed file. War3Net
    // must round-trip the untouched file byte-for-byte, and after the edit only the targeted values may differ.
    public static byte[] RewriteObjectFile(string name, byte[] bytes, MpqArchive archive, IReadOnlyDictionary<string, string> renames, ref int count)
    {
        var data = Read(name, bytes);
        var mods = Modifications(data);
        var edits = new Dictionary<int, string>();
        for (int i = 0; i < mods.Count; i++)
        {
            if (mods[i].Type != ObjectDataType.String || mods[i].Value is not string value)
                continue;
            var rewritten = string.Join(",", value.Split(',').Select(t => RewriteToken(t, archive, renames)));
            if (rewritten != value)
                edits[i] = rewritten;
        }
        if (edits.Count == 0)
            return null;
        if (!Write(data).AsSpan().SequenceEqual(bytes))
            throw new InvalidDataException($"{name}: War3Net does not round-trip this file byte-for-byte — refusing to rewrite it");
        foreach (var (i, v) in edits)
            mods[i].Value = v;
        var result = Write(data);
        var before = Modifications(Read(name, bytes));
        var after = Modifications(Read(name, result));
        if (before.Count != after.Count)
            throw new InvalidDataException($"{name}: modification count changed after the rewrite");
        for (int i = 0; i < after.Count; i++)
        {
            object expected = edits.TryGetValue(i, out var v) ? v : before[i].Value;
            if (after[i].Id != before[i].Id || after[i].Type != before[i].Type || !Equals(after[i].Value, expected) || Key(after[i]) != Key(before[i]))
                throw new InvalidDataException($"{name}: modification #{i} differs unexpectedly after the rewrite");
        }
        count += edits.Count;
        return result;
    }

    // war3map.imp (editor-side list of imports): int32 version, int32 count, then per entry a flags byte and a
    // NUL-terminated UTF-8 path — either the full archive path or one relative to war3mapImported\.
    public static byte[] RewriteImportedFiles(byte[] bytes, IReadOnlyDictionary<string, string> renames, ref int count)
    {
        const string importedDir = @"war3mapImported\";
        var utf8 = new UTF8Encoding(false);
        using var reader = new BinaryReader(new MemoryStream(bytes));
        int version = reader.ReadInt32(), entries = reader.ReadInt32();
        var output = new MemoryStream();
        using var writer = new BinaryWriter(output, utf8, true);
        writer.Write(version);
        writer.Write(entries);
        int n = 0;
        for (int i = 0; i < entries; i++)
        {
            byte flags = reader.ReadByte();
            var raw = new List<byte>();
            for (byte b; (b = reader.ReadByte()) != 0;)
                raw.Add(b);
            var path = utf8.GetString(raw.ToArray());
            if (renames.TryGetValue(path, out var to))
            {
                path = to;
                n++;
            }
            else if (renames.TryGetValue(importedDir + path, out to) && to.StartsWith(importedDir, StringComparison.OrdinalIgnoreCase))
            {
                path = to.Substring(importedDir.Length);
                n++;
            }
            writer.Write(flags);
            writer.Write(utf8.GetBytes(path));
            writer.Write((byte)0);
        }
        var rest = reader.ReadBytes((int)(reader.BaseStream.Length - reader.BaseStream.Position));
        writer.Write(rest);
        writer.Flush();
        if (n == 0)
            return null;
        count += n;
        return output.ToArray();
    }

    static string Key(ObjectDataModification m) => m switch
    {
        LevelObjectDataModification l => $"L{l.Level}P{l.Pointer}",
        VariationObjectDataModification v => $"V{v.Variation}P{v.Pointer}",
        _ => "",
    };

    static object Read(string name, byte[] bytes)
    {
        using var reader = new BinaryReader(new MemoryStream(bytes));
        return Path.GetExtension(name).ToLowerInvariant() switch
        {
            ".w3u" => reader.ReadUnitObjectData(),
            ".w3t" => reader.ReadItemObjectData(),
            ".w3b" => reader.ReadDestructableObjectData(),
            ".w3d" => reader.ReadDoodadObjectData(),
            ".w3a" => reader.ReadAbilityObjectData(),
            ".w3h" => reader.ReadBuffObjectData(),
            ".w3q" => reader.ReadUpgradeObjectData(),
            _ => throw new InvalidDataException($"not an object-data file: {name}"),
        };
    }

    static byte[] Write(object data)
    {
        using var ms = new MemoryStream();
        using (var writer = new BinaryWriter(ms, new UTF8Encoding(false), true))
        {
            switch (data)
            {
                case UnitObjectData d: writer.Write(d); break;
                case ItemObjectData d: writer.Write(d); break;
                case DestructableObjectData d: writer.Write(d); break;
                case DoodadObjectData d: writer.Write(d); break;
                case AbilityObjectData d: writer.Write(d); break;
                case BuffObjectData d: writer.Write(d); break;
                case UpgradeObjectData d: writer.Write(d); break;
                default: throw new InvalidDataException("unsupported object data type");
            }
        }
        return ms.ToArray();
    }

    static List<ObjectDataModification> Modifications(object data) => data switch
    {
        UnitObjectData d => d.BaseUnits.Concat(d.NewUnits).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        ItemObjectData d => d.BaseItems.Concat(d.NewItems).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        DestructableObjectData d => d.BaseDestructables.Concat(d.NewDestructables).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        DoodadObjectData d => d.BaseDoodads.Concat(d.NewDoodads).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        AbilityObjectData d => d.BaseAbilities.Concat(d.NewAbilities).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        BuffObjectData d => d.BaseBuffs.Concat(d.NewBuffs).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        UpgradeObjectData d => d.BaseUpgrades.Concat(d.NewUpgrades).SelectMany(o => o.Modifications.Cast<ObjectDataModification>()).ToList(),
        _ => throw new InvalidDataException("unsupported object data type"),
    };
}

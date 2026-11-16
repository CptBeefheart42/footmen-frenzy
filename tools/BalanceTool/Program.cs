using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.IO.Compression;
using System.Text.RegularExpressions;
using ClosedXML.Excel;
using War3Net.Build;
using War3Net.Build.Extensions;
using War3Net.Build.Object;
using War3Net.IO.Mpq;
using FootmenFrenzy.Shared;

// Footmen Frenzy balance tool.
//   export  <map.w3x> <out.xlsx>          map  -> spreadsheet (Abilities/Units/Items/Upgrades + Effects/Shops)
//   apply   <map.w3x> <in.xlsx> <out.w3x> spreadsheet -> regenerated map (surgical: only edited object-data files)
//   dumpall <map.w3x> <out.csv> [--fill]  every modification across all 4 types, for `make verify`
//
// WC3 3.0 level fill: every map opened for export/reconcile/apply (and dumpall --fill) first gets its
// unset ability levels 5+ filled with the 2.0.4 level-4 defaults (tools/shared/AbilityLevelFill.cs).
//
// Only the curated COMMON fields (+ numeric ability effects) are surfaced; everything else in
// the map is left byte-for-byte untouched. War3Net stores FourCC ids little-endian.

internal static class Program
{
    enum Kind { Ability, Unit, Item, Upgrade }
    record Col(string Code, string Name, bool Advanced);

    // ---- Curated COMMON balance columns per type (data-backed field codes). Advanced => collapsed.
    static readonly Col[] AbilityCommon =
    {
        new("acdn", "Cooldown", false), new("amcs", "Mana Cost", false), new("aare", "Area of Effect", false),
        new("aran", "Cast Range", false), new("adur", "Duration", false), new("ahdu", "Hero Duration", true),
    };
    static readonly Col[] UnitCommon =
    {
        new("uhpm", "Hit Points", false), new("umpi", "Mana", false),
        new("ua1b", "Damage Base", false), new("ua1d", "Dice Number", false), new("ua1s", "Dice Sides", false),
        new("ua1c", "Attack Cooldown", false), new("ua1r", "Attack Range", false),
        new("udef", "Armor", false), new("umvs", "Move Speed", false),
        new("ugol", "Gold", false), new("ulum", "Lumber", false), new("ufoo", "Food", false),
        new("ulev", "Level", true), new("uhpr", "HP Regen", true), new("umpr", "Mana Regen", true),
        new("ubba", "Bounty Base", true), new("ubdi", "Bounty Dice", true), new("ubsi", "Bounty Sides", true),
        new("uacq", "Acquisition Range", true),
    };
    static readonly Col[] ItemCommon =
    {
        new("igol", "Gold", false), new("ilum", "Lumber", false), new("ilev", "Level", false),
        new("isto", "Stock Max", false), new("istr", "Stock Replenish", false), new("iuse", "Charges", false),
        new("isst", "Stock Start Delay", true),
    };
    static readonly Col[] UpgradeCommon =
    {
        new("gglb", "Gold Base", false), new("gglm", "Gold Increment", false),
        new("gtib", "Time Base", false), new("gtim", "Time Increment", false), new("gba1", "Effect 1 Amount", false),
        new("glmb", "Lumber Base", true), new("glmm", "Lumber Increment", true), new("glvl", "Levels", true),
        new("gmo1", "Effect 1 Base", true), new("gba2", "Effect 2 Amount", true), new("gmo2", "Effect 2 Base", true),
        new("gba3", "Effect 3 Amount", true), new("gba4", "Effect 4 Amount", true),
    };

    // Hero primary-attribute block (editable on the Heroes tab; these are unit fields).
    static readonly Col[] HeroAttr =
    {
        new("ustr", "STR", false), new("ustp", "STR/lvl", false),
        new("uagi", "AGI", false), new("uagp", "AGI/lvl", false),
        new("uint", "INT", false), new("uinp", "INT/lvl", false),
    };
    static bool IsHero(in Obj o) =>
        o.Mods.Any(m => m.Field is "uhab" or "upra" or "ustr" or "uagi" or "uint");

    // Combat stat block shown (editable) on the categorized unit tabs.
    static readonly Col[] UnitStat =
    {
        new("uhpm", "Hit Points", false), new("ua1b", "Damage Base", false),
        new("ua1d", "Dice #", false), new("ua1s", "Dice Sides", false),
        new("ua1c", "Atk Cooldown", false), new("ua1r", "Atk Range", false),
        new("udef", "Armor", false), new("umvs", "Move Speed", false),
        new("ugol", "Gold", false), new("ufoo", "Food", false),
    };
    // Categorized unit tabs, in display order. "Bases" is built specially (links to upgrades).
    static readonly string[] UnitCategoryTabs =
        { "Human", "Orc", "Undead", "NightElf", "Elintian", "Bases", "Towers", "Creep Shop", "Summons", "Other" };
    static readonly Dictionary<char, string> RaceByLetter = new()
        { ['h'] = "Human", ['o'] = "Orc", ['u'] = "Undead", ['e'] = "NightElf", ['n'] = "Elintian" };

    static Col[] Common(Kind k) => k switch
    {
        Kind.Ability => AbilityCommon, Kind.Unit => UnitCommon,
        Kind.Item => ItemCommon, _ => UpgradeCommon,
    };
    static bool Leveled(Kind k) => k == Kind.Ability || k == Kind.Upgrade;
    static string TabName(Kind k) => k switch
    {
        Kind.Ability => "Abilities", Kind.Unit => "Units", Kind.Item => "Items", _ => "Upgrades",
    };
    static string MainFile(Kind k) => k switch
    {
        Kind.Ability => "war3map.w3a", Kind.Unit => "war3map.w3u",
        Kind.Item => "war3map.w3t", _ => "war3map.w3q",
    };
    static readonly string[] NameFields = { "unam", "gnam", "inam", "unit" };

    static int Main(string[] args)
    {
        try
        {
            if (args.Length >= 3 && args[0] == "export") return Export(args[1], args[2]);
            if (args.Length >= 4 && args[0] == "apply") return Apply(args[1], args[2], args[3]);
            if (args.Length >= 3 && args[0] == "dumpall") return DumpAll(args[1], args[2], args.Skip(3).Contains("--fill"));
            if (args.Length >= 4 && args[0] == "reconcile") return Reconcile(args[1], args[2], args[3]);
            Console.Error.WriteLine(
                "usage:\n" +
                "  export         <map.w3x> <out.xlsx>            map -> local .xlsx\n" +
                "  apply          <map.w3x> <in.xlsx> <out.w3x>   local .xlsx -> map\n" +
                "  reconcile      <newmap.w3x> <old.xlsx> <out.xlsx>  merge edits into a new map's structure\n" +
                "  dumpall        <map.w3x> <out.csv> [--fill]    every modification (for verify; --fill = after the 3.0 level fill)");
            return 2;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("ERROR: " + e.Message);
            if (Environment.GetEnvironmentVariable("BALANCETOOL_DEBUG") == "1") Console.Error.WriteLine(e);
            return 1;
        }
    }

    // ---------- WC3 3.0 level fill (tools/shared/AbilityLevelFill.cs)
    // Modifications the fill created in this process, so export can tell them from map-authored ones.
    static readonly HashSet<ObjectDataModification> LevelFilled = new(ReferenceEqualityComparer.Instance);

    static AbilityLevelFill.Result FillLevels(Map map)
    {
        var defaults = AbilityLevelDefaults.Load(AbilityLevelDefaults.Resolve());
        AbilityLevelFill.EnsureGameData(map.Info);
        var r = AbilityLevelFill.Fill(map.AbilityObjectData, defaults);
        LevelFilled.UnionWith(r.Added);
        Console.WriteLine($"Level fill: +{r.Cells} cell(s) on {r.Abilities} ability(ies) — unset levels 5+ get the 2.0.4 level-4 defaults (WC3 3.0)" +
            (r.UnknownBases.Count > 0 ? $"; {r.UnknownBases.Count} with a non-Blizzard base skipped" : ""));
        return r;
    }

    // ---------- FourCC / value helpers
    static string Code(int id)
    {
        var b = new[] { (byte)id, (byte)(id >> 8), (byte)(id >> 16), (byte)(id >> 24) };
        var sb = new StringBuilder(4);
        foreach (var c in b) sb.Append(c >= 32 && c < 127 ? (char)c : '?');
        return sb.ToString();
    }
    static bool IsNumeric(ObjectDataType t) => t is ObjectDataType.Int or ObjectDataType.Real or ObjectDataType.Unreal;
    static double NumVal(ObjectDataModification m) => m.Type == ObjectDataType.Int ? m.ValueAsInt : m.ValueAsFloat;

    // ---------- Uniform iteration over the 4 object-data collections
    readonly record struct Mod(string Field, int Level, int Pointer, ObjectDataModification M);
    readonly record struct Obj(string ObjCode, string BaseCode, List<Mod> Mods);

    static IEnumerable<Obj> Objects(Map map, Kind k)
    {
        IEnumerable<(int newId, int oldId, IEnumerable<ObjectDataModification> mods, bool leveled)> raw;
        switch (k)
        {
            case Kind.Ability:
                var a = map.AbilityObjectData;
                raw = (a?.BaseAbilities ?? new()).Concat(a?.NewAbilities ?? new())
                    .Select(o => (o.NewId, o.OldId, (IEnumerable<ObjectDataModification>)o.Modifications, true));
                break;
            case Kind.Upgrade:
                var g = map.UpgradeObjectData;
                raw = (g?.BaseUpgrades ?? new()).Concat(g?.NewUpgrades ?? new())
                    .Select(o => (o.NewId, o.OldId, (IEnumerable<ObjectDataModification>)o.Modifications, true));
                break;
            case Kind.Unit:
                var u = map.UnitObjectData;
                raw = (u?.BaseUnits ?? new()).Concat(u?.NewUnits ?? new())
                    .Select(o => (o.NewId, o.OldId, (IEnumerable<ObjectDataModification>)o.Modifications, false));
                break;
            default:
                var i = map.ItemObjectData;
                raw = (i?.BaseItems ?? new()).Concat(i?.NewItems ?? new())
                    .Select(o => (o.NewId, o.OldId, (IEnumerable<ObjectDataModification>)o.Modifications, false));
                break;
        }
        foreach (var (newId, oldId, mods, leveled) in raw)
        {
            var list = new List<Mod>();
            foreach (var m in mods)
            {
                int lvl = 0, ptr = 0;
                if (m is LevelObjectDataModification lm) { lvl = lm.Level; ptr = lm.Pointer; }
                list.Add(new Mod(Code(m.Id), lvl, ptr, m));
            }
            yield return new Obj(Code(newId != 0 ? newId : oldId), Code(oldId), list);
        }
    }

    // Two real ClosedXML gaps in how it writes row grouping, found by diffing its output against a
    // file LibreOffice itself produced for the same kind of group (create via UNO, group + collapse,
    // save, inspect):
    //  1. <sheetFormatPr> gets outlineLevelCol from column grouping but never outlineLevelRow, even
    //     though rows do get a correct per-row outlineLevel. Excel rebuilds the gutter from the
    //     per-row attribute regardless; LibreOffice appears to want the sheet-level summary hint too.
    //  2. Every hidden/outlined row gets collapsed="1" stamped on it. LibreOffice's own writer NEVER
    //     puts collapsed="true" on a detail row (confirmed: its output for an equivalent collapsed
    //     group has collapsed="false" on every row, hidden and visible alike) — collapsed marks a
    //     summary/boundary row's toggle state, not "this row belongs to a collapsed group". Getting
    //     that stamped on every child row block appears to stop LibreOffice's importer from building
    //     any outline tree at all, even though it still honours each row's plain hidden="1" (which is
    //     why rows import correctly hidden — confirmed via UNO — but there's nothing to click to
    //     expand them). ClosedXML's public API has no way to control either of these directly, so both
    //     get patched into the saved .xlsx afterward instead.
    static void SaveAsWithOutlineFix(XLWorkbook wb, string path)
    {
        wb.SaveAs(path);

        var entries = new Dictionary<string, byte[]>();
        using (var za = ZipFile.OpenRead(path))
            foreach (var e in za.Entries)
            {
                using var s = e.Open();
                using var ms = new MemoryStream();
                s.CopyTo(ms);
                entries[e.FullName] = ms.ToArray();
            }

        bool changed = false;
        foreach (var name in entries.Keys.Where(n => n.StartsWith("xl/worksheets/sheet") && n.EndsWith(".xml")).ToList())
        {
            var xml = Encoding.UTF8.GetString(entries[name]);
            int maxLevel = Regex.Matches(xml, @"<x:row\b[^>]*\boutlineLevel=""(\d+)""")
                .Select(m => int.Parse(m.Groups[1].Value)).DefaultIfEmpty(0).Max();
            if (maxLevel == 0) continue;

            var patched = Regex.Replace(xml, @"<x:sheetFormatPr([^>]*)/>", m =>
                m.Value.Contains("outlineLevelRow") ? m.Value : $"<x:sheetFormatPr{m.Groups[1].Value} outlineLevelRow=\"{maxLevel}\"/>");
            // Attribute order isn't fixed (ClosedXML emits hidden/collapsed BEFORE outlineLevel), so
            // match the whole tag and only touch it if outlineLevel is present anywhere inside.
            patched = Regex.Replace(patched, @"<x:row\b[^>]*>", m =>
                m.Value.Contains("outlineLevel=") ? m.Value.Replace("collapsed=\"1\"", "collapsed=\"0\"") : m.Value);
            if (patched != xml) { entries[name] = Encoding.UTF8.GetBytes(patched); changed = true; }
        }
        if (!changed) return;

        using var fs = File.Create(path);
        using var zip = new ZipArchive(fs, ZipArchiveMode.Create);
        foreach (var (name, data) in entries)
        {
            var entry = zip.CreateEntry(name, CompressionLevel.Optimal);
            using var es = entry.Open();
            es.Write(data, 0, data.Length);
        }
    }

    // =================================================================== EXPORT
    static int Export(string mapPath, string outXlsx)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outXlsx)) ?? ".");
        using var wb = BuildWorkbook(mapPath, out var stats);
        SaveAsWithOutlineFix(wb, outXlsx);
        Console.WriteLine($"{stats} -> {outXlsx}");
        return 0;
    }

    // Builds the full 17-tab workbook for a map (no file I/O). Shared by `export` and `reconcile`.
    static XLWorkbook BuildWorkbook(string mapPath, out string stats)
    {
        var map = Map.Open(mapPath);
        FillLevels(map);
        var names = new NameResolver(map);
        var shops = new ShopIndex(map, names);

        var wb = new XLWorkbook();
        // Build the data tabs first (captures each ability/item's first row for cross-tab links).
        var abilityRows = new Dictionary<string, int>();
        var itemRows = new Dictionary<string, int>();
        var upgradeRows = new Dictionary<string, int>();
        int total = 0;
        total += BuildWideSheet(wb, map, Kind.Ability, names, shops, abilityRows);
        total += BuildWideSheet(wb, map, Kind.Item, names, shops, itemRows);
        total += BuildWideSheet(wb, map, Kind.Upgrade, names, shops, upgradeRows, includeEmpty: true);
        var effectRows = new Dictionary<string, int>();
        int eff = BuildEffectsSheet(wb, map, names, effectRows);
        var abSum = BuildAbilitySummary(map);
        var links = new SkillLinks
        {
            AbilityRows = abilityRows,
            AbilitiesWs = wb.Worksheet(TabName(Kind.Ability)),
            EffectRows = effectRows,
            EffectsWs = wb.Worksheet("Ability Effects"),
        };

        // Categorize non-hero units into race/role tabs.
        var roster = LoadSpawnRoster();                                  // base/spawn roster -> race + tier
        var baseInfo = LoadBases();                                      // base buildings -> spawn/tier/race
        var unitCodes = new HashSet<string>(Objects(map, Kind.Unit).Select(o => o.ObjCode));
        var summonSet = DetectUnitRefs(map, unitCodes, Kind.Ability);     // units summoned/created by abilities
        var creepSet = DetectUnitRefs(map, unitCodes, Kind.Unit, "useu"); // units sold by creep shops
        var cats = new Dictionary<string, List<(Obj, int?)>>();
        var baseUnits = new List<Obj>();
        void Add(string cat, Obj o, int? tier) { if (!cats.TryGetValue(cat, out var l)) cats[cat] = l = new(); l.Add((o, tier)); }
        foreach (var o in Objects(map, Kind.Unit))
        {
            if (IsHero(o)) continue;
            if (baseInfo.ContainsKey(o.ObjCode)) { baseUnits.Add(o); continue; }   // -> dedicated Bases tab
            if (roster.TryGetValue(o.ObjCode, out var info)) Add(info.race, o, info.tier);
            else if (names.Of(Kind.Unit, o).ToUpperInvariant().Contains("TOWER")) Add("Towers", o, null);
            else if (creepSet.Contains(o.ObjCode)) Add("Creep Shop", o, null);
            else if (summonSet.Contains(o.ObjCode)) Add("Summons", o, null);
            else Add("Other", o, null);
        }
        int unitRows = 0;
        foreach (var cat in UnitCategoryTabs)
            if (cats.TryGetValue(cat, out var list)) unitRows += BuildExpandableUnitSheet(wb, cat, list, names, links, abSum);
        unitRows += BuildBasesSheet(wb, baseUnits, baseInfo, names, links, wb.Worksheet(TabName(Kind.Upgrade)), upgradeRows);

        int heroes = BuildHeroesSheet(wb, map, names, links, abSum);
        shops.BuildSheet(wb, wb.Worksheet(TabName(Kind.Item)), itemRows);

        BuildGuideSheet(wb);

        // Tab order: Guide, Heroes, race/role tabs, then the data tabs.
        var order = new[] { "Guide", "Heroes" }.Concat(UnitCategoryTabs)
            .Concat(new[] { "Abilities", "Items", "Upgrades", "Ability Effects", "Shops" }).ToArray();
        int pos = 1;
        foreach (var nm in order) if (wb.TryGetWorksheet(nm, out var sheet)) sheet.Position = pos++;

        stats = $"Exported {heroes} heroes, {unitRows} categorized units, {total} other object rows (+{eff} effects, {shops.Count} shops)";
        return wb;
    }

    // =================================================================== RECONCILE (sheet <- new map version)
    // Migrate an existing sheet to a NEW map version without losing edits:
    //   * rebuild the workbook from the new map (so new objects/fields appear at the new defaults),
    //   * carry every value the old sheet already has forward onto surviving cells (preserve edits),
    //   * append rows for objects the new map dropped, flagged OUTDATED (kept, not deleted).
    // Emits a local .xlsx carrying the merged edits.
    static int Reconcile(string newMapPath, string oldSheetPath, string outXlsx)
    {
        if (!File.Exists(oldSheetPath)) { Console.Error.WriteLine($"reconcile: sheet not found: {oldSheetPath}"); return 1; }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outXlsx)) ?? ".");

        using var wb = BuildWorkbook(newMapPath, out _);   // fresh structure from the new map (gaps already present)
        using var old = OpenWorkbookTolerant(oldSheetPath);

        // Every object code present anywhere in the new workbook — used to decide what's been removed.
        var newCodes = new HashSet<string>(StringComparer.Ordinal);
        foreach (var ws in wb.Worksheets)
        {
            var hdr = HeaderMap(ws);
            if (!hdr.TryGetValue("Code", out var cc)) continue;
            foreach (var row in ws.RowsUsed().Skip(1))
            {
                var code = row.Cell(cc).GetString().Trim();
                if (code.Length > 0) newCodes.Add(code);
            }
        }

        int carried = 0, shadowed = 0, filled = 0, outdated = 0;

        foreach (var ws in wb.Worksheets)
        {
            if (!old.TryGetWorksheet(ws.Name, out var ows)) continue;
            var nhdr = HeaderMap(ws);
            var ohdr = HeaderMap(ows);
            if (!nhdr.ContainsKey("Code") || !ohdr.ContainsKey("Code")) continue;  // Guide/Shops — no object rows

            // Composite key = Code + whichever of Field/Level/Pointer both tabs carry.
            string[] keyCols = new[] { "Code", "Field", "Level", "Pointer" }
                .Where(c => nhdr.ContainsKey(c) && ohdr.ContainsKey(c)).ToArray();
            var valCols = nhdr.Keys.Where(h => ohdr.ContainsKey(h) && Array.IndexOf(keyCols, h) < 0 && !IsBaselineCol(h)).ToList();

            string Key(IXLRangeRow r, Dictionary<string, int> hdr) =>
                string.Join("|", keyCols.Select(c => r.Cell(hdr[c]).GetString().Trim()));

            // Index the old sheet's editable rows (skip blank-Code skill/child rows).
            var oldRows = new Dictionary<string, IXLRangeRow>(StringComparer.Ordinal);
            foreach (var r in ows.RangeUsed().RowsUsed().Skip(1))
                if (r.Cell(ohdr["Code"]).GetString().Trim().Length > 0)
                    oldRows[Key(r, ohdr)] = r;

            // Carry surviving values forward; cells the old sheet lacks stay at the new map's default.
            foreach (var r in ws.RangeUsed().RowsUsed().Skip(1))
            {
                if (r.Cell(nhdr["Code"]).GetString().Trim().Length == 0) continue;
                if (!oldRows.TryGetValue(Key(r, nhdr), out var orow)) { filled++; continue; }  // new row
                foreach (var h in valCols)
                {
                    var ncell = r.Cell(nhdr[h]);
                    if (!ncell.TryGetValue<double>(out var nv)) continue;   // field/level absent in new map -> don't carry
                    if (!orow.Cell(ohdr[h]).TryGetValue<double>(out var ov)) continue;
                    ncell.Value = ov;
                    carried++;
                    if ((float)nv != (float)ov) { shadowed++; ncell.Style.Fill.BackgroundColor = XLColor.FromHtml("#FFF2CC"); }
                }
            }

            // Append rows for objects the new map no longer has, flagged OUTDATED (kept for audit).
            int maxCol = nhdr.Values.Max();
            int at = ws.LastRowUsed().RowNumber();
            foreach (var r in ows.RangeUsed().RowsUsed().Skip(1))
            {
                var code = r.Cell(ohdr["Code"]).GetString().Trim();
                if (code.Length == 0 || newCodes.Contains(code)) continue;   // survived (maybe moved tabs)
                at++;
                foreach (var (h, oc) in ohdr)
                    if (nhdr.TryGetValue(h, out var nc)) ws.Cell(at, nc).Value = r.Cell(oc).Value;
                if (nhdr.TryGetValue("Name", out var nameCol))
                {
                    var nameCell = ws.Cell(at, nameCol);
                    nameCell.Value = "⚠ OUTDATED — " + nameCell.GetString();
                }
                else ws.Cell(at, maxCol + 1).Value = "⚠ OUTDATED";
                var rng = ws.Range(at, 1, at, maxCol + 1);
                rng.Style.Fill.BackgroundColor = XLColor.FromHtml("#F0F0F0");
                rng.Style.Font.Strikethrough = true;
                outdated++;
            }
        }

        SaveAsWithOutlineFix(wb, outXlsx);
        Console.WriteLine($"Reconcile: new map '{Path.GetFileName(newMapPath)}' vs sheet '{Path.GetFileName(oldSheetPath)}'");
        Console.WriteLine($"  carried  {carried} existing value(s) forward ({shadowed} differ from the new map's defaults — highlighted)");
        Console.WriteLine($"  filled   {filled} new row(s) the sheet was missing");
        Console.WriteLine($"  outdated {outdated} row(s) flagged (object gone from the new map)");
        Console.WriteLine($"Wrote {outXlsx}");
        return 0;
    }

    static int BuildWideSheet(XLWorkbook wb, Map map, Kind kind, NameResolver names, ShopIndex shops,
        Dictionary<string, int> rowOf = null, bool includeEmpty = false)
    {
        var ws = wb.Worksheets.Add(TabName(kind));
        var cols = Common(kind);
        var commonSet = cols.Select(c => c.Code).ToHashSet();
        bool leveled = Leveled(kind);
        bool isItem = kind == Kind.Item;

        // Key columns: Code, Name, BaseType, [Shop for items], [Level if leveled]
        var keys = new List<string> { "Code", "Name", "BaseType" };
        if (isItem) keys.Add("Shop");
        if (leveled) keys.Add("Level");
        int keyCols = keys.Count;
        for (int i = 0; i < keys.Count; i++) ws.Cell(1, i + 1).Value = keys[i];
        for (int i = 0; i < cols.Length; i++) ws.Cell(1, keyCols + 1 + i).Value = cols[i].Name;
        int nCols = keyCols + cols.Length;

        int r = 1;
        // Alphabetical by Name (blanks/unnamed last) so the tab is stable and never needs manual sorting.
        var sorted = Objects(map, kind)
            .Select(o => (o, name: names.Of(kind, o)))
            .OrderBy(x => x.name.Length == 0).ThenBy(x => x.name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        foreach (var (o, name) in sorted)
        {
            var byField = new Dictionary<string, Dictionary<int, ObjectDataModification>>();
            var levels = new SortedSet<int>();
            foreach (var m in o.Mods)
            {
                if (!commonSet.Contains(m.Field)) continue;
                if (!byField.TryGetValue(m.Field, out var bl)) byField[m.Field] = bl = new();
                bl[m.Level] = m.M;
                levels.Add(m.Level);
            }
            if (byField.Count == 0 && !includeEmpty) continue; // include empties for upgrades so none look "missing"
            if (levels.Count == 0) levels.Add(0);
            if (rowOf != null && !rowOf.ContainsKey(o.ObjCode)) rowOf[o.ObjCode] = r + 1; // first data row

            var rowLevels = leveled ? (IEnumerable<int>)levels : new[] { levels.Min() };
            foreach (var lvl in rowLevels)
            {
                r++;
                int c = 1;
                ws.Cell(r, c++).Value = o.ObjCode;
                ws.Cell(r, c++).Value = name;
                ws.Cell(r, c++).Value = o.BaseCode;
                if (isItem) ws.Cell(r, c++).Value = shops.ShopsOf(o.ObjCode);
                if (leveled) ws.Cell(r, c++).Value = lvl;
                for (int i = 0; i < cols.Length; i++)
                {
                    if (byField.TryGetValue(cols[i].Code, out var bl))
                    {
                        // non-leveled fields live at level 0; show them on every level row
                        if (bl.TryGetValue(lvl, out var m) || (!leveled && bl.TryGetValue(0, out m)))
                            ws.Cell(r, keyCols + 1 + i).Value = NumVal(m);
                    }
                }
            }
        }

        StyleSheet(ws, r, nCols, keyCols);
        for (int i = 0; i < cols.Length; i++)
            if (cols[i].Advanced) ws.Column(keyCols + 1 + i).OutlineLevel = 1;
        ws.CollapseColumns(1);
        return r - 1;
    }

    static int BuildEffectsSheet(XLWorkbook wb, Map map, NameResolver names, Dictionary<string, int> rowOf = null)
    {
        var ws = wb.Worksheets.Add("Ability Effects");
        var commonSet = AbilityCommon.Select(c => c.Code).ToHashSet();
        string[] hdr = { "Code", "Name", "BaseType", "Field", "Level", "Pointer", "Value" };
        for (int i = 0; i < hdr.Length; i++) ws.Cell(1, i + 1).Value = hdr[i];

        int r = 1;
        // Alphabetical by ability Name (blanks last); each ability's effect rows stay grouped together.
        var sorted = Objects(map, Kind.Ability)
            .Select(o => (o, name: names.Of(Kind.Ability, o)))
            .OrderBy(x => x.name.Length == 0).ThenBy(x => x.name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        foreach (var (o, name) in sorted)
        {
            foreach (var m in o.Mods)
            {
                if (commonSet.Contains(m.Field) || !IsNumeric(m.M.Type)) continue;
                if (rowOf != null && !rowOf.ContainsKey(o.ObjCode)) rowOf[o.ObjCode] = r + 1; // first effect row
                r++;
                ws.Cell(r, 1).Value = o.ObjCode; ws.Cell(r, 2).Value = name; ws.Cell(r, 3).Value = o.BaseCode;
                ws.Cell(r, 4).Value = m.Field; ws.Cell(r, 5).Value = m.Level; ws.Cell(r, 6).Value = m.Pointer;
                ws.Cell(r, 7).Value = NumVal(m.M);
            }
        }
        StyleSheet(ws, r, 7, keyCols: 6);
        return r - 1;
    }

    // Heroes overview: alphabetical, one collapsible group per hero. Hero row carries the
    // (editable) primary-attribute block; expand to read a per-skill summary (read-only).
    static int BuildHeroesSheet(XLWorkbook wb, Map map, NameResolver names,
        SkillLinks links, Dictionary<string, Dictionary<string, SortedDictionary<int, double>>> abSum)
    {
        var ws = wb.Worksheets.Add("Heroes");
        string[] hdr = { "Code", "Name", "Primary", "STR", "STR/lvl", "AGI", "AGI/lvl", "INT", "INT/lvl", "Skill CD", "Skill Mana", "Skill AoE" };
        for (int i = 0; i < hdr.Length; i++) ws.Cell(1, i + 1).Value = hdr[i];
        const int keyCols = 3, nCols = 12;

        var heroes = Objects(map, Kind.Unit).Where(o => IsHero(o))
            .Select(o => (o, name: names.Of(Kind.Unit, o)))
            .OrderBy(x => x.name, StringComparer.OrdinalIgnoreCase).ToList();

        int r = 1, count = 0;
        foreach (var (o, name) in heroes)
        {
            double? Get(string f) { var m = o.Mods.FirstOrDefault(x => x.Field == f); return m.M == null ? null : NumVal(m.M); }
            string primary()
            {
                var m = o.Mods.FirstOrDefault(x => x.Field == "upra");
                var v = m.M?.Value?.ToString() ?? "";
                return v switch { "0" => "STR", "1" => "INT", "2" => "AGI", _ => v };
            }
            r++; count++;
            int c = 1;
            ws.Cell(r, c++).Value = o.ObjCode;
            ws.Cell(r, c++).Value = name;
            ws.Cell(r, c++).Value = primary();
            foreach (var f in new[] { "ustr", "ustp", "uagi", "uagp", "uint", "uinp" })
            { var v = Get(f); if (v.HasValue) ws.Cell(r, c).Value = v.Value; c++; }
            ws.Row(r).Style.Font.Bold = true;

            WriteSkillRows(ws, ref r, SkillCodes(o, "uhab"), names, links, abSum, cdCol: 10);
        }

        StyleSheet(ws, r, nCols, keyCols, valueCols: HeroAttr.Length);
        ws.Column(2).Width = 32;
        ws.Outline.SummaryVLocation = XLOutlineSummaryVLocation.Top; // toggle sits on the hero row
        ws.CollapseRows(1); // start collapsed: a tidy alphabetical hero list you expand
        return count;
    }

    // ---------- shared skill/summary helpers (Heroes + categorized unit tabs)
    static Dictionary<string, Dictionary<string, SortedDictionary<int, double>>> BuildAbilitySummary(Map map)
    {
        var abSum = new Dictionary<string, Dictionary<string, SortedDictionary<int, double>>>();
        foreach (var o in Objects(map, Kind.Ability))
            foreach (var m in o.Mods)
                if (m.Field is "acdn" or "amcs" or "aare")
                {
                    if (!abSum.TryGetValue(o.ObjCode, out var fd)) abSum[o.ObjCode] = fd = new();
                    if (!fd.TryGetValue(m.Field, out var lv)) fd[m.Field] = lv = new();
                    lv[m.Level] = NumVal(m.M);
                }
        return abSum;
    }
    static string Sum(Dictionary<string, Dictionary<string, SortedDictionary<int, double>>> abSum, string code, string field) =>
        abSum.TryGetValue(code, out var fd) && fd.TryGetValue(field, out var lv)
            ? string.Join("/", lv.Values.Select(v => v.ToString("0.###", CultureInfo.InvariantCulture))) : "";

    static IEnumerable<string> SkillCodes(Obj o, params string[] fields)
    {
        var seen = new HashSet<string>();
        foreach (var f in fields)
        {
            var m = o.Mods.FirstOrDefault(x => x.Field == f);
            if (m.M == null) continue;
            foreach (var t in (m.M.Value?.ToString() ?? "").Split(',').Select(x => x.Trim()))
                if (t.Length == 4 && seen.Add(t)) yield return t;
        }
    }

    // Resolves a skill's link target: its row on the Abilities tab if it has common fields,
    // else its first row on the Ability Effects tab (passives/auras), else none.
    sealed class SkillLinks
    {
        public Dictionary<string, int> AbilityRows; public IXLWorksheet AbilitiesWs;
        public Dictionary<string, int> EffectRows; public IXLWorksheet EffectsWs;
        public IXLCell Target(string code)
        {
            if (AbilityRows.TryGetValue(code, out var a)) return AbilitiesWs.Cell(a, 1);
            if (EffectRows.TryGetValue(code, out var e)) return EffectsWs.Cell(e, 1);
            return null;
        }
    }

    static void LinkCell(IXLCell cell, IXLCell target, string tip)
    {
        if (target == null) return;
        cell.SetHyperlink(new XLHyperlink(target, tip));
        cell.Style.Font.FontColor = XLColor.FromHtml("#1155CC");
        cell.Style.Font.Underline = XLFontUnderlineValues.Single;
    }

    // Collapsible (read-only) skill rows under a unit/hero; skill name links to where it's editable.
    // Pure-noise skills (no name, no link, no values — e.g. locust/inventory) are skipped.
    static void WriteSkillRows(IXLWorksheet ws, ref int r, IEnumerable<string> skillCodes, NameResolver names,
        SkillLinks links, Dictionary<string, Dictionary<string, SortedDictionary<int, double>>> abSum, int cdCol)
    {
        foreach (var sc in skillCodes)
        {
            string nm = names.AbilityName(sc);
            var target = links.Target(sc);
            string cd = Sum(abSum, sc, "acdn"), mana = Sum(abSum, sc, "amcs"), aoe = Sum(abSum, sc, "aare");
            if (nm == sc && target == null && cd == "" && mana == "" && aoe == "") continue; // noise
            r++;
            var nameCell = ws.Cell(r, 2);
            nameCell.Value = "    ↳ " + nm;
            LinkCell(nameCell, target, "Edit this ability");
            ws.Cell(r, cdCol).Value = cd;
            ws.Cell(r, cdCol + 1).Value = mana;
            ws.Cell(r, cdCol + 2).Value = aoe;
            ws.Row(r).OutlineLevel = 1;
        }
    }

    static Dictionary<string, (string spawns, int tier, string race)> LoadBases()
    {
        var d = new Dictionary<string, (string, int, string)>();
        foreach (var p in new[] { Repo.Data("bases.csv") })
        {
            if (!File.Exists(p)) continue;
            foreach (var line in File.ReadLines(p).Skip(1))
            {
                var c = SplitCsv(line);
                if (c.Count >= 4 && int.TryParse(c[2], out var tier)) d[c[0]] = (c[1], tier, c[3]);
            }
            break;
        }
        return d;
    }

    // The Bases tab: base/barracks buildings (editable stats), expanding to the upgrades they
    // research (link to Upgrades) and their abilities (link to Abilities).
    static int BuildBasesSheet(XLWorkbook wb, List<Obj> bases, Dictionary<string, (string spawns, int tier, string race)> info,
        NameResolver names, SkillLinks links, IXLWorksheet upgradesWs, Dictionary<string, int> upgradeRows)
    {
        var ws = wb.Worksheets.Add("Bases");
        string[] keys = { "Code", "Name", "Tier", "Race" };
        for (int i = 0; i < keys.Length; i++) ws.Cell(1, i + 1).Value = keys[i];
        int keyCols = keys.Length;
        for (int i = 0; i < UnitStat.Length; i++) ws.Cell(1, keyCols + 1 + i).Value = UnitStat[i].Name;
        int nCols = keyCols + UnitStat.Length;

        int r = 1;
        var ordered = bases
            .Select(o => (o, meta: info.TryGetValue(o.ObjCode, out var m) ? m : ("", 99, "")))
            .OrderBy(x => x.meta.Item3).ThenBy(x => x.meta.Item2).ThenBy(x => names.Of(Kind.Unit, x.o), StringComparer.OrdinalIgnoreCase)
            .ToList();
        foreach (var (o, meta) in ordered)
        {
            double? Get(string f) { var m = o.Mods.FirstOrDefault(x => x.Field == f); return m.M == null ? null : NumVal(m.M); }
            r++;
            int c = 1;
            ws.Cell(r, c++).Value = o.ObjCode;
            ws.Cell(r, c++).Value = names.Of(Kind.Unit, o);
            ws.Cell(r, c++).Value = meta.Item2 == 99 ? "" : meta.Item2.ToString();
            ws.Cell(r, c++).Value = meta.Item3;
            for (int i = 0; i < UnitStat.Length; i++) { var v = Get(UnitStat[i].Code); if (v.HasValue) ws.Cell(r, keyCols + 1 + i).Value = v.Value; }
            ws.Row(r).Style.Font.Bold = true;

            foreach (var ug in SkillCodes(o, "ures"))
            {
                r++;
                var cell = ws.Cell(r, 2);
                cell.Value = "    ⤷ upgrade: " + names.UpgradeName(ug);
                LinkCell(cell, upgradeRows.TryGetValue(ug, out var ur) ? upgradesWs.Cell(ur, 1) : null, "Edit on the Upgrades tab");
                ws.Row(r).OutlineLevel = 1;
            }
            foreach (var ab in SkillCodes(o, "uabi"))
            {
                string nm = names.AbilityName(ab);
                var target = links.Target(ab);
                if (nm == ab && target == null) continue; // skip unnamed/no-data passives
                r++;
                var cell = ws.Cell(r, 2);
                cell.Value = "    ↳ " + nm;
                LinkCell(cell, target, "Edit this ability");
                ws.Row(r).OutlineLevel = 1;
            }
        }
        StyleSheet(ws, r, nCols, keyCols);
        ws.Column(2).Width = 32;
        ws.Outline.SummaryVLocation = XLOutlineSummaryVLocation.Top;
        ws.CollapseRows(1);
        return bases.Count;
    }

    // A categorized unit tab: header row = editable combat stats (+ optional Tier); expand to skills.
    static int BuildExpandableUnitSheet(XLWorkbook wb, string tab, List<(Obj o, int? tier)> units,
        NameResolver names, SkillLinks links,
        Dictionary<string, Dictionary<string, SortedDictionary<int, double>>> abSum)
    {
        var ws = wb.Worksheets.Add(tab);
        bool showTier = units.Any(u => u.tier.HasValue);
        var keys = new List<string> { "Code", "Name" };
        if (showTier) keys.Add("Tier");
        int keyCols = keys.Count;
        for (int i = 0; i < keys.Count; i++) ws.Cell(1, i + 1).Value = keys[i];
        for (int i = 0; i < UnitStat.Length; i++) ws.Cell(1, keyCols + 1 + i).Value = UnitStat[i].Name;
        int cdCol = keyCols + UnitStat.Length + 1;
        ws.Cell(1, cdCol).Value = "Skill CD"; ws.Cell(1, cdCol + 1).Value = "Skill Mana"; ws.Cell(1, cdCol + 2).Value = "Skill AoE";
        int nCols = cdCol + 2;

        int r = 1;
        var ordered = units
            .Select(u => (u.o, u.tier, name: names.Of(Kind.Unit, u.o)))
            .OrderBy(u => u.name.Length == 0)               // named units first, blanks last
            .ThenBy(u => u.name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        foreach (var (o, tier, name) in ordered)
        {
            double? Get(string f) { var m = o.Mods.FirstOrDefault(x => x.Field == f); return m.M == null ? null : NumVal(m.M); }
            r++;
            int c = 1;
            ws.Cell(r, c++).Value = o.ObjCode;
            ws.Cell(r, c++).Value = name;
            if (showTier) { if (tier.HasValue) ws.Cell(r, c).Value = tier.Value; c++; }
            for (int i = 0; i < UnitStat.Length; i++) { var v = Get(UnitStat[i].Code); if (v.HasValue) ws.Cell(r, keyCols + 1 + i).Value = v.Value; }
            ws.Row(r).Style.Font.Bold = true;
            WriteSkillRows(ws, ref r, SkillCodes(o, "uhab", "uabi"), names, links, abSum, cdCol);
        }
        StyleSheet(ws, r, nCols, keyCols, valueCols: UnitStat.Length);
        ws.Column(2).Width = 30;
        ws.Outline.SummaryVLocation = XLOutlineSummaryVLocation.Top;
        ws.CollapseRows(1);
        return units.Count;
    }

    // Unit codes referenced by ability data (summons) or by a specific unit field (e.g. useu = units sold).
    static HashSet<string> DetectUnitRefs(Map map, HashSet<string> unitCodes, Kind kind, string onlyField = null)
    {
        var res = new HashSet<string>();
        foreach (var o in Objects(map, kind))
            foreach (var m in o.Mods)
            {
                if (onlyField != null && m.Field != onlyField) continue;
                if (LevelFilled.Contains(m.M)) continue; // categorize by what the map authored, not by fill defaults
                if (m.M.Type == ObjectDataType.String)
                    foreach (var t in (m.M.Value?.ToString() ?? "").Split(',').Select(x => x.Trim()))
                        { if (t.Length == 4 && unitCodes.Contains(t)) res.Add(t); }
                else if (m.M.Type == ObjectDataType.Int)
                    { var c = Code(m.M.ValueAsInt); if (unitCodes.Contains(c)) res.Add(c); }
            }
        return res;
    }

    // A friendly first tab explaining the workbook for non-technical editors.
    static void BuildGuideSheet(XLWorkbook wb)
    {
        var ws = wb.Worksheets.Add("Guide");
        var rows = new (string a, string b)[]
        {
            ("Footmen Frenzy — Balance Workbook", ""),
            ("", ""),
            ("HOW TO USE", ""),
            ("Edit the white number cells.", "Grey columns are identifiers (Code/Name/…) and are locked — you can't edit them."),
            ("Every tab is sorted A–Z and locked.", "Sorting is disabled so the rows can't get scrambled; the order is always alphabetical."),
            ("Need a different order? Sort or filter freely", "— matching is key-based, so row order never affects the build."),
            ("Click the [+] on the left margin", "to expand a hero / unit / base / shop and see its skills, items or upgrades."),
            ("Blue underlined names are links", "click one to jump to where that thing is editable (e.g. a skill → the Abilities tab)."),
            ("Only change existing numbers.", "Filling a blank cell is ignored when the map is rebuilt. Ability levels 5+ come pre-filled with the pre-3.0 defaults (WC3 3.0 fix)."),
            ("A cell turns red the moment you edit it.", "That means it now differs from the current map (i.e. not built/shipped yet)."),
            ("To review just your edits:", "click a tab's filter icon -> Filter by color -> Conditional format color -> the red."),
            ("When done: save as .xlsx,", "then run  'make all'  to build the balanced map and verify only your edits changed."),
            ("", ""),
            ("TABS", ""),
            ("Heroes", "Every hero: primary attributes (editable) + expand to its 4 skills."),
            ("Human / Orc / Undead / NightElf / Elintian", "The base/spawn units of each race, by tier. Expand for unit abilities."),
            ("Bases", "Base/barracks buildings per race & tier; expand to the upgrades they research + abilities."),
            ("Towers", "Tower units; expand for tower abilities."),
            ("Creep Shop", "Units sold at creep shops."),
            ("Summons", "Units created by abilities (broad heuristic — also catches morph/transform targets)."),
            ("Other", "Everything else (named units first; unnamed internal/dummy units last)."),
            ("Abilities", "All abilities with cooldown / mana / area / range / duration, per level."),
            ("Ability Effects", "Per-ability effect values (lifesteal %, damage, …). Filter by Code or BaseType."),
            ("Items", "Item economy (gold / stock / charges) + which Shop sells each."),
            ("Upgrades", "Research upgrades: cost (base+increment) and effect amounts, per level."),
            ("Shops", "Each shop; expand to the items it sells (links to the Items tab)."),
        };
        for (int i = 0; i < rows.Length; i++) { ws.Cell(i + 1, 1).Value = rows[i].a; ws.Cell(i + 1, 2).Value = rows[i].b; }
        ws.Cell(1, 1).Style.Font.Bold = true; ws.Cell(1, 1).Style.Font.FontSize = 14;
        foreach (var hr in new[] { 3, rows.Length - 13 }) ws.Cell(hr, 1).Style.Font.Bold = true; // HOW TO USE / TABS
        ws.Column(1).Width = 42; ws.Column(2).Width = 80;
        ws.Range(rows.Length - 12, 1, rows.Length, 1).Style.Font.Bold = true;
        ws.Protect().AllowElement(XLSheetProtectionElements.AutoFilter); // reference text, fully locked
    }

    static Dictionary<string, (int tier, string race)> LoadSpawnRoster()
    {
        var d = new Dictionary<string, (int, string)>();
        foreach (var p in new[] { Repo.Data("spawns.csv") })
        {
            if (!File.Exists(p)) continue;
            foreach (var line in File.ReadLines(p).Skip(1))
            {
                var c = SplitCsv(line);
                if (c.Count >= 4 && int.TryParse(c[2], out var tier)) d[c[0]] = (tier, c[3]);
            }
            break;
        }
        return d;
    }

    // Per-tab layout of the editable value block, recorded by StyleSheet for every tab that has one
    // (valueCols != 0). Mirrors a hidden "baseline" copy of
    // each value cell (the value currently baked in the map) so a conditional-format rule can turn
    // a cell red the instant it's edited to differ — no tool run required, see [[balance-tool]]. Keyed
    // by tab name; repopulated fresh every BuildWorkbook() call (single-shot CLI process, so no staleness
    // across commands).
    readonly record struct ValueBlock(int ValueStart, int Width, int BaselineStart, int LastRow);
    static readonly Dictionary<string, ValueBlock> ValueLayout = new();

    // Red fill for "edited but not yet built into the map" (the offline conditional-format rule).
    const string HlUncommittedHex = "#F4CCCC";

    // valueCols = how many editable value columns follow the key columns (-1 = all of them).
    // Trailing read-only columns (e.g. the "Skill CD/Mana/AoE" summaries) are excluded by passing a count.
    static void StyleSheet(IXLWorksheet ws, int lastRow, int nCols, int keyCols, int valueCols = -1)
    {
        var header = ws.Range(1, 1, 1, nCols);
        header.Style.Font.Bold = true;
        header.Style.Font.FontColor = XLColor.White;
        header.Style.Fill.BackgroundColor = XLColor.FromHtml("#4472C4");
        header.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
        if (lastRow >= 2)
            ws.Range(2, 1, lastRow, keyCols).Style.Fill.BackgroundColor = XLColor.FromHtml("#F2F2F2");
        ws.SheetView.FreezeRows(1);
        ws.SheetView.FreezeColumns(keyCols);
        ws.Range(1, 1, Math.Max(lastRow, 1), nCols).SetAutoFilter();
        ws.Columns(1, nCols).Width = 13;
        ws.Column(2).Width = 28; // Name
        LockSheet(ws, lastRow, keyCols, valueCols < 0 ? nCols : keyCols + valueCols);

        int width = valueCols < 0 ? nCols - keyCols : valueCols;
        if (width > 0 && lastRow >= 2)
        {
            int valueStart = keyCols + 1, baselineStart = nCols + 1;
            for (int r = 2; r <= lastRow; r++)
                for (int i = 0; i < width; i++)
                {
                    var src = ws.Cell(r, valueStart + i);
                    if (src.TryGetValue<double>(out var v)) ws.Cell(r, baselineStart + i).Value = v;
                }
            for (int i = 0; i < width; i++) ws.Cell(1, baselineStart + i).Value = "_baseline_" + ws.Cell(1, valueStart + i).GetString();
            ws.Columns(baselineStart, baselineStart + width - 1).Hide();
            ValueLayout[ws.Name] = new ValueBlock(valueStart, width, baselineStart, lastRow);

            // Offline twin of HighlightInit's live Sheets rule: a native OOXML conditional-format rule
            // so a cell turns red the instant it's edited in Excel or LibreOffice. Same formula shape (blank = "no instruction", so never red; ROUND(...,4) to
            // avoid float32/double noise flagging an untouched cell) as the Sheets rule. ONE rule covers
            // the whole value block (not one AddConditionalFormat call per column) — every value column
            // sits at the same fixed offset from its own baseline column (baselineStart - valueStart),
            // so a single formula anchored at the range's top-left cell auto-adjusts per cell exactly
            // like a filled-across formula. (Calling AddConditionalFormat once per column instead was
            // tried first and silently broke: ClosedXML merges same-style adjacent single-column CF
            // ranges into one <conditionalFormatting> sqref on save but keeps only ONE column's formula
            // — every other column ends up highlighted by the wrong comparison.)
            var hlColor = XLColor.FromHtml(HlUncommittedHex);
            string anchorV = ColLetter(valueStart), anchorB = ColLetter(baselineStart);
            string formula = $"=AND({anchorV}2<>\"\", IFERROR(ROUND({anchorV}2-{anchorB}2,4)<>0, TRUE))";
            ws.Range(2, valueStart, lastRow, valueStart + width - 1).AddConditionalFormat().WhenIsTrue(formula).Fill.SetBackgroundColor(hlColor);
        }
    }

    // Keep the alphabetical order stable: only the white value cells are editable; identifiers and
    // read-only cells stay locked, and the sheet is protected so Data->Sort can't scramble the rows.
    // (Fully enforced in Excel/LibreOffice. The build
    // ignores row order regardless, so this protects the *view*, never the output.)
    static void LockSheet(IXLWorksheet ws, int lastRow, int keyCols, int lastEditCol)
    {
        if (lastRow >= 2 && lastEditCol > keyCols)
            ws.Range(2, keyCols + 1, lastRow, lastEditCol).Style.Protection.SetLocked(false);
        ws.Protect()
            .AllowElement(XLSheetProtectionElements.AutoFilter)
            .AllowElement(XLSheetProtectionElements.FormatCells)
            .AllowElement(XLSheetProtectionElements.FormatColumns)
            .AllowElement(XLSheetProtectionElements.FormatRows);
    }

    // =================================================================== APPLY
    static int Apply(string mapPath, string inXlsx, string outMap)
    {
        var map = Map.Open(mapPath);
        var fill = FillLevels(map);
        using var wb = OpenWorkbookTolerant(inXlsx);
        return ApplyWorkbook(wb, map, mapPath, outMap, fill.Cells);
    }

    // Reads edited values from any workbook (local .xlsx OR an in-memory book built from the live
    // workbook) and regenerates the map. Matching is key-based (Code|Field|Level[|Pointer]), so
    // row order is irrelevant.
    static int ApplyWorkbook(XLWorkbook wb, Map map, string mapPath, string outMap, int levelFilled = 0)
    {
        var changed = new HashSet<Kind>();
        int applied = 0, missing = 0;

        foreach (var k in new[] { Kind.Ability, Kind.Item, Kind.Upgrade })
        {
            if (!wb.TryGetWorksheet(TabName(k), out var ws)) continue;
            // index existing common-field mods for this kind
            var commonSet = Common(k).Select(c => c.Code).ToHashSet();
            var index = new Dictionary<string, ObjectDataModification>();
            foreach (var o in Objects(map, k))
                foreach (var m in o.Mods)
                    if (commonSet.Contains(m.Field)) index[$"{o.ObjCode}|{m.Field}|{m.Level}"] = m.M;

            var hdr = HeaderMap(ws);
            int cCode = hdr["Code"];
            int cLevel = Leveled(k) && hdr.TryGetValue("Level", out var lv) ? lv : 0;
            var colToField = new Dictionary<int, string>();
            foreach (var f in Common(k)) if (hdr.TryGetValue(f.Name, out var col)) colToField[col] = f.Code;

            int before = applied;
            foreach (var row in ws.RowsUsed().Skip(1))
            {
                string obj = row.Cell(cCode).GetString().Trim();
                if (obj.Length == 0) continue;
                int level = cLevel > 0 ? (int)row.Cell(cLevel).GetDouble() : 0;
                foreach (var (col, fc) in colToField)
                {
                    var cell = row.Cell(col);
                    if (cell.IsEmpty() || !cell.TryGetValue<double>(out var v)) continue;
                    if (index.TryGetValue($"{obj}|{fc}|{level}", out var m)) applied += Set(m, v, obj, fc, level);
                    else missing++;
                }
            }
            if (applied > before) changed.Add(k);
        }

        // Ability Effects (long) -> also Ability kind
        if (wb.TryGetWorksheet("Ability Effects", out var ews))
        {
            var effIdx = new Dictionary<string, ObjectDataModification>();
            var commonSet = AbilityCommon.Select(c => c.Code).ToHashSet();
            foreach (var o in Objects(map, Kind.Ability))
                foreach (var m in o.Mods)
                    if (!commonSet.Contains(m.Field) && IsNumeric(m.M.Type))
                        effIdx[$"{o.ObjCode}|{m.Field}|{m.Level}|{m.Pointer}"] = m.M;

            var hdr = HeaderMap(ews);
            int before = applied;
            foreach (var row in ews.RowsUsed().Skip(1))
            {
                string obj = row.Cell(hdr["Code"]).GetString().Trim();
                if (obj.Length == 0) continue;
                string fc = row.Cell(hdr["Field"]).GetString().Trim();
                int level = (int)row.Cell(hdr["Level"]).GetDouble();
                int ptr = (int)row.Cell(hdr["Pointer"]).GetDouble();
                var cell = row.Cell(hdr["Value"]);
                if (cell.IsEmpty() || !cell.TryGetValue<double>(out var v)) continue;
                if (effIdx.TryGetValue($"{obj}|{fc}|{level}|{ptr}", out var m)) applied += Set(m, v, obj, fc, level);
                else missing++;
            }
            if (applied > before) changed.Add(Kind.Ability);
        }

        // Categorized unit tabs (Human/.../Other): combat-stat cells write back to unit object data.
        {
            var statFields = UnitStat.Select(c => c.Code).ToHashSet();
            var idx = new Dictionary<string, ObjectDataModification>();
            foreach (var o in Objects(map, Kind.Unit))
                foreach (var m in o.Mods)
                    if (statFields.Contains(m.Field)) idx[$"{o.ObjCode}|{m.Field}"] = m.M;
            foreach (var tab in UnitCategoryTabs)
            {
                if (!wb.TryGetWorksheet(tab, out var ws)) continue;
                var hdr = HeaderMap(ws);
                if (!hdr.TryGetValue("Code", out var cCode)) continue;
                var colToField = new Dictionary<int, string>();
                foreach (var col in UnitStat) if (hdr.TryGetValue(col.Name, out var ci)) colToField[ci] = col.Code;
                int before = applied;
                foreach (var row in ws.RowsUsed().Skip(1))
                {
                    string obj = row.Cell(cCode).GetString().Trim();
                    if (obj.Length == 0) continue; // skill rows
                    foreach (var (ci, fc) in colToField)
                    {
                        var cell = row.Cell(ci);
                        if (cell.IsEmpty() || !cell.TryGetValue<double>(out var v)) continue;
                        if (idx.TryGetValue($"{obj}|{fc}", out var m)) applied += Set(m, v, obj, fc, 0);
                        else missing++;
                    }
                }
                if (applied > before) changed.Add(Kind.Unit);
            }
        }

        // Heroes tab: editable primary-attribute cells write back to unit object data.
        if (wb.TryGetWorksheet("Heroes", out var hws))
        {
            var attrFields = HeroAttr.Select(c => c.Code).ToHashSet();
            var idx = new Dictionary<string, ObjectDataModification>();
            foreach (var o in Objects(map, Kind.Unit))
                foreach (var m in o.Mods)
                    if (attrFields.Contains(m.Field)) idx[$"{o.ObjCode}|{m.Field}"] = m.M;

            var hdr = HeaderMap(hws);
            int cCode = hdr["Code"];
            var colToField = new Dictionary<int, string>();
            foreach (var col in HeroAttr) if (hdr.TryGetValue(col.Name, out var ci)) colToField[ci] = col.Code;

            int before = applied;
            foreach (var row in hws.RowsUsed().Skip(1))
            {
                string obj = row.Cell(cCode).GetString().Trim(); // skill rows have a blank Code
                if (obj.Length == 0) continue;
                foreach (var (ci, fc) in colToField)
                {
                    var cell = row.Cell(ci);
                    if (cell.IsEmpty() || !cell.TryGetValue<double>(out var v)) continue;
                    if (idx.TryGetValue($"{obj}|{fc}", out var m)) applied += Set(m, v, obj, fc, 0);
                    else missing++;
                }
            }
            if (applied > before) changed.Add(Kind.Unit);
        }

        Console.WriteLine($"Applied {applied} change(s) across {changed.Count} type(s)." +
            (missing > 0 ? $" ({missing} edited cell(s) had no existing field/level to update.)" : ""));
        if (levelFilled > 0) changed.Add(Kind.Ability); // the level fill itself changes war3map.w3a

        BuildMap(map, mapPath, outMap, changed);
        return 0;
    }

    static int Set(ObjectDataModification m, double v, string obj, string fc, int level)
    {
        // Compare in the value's STORED type (32-bit float / int), not as double, so a
        // spreadsheet's "0.65" doesn't look different from float 0.6499999.
        if (m.Type == ObjectDataType.Int)
        {
            int nv = (int)Math.Round(v), ov = m.ValueAsInt;
            if (nv == ov) return 0;
            Console.WriteLine($"  {obj} {fc} L{level}: {ov} -> {nv}");
            m.Value = nv;
        }
        else
        {
            float nv = (float)v, ov = m.ValueAsFloat;
            if (nv == ov) return 0;
            Console.WriteLine($"  {obj} {fc} L{level}: {ov.ToString(CultureInfo.InvariantCulture)} -> {nv.ToString(CultureInfo.InvariantCulture)}");
            m.Value = nv;
        }
        return 1;
    }

    // Surgical rebuild: regenerate ONLY the object-data files for types that actually changed;
    // copy every other file (war3map.wts, terrain, triggers, imports, skins) VERBATIM.
    static void BuildMap(Map map, string mapPath, string outMap, HashSet<Kind> changed)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outMap)) ?? ".");
        var fresh = new Dictionary<string, MpqFile>(StringComparer.OrdinalIgnoreCase);
        if (changed.Contains(Kind.Ability)) fresh[MainFile(Kind.Ability)] = map.GetAbilityObjectDataFile(null);
        if (changed.Contains(Kind.Unit)) fresh[MainFile(Kind.Unit)] = map.GetUnitObjectDataFile(null);
        if (changed.Contains(Kind.Item)) fresh[MainFile(Kind.Item)] = map.GetItemObjectDataFile(null);
        if (changed.Contains(Kind.Upgrade)) fresh[MainFile(Kind.Upgrade)] = map.GetUpgradeObjectDataFile(null);

        var managed = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "(listfile)", "(attributes)", "(signature)" };
        using var src = MpqArchive.Open(mapPath, true);
        src.DiscoverFileNames();
        var builder = new MpqArchiveBuilder();
        foreach (var f in fresh.Values) builder.AddFile(f);

        int copied = 0;
        foreach (var f in src.GetMpqFiles())
        {
            if (f is MpqKnownFile k && (fresh.ContainsKey(k.FileName) || managed.Contains(k.FileName))) continue;
            builder.AddFile(f); copied++;
        }
        builder.SaveWithPreArchiveData(outMap, new MpqArchiveCreateOptions { BlockSize = 3 });
        Console.WriteLine($"Copied {copied} file(s) verbatim; regenerated {(fresh.Count == 0 ? "nothing" : string.Join(", ", fresh.Keys))}.");
        Console.WriteLine($"BUILD OK -> {outMap}");
    }

    // ---------- Name resolution (TRIGSTR -> string table; abilities also use abilities.csv)
    sealed class NameResolver
    {
        readonly Dictionary<uint, string> _trig = new();
        readonly Dictionary<Kind, Dictionary<string, string>> _csv = new();
        public NameResolver(Map map)
        {
            if (map.TriggerStrings != null)
                foreach (var s in map.TriggerStrings.Strings) _trig[s.Key] = s.Value ?? "";
            // Names come from the rework's Constants.cs (same map lineage), exported to *.csv.
            _csv[Kind.Ability] = Load("abilities.csv");
            _csv[Kind.Unit] = Load("units.csv");
            _csv[Kind.Item] = Load("items.csv");
            _csv[Kind.Upgrade] = Load("upgrades.csv");
        }
        static Dictionary<string, string> Load(string file)
        {
            var d = new Dictionary<string, string>();
            foreach (var p in new[] { Repo.Data(file) })
            {
                if (!File.Exists(p)) continue;
                foreach (var line in File.ReadLines(p).Skip(1))
                {
                    var c = SplitCsv(line);
                    if (c.Count >= 3 && !d.ContainsKey(c[0])) d[c[0]] = c[2];
                }
                break;
            }
            return d;
        }
        public string Resolve(string v)
        {
            if (v != null && v.StartsWith("TRIGSTR_") && uint.TryParse(v.AsSpan(8).Trim(), out var key) && _trig.TryGetValue(key, out var t))
                return t;
            return v ?? "";
        }
        public string Of(Kind kind, Obj o)
        {
            if (_csv.TryGetValue(kind, out var d) && d.TryGetValue(o.ObjCode, out var n) && n.Length > 0) return n;
            foreach (var m in o.Mods)
                if (Array.IndexOf(NameFields, m.Field) >= 0 && m.M.Type == ObjectDataType.String)
                {
                    var s = Resolve(m.M.Value?.ToString());
                    if (!string.IsNullOrWhiteSpace(s)) return s;
                }
            return "";
        }
        public string UnitName(string code) => _csv[Kind.Unit].TryGetValue(code, out var n) && n.Length > 0 ? n : code;
        public string AbilityName(string code) => _csv[Kind.Ability].TryGetValue(code, out var n) && n.Length > 0 ? n : code;
        public string UpgradeName(string code) => _csv[Kind.Upgrade].TryGetValue(code, out var n) && n.Length > 0 ? n : code;
    }

    // ---------- Shop index (which shop sells which item, via the unit 'usei' field)
    sealed class ShopIndex
    {
        readonly Dictionary<string, List<string>> _shopNamesOfItem = new();      // item -> shop NAMES
        readonly List<(string code, string shopName, List<string> items)> _shops = new();
        readonly Dictionary<string, string> _itemNames;
        public int Count => _shops.Count;
        public ShopIndex(Map map, NameResolver names)
        {
            _itemNames = new Dictionary<string, string>();
            foreach (var o in Objects(map, Kind.Item)) _itemNames[o.ObjCode] = names.Of(Kind.Item, o);
            foreach (var o in Objects(map, Kind.Unit))
            {
                var sold = o.Mods.FirstOrDefault(m => m.Field == "usei");
                if (sold.M == null) continue;
                var items = (sold.M.Value?.ToString() ?? "").Split(',').Select(t => t.Trim())
                    .Where(t => t.Length == 4 && _itemNames.ContainsKey(t)).ToList();
                if (items.Count == 0) continue;
                string shopName = names.UnitName(o.ObjCode);
                _shops.Add((o.ObjCode, shopName, items));
                foreach (var it in items)
                {
                    if (!_shopNamesOfItem.TryGetValue(it, out var l)) _shopNamesOfItem[it] = l = new();
                    if (!l.Contains(shopName)) l.Add(shopName);
                }
            }
        }
        public string ShopsOf(string item) => _shopNamesOfItem.TryGetValue(item, out var l) ? string.Join("; ", l) : "";
        // Expandable: one collapsible group per shop; expand to its items (each links to the Items tab).
        public void BuildSheet(XLWorkbook wb, IXLWorksheet itemsWs, Dictionary<string, int> itemRows)
        {
            var ws = wb.Worksheets.Add("Shops");
            string[] hdr = { "Shop / Item", "Code", "# Items" };
            for (int i = 0; i < hdr.Length; i++) ws.Cell(1, i + 1).Value = hdr[i];
            int r = 1;
            foreach (var (code, shopName, items) in _shops.OrderBy(s => s.shopName))
            {
                r++;
                ws.Cell(r, 1).Value = shopName;
                ws.Cell(r, 2).Value = code;
                ws.Cell(r, 3).Value = items.Count;
                ws.Row(r).Style.Font.Bold = true;
                foreach (var it in items)
                {
                    r++;
                    var cell = ws.Cell(r, 1);
                    cell.Value = "    ↳ " + (_itemNames.TryGetValue(it, out var n) && n.Length > 0 ? n : it);
                    ws.Cell(r, 2).Value = it;
                    if (itemRows.TryGetValue(it, out var ir))
                    {
                        cell.SetHyperlink(new XLHyperlink(itemsWs.Cell(ir, 1), "Edit on the Items tab"));
                        cell.Style.Font.FontColor = XLColor.FromHtml("#1155CC");
                        cell.Style.Font.Underline = XLFontUnderlineValues.Single;
                    }
                    ws.Row(r).OutlineLevel = 1;
                }
            }
            StyleSheet(ws, r, 3, keyCols: 2, valueCols: 0); // Shops are read-only (# Items is a count)
            ws.Column(1).Width = 34;
            ws.Outline.SummaryVLocation = XLOutlineSummaryVLocation.Top;
            ws.CollapseRows(1);
        }
    }

    static XLWorkbook OpenWorkbookTolerant(string path)
    {
        try { return new XLWorkbook(path); }
        catch (Exception)
        {
            string tmp = Path.Combine(Path.GetTempPath(), "ff_balance_" + Guid.NewGuid().ToString("N") + ".xlsx");
            File.Copy(path, tmp, true);
            using (var zip = ZipFile.Open(tmp, ZipArchiveMode.Update))
            {
                var entry = zip.GetEntry("docProps/core.xml");
                if (entry != null)
                {
                    string xml;
                    using (var rd = new StreamReader(entry.Open())) xml = rd.ReadToEnd();
                    string fixedXml = Regex.Replace(xml, @"([+-]\d{2}:\d{2})Z", "$1");
                    if (fixedXml != xml)
                    {
                        entry.Delete();
                        var ne = zip.CreateEntry("docProps/core.xml");
                        using var w = new StreamWriter(ne.Open());
                        w.Write(fixedXml);
                    }
                }
            }
            return new XLWorkbook(tmp);
        }
    }

    static Dictionary<string, int> HeaderMap(IXLWorksheet ws)
    {
        var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var c in ws.Row(1).CellsUsed()) map[c.GetString().Trim()] = c.Address.ColumnNumber;
        return map;
    }

    // =================================================================== WORKBOOK COLUMN HELPERS
    // Header columns that identify a row (never written as balance values).
    static readonly HashSet<string> IdentifierCols = new(StringComparer.OrdinalIgnoreCase)
        { "Code", "Name", "BaseType", "Shop", "Level", "Pointer", "Field", "Tier", "Race", "Primary" };

    // Hidden mirror columns StyleSheet writes alongside every value column (see ValueLayout) —
    // never a real balance field, so generic "every non-identifier header is a value column"
    // scans (reconcile) must skip them explicitly.
    static bool IsBaselineCol(string h) => h != null && h.StartsWith("_baseline_", StringComparison.Ordinal);

    static string ColLetter(int col1)
    {
        var s = "";
        while (col1 > 0) { int m = (col1 - 1) % 26; s = (char)('A' + m) + s; col1 = (col1 - m - 1) / 26; }
        return s;
    }

    static bool TryNum(object o, out double d)
    {
        d = 0;
        switch (o)
        {
            case null: return false;
            case double x: d = x; return true;
            case float x: d = x; return true;
            case long x: d = x; return true;
            case int x: d = x; return true;
            case decimal x: d = (double)x; return true;
            case string s: return double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out d);
            default: return double.TryParse(o.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out d);
        }
    }

    static void PutCell(IXLCell cell, object v)
    {
        switch (v)
        {
            case null: break;
            case double x: cell.Value = x; break;
            case float x: cell.Value = x; break;
            case long x: cell.Value = x; break;
            case int x: cell.Value = x; break;
            case decimal x: cell.Value = (double)x; break;
            case bool x: cell.Value = x; break;
            case string s: cell.Value = s; break;
            default: cell.Value = v.ToString(); break;
        }
    }

    // =================================================================== DUMPALL (verify, all types)
    static int DumpAll(string mapPath, string outCsv, bool fill = false)
    {
        var map = Map.Open(mapPath);
        if (fill) FillLevels(map);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outCsv)) ?? ".");
        int rows = 0;
        using var w = new StreamWriter(outCsv, false, new UTF8Encoding(false));
        w.WriteLine("Type,ObjectCode,BaseCode,Field,Level,Pointer,Type2,Value");
        foreach (var k in new[] { Kind.Ability, Kind.Unit, Kind.Item, Kind.Upgrade })
            foreach (var o in Objects(map, k))
                foreach (var m in o.Mods)
                {
                    w.WriteLine(string.Join(",", k, Csv(o.ObjCode), Csv(o.BaseCode), Csv(m.Field),
                        m.Level, m.Pointer, Csv(m.M.Type.ToString()), Csv(ValStr(m.M))));
                    rows++;
                }
        w.Flush();
        Console.WriteLine($"Dumped {rows} modifications (all types) -> {outCsv}");
        return 0;
    }

    static string ValStr(ObjectDataModification m)
    {
        try
        {
            return m.Type switch
            {
                ObjectDataType.Int => m.ValueAsInt.ToString(CultureInfo.InvariantCulture),
                ObjectDataType.Real or ObjectDataType.Unreal => m.ValueAsFloat.ToString(CultureInfo.InvariantCulture),
                _ => m.Value?.ToString() ?? "",
            };
        }
        catch { return m.Value?.ToString() ?? ""; }
    }

    static string Csv(string s)
    {
        s ??= "";
        if (s.Contains('"') || s.Contains(',') || s.Contains('\n') || s.Contains('\r'))
            return "\"" + s.Replace("\"", "\"\"") + "\"";
        return s;
    }

    static List<string> SplitCsv(string line)
    {
        var result = new List<string>();
        var sb = new StringBuilder();
        bool q = false;
        for (int i = 0; i < line.Length; i++)
        {
            char ch = line[i];
            if (q)
            {
                if (ch == '"') { if (i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i++; } else q = false; }
                else sb.Append(ch);
            }
            else if (ch == '"') q = true;
            else if (ch == ',') { result.Add(sb.ToString()); sb.Clear(); }
            else sb.Append(ch);
        }
        result.Add(sb.ToString());
        return result;
    }
}

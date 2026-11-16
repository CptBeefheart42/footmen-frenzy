using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using War3Net.Build.Info;
using War3Net.Build.Object;

// Shared by tools/BalanceTool and scripting/build (linked into both csproj files).
//
// WC3 3.0.0 stopped applying an ability's AbilityData.slk LEVEL-4 column to levels 5+: on abilities
// with more than 4 levels, any per-level field the map never set at levels 5+ now reads 0 (free
// spells, zero cooldowns, zero cast range). Our maps were saved for 2.0.4, where those cells were
// never needed. The "level fill" writes them explicitly with the exact 2.0.4 level-4 defaults from
// ability_level_defaults.csv (tools/slk/extract_ability_defaults.py), so the maps play the same on
// 3.0 as they did on 2.0.4 — regardless of whether Blizzard later restores the old rule.
namespace FootmenFrenzy.Shared
{
    public sealed class AbilityLevelDefaults
    {
        public const string FileName = "ability_level_defaults.csv";

        public readonly struct Entry
        {
            public Entry(int id, int pointer, ObjectDataType type, object value)
            {
                Id = id; Pointer = pointer; Type = type; Value = value;
            }

            public int Id { get; }
            public int Pointer { get; }
            public ObjectDataType Type { get; }
            public object Value { get; }
        }

        readonly Dictionary<int, Entry[]> _byBase;

        AbilityLevelDefaults(string path, Dictionary<int, Entry[]> byBase)
        {
            Path = path;
            _byBase = byBase;
        }

        public string Path { get; }

        public int CellCount => _byBase.Values.Sum(e => e.Length);

        public bool IsKnownBase(int baseId) => _byBase.ContainsKey(baseId);

        public IReadOnlyList<Entry> For(int baseId) => _byBase.TryGetValue(baseId, out var e) ? e : Array.Empty<Entry>();

        // FF_LEVEL_DEFAULTS wins; else <repoRoot>/ability_level_defaults.csv; else the working dir and
        // its parents (the balance tool runs from the repo root, like abilities.csv).
        public static string Resolve()
        {
            var env = Environment.GetEnvironmentVariable("FF_LEVEL_DEFAULTS");
            if (!string.IsNullOrWhiteSpace(env))
            {
                if (!File.Exists(env)) throw new FileNotFoundException($"FF_LEVEL_DEFAULTS points at a missing file: {env}");
                return env;
            }
            var path = Repo.Data(FileName);
            if (!File.Exists(path)) throw new FileNotFoundException($"{path} not found; regenerate it with tools/slk/extract_ability_defaults.py or set FF_LEVEL_DEFAULTS.");
            return path;
        }

        public static AbilityLevelDefaults Load(string path)
        {
            var byBase = new Dictionary<int, List<Entry>>();
            int lineNo = 0;
            bool header = false;
            foreach (var line in File.ReadLines(path))
            {
                lineNo++;
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                var c = SplitCsv(line);
                if (!header)
                {
                    if (c.Count < 5 || c[0] != "BaseCode") throw new InvalidDataException($"{path}:{lineNo}: expected header BaseCode,Field,Pointer,Type,Value");
                    header = true;
                    continue;
                }
                if (c.Count != 5 || c[0].Length != 4) throw new InvalidDataException($"{path}:{lineNo}: malformed row");
                int baseId = AbilityLevelFill.FourCC(c[0]);
                if (!byBase.TryGetValue(baseId, out var list)) byBase[baseId] = list = new List<Entry>();
                if (c[1].Length == 0) continue; // known base with nothing to fill
                if (c[1].Length is < 3 or > 4) throw new InvalidDataException($"{path}:{lineNo}: bad field id '{c[1]}'");
                try
                {
                    var type = (ObjectDataType)Enum.Parse(typeof(ObjectDataType), c[3]);
                    object value = type switch
                    {
                        ObjectDataType.Int => int.Parse(c[4], NumberStyles.Integer, CultureInfo.InvariantCulture),
                        ObjectDataType.Real or ObjectDataType.Unreal => float.Parse(c[4], NumberStyles.Float, CultureInfo.InvariantCulture),
                        ObjectDataType.String => c[4],
                        _ => throw new InvalidDataException($"unsupported type {c[3]}"),
                    };
                    list.Add(new Entry(AbilityLevelFill.FourCC(c[1]), int.Parse(c[2], CultureInfo.InvariantCulture), type, value));
                }
                catch (Exception e) when (e is FormatException or OverflowException or ArgumentException)
                {
                    throw new InvalidDataException($"{path}:{lineNo}: {e.Message}");
                }
            }
            if (!header) throw new InvalidDataException($"{path}: no header row");
            return new AbilityLevelDefaults(path, byBase.ToDictionary(kv => kv.Key, kv => kv.Value.ToArray()));
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

    public static class AbilityLevelFill
    {
        public sealed class Result
        {
            public int Cells { get; internal set; }
            public int Abilities { get; internal set; }

            // The modifications this fill created (reference identity), so consumers can tell filled
            // cells from map-authored ones.
            public HashSet<ObjectDataModification> Added { get; } = new(ReferenceEqualityComparer.Instance);

            // "object/base" pairs with >4 levels whose base isn't a Blizzard ability (skipped).
            public List<string> UnknownBases { get; } = new();
        }

        static readonly int LevelsField = FourCC("alev");

        // w3a stores an opaque trailing int per modification ("sanity check": 0 or an object id,
        // mixed in WE-saved maps). War3Net keeps it internal; we copy a sibling's value for fidelity.
        static readonly PropertyInfo SanityCheck =
            typeof(ObjectDataModification).GetProperty("SanityCheck", BindingFlags.NonPublic | BindingFlags.Instance)
            ?? throw new MissingMemberException("War3Net ObjectDataModification.SanityCheck not found — War3Net version changed?");

        // For callers that add cells of their own (the probe build's FF_OBJECT_OVERRIDES): give the new cell
        // the trailing sanity-check int of an existing cell of the same object (0 when it has none).
        public static void CopySanityCheck(ObjectDataModification from, ObjectDataModification to) =>
            SanityCheck.SetValue(to, from == null ? 0 : (int)SanityCheck.GetValue(from));

        // A few metadata ids are 3 chars (e.g. "Crs"); the map stores them NUL-padded ("Crs\0").
        public static int FourCC(string code)
        {
            if (code == null || code.Length is < 3 or > 4) throw new ArgumentException($"not a 4-char id: '{code}'");
            return code[0] | (code[1] << 8) | (code[2] << 16) | (code.Length == 4 ? code[3] << 24 : 0);
        }

        public static string Code(int id) =>
            new string(new[] { (char)(id & 0xFF), (char)((id >> 8) & 0xFF), (char)((id >> 16) & 0xFF), (char)((id >> 24) & 0xFF) });

        // The defaults table is the 2.0.4 TFT "Custom" game data set (_balance/custom_v1); refuse to
        // apply it to a map that declares anything else.
        public static void EnsureGameData(MapInfo info)
        {
            if (info == null) throw new InvalidDataException("level fill: the map has no war3map.w3i");
            if (info.GameDataVersion != GameDataVersion.TFT || info.GameDataSet != GameDataSet.Custom)
                throw new InvalidDataException(
                    $"level fill: map declares game data {info.GameDataVersion}/{info.GameDataSet}, but {AbilityLevelDefaults.FileName} is TFT/Custom (custom_v1).");
        }

        public static Result Fill(AbilityObjectData data, AbilityLevelDefaults defaults, bool dryRun = false)
        {
            var result = new Result();
            if (data == null) return result;
            foreach (var obj in data.BaseAbilities.Concat(data.NewAbilities))
            {
                var levelsMod = obj.Modifications.FirstOrDefault(m => m.Id == LevelsField && m.Level == 0);
                if (levelsMod == null || levelsMod.Type != ObjectDataType.Int) continue;
                int levels = levelsMod.ValueAsInt;
                if (levels <= 4) continue;

                // Based on something that isn't a Blizzard ability (e.g. another custom ability):
                // no SLK defaults exist for it in any version, so there is nothing to restore.
                if (!defaults.IsKnownBase(obj.OldId))
                {
                    result.UnknownBases.Add($"{Code(obj.NewId != 0 ? obj.NewId : obj.OldId)}/{Code(obj.OldId)}");
                    continue;
                }

                var present = new HashSet<(int, int)>();
                var sanityByField = new Dictionary<int, int>();
                foreach (var m in obj.Modifications)
                {
                    present.Add((m.Id, m.Level));
                    sanityByField[m.Id] = (int)SanityCheck.GetValue(m);
                }

                int before = result.Cells;
                var entries = defaults.For(obj.OldId);
                for (int level = 5; level <= levels; level++)
                {
                    foreach (var e in entries)
                    {
                        if (present.Contains((e.Id, level))) continue;
                        result.Cells++;
                        if (dryRun) continue;
                        var mod = new LevelObjectDataModification
                        {
                            Id = e.Id,
                            Type = e.Type,
                            Level = level,
                            Pointer = e.Pointer,
                            Value = e.Value,
                        };
                        SanityCheck.SetValue(mod, sanityByField.TryGetValue(e.Id, out var sc) ? sc : 0);
                        obj.Modifications.Add(mod);
                        result.Added.Add(mod);
                    }
                }
                if (result.Cells > before) result.Abilities++;
            }
            return result;
        }
    }
}

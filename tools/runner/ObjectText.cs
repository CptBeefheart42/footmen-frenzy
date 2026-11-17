using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using FootmenFrenzy.Shared;
using War3Net.Build.Extensions;
using War3Net.Build.Object;
using War3Net.IO.Mpq;

/// <summary>
/// A map's object data (units, items, abilities, upgrades, buffs, doodads, destructables, and their skin files) as
/// readable text, and back to the exact bytes. One text file per object-data file:
/// <code>
/// format v3
///
/// [A0KF : AFv1]                       a new object (its id : the object it is based on); [hfoo] changes a stock object
/// end = base                          the number the file stores after each field (base / new: an object id; default 0)
/// acdn.1.0 real = 12.5                field.level.pointer (abilities, upgrades; doodads: field.variation.pointer)
/// unam string = "Footman" @0          field (units, items, buffs, destructables); @x: this field's own end number
/// </code>
/// Types: int, real, unreal, string. "unk = ..." appears only for an object whose extra numbers are not the usual
/// single 0. Text after # is a comment: the field's name in the World Editor (data/object_fields.csv), written on
/// export and ignored on import.
/// </summary>
static class ObjectText
{
    /// <summary>The object-data files of a map, with the kind their field names are listed under.</summary>
    public static readonly (string File, string Kind)[] Files =
    {
        ("war3map.w3u", "unit"), ("war3map.w3t", "item"), ("war3map.w3b", "destructable"), ("war3map.w3d", "doodad"),
        ("war3map.w3a", "ability"), ("war3map.w3h", "buff"), ("war3map.w3q", "upgrade"),
        ("war3mapSkin.w3u", "unit"), ("war3mapSkin.w3t", "item"), ("war3mapSkin.w3b", "destructable"),
        ("war3mapSkin.w3d", "doodad"), ("war3mapSkin.w3a", "ability"), ("war3mapSkin.w3h", "buff"),
        ("war3mapSkin.w3q", "upgrade"),
    };

    sealed record Field(int Id, int Level, int Pointer, ObjectDataType Type, object Value, int End);
    sealed record Obj(int OldId, int NewId, List<int> Unk, List<Field> Fields);
    sealed record Data(ObjectDataFormatVersion Version, List<Obj> Base, List<Obj> New);

    static readonly PropertyInfo EndProperty =
        typeof(ObjectDataModification).GetProperty("SanityCheck", BindingFlags.NonPublic | BindingFlags.Instance)
        ?? throw new MissingMemberException("War3Net ObjectDataModification.SanityCheck not found — War3Net version changed?");

    /// <summary>
    /// <c>objects export &lt;map.w3x&gt; &lt;dir&gt;</c>: every object-data file of the map as &lt;dir&gt;/&lt;file&gt;.txt;
    /// <c>objects to-binary &lt;dir&gt; &lt;out dir&gt;</c>: every &lt;file&gt;.txt of &lt;dir&gt; as the binary file in &lt;out dir&gt;
    /// (<c>to-text</c> the other way);
    /// <c>objects check &lt;map.w3x&gt; &lt;dir&gt;</c>: the text gives back the map's own bytes for every file.
    /// </summary>
    public static int Run(string[] args)
    {
        try
        {
            return RunCommand(args);
        }
        catch (Exception e) when (e is InvalidDataException or FormatException or ArgumentException)
        {
            Console.WriteLine($"OBJECTS: {e.Message}");
            return 1;
        }
    }

    static int RunCommand(string[] args)
    {
        if (args.Length != 3 || args[0] is not ("export" or "to-binary" or "to-text" or "check"))
        {
            Console.WriteLine("usage: objects export|check <map.w3x> <dir> | objects to-binary|to-text <dir> <out dir>");
            return 2;
        }
        var names = FieldNames();
        if (args[0] == "to-text")
        {
            Directory.CreateDirectory(args[2]);
            foreach (var (file, kind) in Files)
            {
                var binary = Path.Combine(args[1], file);
                if (File.Exists(binary))
                    File.WriteAllText(Path.Combine(args[2], file + ".txt"), ToText(file, kind, File.ReadAllBytes(binary), names), new UTF8Encoding(false));
            }
            return 0;
        }
        if (args[0] == "to-binary")
        {
            Directory.CreateDirectory(args[2]);
            foreach (var (file, _) in Files)
            {
                var text = Path.Combine(args[1], file + ".txt");
                if (File.Exists(text))
                    File.WriteAllBytes(Path.Combine(args[2], file), ToBinary(file, File.ReadAllText(text, Encoding.UTF8)));
            }
            return 0;
        }
        using var archive = MpqArchive.Open(new MemoryStream(StartMap.Readable(File.ReadAllBytes(args[1])) ?? throw new InvalidDataException("unreadable map")), false);
        int problems = 0, files = 0;
        foreach (var (file, kind) in Files)
        {
            if (!archive.FileExists(file))
                continue;
            byte[] bytes;
            using (var s = archive.OpenFile(file))
            using (var ms = new MemoryStream())
            {
                s.CopyTo(ms);
                bytes = ms.ToArray();
            }
            var path = Path.Combine(args[2], file + ".txt");
            if (args[0] == "export")
            {
                Directory.CreateDirectory(args[2]);
                File.WriteAllText(path, ToText(file, kind, bytes, names), new UTF8Encoding(false));
            }
            else if (!File.Exists(path) || !ToBinary(file, File.ReadAllText(path, Encoding.UTF8)).AsSpan().SequenceEqual(bytes))
            {
                Console.WriteLine($"OBJECTS: {file}: the text does not give back the map's bytes");
                problems++;
            }
            files++;
        }
        Console.WriteLine(args[0] == "export" ? $"OBJECTS: {files} file(s) -> {args[2]}" : $"OBJECTS: {files - problems}/{files} file(s) identical");
        return problems == 0 ? 0 : 1;
    }

    /// <summary>A binary object-data file as text.</summary>
    public static string ToText(string file, string kind, byte[] bytes, Dictionary<string, string> names)
    {
        var data = Read(file, bytes);
        var sb = new StringBuilder();
        sb.Append($"# {file}: {kind} data of the map. Edit values here; field names: data/object_fields.csv.\n");
        sb.Append($"format {data.Version}\n");
        foreach (var obj in data.Base.Concat(data.New))
        {
            bool isNew = data.New.Contains(obj);
            sb.Append('\n').Append(isNew ? $"[{Code(obj.NewId)} : {Code(obj.OldId)}]" : $"[{Code(obj.OldId)}]").Append('\n');
            if (!(obj.Unk.Count == 1 && obj.Unk[0] == 0))
                sb.Append("unk = ").Append(obj.Unk.Count == 0 ? "none" : string.Join(", ", obj.Unk)).Append('\n');
            int usual = obj.Fields.Count == 0 ? 0 : obj.Fields.GroupBy(f => f.End).OrderByDescending(g => g.Count()).First().Key;
            if (usual != 0)
                sb.Append("end = ").Append(EndName(usual, obj)).Append('\n');
            foreach (var f in obj.Fields)
            {
                var key = Leveled(file) ? $"{Code(f.Id)}.{f.Level}.{f.Pointer}" : Code(f.Id);
                var marker = f.End == usual ? "" : " @" + EndName(f.End, obj);
                var line = $"{key} {f.Type.ToString().ToLowerInvariant()} = {Format(f.Type, f.Value)}{marker}";
                sb.Append(line);
                var label = NameOf(names, kind, file, Code(f.Id));
                if (label != null)
                    sb.Append(' ', Math.Max(1, 40 - line.Length)).Append("# ").Append(label);
                sb.Append('\n');
            }
        }
        return sb.ToString();
    }

    /// <summary>Text back to the binary object-data file.</summary>
    public static byte[] ToBinary(string file, string text)
    {
        ObjectDataFormatVersion version = ObjectDataFormatVersion.v3;
        var all = new List<(Obj Obj, bool IsNew)>();
        Obj current = null;
        int usual = 0;
        int lineNo = 0;
        foreach (var raw in text.Split('\n'))
        {
            lineNo++;
            var line = StripComment(raw).Trim();
            if (line.Length == 0)
                continue;
            if (line.StartsWith("format ", StringComparison.Ordinal))
            {
                version = Enum.Parse<ObjectDataFormatVersion>(line.Substring(7).Trim());
                continue;
            }
            if (line.StartsWith('['))
            {
                var inner = line.Trim('[', ']');
                var parts = inner.Split(':', StringSplitOptions.TrimEntries);
                current = parts.Length == 2
                    ? new Obj(Id(parts[1]), Id(parts[0]), new List<int>(), new List<Field>())
                    : new Obj(Id(parts[0]), 0, new List<int>(), new List<Field>());
                current.Unk.Add(0);
                usual = 0;
                all.Add((current, parts.Length == 2));
                continue;
            }
            if (current == null)
                throw new InvalidDataException($"{file}:{lineNo}: a field before the first [object] line");
            if (line.StartsWith("unk ", StringComparison.Ordinal) || line.StartsWith("unk=", StringComparison.Ordinal))
            {
                current.Unk.Clear();
                var list = line.Substring(line.IndexOf('=') + 1).Trim();
                if (list != "none")
                    current.Unk.AddRange(list.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Select(int.Parse));
                continue;
            }
            if (line.StartsWith("end ", StringComparison.Ordinal) || line.StartsWith("end=", StringComparison.Ordinal))
            {
                usual = ParseEnd(line.Substring(line.IndexOf('=') + 1).Trim(), current);
                continue;
            }
            current.Fields.Add(ParseField(file, lineNo, line, current, usual));
        }
        var data = new Data(version, all.Where(x => !x.IsNew).Select(x => x.Obj).ToList(), all.Where(x => x.IsNew).Select(x => x.Obj).ToList());
        return Write(file, data);
    }

    static Field ParseField(string file, int lineNo, string line, Obj obj, int usual)
    {
        int eq = line.IndexOf('=');
        if (eq < 0)
            throw new InvalidDataException($"{file}:{lineNo}: expected '<field> <type> = <value>'");
        var head = line.Substring(0, eq).Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (head.Length != 2 || !Enum.TryParse<ObjectDataType>(head[1], true, out var type))
            throw new InvalidDataException($"{file}:{lineNo}: expected '<field> <type> = <value>' with type int, real, unreal or string");
        var keyParts = head[0].Split('.');
        int level = keyParts.Length > 1 ? int.Parse(keyParts[1], CultureInfo.InvariantCulture) : 0;
        int pointer = keyParts.Length > 2 ? int.Parse(keyParts[2], CultureInfo.InvariantCulture) : 0;
        var rest = line.Substring(eq + 1).Trim();
        int end = usual;
        if (type != ObjectDataType.String || !rest.EndsWith('"'))
        {
            int at = rest.LastIndexOf(" @", StringComparison.Ordinal);
            if (at >= 0)
            {
                end = ParseEnd(rest.Substring(at + 2).Trim(), obj);
                rest = rest.Substring(0, at).Trim();
            }
        }
        return new Field(Id(keyParts[0]), level, pointer, type, ParseValue(file, lineNo, type, rest), end);
    }

    static string Format(ObjectDataType type, object value) => type switch
    {
        ObjectDataType.Int => ((int)value).ToString(CultureInfo.InvariantCulture),
        ObjectDataType.Real or ObjectDataType.Unreal => ((float)value).ToString("R", CultureInfo.InvariantCulture),
        ObjectDataType.String => Quote((string)value),
        _ => throw new InvalidDataException($"unknown object data type {type}"),
    };

    static object ParseValue(string file, int lineNo, ObjectDataType type, string text) => type switch
    {
        ObjectDataType.Int => int.Parse(text, NumberStyles.Integer, CultureInfo.InvariantCulture),
        ObjectDataType.Real or ObjectDataType.Unreal => float.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture),
        ObjectDataType.String => Unquote(file, lineNo, text),
        _ => throw new InvalidDataException($"{file}:{lineNo}: unknown type {type}"),
    };

    static string EndName(int end, Obj obj) =>
        end == 0 ? "0" : end == obj.OldId ? "base" : end == obj.NewId ? "new" : Code(end);

    static int ParseEnd(string marker, Obj obj) => marker switch
    {
        "0" => 0,
        "base" => obj.OldId,
        "new" => obj.NewId,
        _ => Id(marker),
    };

    /// <summary>A string as a quoted, escaped literal: \" \\ \n \r \t and \u00XX for other control characters.</summary>
    static string Quote(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (var c in s)
        {
            sb.Append(c switch
            {
                '"' => "\\\"", '\\' => "\\\\", '\n' => "\\n", '\r' => "\\r", '\t' => "\\t",
                _ => c < 32 ? $"\\u{(int)c:x4}" : c.ToString(),
            });
        }
        return sb.Append('"').ToString();
    }

    static string Unquote(string file, int lineNo, string text)
    {
        if (text.Length < 2 || text[0] != '"' || text[^1] != '"')
            throw new InvalidDataException($"{file}:{lineNo}: a string value is written in double quotes");
        var sb = new StringBuilder();
        for (int i = 1; i < text.Length - 1; i++)
        {
            if (text[i] != '\\') { sb.Append(text[i]); continue; }
            char n = text[++i];
            sb.Append(n switch
            {
                'n' => "\n", 'r' => "\r", 't' => "\t", '"' => "\"", '\\' => "\\",
                'u' => ((char)Convert.ToInt32(text.Substring(i + 1, 4), 16)).ToString(),
                _ => throw new InvalidDataException($"{file}:{lineNo}: unknown escape \\{n}"),
            });
            if (n == 'u') i += 4;
        }
        return sb.ToString();
    }

    // Text after an unquoted # is a comment.
    static string StripComment(string line)
    {
        bool quoted = false;
        for (int i = 0; i < line.Length; i++)
        {
            if (line[i] == '\\' && quoted) { i++; continue; }
            if (line[i] == '"') quoted = !quoted;
            else if (line[i] == '#' && !quoted) return line.Substring(0, i);
        }
        return line;
    }

    static bool Leveled(string file) => file.EndsWith(".w3a") || file.EndsWith(".w3q") || file.EndsWith(".w3d");

    static string Code(int id) => AbilityLevelFill.Code(id).TrimEnd('\0');
    static int Id(string code) => AbilityLevelFill.FourCC(code);

    /// <summary>Field names by kind and field id, from data/object_fields.csv.</summary>
    public static Dictionary<string, string> FieldNames()
    {
        var names = new Dictionary<string, string>();
        var path = Repo.Data("object_fields.csv");
        if (!File.Exists(path))
            return names;
        foreach (var line in File.ReadLines(path).Where(l => !l.StartsWith('#')).Skip(1))
        {
            var cols = line.Split(',');
            if (cols.Length >= 3)
                names[cols[0] + "|" + cols[1]] = cols[2].Trim('"');
        }
        return names;
    }

    static string NameOf(Dictionary<string, string> names, string kind, string file, string field) =>
        names.GetValueOrDefault((file.Contains("Skin") ? "skin" : kind) + "|" + field) ?? names.GetValueOrDefault(kind + "|" + field);

    // ---- War3Net's three shapes of object data <-> one model --------------------------------------------------------

    static Data Read(string file, byte[] bytes)
    {
        var r = new BinaryReader(new MemoryStream(bytes));
        switch (Path.GetExtension(file))
        {
            case ".w3u": { var d = r.ReadUnitObjectData(); return new Data(d.FormatVersion, FromSimple(d.BaseUnits), FromSimple(d.NewUnits)); }
            case ".w3t": { var d = r.ReadItemObjectData(); return new Data(d.FormatVersion, FromSimple(d.BaseItems), FromSimple(d.NewItems)); }
            case ".w3b": { var d = r.ReadDestructableObjectData(); return new Data(d.FormatVersion, FromSimple(d.BaseDestructables), FromSimple(d.NewDestructables)); }
            case ".w3h": { var d = r.ReadBuffObjectData(); return new Data(d.FormatVersion, FromSimple(d.BaseBuffs), FromSimple(d.NewBuffs)); }
            case ".w3a": { var d = r.ReadAbilityObjectData(); return new Data(d.FormatVersion, FromLevel(d.BaseAbilities), FromLevel(d.NewAbilities)); }
            case ".w3q": { var d = r.ReadUpgradeObjectData(); return new Data(d.FormatVersion, FromLevel(d.BaseUpgrades), FromLevel(d.NewUpgrades)); }
            case ".w3d": { var d = r.ReadDoodadObjectData(); return new Data(d.FormatVersion, FromVariation(d.BaseDoodads), FromVariation(d.NewDoodads)); }
            default: throw new ArgumentException($"not an object-data file: {file}");
        }
    }

    static byte[] Write(string file, Data data)
    {
        using var ms = new MemoryStream();
        using (var w = new BinaryWriter(ms, Encoding.UTF8, true))
        {
            switch (Path.GetExtension(file))
            {
                case ".w3u": w.Write(new UnitObjectData(data.Version) { BaseUnits = ToSimple(data.Base), NewUnits = ToSimple(data.New) }); break;
                case ".w3t": w.Write(new ItemObjectData(data.Version) { BaseItems = ToSimple(data.Base), NewItems = ToSimple(data.New) }); break;
                case ".w3b": w.Write(new DestructableObjectData(data.Version) { BaseDestructables = ToSimple(data.Base), NewDestructables = ToSimple(data.New) }); break;
                case ".w3h": w.Write(new BuffObjectData(data.Version) { BaseBuffs = ToSimple(data.Base), NewBuffs = ToSimple(data.New) }); break;
                case ".w3a": w.Write(new AbilityObjectData(data.Version) { BaseAbilities = ToLevel(data.Base), NewAbilities = ToLevel(data.New) }); break;
                case ".w3q": w.Write(new UpgradeObjectData(data.Version) { BaseUpgrades = ToLevel(data.Base), NewUpgrades = ToLevel(data.New) }); break;
                case ".w3d": w.Write(new DoodadObjectData(data.Version) { BaseDoodads = ToVariation(data.Base), NewDoodads = ToVariation(data.New) }); break;
                default: throw new ArgumentException($"not an object-data file: {file}");
            }
        }
        return ms.ToArray();
    }

    static int End(ObjectDataModification m) => (int)EndProperty.GetValue(m);
    static T WithEnd<T>(T m, int end) where T : ObjectDataModification { EndProperty.SetValue(m, end); return m; }

    static List<Obj> FromSimple(List<SimpleObjectModification> list) => list.Select(o => new Obj(o.OldId, o.NewId, o.Unk.ToList(),
        o.Modifications.Select(m => new Field(m.Id, 0, 0, m.Type, m.Value, End(m))).ToList())).ToList();
    static List<Obj> FromLevel(List<LevelObjectModification> list) => list.Select(o => new Obj(o.OldId, o.NewId, o.Unk.ToList(),
        o.Modifications.Select(m => new Field(m.Id, m.Level, m.Pointer, m.Type, m.Value, End(m))).ToList())).ToList();
    static List<Obj> FromVariation(List<VariationObjectModification> list) => list.Select(o => new Obj(o.OldId, o.NewId, o.Unk.ToList(),
        o.Modifications.Select(m => new Field(m.Id, m.Variation, m.Pointer, m.Type, m.Value, End(m))).ToList())).ToList();

    static List<SimpleObjectModification> ToSimple(List<Obj> list) => list.Select(o =>
    {
        var x = new SimpleObjectModification { OldId = o.OldId, NewId = o.NewId };
        x.Unk.AddRange(o.Unk);
        x.Modifications.AddRange(o.Fields.Select(f => WithEnd(new SimpleObjectDataModification { Id = f.Id, Type = f.Type, Value = f.Value }, f.End)));
        return x;
    }).ToList();
    static List<LevelObjectModification> ToLevel(List<Obj> list) => list.Select(o =>
    {
        var x = new LevelObjectModification { OldId = o.OldId, NewId = o.NewId };
        x.Unk.AddRange(o.Unk);
        x.Modifications.AddRange(o.Fields.Select(f => WithEnd(new LevelObjectDataModification { Id = f.Id, Level = f.Level, Pointer = f.Pointer, Type = f.Type, Value = f.Value }, f.End)));
        return x;
    }).ToList();
    static List<VariationObjectModification> ToVariation(List<Obj> list) => list.Select(o =>
    {
        var x = new VariationObjectModification { OldId = o.OldId, NewId = o.NewId };
        x.Unk.AddRange(o.Unk);
        x.Modifications.AddRange(o.Fields.Select(f => WithEnd(new VariationObjectDataModification { Id = f.Id, Variation = f.Level, Pointer = f.Pointer, Type = f.Type, Value = f.Value }, f.End)));
        return x;
    }).ToList();
}

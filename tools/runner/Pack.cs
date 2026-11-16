using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using War3Net.IO.Mpq;

/// <summary>
/// Writes a new map archive from a source archive: every entry carried over as it is (named or not), except the
/// replaced and dropped ones, plus new entries. A source without a (listfile) has unnamed entries; they keep their
/// exact hash-table slots, because the game finds a file by probing from its name's slot.
/// </summary>
static class MpqRepack
{
    /// <summary>What a repack wrote.</summary>
    public readonly record struct Result(int Total, int Carried, int Unnamed, int Dropped);

    static readonly HashSet<ulong> InternalNames = new()
    {
        MpqHash.GetHashedFileName("(listfile)"), MpqHash.GetHashedFileName("(attributes)"), MpqHash.GetHashedFileName("(signature)"),
    };

    /// <summary>
    /// Writes <paramref name="outPath"/>; prints the problem and returns null when the archive can't be written
    /// faithfully.
    /// </summary>
    /// <param name="archive">The open source archive.</param>
    /// <param name="sourcePath">Its file, for reading the hash-table layout.</param>
    /// <param name="replacements">New contents of existing entries, by name hash; every one must match an entry.</param>
    /// <param name="newEntries">Entries the source does not have.</param>
    /// <param name="dropped">Name hashes of entries to leave out.</param>
    /// <param name="outPath">The archive to write (overwritten).</param>
    public static Result? Write(MpqArchive archive, string sourcePath, Dictionary<ulong, MpqFile> replacements,
        List<MpqFile> newEntries, HashSet<ulong> dropped, string outPath)
    {
        var pending = new Dictionary<ulong, MpqFile>(replacements);
        var files = new List<MpqFile>();
        int carried = 0, unnamed = 0, droppedCount = 0;
        foreach (var f in archive.GetMpqFiles().ToList())
        {
            if (InternalNames.Contains(f.Name))
                continue;
            if (dropped.Contains(f.Name))
            {
                droppedCount++;
                continue;
            }
            if (pending.Remove(f.Name, out var replacement))
            {
                files.Add(replacement);
                continue;
            }
            files.Add(f);
            carried++;
            if (f is not MpqKnownFile)
                unnamed++;
        }
        if (pending.Count > 0)
        {
            Console.WriteLine("PACK: internal error — a replacement entry was not matched in the source archive.");
            return null;
        }
        files.AddRange(newEntries);
        bool hadListFile = archive.FileExists("(listfile)");
        if (hadListFile && unnamed > 0)
        {
            // Named entries are placed by probing, unnamed ones pinned to their old slot — mixing the
            // two can collide. No map of ours does this; refuse rather than guess.
            Console.WriteLine($"PACK: the source has a partial (listfile) ({unnamed} entries unnamed) — unsupported.");
            return null;
        }
        var sourceTable = MpqTables.ReadHashTable(sourcePath);
        var options = new MpqArchiveCreateOptions
        {
            ListFileCreateMode = hadListFile ? MpqFileCreateMode.Overwrite : MpqFileCreateMode.Prune,
            // Unnamed entries are pinned to their source slots (see below); a slot vacated by pruning
            // (attributes) could then cut the probe chain that leads to one of them. Regenerating the
            // file keeps its slot occupied (fresh CRCs, placed by name into the same chain).
            AttributesCreateMode = unnamed > 0 ? MpqFileCreateMode.Overwrite : MpqFileCreateMode.Prune,
            AttributesFlags = AttributesFlags.Crc32,   // no timestamps — keeps the build reproducible
            BlockSize = 3,
            // An unnamed entry's hash-table slot can only be reproduced in a table of the SAME size
            // (its slot is name-hash mod size, and the name is unknown); with a bigger table War3Net
            // hedges by cloning the entry into every candidate slot (8x for 2048 -> 16384), which
            // bloats the block table. Keeping the source size makes the carry-over exact.
            HashTableSize = checked((ushort)sourceTable.Length),
        };
        if (File.Exists(outPath)) File.Delete(outPath);  // MpqArchive.Create refuses to overwrite (CreateNew); allow reruns
        using (MpqArchive.Create(outPath, files, options)) { }
        KeepChains(sourceTable, outPath);

        // Post-condition for the unnamed case: every entry must sit exactly where the source had it and no
        // source-occupied slot may have been vacated. Anything else would surface only in-game, as
        // "file not found"/"map corrupted".
        if (unnamed > 0)
        {
            var problems = MpqTables.CompareLayout(sourceTable, MpqTables.ReadHashTable(outPath));
            if (problems.Count > 0)
            {
                foreach (var pr in problems) Console.WriteLine($"PACK: LAYOUT CHECK FAILED — {pr}");
                File.Delete(outPath);
                return null;
            }
            Console.WriteLine($"PACK: hash-table layout preserved ({sourceTable.Length} slots).");
        }
        return new Result(files.Count, carried, unnamed, droppedCount);
    }

    /// <summary>
    /// Marks deleted every hash slot that was in use or deleted in the source but is empty in the written archive. The
    /// game looks a file up by probing from its name's slot until an empty one, so a slot vacated by a dropped entry
    /// must stay "deleted" (probe on), never become "empty" (probe stops), or files behind it become unreachable.
    /// </summary>
    static void KeepChains(MpqTables.MpqHashSlot[] source, string outPath)
    {
        var bytes = MpqTables.EditHashTable(File.ReadAllBytes(outPath), words =>
        {
            int marked = 0;
            for (int i = 0; i < source.Length; i++)
            {
                if (!source[i].IsEmpty && words[i * 4 + 3] == 0xFFFFFFFF)
                {
                    words[i * 4] = words[i * 4 + 1] = words[i * 4 + 2] = 0xFFFFFFFF;
                    words[i * 4 + 3] = 0xFFFFFFFE;
                    marked++;
                }
            }
            return marked;
        }, out int count);
        if (count > 0)
        {
            File.WriteAllBytes(outPath, bytes);
            Console.WriteLine($"PACK: {count} vacated hash slot(s) marked deleted, so every lookup chain stays intact.");
        }
    }
}

/// <summary>
/// Prepares a starting map that another MPQ tool (StormLib) wrote, so War3Net reads and rewrites it faithfully.
/// </summary>
static class StartMap
{
    const uint Empty = 0xFFFFFFFF, Deleted = 0xFFFFFFFE;

    /// <summary>
    /// Returns the archive with two kinds of hash entries made harmless, files and lookup chains unchanged:
    /// deleted entries that still carry a file name (War3Net would resolve the name to the deleted marker), and
    /// extra entries of a file stored twice under one name with identical contents (War3Net keeps one entry per
    /// name, which would vacate a slot inside a lookup chain). Prints the problem and returns null when one name
    /// holds two different files: which one the game reads cannot be decided without the name.
    /// </summary>
    /// <param name="archive">The starting map's bytes.</param>
    public static byte[] Readable(byte[] archive)
    {
        archive = MpqTables.EditHashTable(archive, ClearDeletedNames, out int cleared);
        if (cleared > 0)
            Console.WriteLine($"PACK: ignored {cleared} deleted hash entr{(cleared == 1 ? "y" : "ies")} of the starting map.");

        var duplicates = DuplicateSlots(archive);
        if (duplicates.Count == 0)
            return archive;
        var contents = BlockContents(archive);
        var extra = new List<int>();
        foreach (var group in duplicates)
        {
            var first = contents(group[0].Block);
            foreach (var (slot, block) in group.Skip(1))
            {
                if (!contents(block).AsSpan().SequenceEqual(first))
                {
                    Console.WriteLine($"PACK: the starting map holds two different files under one name (blocks {group[0].Block} and {block}); "
                        + "rebuild it so each name holds one file.");
                    return null;
                }
                extra.Add(slot);
            }
        }
        archive = MpqTables.EditHashTable(archive, words =>
        {
            foreach (var slot in extra)
            {
                words[slot * 4] = words[slot * 4 + 1] = words[slot * 4 + 2] = Empty;
                words[slot * 4 + 3] = Deleted;
            }
            return extra.Count;
        }, out _);
        Console.WriteLine($"PACK: {extra.Count} file(s) of the starting map were stored twice with identical contents; kept one copy each.");
        return archive;
    }

    static int ClearDeletedNames(uint[] words)
    {
        int cleared = 0;
        for (int i = 0; i < words.Length; i += 4)
        {
            if (words[i + 3] == Deleted && (words[i] != Empty || words[i + 1] != Empty))
            {
                words[i] = words[i + 1] = words[i + 2] = Empty;
                cleared++;
            }
        }
        return cleared;
    }

    /// <summary>Groups the live hash slots that share name hashes, locale and platform (two or more per group).</summary>
    static List<List<(int Slot, uint Block)>> DuplicateSlots(byte[] archive)
    {
        var groups = new Dictionary<(uint, uint, uint), List<(int, uint)>>();
        MpqTables.EditHashTable(archive, words =>
        {
            for (int i = 0; i < words.Length; i += 4)
            {
                if (words[i + 3] >= Deleted)
                    continue;
                var key = (words[i], words[i + 1], words[i + 2]);
                if (!groups.TryGetValue(key, out var list))
                    groups[key] = list = new List<(int, uint)>();
                list.Add((i / 4, words[i + 3]));
            }
            return 0;
        }, out _);
        return groups.Values.Where(g => g.Count > 1).ToList();
    }

    /// <summary>Reads a file's contents by its block-table index.</summary>
    static Func<uint, byte[]> BlockContents(byte[] archive)
    {
        var mpq = MpqArchive.Open(new MemoryStream(archive), false);
        var entries = mpq.ToList();
        return block =>
        {
            using var stream = mpq.OpenFile(entries[(int)block]);
            using var ms = new MemoryStream();
            stream.CopyTo(ms);
            return ms.ToArray();
        };
    }
}

/// <summary>
/// The <c>pack</c> command: builds a complete map from a project's starting map, its text sources and its list of
/// binary files.
/// </summary>
/// <remarks>
/// The map's entries are the text files under the source folder (path with backslashes) and the binary files named
/// in the binaries list (name, SHA-256, size), whose contents are kept out of the repository. An entry equal to the
/// starting map's is carried over untouched, a changed one replaces it, a new one is added. A binary's contents come
/// from the starting map when the checksums match, otherwise from the blob folder (files named by their SHA-256).
/// Entries in neither the sources nor the list stay in the map as they are.
/// </remarks>
static class Pack
{
    /// <summary>
    /// <c>pack &lt;start.w3x&gt; &lt;src dir&gt; &lt;out.w3x&gt; [--binaries &lt;json&gt;] [--blobs &lt;dir&gt;]
    /// [--script &lt;war3map.j&gt;] [--missing &lt;file&gt;]</c>. <c>--script</c> replaces <c>src/war3map.j</c> (the
    /// assembled script); <c>--missing</c> receives the binaries (<c>sha256 size</c> per line) the blob folder lacks,
    /// and the command exits 3 so the caller can fetch them and run again. <c>--drop a,b</c> leaves those entries of the
    /// starting map out of the built map.
    /// </summary>
    public static int Run(string[] args)
    {
        if (args.Length < 3)
        {
            Console.WriteLine("usage: pack <start.w3x> <src dir> <out.w3x> [--binaries json] [--blobs dir] [--script war3map.j] [--missing file] [--drop a,b]");
            return 2;
        }
        string startMap = args[0], srcDir = args[1], outPath = args[2];
        string script = Option(args, "--script"), blobs = Option(args, "--blobs"), missingList = Option(args, "--missing");
        var drop = (Option(args, "--drop") ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(n => n.Trim().Replace('/', '\\')).ToList();
        var binaries = Option(args, "--binaries") is string list
            ? JsonSerializer.Deserialize<Dictionary<string, Binary>>(File.ReadAllText(list), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            : new Dictionary<string, Binary>();

        var readable = outPath + ".start";
        var startBytes = StartMap.Readable(File.ReadAllBytes(startMap));
        if (startBytes == null)
            return 1;
        File.WriteAllBytes(readable, startBytes);
        try
        {
            using var archive = MpqArchive.Open(readable, true);
            // Lookups name the entries of the instance they run on, and named entries get re-placed in the repack:
            // every lookup goes through this twin so `archive` keeps its unnamed entries in their slots.
            using var probe = MpqArchive.Open(readable, true);

            var entries = new SortedDictionary<string, Func<byte[]>>(StringComparer.Ordinal);
            foreach (var path in Directory.EnumerateFiles(srcDir, "*", SearchOption.AllDirectories))
            {
                var name = Path.GetRelativePath(srcDir, path).Replace(Path.DirectorySeparatorChar, '\\').Replace('/', '\\');
                entries[name] = name == "war3map.j" && script != null ? () => File.ReadAllBytes(script) : () => File.ReadAllBytes(path);
            }
            var missing = new List<string>();
            var replacements = new Dictionary<ulong, MpqFile>();
            var newEntries = new List<MpqFile>();
            int unchanged = 0;
            foreach (var (listed, binary) in binaries)
            {
                var name = listed.Replace('/', '\\');
                byte[] current = probe.FileExists(name) ? ReadAll(probe.OpenFile(name)) : null;
                if (current != null && Sha256(current) == binary.Sha256)
                {
                    unchanged++;
                    continue;
                }
                var blob = blobs == null ? null : Path.Combine(blobs, binary.Sha256);
                if (blob == null || !File.Exists(blob))
                    missing.Add($"{binary.Sha256} {binary.Size}");
                else
                    entries[name] = () => File.ReadAllBytes(blob);
            }
            if (missing.Count > 0)
            {
                if (missingList != null)
                    File.WriteAllLines(missingList, missing);
                Console.WriteLine($"PACK: {missing.Count} changed binary file(s) are not downloaded yet.");
                return 3;
            }
            foreach (var (name, read) in entries)
            {
                if (name is "(listfile)" or "(attributes)" or "(signature)")
                    continue;
                byte[] current = probe.FileExists(name) ? ReadAll(probe.OpenFile(name)) : null;
                var bytes = read();
                if (current != null && current.AsSpan().SequenceEqual(bytes))
                {
                    unchanged++;
                    continue;
                }
                var file = MpqFile.New(new MemoryStream(bytes), name, false);
                if (current != null)
                    replacements[MpqHash.GetHashedFileName(name)] = file;
                else
                    newEntries.Add(file);
                Console.WriteLine($"PACK: {(current != null ? "changed" : "new")} {name}");
            }
            foreach (var name in drop)
            {
                if (!probe.FileExists(name))
                {
                    Console.WriteLine($"PACK: {name} is to be dropped but the starting map does not hold it.");
                    return 1;
                }
                Console.WriteLine($"PACK: dropped {name}");
            }
            var dropped = drop.Select(MpqHash.GetHashedFileName).ToHashSet();
            var result = MpqRepack.Write(archive, readable, replacements, newEntries, dropped, outPath);
            if (result == null)
                return 1;
            Console.WriteLine($"PACK: {result.Value.Total} entries — {unchanged} unchanged, {replacements.Count} replaced, " +
                $"{newEntries.Count} added -> {outPath}");
            return 0;
        }
        finally
        {
            File.Delete(readable);
        }
    }

    /// <summary>One binary file of the map: its SHA-256 and size in bytes.</summary>
    sealed record Binary(string Sha256, long Size);

    static string Option(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    static byte[] ReadAll(Stream stream)
    {
        using (stream)
        using (var ms = new MemoryStream())
        {
            stream.CopyTo(ms);
            return ms.ToArray();
        }
    }

    static string Sha256(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
}

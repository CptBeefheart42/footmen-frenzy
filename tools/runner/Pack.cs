using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
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
/// The <c>pack</c> command: builds a complete map from a project's starting map and its source folder.
/// </summary>
/// <remarks>
/// Every file under the source folder is an archive entry (path with backslashes). A file whose bytes equal the
/// starting map's entry is carried over untouched; a changed file replaces the entry, a new one is added. Git LFS
/// pointer files stand for their object: equal to the starting map's entry means unchanged, otherwise the object is
/// read from the LFS cache folder. Files missing from the source folder stay in the map as they are.
/// </remarks>
static class Pack
{
    const string LfsPointerStart = "version https://git-lfs.github.com/spec/v1\n";

    /// <summary>
    /// <c>pack &lt;start.w3x&gt; &lt;src dir&gt; &lt;out.w3x&gt; [--script &lt;war3map.j&gt;] [--lfs-cache &lt;dir&gt;]
    /// [--missing &lt;file&gt;]</c>. <c>--script</c> replaces <c>src/war3map.j</c> (the assembled script);
    /// <c>--missing</c> receives the LFS objects (<c>oid size</c> per line) that the cache lacks, and the command
    /// exits 3 so the caller can fetch them and run again.
    /// </summary>
    public static int Run(string[] args)
    {
        if (args.Length < 3)
        {
            Console.WriteLine("usage: pack <start.w3x> <src dir> <out.w3x> [--script <war3map.j>] [--lfs-cache <dir>] [--missing <file>]");
            return 2;
        }
        string startMap = args[0], srcDir = args[1], outPath = args[2];
        string script = Option(args, "--script"), lfsCache = Option(args, "--lfs-cache"), missingList = Option(args, "--missing");

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

            var replacements = new Dictionary<ulong, MpqFile>();
            var newEntries = new List<MpqFile>();
            var missing = new List<string>();
            int unchanged = 0;
            foreach (var path in Directory.EnumerateFiles(srcDir, "*", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal))
            {
                var name = Path.GetRelativePath(srcDir, path).Replace('/', '\\').Replace(Path.DirectorySeparatorChar, '\\');
                if (name is "(listfile)" or "(attributes)" or "(signature)")
                    continue;
                byte[] current = probe.FileExists(name) ? ReadAll(probe.OpenFile(name)) : null;
                byte[] bytes = name == "war3map.j" && script != null ? File.ReadAllBytes(script) : File.ReadAllBytes(path);
                if (IsLfsPointer(bytes, out var oid, out var size))
                {
                    if (current != null && Sha256(current) == oid)
                    {
                        unchanged++;
                        continue;
                    }
                    var cached = lfsCache == null ? null : Path.Combine(lfsCache, oid);
                    if (cached == null || !File.Exists(cached))
                    {
                        missing.Add($"{oid} {size}");
                        continue;
                    }
                    bytes = File.ReadAllBytes(cached);
                }
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
            if (missing.Count > 0)
            {
                if (missingList != null)
                    File.WriteAllLines(missingList, missing);
                Console.WriteLine($"PACK: {missing.Count} changed file(s) are Git LFS pointers without their content (git lfs pull).");
                return 3;
            }
            var result = MpqRepack.Write(archive, readable, replacements, newEntries, new HashSet<ulong>(), outPath);
            if (result == null)
                return 1;
            Console.WriteLine($"PACK: {result.Value.Total} entries — {unchanged} source files unchanged, {replacements.Count} replaced, " +
                $"{newEntries.Count} added -> {outPath}");
            return 0;
        }
        finally
        {
            File.Delete(readable);
        }
    }

    static string Option(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    static bool IsLfsPointer(byte[] bytes, out string oid, out long size)
    {
        oid = null;
        size = 0;
        if (bytes.Length > 512 || !bytes.AsSpan().StartsWith(Encoding.ASCII.GetBytes(LfsPointerStart)))
            return false;
        foreach (var line in Encoding.ASCII.GetString(bytes).Split('\n'))
        {
            if (line.StartsWith("oid sha256:", StringComparison.Ordinal)) oid = line.Substring(11).Trim();
            else if (line.StartsWith("size ", StringComparison.Ordinal)) long.TryParse(line.Substring(5), out size);
        }
        return oid != null;
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

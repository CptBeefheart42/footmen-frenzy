using System;
using System.IO;

namespace FootmenFrenzy.Shared
{
    /// <summary>
    /// Finds the repository the tools belong to, so they run from any working folder on any system.
    /// </summary>
    public static class Repo
    {
        private static readonly Lazy<string> RootPath = new Lazy<string>(FindRoot);

        /// <summary>
        /// The repository root: <c>FF_REPO</c> when set, otherwise the nearest folder above the working folder or the
        /// tool's own folder that holds both <c>projects/</c> and <c>data/</c>.
        /// </summary>
        public static string Root => RootPath.Value;

        /// <summary>Returns the path of a file in the repository's <c>data/</c> folder.</summary>
        /// <param name="name">File name inside <c>data/</c>, e.g. <c>common.j</c>.</param>
        public static string Data(string name) => Path.Combine(Root, "data", name);

        private static string FindRoot()
        {
            var fromEnvironment = Environment.GetEnvironmentVariable("FF_REPO");
            if (!string.IsNullOrWhiteSpace(fromEnvironment))
                return Path.GetFullPath(fromEnvironment);
            foreach (var start in new[] { Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
            {
                for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
                {
                    if (Directory.Exists(Path.Combine(dir.FullName, "projects")) && Directory.Exists(Path.Combine(dir.FullName, "data")))
                        return dir.FullName;
                }
            }
            throw new DirectoryNotFoundException(
                "Cannot find the repository (a folder with projects/ and data/) above the working folder; set FF_REPO.");
        }
    }
}

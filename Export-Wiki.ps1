[CmdletBinding()]
param(
    [ValidateSet('all', '799x', 'solo')][string]$Project = 'all',
    [ValidateSet('base', 'built')][string]$Source = 'base',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$families = if ($Project -eq 'all') { @('799x', 'solo') } else { @($Project) }
foreach ($family in $families) {
    & $Python (Join-Path $PSScriptRoot 'tools/export_wiki.py') $family --source $Source
    if ($LASTEXITCODE -ne 0) { throw "Could not export the $family balance wiki." }
}

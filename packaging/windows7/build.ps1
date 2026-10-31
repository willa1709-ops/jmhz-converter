param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Wheelhouse,
    [Parameter(Mandatory=$true)][string]$WheelManifest,
    [Parameter(Mandatory=$true)][string]$ApprovedSha256,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$builder = Join-Path (Split-Path -Parent $scriptDirectory) 'build_windows.py'
& $Python $builder --variant win7-x86 --wheelhouse $Wheelhouse --wheel-manifest $WheelManifest --approved-sha256 $ApprovedSha256 --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Test build failed; no accepted EXE is claimed.' }

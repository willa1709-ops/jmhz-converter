param([Parameter(Mandatory=$true)][string]$DataRoot)
$ErrorActionPreference = 'Stop'
$full = [IO.Path]::GetFullPath($DataRoot)
if ($full.StartsWith('\\') -or $full.TrimEnd('\') -eq [IO.Path]::GetPathRoot($full).TrimEnd('\')) {
    throw 'Use a dedicated local data folder, never a drive root or UNC path.'
}
New-Item -ItemType Directory -Force -Path $full | Out-Null
# Enumerate without following junctions. Reject links before changing any ACL.
$pending = New-Object System.Collections.Stack
$pending.Push($full)
$entries = @()
while ($pending.Count -gt 0) {
    $path = [string]$pending.Pop()
    $attributes = [IO.File]::GetAttributes($path)
    if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Links are not allowed in the data tree.' }
    $directory = ($attributes -band [IO.FileAttributes]::Directory) -ne 0
    $entries += New-Object PSObject -Property @{ Path=$path; Directory=$directory }
    if ($directory) { foreach ($child in [IO.Directory]::GetFileSystemEntries($path)) { $pending.Push($child) } }
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
try {
    foreach ($entry in $entries) {
        if ($entry.Directory) {
            $acl = New-Object Security.AccessControl.DirectorySecurity
            $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
        } else {
            $acl = New-Object Security.AccessControl.FileSecurity
            $inherit = [Security.AccessControl.InheritanceFlags]::None
        }
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($principal in @($sid, $system)) {
            $rule = New-Object Security.AccessControl.FileSystemAccessRule($principal, 'FullControl', $inherit, 'None', 'Allow')
            $acl.AddAccessRule($rule)
        }
        if ($entry.Directory) { [IO.Directory]::SetAccessControl($entry.Path, $acl) }
        else { [IO.File]::SetAccessControl($entry.Path, $acl) }
    }
} catch { throw 'ACL update failed or was partial. Verify locally; this installation is not yet secured.' }
Write-Output 'Private ACL command completed. Test denial under another user, SYSTEM access and new-file inheritance. This is not encryption.'

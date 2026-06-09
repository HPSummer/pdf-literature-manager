$ExePath = Join-Path $PSScriptRoot "dist\pdf-manager.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "exe not found: $ExePath — run build_exe.ps1 first"
    exit 1
}
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "pdf文献管理.lnk"
$WScript = New-Object -ComObject WScript.Shell
$Shortcut = $WScript.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = Split-Path $ExePath
$Shortcut.Description = "PDF 文献管理工具"
$Shortcut.Save()
Write-Host "Shortcut created: $ShortcutPath"

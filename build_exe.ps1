$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv-dist"
$AssetsDir = Join-Path $ProjectRoot "assets"
$IconPath = Join-Path $AssetsDir "pdf_manager.ico"
$PipIndexArgs = @(
    "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple",
    "--trusted-host", "pypi.tuna.tsinghua.edu.cn",
    "--timeout", "60"
)

Write-Host "== PDF Manager build =="

function Resolve-Python {
    $Candidates = @(
        @("python", ""),
        @("py", "-3.11"),
        @("py", "-3.12"),
        @("py", "-3.13"),
        @("py", "-3.14")
    )
    foreach ($Candidate in $Candidates) {
        $Exe = $Candidate[0]
        $Arg = $Candidate[1]
        try {
            if ($Arg) {
                $Version = & $Exe $Arg -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            } else {
                $Version = & $Exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            }
            if ($LASTEXITCODE -eq 0) {
                $Parts = $Version.Trim().Split(".")
                if ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -ge 9) {
                    return $Candidate
                }
            }
        } catch {
            continue
        }
    }
    throw "Python 3.9+ is required. Install Python 3.11 or newer, then rerun this script."
}

$HostPython = Resolve-Python

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    if ($HostPython[1]) {
        & $HostPython[0] $HostPython[1] -m venv $VenvDir
    } else {
        & $HostPython[0] -m venv $VenvDir
    }
}

$Python = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"
$Pytest = Join-Path $VenvDir "Scripts\pytest.exe"
$PyInstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"

$VenvVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$VenvParts = $VenvVersion.Trim().Split(".")
if ([int]$VenvParts[0] -ne 3 -or [int]$VenvParts[1] -lt 9) {
    throw "Existing build venv uses Python $VenvVersion, but this project requires Python 3.9+. Delete '$VenvDir' and rerun build_exe.ps1."
}

& $Python -m pip --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Bootstrapping pip..."
    & $Python -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Could not bootstrap pip in build venv."
        exit 1
    }
}

Write-Host "Installing build tools..."
& $Pip install --upgrade setuptools wheel @PipIndexArgs --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Build tool installation failed. Check network access, then rerun build_exe.ps1."
    exit 1
}

Write-Host "Installing dependencies..."
& $Pip install -e "$ProjectRoot[dev]" pyinstaller @PipIndexArgs --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed. Check network access to PyPI, then rerun build_exe.ps1."
    exit 1
}

Write-Host "Generating app icon..."
& $Python (Join-Path $ProjectRoot "scripts\generate_icon.py")

Write-Host "Running tests..."
& $Pytest "$ProjectRoot\tests" -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed. Aborting build."
    exit 1
}

Write-Host "Building Windows exe..."
$AddData = "$AssetsDir;assets"
& $PyInstaller --onefile --windowed --name pdf-manager `
    --clean --noconfirm `
    --icon "$IconPath" `
    --add-data "$AddData" `
    --paths "$ProjectRoot\src" `
    "$ProjectRoot\src\pdf_manager\__main__.py"

$Exe = Join-Path $ProjectRoot "dist\pdf-manager.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Build failed: exe not found."
    exit 1
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$Lnk = Join-Path $Desktop "PDF Literature Manager.lnk"
$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut($Lnk)
$SC.TargetPath = $Exe
$SC.WorkingDirectory = Split-Path $Exe
$SC.IconLocation = "$Exe,0"
$SC.Description = "PDF literature manager with IEEE references, BibTeX, and Obsidian notes"
$SC.Save()

Write-Host ""
Write-Host "Build complete: $Exe"
Write-Host "Desktop shortcut: $Lnk"

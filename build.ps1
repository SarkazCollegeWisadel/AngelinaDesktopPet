param(
    [switch]$SkipInstall,
    [string]$PythonExecutable
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (-not $PythonExecutable) {
        $PythonExecutable = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    if (-not $PythonExecutable) {
        throw 'Python was not found. Install Python 3.11+ or pass -PythonExecutable.'
    }
    & $PythonExecutable -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed with exit code $LASTEXITCODE."
    }
}

if (-not $SkipInstall) {
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE."
    }
}

& $VenvPython (Join-Path $ProjectRoot 'tools\prepare_assets.py')
if ($LASTEXITCODE -ne 0) {
    throw "Asset preparation failed with exit code $LASTEXITCODE."
}
& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot 'tests') -v
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed with exit code $LASTEXITCODE."
}
& $VenvPython -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot 'AngelinaDesktopPet.spec')
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE. Close the running desktop pet and retry."
}
$ReleaseDir = Join-Path $ProjectRoot 'release'
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ReleaseExe = Join-Path $ReleaseDir 'AngelinaDesktopPet.exe'
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'dist\AngelinaDesktopPet.exe') -Destination $ReleaseExe -Force
Write-Host "Build complete: $ReleaseExe"

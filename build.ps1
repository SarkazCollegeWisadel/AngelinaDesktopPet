param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = 'C:\Users\Im1ssu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (-not (Test-Path -LiteralPath $BundledPython)) {
        throw 'Python was not found. Install Python 3.11+ or update BundledPython in build.ps1.'
    }
    & $BundledPython -m venv (Join-Path $ProjectRoot '.venv')
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
$DistRoot = Join-Path $ProjectRoot 'dist\AngelinaDesktopPet'
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'README.md') -Destination (Join-Path $DistRoot 'README.md') -Force

$ReleaseDir = Join-Path $ProjectRoot 'release'
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ZipPath = Join-Path $ReleaseDir 'AngelinaDesktopPet-Windows-x64.zip'
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $DistRoot '*') -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Build complete: $ZipPath"

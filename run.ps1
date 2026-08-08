$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Run build.ps1 or install requirements.txt first.'
}
& $Python (Join-Path $ProjectRoot 'main.py')

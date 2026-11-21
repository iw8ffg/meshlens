<#
 Build locale: web, PyInstaller (e facoltativamente go-pmtiles). Non serve Inno Setup.
 Uso: tools\build.ps1 [-WithTool]
#>
param([switch]$WithTool)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Push-Location web
npm ci
if ($LASTEXITCODE) { throw "npm ci fallito" }
npm run build
if ($LASTEXITCODE) { throw "build web fallita" }
Pop-Location

& $py -m pip install pyinstaller pystray Pillow
if ($LASTEXITCODE) { throw "pip fallito" }
& $py -m PyInstaller packaging\meshlens.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE) { throw "PyInstaller fallito" }

if ($WithTool) {
    & $py tools\fetch_pmtiles.py (Join-Path $root "dist\MeshLens\tools")
    if ($LASTEXITCODE) { throw "download go-pmtiles fallito" }
}
Write-Host "Pronto: dist\MeshLens\MeshLens.exe"

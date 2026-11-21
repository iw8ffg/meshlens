<#
 Build locale: web, PyInstaller, licenze e go-pmtiles. Non serve Inno Setup.
 Uso: tools\build.ps1
#>
param()
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

& $py -m pip install pyinstaller pystray Pillow pip-licenses
if ($LASTEXITCODE) { throw "pip fallito" }
& $py -m PyInstaller packaging\meshlens.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE) { throw "PyInstaller fallito" }

# licenses\ (testi completi, richiede rete) e tools\pmtiles.exe con SHA-256 verificato
& $py tools\gen_licenses.py (Join-Path $root "dist\MeshLens\licenses")
if ($LASTEXITCODE) { throw "generazione licenze fallita" }
Write-Host "Pronto: dist\MeshLens\MeshLens.exe"

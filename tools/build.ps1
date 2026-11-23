<#
 Build locale: web, PyInstaller, licenze e go-pmtiles. Non serve Inno Setup.
 Uso: tools\build.ps1 [-NoSign]

 Firma del codice (facoltativa, configurata SOLO da variabili d'ambiente; nessun certificato,
 thumbprint o password nel repository):
   MESHLENS_SIGN_THUMBPRINT     certificato nell'archivio di Windows (nessuna password)
   MESHLENS_SIGN_PFX            in alternativa: file .pfx ...
   MESHLENS_SIGN_PFX_PASSWORD   ... e la sua password
   MESHLENS_SIGN_TIMESTAMP      server di marca temporale (predefinito DigiCert)
 Senza configurazione (o con -NoSign) la build prosegue senza firma e lo dice.
 Configurata ma non riuscita: la build si ferma (mai un eseguibile non firmato spacciato per firmato).
#>
param([switch]$NoSign)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-SignTool {
    $cmd = Get-Command signtool -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $found = Get-ChildItem -Path $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\' } |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

function Invoke-OptionalSign([string]$File) {
    $thumb = $env:MESHLENS_SIGN_THUMBPRINT
    $pfx = $env:MESHLENS_SIGN_PFX
    if ($NoSign -or (-not $thumb -and -not $pfx)) {
        Write-Host "Firma del codice saltata: nessun certificato configurato"
        return
    }
    $tool = Find-SignTool
    if (-not $tool) { throw "Firma configurata ma signtool non trovato (installa il Windows SDK)" }
    $ts = $env:MESHLENS_SIGN_TIMESTAMP
    if (-not $ts) { $ts = "http://timestamp.digicert.com" }
    $signArgs = @("sign", "/fd", "sha256", "/tr", $ts, "/td", "sha256")
    if ($thumb) {
        $signArgs += @("/sha1", $thumb)
    } else {
        if (-not (Test-Path $pfx)) { throw "Il certificato indicato in MESHLENS_SIGN_PFX non esiste" }
        $signArgs += @("/f", $pfx)
        if ($env:MESHLENS_SIGN_PFX_PASSWORD) { $signArgs += @("/p", $env:MESHLENS_SIGN_PFX_PASSWORD) }
    }
    # la riga di comando (con l'eventuale password) non viene mai stampata
    & $tool @signArgs $File | Out-Null
    if ($LASTEXITCODE) { throw "Firma del codice non riuscita" }
    & $tool verify /pa $File | Out-Null
    if ($LASTEXITCODE) { throw "Verifica della firma non riuscita" }
    Write-Host "Firmato: $File"
}

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

Invoke-OptionalSign (Join-Path $root "dist\MeshLens\MeshLens.exe")

# licenses\ (testi completi, richiede rete) e tools\pmtiles.exe con SHA-256 verificato
& $py tools\gen_licenses.py (Join-Path $root "dist\MeshLens\licenses")
if ($LASTEXITCODE) { throw "generazione licenze fallita" }
Write-Host "Pronto: dist\MeshLens\MeshLens.exe"

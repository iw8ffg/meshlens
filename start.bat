@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente Python...
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 goto :nopython
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] < (3,15) else 1)"
    if errorlevel 1 (
        rmdir /s /q .venv
        goto :nopython
    )
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 (
        rmdir /s /q .venv
        echo Errore nell'installazione delle dipendenze. Controlla la connessione e riprova.
        pause
        exit /b 1
    )
)
if not exist "web\dist" (
    where npm >nul 2>nul
    if not errorlevel 1 (
        pushd web
        call npm ci && call npm run build
        popd
    ) else (
        echo npm non trovato: l'interfaccia web non verra compilata.
    )
)
".venv\Scripts\meshlens.exe" run
pause
exit /b 0

:nopython
echo Errore: serve Python 3.12 o superiore (fino alla 3.14).
pause
exit /b 1

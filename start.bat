@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente Python...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 ( echo Errore: Python 3.12 o superiore non trovato. & pause & exit /b 1 )
    ".venv\Scripts\python.exe" -m pip install -e . || ( echo Errore nell'installazione. & pause & exit /b 1 )
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

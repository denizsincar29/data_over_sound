@echo off
setlocal EnableDelayedExpansion

echo ===================================================
echo Data Over Sound - Windows Build
echo ===================================================

:: Ensure uv is available
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found on PATH.
    echo Install it from https://astral.sh/uv/install.sh and re-run.
    exit /b 1
)

:: Sync dependencies
echo [1/3] Syncing dependencies...
set GGWAVE_USE_CYTHON=1
uv sync
if errorlevel 1 (
    echo ERROR: uv sync failed.
    exit /b 1
)

:: Build with PyInstaller
echo [2/3] Building with PyInstaller...
uv run pyinstaller --noconfirm --onedir --windowed ^
    --name "DataOverSound" ^
    --collect-all ggwave ^
    --collect-all sounddevice ^
    --hidden-import wx ^
    --hidden-import numpy ^
    --hidden-import accessible_output3 ^
    main.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

:: Package into dist folder (PyInstaller already does this, but we'll ensure everything is clean)
echo [3/3] Packaging...
powershell -NoProfile -Command "Compress-Archive -Path 'dist/DataOverSound' -DestinationPath 'dist/DataOverSound-windows.zip' -Force"

echo ===================================================
echo Build complete!
echo Output: dist/DataOverSound
echo Archive: dist/DataOverSound-windows.zip
echo ===================================================
endlocal

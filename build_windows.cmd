@echo off
REM Builds MopVOD.exe: the collector/publisher as a single console exe (PyInstaller, no Python needed).
REM Put programs.json and github_token.txt next to the exe; out\ and cache\ are created beside it.
REM Output: MopVOD\windows\dist\MopVOD.exe
setlocal
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --console --name MopVOD ^
  --distpath "%~dp0windows\dist" --workpath "%~dp0windows\build" --specpath "%~dp0windows" ^
  "%~dp0mopvod.py"
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)
echo.
echo Windows exe ready: %~dp0windows\dist\MopVOD.exe
endlocal

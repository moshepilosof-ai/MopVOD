@echo off
REM Collects new episodes for all programs and uploads to GitHub.
cd /d "%~dp0"
MopVOD.exe --publish
pause

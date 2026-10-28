@echo off
REM Uploads what is already in out\ to GitHub (needs github_token.txt next to this file).
cd /d "%~dp0"
MopVOD.exe --publish-only
pause

@echo off
setlocal
set "DISTRO=%~1"
if "%DISTRO%"=="" set "DISTRO=Ubuntu-24.04"
echo Starting TG Atelier in %DISTRO%...
echo Project must be installed at ~/tg-ai-steward inside WSL.
wsl.exe -d "%DISTRO%" -- bash -lc "cd ~/tg-ai-steward && bash ./start-dashboard.sh"
if errorlevel 1 echo Startup failed. Check WSL distribution name and project folder.
pause

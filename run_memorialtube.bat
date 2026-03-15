@echo off
setlocal

set "DISTRO=Ubuntu"
set "REPO=/mnt/d/WorkSpace/MemorialTube"
set "SCRIPT=scripts/smoke_pipeline.sh"
set "DOCKER_DESKTOP_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
if "%INSTALL_AI%"=="" set "INSTALL_AI=1"
if "%SMOKE_TIMEOUT_SECONDS%"=="" (
  if "%INSTALL_AI%"=="1" (
    set "SMOKE_TIMEOUT_SECONDS=1800"
  ) else (
    set "SMOKE_TIMEOUT_SECONDS=240"
  )
)
if "%POLL_INTERVAL_SECONDS%"=="" set "POLL_INTERVAL_SECONDS=2"

if exist "%DOCKER_DESKTOP_EXE%" (
  echo [INFO] Starting Docker Desktop...
  start "" "%DOCKER_DESKTOP_EXE%"
) else (
  echo [WARN] Docker Desktop executable not found: "%DOCKER_DESKTOP_EXE%"
)

echo [INFO] Running smoke pipeline in WSL distro "%DISTRO%"... ^(INSTALL_AI=%INSTALL_AI%, TIMEOUT=%SMOKE_TIMEOUT_SECONDS%s, INTERVAL=%POLL_INTERVAL_SECONDS%s^)
wsl -d %DISTRO% bash -lc "cd %REPO% && chmod +x %SCRIPT% && INSTALL_AI=%INSTALL_AI% SMOKE_TIMEOUT_SECONDS=%SMOKE_TIMEOUT_SECONDS% POLL_INTERVAL_SECONDS=%POLL_INTERVAL_SECONDS% ./%SCRIPT%"
if errorlevel 1 (
  echo [ERROR] MemorialTube smoke pipeline failed. ^(errorlevel=%errorlevel%^) 
  if "%NO_PAUSE%"=="" pause
  exit /b %errorlevel%
)

echo [OK] MemorialTube smoke pipeline completed.
if "%NO_PAUSE%"=="" pause
exit /b 0

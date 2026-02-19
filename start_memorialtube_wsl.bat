@echo off
setlocal

set "REPO_WSL=/mnt/c/MemorialTube"
set "DISTRO=%~1"

if "%DISTRO%"=="" goto :RUN_DEFAULT

echo [info] Starting MemorialTube backend in WSL distro %DISTRO%
echo [info] Ensuring PostgreSQL/Redis services...
wsl.exe -d "%DISTRO%" -u root bash -lc "service postgresql start >/dev/null 2>&1 || true; service redis-server start >/dev/null 2>&1 || true"
wsl.exe -d "%DISTRO%" bash -lc "cd %REPO_WSL% && chmod +x scripts/start_backend.sh && ./scripts/start_backend.sh"
goto :CHECK_RESULT

:RUN_DEFAULT
echo [info] Starting MemorialTube backend in WSL default distro
echo [info] Ensuring PostgreSQL/Redis services...
wsl.exe -u root bash -lc "service postgresql start >/dev/null 2>&1 || true; service redis-server start >/dev/null 2>&1 || true"
wsl.exe bash -lc "cd %REPO_WSL% && chmod +x scripts/start_backend.sh && ./scripts/start_backend.sh"

:CHECK_RESULT

if errorlevel 1 (
  echo [error] Failed to start backend. check output above.
  echo [hint] Usage: start_memorialtube_wsl.bat [DistroName]
  exit /b 1
)

echo [ok] Start command completed.
endlocal

@echo off
setlocal

set "ROOT=%~dp0"
set "SPRING_ROOT=%ROOT%spring-api"

if not exist "%SPRING_ROOT%" (
  echo [ERROR] spring-api directory not found.
  exit /b 1
)

where java >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing JDK 21...
  winget install -e --id Microsoft.OpenJDK.21 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERROR] Failed to install JDK 21.
    exit /b 1
  )
)

where gradle >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing Gradle...
  winget install -e --id Gradle.Gradle --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERROR] Failed to install Gradle.
    exit /b 1
  )
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing FFmpeg...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERROR] Failed to install FFmpeg.
    exit /b 1
  )
)

cd /d "%SPRING_ROOT%"
gradle bootRun

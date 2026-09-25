@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title QA Community - LiteLLM Gateway

cd /d "%~dp0"
set "LITELLM_EXE=F:\Anaconda_envs\envs\qa\Scripts\litellm.exe"
set "LITELLM_ENV=%CD%\.env.litellm"
set "LITELLM_CONFIG=%CD%\litellm_config.yaml"

if not exist "!LITELLM_EXE!" (
    echo [ERROR] LiteLLM executable was not found:
    echo !LITELLM_EXE!
    goto :failed
)

if not exist "!LITELLM_ENV!" (
    echo [ERROR] Environment file was not found:
    echo !LITELLM_ENV!
    goto :failed
)

if not exist "!LITELLM_CONFIG!" (
    echo [ERROR] Gateway config was not found:
    echo !LITELLM_CONFIG!
    goto :failed
)

if /I "%~1"=="--check" (
    echo [OK] LiteLLM executable, environment file and config are ready.
    exit /b 0
)

echo Starting LiteLLM gateway at http://127.0.0.1:4000 ...
echo Press Ctrl+C to stop the gateway.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; foreach ($line in Get-Content -LiteralPath $env:LITELLM_ENV) { if ($line -match '^\s*([^#][^=]*)=(.*)$') { $name = $matches[1].Trim(); $value = $matches[2].Trim().Trim([char]34).Trim([char]39); [Environment]::SetEnvironmentVariable($name, $value, 'Process') } }; & $env:LITELLM_EXE --config $env:LITELLM_CONFIG --port 4000 --host 127.0.0.1"

if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Gateway did not start. Review the error above.
pause
exit /b 1

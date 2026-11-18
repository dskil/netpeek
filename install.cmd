@echo off
REM NetPeek / fsociety - make `netpeek` and `fsociety` available in every
REM terminal, using an isolated virtual environment (nothing global changes).
REM
REM Usage:  install.cmd
REM         install.cmd --dry-run     (show what would happen)
REM
REM What it does:
REM   1. creates .venv in this folder (needs Python 3.9+)
REM   2. pip installs this package into it
REM   3. adds .venv\Scripts to your *user* PATH (no admin rights needed)
REM   4. prints how to remove everything again (uninstall.cmd)

setlocal EnableExtensions

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "VENV=%HERE%\.venv"
set "BIN=%VENV%\Scripts"

set "DRY="
if /I "%~1"=="--dry-run" set "DRY=1"
if /I "%~1"=="-n" set "DRY=1"

echo.
echo  NetPeek / fsociety installer
echo  ============================
echo  project : %HERE%
echo  venv    : %VENV%
echo  PATH    : %BIN%
echo.

REM --------------------------------------------------------------------- #
REM Find a Python 3.9+ interpreter
REM --------------------------------------------------------------------- #

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo  [X] Python 3.9+ was not found.
    echo      Install it from https://www.python.org/downloads/
    echo      and tick "Add python.exe to PATH".
    exit /b 9009
)

REM Verify the version is 3.9 or newer.
set "VERSION_OK="
for /f "delims=" %%v in ('%PY% -c "import sys;print(1 if sys.version_info>=(3,9) else 0)" 2^>nul') do set "VERSION_OK=%%v"
if not "%VERSION_OK%"=="1" (
    echo  [X] Python 3.9 or newer is required.
    %PY% --version
    exit /b 9009
)
echo  [ok] Python found: %PY%

if defined DRY (
    echo.
    echo  DRY RUN - nothing was changed.
    echo    would create : %VENV%
    echo    would install: pip install "%HERE%"
    echo    would add to PATH ^(user scope^): %BIN%
    exit /b 0
)

REM --------------------------------------------------------------------- #
REM 1. Create the virtual environment
REM --------------------------------------------------------------------- #

if exist "%BIN%\python.exe" (
    echo  [ok] virtual environment already exists
) else (
    echo  [..] creating virtual environment
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo  [X] could not create the virtual environment.
        echo      Try:  %PY% -m venv "%VENV%"
        exit /b 1
    )
    echo  [ok] virtual environment created
)

REM --------------------------------------------------------------------- #
REM 2. Install the package
REM --------------------------------------------------------------------- #

echo  [..] installing netpeek into the venv
"%BIN%\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip
"%BIN%\python.exe" -m pip install --quiet --disable-pip-version-check "%HERE%"
if errorlevel 1 (
    echo  [X] installation failed.
    exit /b 1
)
echo  [ok] netpeek installed

REM --------------------------------------------------------------------- #
REM 3. Add the venv Scripts folder to the user PATH
REM --------------------------------------------------------------------- #

echo  [..] registering the venv on your user PATH
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$bin = [Environment]::GetEnvironmentVariable('Path','User');" ^
  "$parts = @($bin -split ';' | Where-Object { $_ -ne '' });" ^
  "if ($parts -notcontains '%BIN%') {" ^
  "  $parts += '%BIN%';" ^
  "  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User');" ^
  "  Write-Output 'added'" ^
  "} else { Write-Output 'already-present' }"

REM --------------------------------------------------------------------- #
REM 4. Verify
REM --------------------------------------------------------------------- #

echo.
echo  Checking the installation:
"%BIN%\netpeek.exe" version
if errorlevel 1 (
    echo  [X] netpeek.exe did not run.
    exit /b 1
)
"%BIN%\fsociety.exe" version
if errorlevel 1 (
    echo  [X] fsociety.exe did not run.
    exit /b 1
)

echo.
echo  Done.
echo.
echo    open a NEW terminal and try:
echo        netpeek --help
echo        netpeek me
echo        fsociety --help
echo.
echo    (this window keeps the old PATH; use the new terminal window^)
echo    to remove everything:  uninstall.cmd
echo.
exit /b 0

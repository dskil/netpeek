@echo off
REM NetPeek / fsociety - run straight from a fresh clone, no install needed.
REM
REM   netpeek.bat --help
REM   netpeek.bat me --ip
REM
REM Prefers the pip-installed console script when it exists, otherwise runs
REM this checkout with whatever Python is on PATH.

setlocal

set "HERE=%~dp0"
set "ARGS=%*"

REM 1) Is there an installed netpeek.exe somewhere that is NOT this folder?
set "INSTALLED="
for /f "delims=" %%p in ('where netpeek.exe 2^>nul') do (
    if not defined INSTALLED (
        if /I not "%%~dp%%p"=="%HERE%" set "INSTALLED=%%p"
    )
)
if defined INSTALLED (
    "%INSTALLED%" %ARGS%
    exit /b %errorlevel%
)

REM 2) Run from this checkout.
set "PY="
if exist "%HERE%.venv\Scripts\python.exe" set "PY=%HERE%.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [netpeek] Python 3.9+ was not found on PATH. 1>&2
    echo [netpeek] Install it from https://www.python.org/downloads/ 1>&2
    echo [netpeek]   ^(tick "Add python.exe to PATH" during setup^) 1>&2
    exit /b 9009
)

set "PYTHONPATH=%HERE%"
%PY% -m netpeek %ARGS%
exit /b %errorlevel%

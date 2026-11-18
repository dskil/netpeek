@echo off
REM NetPeek / fsociety - same wrapper as netpeek.bat, under the other name.
REM Both names run the same tool with the same commands.

setlocal

set "HERE=%~dp0"
set "ARGS=%*"

set "INSTALLED="
for /f "delims=" %%p in ('where fsociety.exe 2^>nul') do (
    if not defined INSTALLED (
        if /I not "%%~dp%%p"=="%HERE%" set "INSTALLED=%%p"
    )
)
if defined INSTALLED (
    "%INSTALLED%" %ARGS%
    exit /b %errorlevel%
)

set "PY="
if exist "%HERE%.venv\Scripts\python.exe" set "PY=%HERE%.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [fsociety] Python 3.9+ was not found on PATH. 1>&2
    echo [fsociety] Install it from https://www.python.org/downloads/ 1>&2
    exit /b 9009
)

set "PYTHONPATH=%HERE%"
set "NETPEEK_PROG=fsociety"
%PY% -m netpeek %ARGS%
exit /b %errorlevel%

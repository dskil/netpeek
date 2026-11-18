@echo off
REM NetPeek / fsociety - undo what install.cmd did.
REM Removes the PATH entry and deletes .venv. Your repository is untouched.

setlocal EnableExtensions

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "VENV=%HERE%\.venv"
set "BIN=%VENV%\Scripts"

echo.
echo  NetPeek / fsociety uninstaller
echo  ==============================
echo.

echo  [..] removing the venv from your user PATH
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$bin = [Environment]::GetEnvironmentVariable('Path','User');" ^
  "if ($null -ne $bin) {" ^
  "  $parts = @($bin -split ';' | Where-Object { $_ -ne '' -and $_ -ne '%BIN%' });" ^
  "  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User');" ^
  "}"
echo  [ok] PATH cleaned

if exist "%VENV%" (
    echo  [..] deleting %VENV%
    rmdir /s /q "%VENV%"
    echo  [ok] virtual environment deleted
) else (
    echo  [ok] no virtual environment to delete
)

echo.
echo  Done. Open a new terminal for the PATH change to take effect.
echo  If you also installed with "pip install .", remove that copy with:
echo      pip uninstall netpeek
echo.
exit /b 0

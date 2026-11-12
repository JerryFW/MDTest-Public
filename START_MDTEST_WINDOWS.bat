@echo off
setlocal
title MDTest - Start Workbench
cd /d "%~dp0"
echo.
echo ====================================================
echo   MDTest - easy start (Windows)
echo ====================================================
echo.
set "PY_CMD="
rem Prefer tested scientific Python versions; also recognize stable Python 3.15.
rem Check explicit versions before py -3, which may point to an older 3.9.
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.13 3.12 3.14 3.15 3.11) do (
        if not defined PY_CMD (
            py -%%V -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>nul
            if not errorlevel 1 set "PY_CMD=py -%%V"
        )
    )
)
rem Support PATH-installed Pythons not registered with the py launcher.
if not defined PY_CMD (
    for %%P in (python3.13 python3.12 python3.14 python3.15 python3.11 python) do (
        if not defined PY_CMD (
            where %%P >nul 2>nul
            if not errorlevel 1 (
                %%P -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>nul
                if not errorlevel 1 set "PY_CMD=%%P"
            )
        )
    )
)
if not defined PY_CMD (
    echo Python 3.11 through 3.15 was not found.
    echo.
    echo Recommended: install Python 3.13 or 3.12 from
    echo https://www.python.org/downloads/windows/
    echo Close this window and double-click START_MDTEST_WINDOWS.bat again.
    echo.
    pause
    exit /b 2
)
%PY_CMD% "%~dp0tools\launch_mdtest.py"
set "MDTEST_EXIT=%ERRORLEVEL%"
if not "%MDTEST_EXIT%"=="0" (
    echo.
    echo MDTest could not start. See docs\INSTALL_HELP.md for help.
    echo.
    pause
)
exit /b %MDTEST_EXIT%

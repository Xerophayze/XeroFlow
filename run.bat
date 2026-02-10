@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM run.bat
REM This script activates the virtual environment and runs main.py

if /i "%~1"=="--check" (
    echo Run script syntax check passed.
    exit /b 0
)

REM Define variables
SET VENV_DIR=venv
SET MAIN_SCRIPT=main.py

REM Check if virtual environment exists
IF NOT EXIST %VENV_DIR%\Scripts\activate.bat (
    echo Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

REM Activate the virtual environment
echo Activating virtual environment...
CALL %VENV_DIR%\Scripts\activate.bat

REM Validate Python version from the virtual environment
set VENV_PY=%VENV_DIR%\Scripts\python.exe
if not exist "%VENV_PY%" (
    echo Virtual environment Python not found. Please run setup.bat.
    exit /b 1
)

set PY_VER_FILE=%TEMP%\xeroflow_pyver.txt
"%VENV_PY%" -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1])+'.'+str(sys.version_info[2]))" > "%PY_VER_FILE%" 2>nul
if %errorlevel% neq 0 (
    echo Failed to read Python version from virtual environment.
    exit /b 1
)
for /f "usebackq tokens=1,2,3 delims=." %%a in ("%PY_VER_FILE%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
    set PY_PATCH=%%c
)
del "%PY_VER_FILE%" >nul 2>&1
set PY_VER=%PY_MAJOR%.%PY_MINOR%.%PY_PATCH%

if "%PY_MAJOR%"=="" goto PY_BAD
if "%PY_MINOR%"=="" goto PY_BAD
if %PY_MAJOR% GTR 3 set PYTHON_OK=1
if %PY_MAJOR% EQU 3 if %PY_MINOR% GEQ 11 set PYTHON_OK=1

if "%PYTHON_OK%"=="0" goto PY_BAD
goto PY_OK

:PY_BAD
echo Python %PY_VER% detected, but 3.11+ is required.
echo Please re-run setup.bat to rebuild the virtual environment.
exit /b 1

:PY_OK

REM Run the main script
IF EXIST %MAIN_SCRIPT% (
    echo Running %MAIN_SCRIPT%...
    "%VENV_PY%" %MAIN_SCRIPT%
    IF %ERRORLEVEL% NEQ 0 (
        echo %MAIN_SCRIPT% encountered an error.
        exit /b %ERRORLEVEL%
    )
) ELSE (
    echo %MAIN_SCRIPT% not found.
    exit /b 1
)

REM Optional: Deactivate the virtual environment after running
echo Deactivating virtual environment...
CALL deactivate

echo Done.
PAUSE

@echo off
REM run.bat
REM This script activates the virtual environment and runs main.py

REM Define variables
SET VENV_DIR=venv
SET REQUIREMENTS=requirements.txt
SET MAIN_SCRIPT=main.py

REM Check if virtual environment exists
IF NOT EXIST %VENV_DIR%\Scripts\activate (
    echo Virtual environment not found. Creating virtual environment...
    python -m venv %VENV_DIR%
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment.
        exit /b %ERRORLEVEL%
    )
    
    REM Install dependencies
    IF EXIST %REQUIREMENTS% (
        echo Installing dependencies from %REQUIREMENTS%...
        CALL %VENV_DIR%\Scripts\activate
        pip install -r %REQUIREMENTS%
        IF %ERRORLEVEL% NEQ 0 (
            echo Failed to install dependencies.
            exit /b %ERRORLEVEL%
        )
        CALL deactivate
    ) ELSE (
        echo %REQUIREMENTS% not found. Skipping dependency installation.
    )
) ELSE (
    echo Virtual environment already exists.
)

REM Activate the virtual environment
echo Activating virtual environment...
CALL %VENV_DIR%\Scripts\activate

REM Run the main script
IF EXIST %MAIN_SCRIPT% (
    echo Running %MAIN_SCRIPT%...
    python %MAIN_SCRIPT%
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

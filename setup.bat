@echo off
REM setup_and_run.bat
REM This script checks for Python, installs it if necessary, sets up the virtual environment, installs dependencies, and runs main.py.

REM Define variables
SET VENV_DIR=venv
SET REQUIREMENTS=requirements.txt
SET MAIN_SCRIPT=main.py
SET PYTHON_INSTALLER=python-installer.exe
SET PYTHON_URL=https://www.python.org/ftp/python/3.10.0/python-3.10.0-amd64.exe

REM Check if Python is installed
echo Checking if Python is installed...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not installed. Downloading and installing Python...
    
    REM Download Python installer
    IF EXIST "%PYTHON_INSTALLER%" (
        del /f /q "%PYTHON_INSTALLER%"
    )
    
    REM Use curl if available, otherwise fallback to bitsadmin
    curl -o %PYTHON_INSTALLER% %PYTHON_URL% --silent --show-error || bitsadmin /transfer downloadpython /priority high %PYTHON_URL% "%CD%\%PYTHON_INSTALLER%"
    
    IF NOT EXIST "%PYTHON_INSTALLER%" (
        echo Failed to download Python installer. Please check your internet connection.
        exit /b 1
    )
    
    REM Install Python silently
    echo Installing Python silently...
    start /wait %PYTHON_INSTALLER% /quiet InstallAllUsers=1 PrependPath=1
    IF %ERRORLEVEL% NEQ 0 (
        echo Python installation failed.
        exit /b %ERRORLEVEL%
    ) ELSE (
        echo Python installed successfully.
    )
) ELSE (
    echo Python is already installed.
)

REM Check if pip is installed
echo Checking if pip is available...
python -m pip --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Pip is not installed. Installing pip...
    python -m ensurepip --upgrade
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to install pip.
        exit /b %ERRORLEVEL%
    )
) ELSE (
    echo Pip is available.
)

REM Check if virtual environment exists
IF NOT EXIST %VENV_DIR%\Scripts\activate (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment.
        exit /b %ERRORLEVEL%
    )
) ELSE (
    echo Virtual environment already exists.
)

REM Activate the virtual environment
echo Activating virtual environment...
CALL %VENV_DIR%\Scripts\activate

REM Install dependencies without upgrading pip
IF EXIST %REQUIREMENTS% (
    echo Installing dependencies from %REQUIREMENTS%...
    pip install -r %REQUIREMENTS%
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to install dependencies.
        exit /b %ERRORLEVEL%
    )
) ELSE (
    echo %REQUIREMENTS% not found. Skipping dependency installation.
)

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

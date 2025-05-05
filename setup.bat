@echo off
REM setup.bat
REM This script sets up the virtual environment, checks for dependencies, and installs requirements.

REM Define variables
SET VENV_DIR=venv
SET SWIG_DIR=C:\swigwin  REM Define SWIG directory if not in PATH

REM Check if Python 3.10 or higher is available
echo Checking if Python 3.10 or higher is available...
python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" > version.tmp
SET /p PYTHON_VERSION=<version.tmp
DEL version.tmp

FOR /F "tokens=1,2 delims=." %%a IN ("%PYTHON_VERSION%") DO (
    SET PYTHON_MAJOR=%%a
    SET PYTHON_MINOR=%%b
)

IF "%PYTHON_MAJOR%"=="3" IF %PYTHON_MINOR% GEQ 10 (
    echo Python %PYTHON_VERSION% is available and compatible.
) ELSE (
    echo Python 3.10 or higher is required but found version %PYTHON_VERSION%.
    echo Please install Python 3.10 or higher from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

REM Check if pip is available
echo Checking if pip is available...
python -m pip --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Pip is not installed. Please ensure pip is available with Python.
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
) ELSE (
    echo Pip is available.
)

REM Create virtual environment if it doesn't exist
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
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    exit /b %ERRORLEVEL%
)

REM Upgrade pip and install wheel separately to avoid conflicts
echo Upgrading pip and installing wheel...
python -m pip install --upgrade pip wheel
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to upgrade pip or install wheel.
    exit /b %ERRORLEVEL%
)

REM Install dependencies from requirements.txt
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    exit /b %ERRORLEVEL%
)

REM Ensure langchain_community is installed (if not already in requirements.txt)
pip show langchain_community >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo langchain_community module not found. Attempting to install it separately...
    pip install langchain-community
    IF %ERRORLEVEL% NEQ 0 (
        echo Failed to install langchain_community.
        exit /b %ERRORLEVEL%
    )
)

REM Inform user of successful setup
echo.
echo Setup completed successfully!
echo You can now run the application by executing run.bat.
echo.

REM Optional: Deactivate the virtual environment
echo Deactivating virtual environment...
CALL deactivate

echo Done.
PAUSE

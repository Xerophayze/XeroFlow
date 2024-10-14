@echo off
REM setup.bat
REM This script sets up the virtual environment, checks for dependencies, and installs requirements.

REM Define variables
SET VENV_DIR=venv
SET SWIG_DIR=C:\swigwin  REM Define SWIG directory if not in PATH

REM Check if Python is available
echo Checking if Python is available...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not found in PATH. Please install or adjust the PATH variable.
    exit /b 1
) ELSE (
    echo Python is available.
)

REM Check if pip is available
echo Checking if pip is available...
python -m pip --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Pip is not installed. Please ensure pip is available and try again.
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

REM Upgrade pip and install wheel separately to avoid conflicts
echo Upgrading pip and installing wheel...
%VENV_DIR%\Scripts\python.exe -m pip install --upgrade pip wheel
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to upgrade pip or install wheel.
    exit /b %ERRORLEVEL%
)

REM Install numpy without strict version constraint
echo Installing numpy without version constraint...
pip install numpy
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to install numpy.
    exit /b %ERRORLEVEL%
)

REM Attempt to install faiss-cpu if available (optional)
echo Attempting to install faiss-cpu from prebuilt wheels...
pip install faiss-cpu || echo "Warning: faiss-cpu installation failed. Skipping faiss-cpu installation."
IF %ERRORLEVEL% NEQ 0 (
    echo Skipping faiss-cpu installation due to compatibility issues.
)

REM Install additional dependencies from requirements.txt
echo Installing additional dependencies...
pip install -r requirements.txt --no-deps
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    exit /b %ERRORLEVEL%
)

REM Ensure langchain_community is installed
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

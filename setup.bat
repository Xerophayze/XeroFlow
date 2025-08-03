@echo off
setlocal

REM Set the name of the virtual environment directory
set VENV_DIR=venv

REM Check for Python 3.10 or higher
echo Checking if Python 3.10 or higher is available...
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.10 or higher and try again.
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if "%PYTHON_MAJOR%" neq "3" (
    set COMPATIBLE=0
) else if %PYTHON_MINOR% lss 10 (
    set COMPATIBLE=0
) else (
    set COMPATIBLE=1
)

if "%COMPATIBLE%" == "1" (
    echo Python %PYTHON_VERSION% is available and compatible.
) else (
    echo Python 3.10 or higher is required, but found version %PYTHON_VERSION%.
    echo Please install a compatible version of Python and try again.
    exit /b 1
)

REM Check for pip
echo Checking if pip is available...
where pip >nul 2>nul
if %errorlevel% neq 0 (
    echo Pip is not available. Please ensure Python is installed correctly with pip.
    exit /b 1
)
echo Pip is available.

REM Create virtual environment if it doesn't exist
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

REM Activate virtual environment
echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

REM Upgrade pip, wheel, and setuptools
echo Upgrading pip, wheel, and setuptools...
python -m pip install --upgrade pip wheel setuptools

REM Install all dependencies from requirements.txt
echo Installing all dependencies from requirements.txt...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Failed to install dependencies from requirements.txt.
    exit /b 1
)

echo Installation of all dependencies completed successfully.

REM Deactivate and clean up
call "%VENV_DIR%\Scripts\deactivate.bat"

endlocal

echo Setup complete. You can now run the application.
pause

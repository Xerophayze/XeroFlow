@echo off
setlocal

REM Set the name of the virtual environment
set VENV_DIR=venv

:CHECK_PYTHON
echo Checking for Python...
REM Use the 'py' launcher if available, otherwise check for 'python'
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python
    ) else (
        goto INSTALL_PYTHON
    )
)
echo Python found.
goto SETUP_ENV

:INSTALL_PYTHON
echo Python is not installed or not in the system's PATH.
set /p "CHOICE=Would you like to download and install it automatically? (Y/N): "
if /i not "%CHOICE%"=="Y" (
    echo Installation declined. Please install Python 3 manually and re-run this script.
    pause
    exit /b 1
)

echo Downloading Python installer...

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"

echo Running Python installer silently. This may take a few minutes and require administrator permission...

start /wait %TEMP%\python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

if %errorlevel% neq 0 (
    echo Python installation failed. Please try installing it manually from python.org.
    pause
    exit /b 1
)

echo Python installation complete.

REM Clean up the installer
del %TEMP%\python_installer.exe

REM Re-check for Python after installation
goto CHECK_PYTHON

:SETUP_ENV
REM Check if the virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo Installing dependencies from requirements.txt...
REM Upgrade pip, wheel, and setuptools
echo Upgrading pip, wheel, and setuptools...
python -m pip install --upgrade pip wheel setuptools

REM Install all dependencies from requirements.txt
echo Installing all dependencies from requirements.txt...
pip install -r requirements.txt

REM Install PyTorch with CUDA support (falls back to CPU wheels if needed)
echo Installing PyTorch (CUDA wheels)...
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
if %errorlevel% neq 0 (
    echo CUDA wheels failed to install. Falling back to CPU wheels...
    pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cpu
    if %errorlevel% neq 0 (
        echo Failed to install PyTorch. Please install manually and re-run this script.
        exit /b 1
    )
)

if %errorlevel% neq 0 (
    echo Failed to install dependencies from requirements.txt.
    exit /b 1
)

echo Installation of all dependencies completed successfully.

REM Ensure ffmpeg is available (auto-installs a local copy if needed)
echo Ensuring ffmpeg is available...
python -c "from utils.ffmpeg_installer import ensure_ffmpeg_available; p=ensure_ffmpeg_available(True); print('FFmpeg path:', p)"

REM Deactivate and clean up
call "%VENV_DIR%\Scripts\deactivate.bat"

endlocal

echo Setup complete. You can now run the application.
pause

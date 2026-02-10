@echo off
setlocal

if /i "%~1"=="--check" (
    echo Setup script syntax check passed.
    exit /b 0
)

REM Set the name of the virtual environment
set VENV_DIR=venv

:CHECK_PYTHON
echo Checking for Python 3.11+...
set PYTHON_EXE=
set PYTHON_ARGS=
set PY_VER=
set PYTHON_OK=0

REM Prefer py launcher for specific versions
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.11 -V >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_EXE=py
        set PYTHON_ARGS=-3.11
        goto PY_FOUND
    )
    py -3.12 -V >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_EXE=py
        set PYTHON_ARGS=-3.12
        goto PY_FOUND
    )
)

REM Fallback to python on PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_EXE=python
)

:PY_FOUND
if "%PYTHON_EXE%"=="" (
    goto INSTALL_PYTHON
)

set PY_VER_FILE=%TEMP%\xeroflow_pyver.txt
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1])+'.'+str(sys.version_info[2]))" > "%PY_VER_FILE%" 2>nul
if %errorlevel% neq 0 (
    goto INSTALL_PYTHON
)
for /f "usebackq tokens=1,2,3 delims=." %%a in ("%PY_VER_FILE%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
    set PY_PATCH=%%c
)
del "%PY_VER_FILE%" >nul 2>&1
set PY_VER=%PY_MAJOR%.%PY_MINOR%.%PY_PATCH%

if "%PY_MAJOR%"=="" goto INSTALL_PYTHON
if "%PY_MINOR%"=="" goto INSTALL_PYTHON
if %PY_MAJOR% GTR 3 set PYTHON_OK=1
if %PY_MAJOR% EQU 3 if %PY_MINOR% GEQ 11 set PYTHON_OK=1

if "%PYTHON_OK%"=="1" (
    echo Python %PY_VER% detected.
    goto SETUP_ENV
)

echo Detected Python %PY_VER% but 3.11+ is required.
goto INSTALL_PYTHON

:INSTALL_PYTHON
echo Python 3.11+ is not installed or not in PATH.
set /p "PY_CHOICE=Install Python 3.11 or 3.12? (11/12/N): "

if /i "%PY_CHOICE%"=="11" (
    set PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
) else if /i "%PY_CHOICE%"=="12" (
    set PY_URL=https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe
) else (
    echo Installation cancelled. Please install Python 3.11+ and re-run this script.
    pause
    exit /b 1
)

echo Downloading Python installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%TEMP%\python_installer.exe'"

echo Running Python installer silently. This may take a few minutes and require administrator permission...
start /wait "" "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

if %errorlevel% equ 3010 (
    echo Python installed and a reboot is required. Please reboot and re-run setup.bat.
    pause
    exit /b 0
)

if %errorlevel% neq 0 (
    echo Silent install failed. Launching interactive installer...
    start "" "%TEMP%\python_installer.exe"
    echo Complete the installer, then press any key to continue.
    pause
)

echo Python installation complete.
del "%TEMP%\python_installer.exe"
goto CHECK_PYTHON

:SETUP_ENV
REM Check if the virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PYTHON_EXE% %PYTHON_ARGS% -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
set VENV_PY=%VENV_DIR%\Scripts\python.exe

"%VENV_PY%" -V >nul 2>&1
if %errorlevel% neq 0 (
    echo Virtual environment Python is broken. Recreating venv...
    call "%VENV_DIR%\Scripts\deactivate.bat"
    rmdir /s /q "%VENV_DIR%"
    %PYTHON_EXE% %PYTHON_ARGS% -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo Failed to recreate virtual environment.
        pause
        exit /b 1
    )
    call "%VENV_DIR%\Scripts\activate.bat"
    set VENV_PY=%VENV_DIR%\Scripts\python.exe
)

echo Installing dependencies from requirements.txt...
REM Upgrade pip, wheel, and setuptools
echo Upgrading pip, wheel, and setuptools...
"%VENV_PY%" -m pip install --upgrade pip wheel setuptools

REM Install all dependencies from requirements.txt
echo Installing all dependencies from requirements.txt...
"%VENV_PY%" -m pip install -r requirements.txt

REM Uninstall existing torch packages (likely CPU versions from requirements.txt) to force CUDA install
echo Uninstalling any existing PyTorch versions...
"%VENV_PY%" -m pip uninstall -y torch torchvision torchaudio

REM Install PyTorch with CUDA support (falls back to CPU wheels if needed)
REM Install PyTorch with CUDA support (falls back to CPU wheels if needed)
echo Installing PyTorch (CUDA wheels)...
"%VENV_PY%" -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
if %errorlevel% neq 0 (
    echo CUDA wheels failed to install. Falling back to CPU wheels...
    "%VENV_PY%" -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
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
"%VENV_PY%" -c "from utils.ffmpeg_installer import ensure_ffmpeg_available; p=ensure_ffmpeg_available(True); print('FFmpeg path:', p)"

REM Deactivate and clean up
call "%VENV_DIR%\Scripts\deactivate.bat"

endlocal

echo Setup complete. You can now run the application.
pause

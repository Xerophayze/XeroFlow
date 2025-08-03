@echo off
REM XeroFlow Client Starter
echo Starting XeroFlow Client...

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3.6 or higher.
    pause
    exit /b 1
)

REM Check for required packages
echo Checking dependencies...
python -c "import tkinter" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo tkinter is not installed. This should be included with Python.
    echo Please install Python with tkinter support.
    pause
    exit /b 1
)

REM Check for PIL/Pillow
python -c "import PIL" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing Pillow
    pip install pillow
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install Pillow. Please install it manually with: pip install pillow
        pause
        exit /b 1
    )
)

REM Check for tkinterdnd2
python -c "import tkinterdnd2" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing tkinterdnd2 for drag and drop support...
    pip install tkinterdnd2
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install tkinterdnd2. Drag and drop will not be available.
        echo You can install it manually with: pip install tkinterdnd2
        echo Continuing without drag and drop support...
    ) else (
        echo tkinterdnd2 installed successfully. Drag and drop support enabled.
    )
)

REM Run the application
echo Launching XeroFlow Client...
python Source\xeroflow_client.py

REM If we get here, the application has exited
echo XeroFlow Client has closed.
pause

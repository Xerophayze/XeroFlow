@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_URL=https://github.com/Xerophayze/XeroFlow.git"
set "REPO_DIR=XeroFlow"
set "GIT_INSTALLER_URL="
set "GIT_INSTALLER=%TEMP%\git-installer.exe"

echo ========================================
echo XeroFlow Windows Install/Update
echo ========================================
echo.

echo Checking Git installation...
where git >nul 2>&1
if errorlevel 1 (
    echo Git not found. Downloading and installing Git for Windows...
    powershell -NoLogo -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $api='https://api.github.com/repos/git-for-windows/git/releases/latest'; $headers=@{ 'User-Agent'='TTS-Story-Installer' }; try { $release=Invoke-RestMethod -Uri $api -Headers $headers -ErrorAction Stop; $asset=$release.assets | Where-Object { $_.name -match '64-bit\.exe$' -and $_.name -notmatch 'portable' -and $_.name -notmatch 'mingit' } | Select-Object -First 1; if (-not $asset) { throw 'Unable to find Git 64-bit installer asset.' } $url=$asset.browser_download_url; try { Invoke-WebRequest -Uri $url -OutFile '%GIT_INSTALLER%' -UseBasicParsing -ErrorAction Stop } catch { try { Start-BitsTransfer -Source $url -Destination '%GIT_INSTALLER%' -ErrorAction Stop } catch { Write-Error $_.Exception.Message; exit 1 } } } catch { Write-Error $_.Exception.Message; exit 1 }"
    if errorlevel 1 (
        echo ERROR: Failed to download Git installer.
        pause
        exit /b 1
    )

    "%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP-
    if errorlevel 1 (
        echo ERROR: Git installer failed.
        pause
        exit /b 1
    )

    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    where git >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Git installed but not found in PATH. Please restart your terminal.
        pause
        exit /b 1
    )
) else (
    echo Git is installed.
)

echo.
echo Cloning or updating repository...
if exist "%REPO_DIR%" (
    if exist "%REPO_DIR%\.git" (
        echo Repository found. Pulling latest updates...
        pushd "%REPO_DIR%"
        git pull
        if errorlevel 1 (
            echo ERROR: Git pull failed.
            popd
            pause
            exit /b 1
        )
        popd
    ) else (
        echo ERROR: "%REPO_DIR%" exists but is not a Git repository.
        echo Please rename or remove the folder and re-run this script.
        pause
        exit /b 1
    )
) else (
    git clone "%REPO_URL%" "%REPO_DIR%"
    if errorlevel 1 (
        echo ERROR: Git clone failed.
        pause
        exit /b 1
    )
)

echo.
choice /C YN /M "Run setup.bat to update dependencies/components?"
if errorlevel 2 (
    echo Skipping setup. Git update complete.
    goto :Done
)

echo.
echo Running setup.bat...
if exist "%REPO_DIR%\setup.bat" (
    pushd "%REPO_DIR%"
    call setup.bat
    popd
) else (
    echo ERROR: setup.bat not found in %REPO_DIR%.
    pause
    exit /b 1
)

echo.
echo ✅ Install/update complete.
:Done
pause

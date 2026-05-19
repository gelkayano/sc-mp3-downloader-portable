@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ========================================
echo Building SoundCloud MP3 Downloader
echo ========================================
echo.

:: ============================================
:: STEP 1 — Update pip itself
:: ============================================
echo [1/5] Updating pip...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo ⚠ pip update failed, continuing...
)
echo ✅ pip up to date
echo.

:: ============================================
:: STEP 2 — Update Python dependencies
:: ============================================
echo [2/5] Updating Python packages...
python -m pip install --upgrade yt-dlp customtkinter pillow pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ❌ ERROR: Failed to update packages!
    pause
    exit /b 1
)
echo ✅ yt-dlp, customtkinter, pillow, pyinstaller updated
echo.

:: ============================================
:: STEP 3 — Check ffmpeg
:: ============================================
echo [3/5] Checking ffmpeg...
if not exist "ffmpeg.exe" (
    echo ❌ ERROR: ffmpeg.exe not found in current folder!
    echo Download it from https://ffmpeg.org and place here.
    pause
    exit /b 1
)
echo ✅ ffmpeg.exe found

:: aria2c is optional — include in bundle only if present
set ARIA2_FLAG=
if exist "aria2c.exe" (
    set ARIA2_FLAG=--add-binary "aria2c.exe;."
    echo ✅ aria2c.exe found ^(will be bundled^)
) else (
    echo ℹ aria2c.exe not found ^(optional, skipping^)
)
echo.

:: ============================================
:: STEP 4 — Recreate icon (always fresh)
:: ============================================
echo [4/5] Generating icon...
python create_icon.py
if %errorlevel% neq 0 (
    echo ❌ ERROR: Failed to create icon.ico!
    pause
    exit /b 1
)
echo ✅ icon.ico ready
echo.

:: ============================================
:: STEP 5 — Build
:: ============================================
echo [5/5] Building executable...
echo.

pyinstaller --noconfirm --onedir --windowed ^
    --name "SoundCloud Downloader" ^
    --icon "icon.ico" ^
    --add-binary "ffmpeg.exe;." ^
    %ARIA2_FLAG% ^
    --add-data "icon.ico;." ^
    --add-data "splash.py;." ^
    --hidden-import "yt_dlp" ^
    --hidden-import "customtkinter" ^
    --collect-all "customtkinter" ^
    --collect-all "yt_dlp" ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

:: ============================================
:: DONE
:: ============================================
echo.
echo ========================================
echo ✅ Build complete!
echo    Folder: dist\SoundCloud Downloader\
echo ========================================
echo.

pause
@echo off
rem One-click launcher for Windows: double-click to set up (first run only) and start pdf2kindle.
setlocal
cd /d "%~dp0"
title pdf2kindle

if exist ".venv\Scripts\pdf2kindle.exe" goto :ocr

echo === First run: installing pdf2kindle ===
where uv >nul 2>nul
if not errorlevel 1 (
    uv sync --no-dev
    goto :installed
)
where python >nul 2>nul
if errorlevel 1 (
    echo Python 3.12+ is required. Install it from https://www.python.org/downloads/ and run this again.
    goto :fail
)
python -m uv --version >nul 2>nul
if errorlevel 1 python -m pip install --user --quiet uv
python -m uv sync --no-dev
:installed
if not exist ".venv\Scripts\pdf2kindle.exe" goto :fail

:ocr
set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
where tesseract >nul 2>nul
if not errorlevel 1 goto :models
if exist "%TESS%" goto :models
echo.
echo Tesseract OCR is not installed. Without it, scanned pages are kept as page images.
choice /c YN /m "Install Tesseract now with winget"
if errorlevel 2 goto :start
winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-source-agreements --accept-package-agreements

:models
set "TESSDATA=%USERPROFILE%\.pdf2kindle\tessdata"
if exist "%TESSDATA%\ben.traineddata" goto :start
echo Downloading Bengali and English OCR models (about 37 MB, first run only)...
if not exist "%TESSDATA%" mkdir "%TESSDATA%"
for %%L in (ben eng osd) do (
    curl -fsSL -o "%TESSDATA%\%%L.traineddata" "https://github.com/tesseract-ocr/tessdata_best/raw/main/%%L.traineddata"
)

:start
echo.
".venv\Scripts\pdf2kindle.exe" serve --open
goto :end

:fail
echo.
echo Setup failed. See the messages above.
:end
pause

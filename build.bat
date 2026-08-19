@echo off
cd /d "%~dp0"
echo ================================================
echo   FormatMaster build script (onedir / folder mode)
echo   Output: ..\FormatMaster_dist\dist\FormatMaster
echo ================================================
echo.
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Please check project structure.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" build.py
set CODE=%errorlevel%
echo.
if "%CODE%"=="0" (
    echo [OK] Build succeeded! Output at ..\FormatMaster_dist\dist\FormatMaster
) else (
    echo [FAILED] Build exited with code %CODE%. See log above.
)
echo.
pause

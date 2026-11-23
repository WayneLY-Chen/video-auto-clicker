@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py build.py
) else (
    python build.py
)
if errorlevel 1 echo. & echo Build failed. Please check the messages above.
pause

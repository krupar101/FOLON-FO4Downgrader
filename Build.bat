@echo off
setlocal
cd /d "%~dp0" || exit /b 1

rem A previous one-folder build may leave dist\_internal and an old EXE.
rem --clean only clears PyInstaller caches, NOT these stale distribution files.
if exist "dist" (
    echo Removing previous dist directory...
    rmdir /s /q "dist" || exit /b 1
)
if exist "build" (
    echo Removing previous build directory...
    rmdir /s /q "build" || exit /b 1
)

py -3.12 -m venv .venv\win || exit /b 1
call .venv\win\Scripts\activate.bat || exit /b 1
python -m pip install -r requirements-build.txt || exit /b 1
python -m unittest discover -s tests -v || exit /b 1
python -m PyInstaller --clean -y FOLON-Downgrader.spec || exit /b 1
python packaging\verify-windows-onefile.py || exit /b 1
python packaging\smoke-test.py || exit /b 1

echo.
echo SUCCESS: Share ONLY dist\Downgrader-2.0.exe
endlocal

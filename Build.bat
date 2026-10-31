@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv .venv\win || exit /b 1
call .venv\win\Scripts\activate.bat
python -m pip install -r requirements-build.txt || exit /b 1
python -m unittest discover -s tests -v || exit /b 1
python -m PyInstaller --clean -y FOLON-Downgrader.spec || exit /b 1
endlocal

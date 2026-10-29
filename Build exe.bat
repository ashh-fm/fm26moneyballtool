@echo off
rem Builds "FM26 Moneyball.exe" into the dist folder. Needs: python -m pip install pyinstaller
cd /d "%~dp0reader"
python -m PyInstaller --noconfirm --onefile --windowed --name "FM26 Moneyball" ^
  --add-data "%~dp0FM26 Moneyball.html;." ^
  --distpath "%~dp0dist" --workpath "%TEMP%\fm26-moneyball-build" --specpath "%TEMP%\fm26-moneyball-build" ^
  app.py
if errorlevel 1 (echo Build failed & pause & exit /b 1)
echo.
echo Built: "%~dp0dist\FM26 Moneyball.exe"

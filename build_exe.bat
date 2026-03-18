@echo off
chcp 65001 >nul
REM MT5 Gold Trader Bot - telepíthető exe készítése
REM Előtte: pip install -r requirements.txt  (customtkinter, pydantic, MetaTrader5, stb.)

echo Függőségek ellenőrzése...
python -c "import customtkinter; import pydantic; import MetaTrader5" 2>nul
if %ERRORLEVEL% neq 0 (
    echo Hiányzó modul. Futtasd: pip install -r requirements.txt
    echo Majd indítsd újra a build_exe.bat-ot.
    pause
    exit /b 1
)
echo Telepíthető program összeállítása...
python -m PyInstaller --noconfirm gold_trader.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo A build sikertelen. Ha "No module named PyInstaller" a hiba:
    echo   Futtasd: pip install pyinstaller
    echo Majd indítsd újra a build_exe.bat-ot.
    echo.
    pause
    exit /b 1
)
echo.
echo Kész. A program: dist\MT5 Gold Trader Bot.exe
echo Az exe-t másold bárhová; futtatás előtt indítsd el az MT5 terminált.
pause

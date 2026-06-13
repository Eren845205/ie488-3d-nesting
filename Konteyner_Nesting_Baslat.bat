@echo off
chcp 65001 >nul
title Konteyner Nesting Sistemi

echo ============================================================
echo  Konteyner Nesting Sistemi - Demo Sunucusu
echo ============================================================
echo  Sunucu baslatiliyor: http://127.0.0.1:8765
echo  Bu pencereyi kapatirsaniz sunucu durur.
echo ============================================================
echo.

cd /d "%~dp0"

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"

python -m src.webapp.app

echo.
echo Sunucu durduruldu. Pencereyi kapatabilirsiniz.
pause

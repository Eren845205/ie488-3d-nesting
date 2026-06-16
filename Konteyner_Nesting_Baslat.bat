@echo off
chcp 65001 >nul
title Konteyner Nesting Sistemi
cd /d "%~dp0"

echo ============================================================
echo  Konteyner Nesting Sistemi - http://127.0.0.1:8765
echo  Bu pencereyi kapatirsaniz sunucu durur.
echo ============================================================
echo.

echo Eski sunucu sureci (varsa) kapatiliyor...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Sunucu baslatiliyor; tarayici birkac saniye icinde otomatik acilacak...
echo.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://127.0.0.1:8765'"

python -m src.webapp.app

echo.
echo Sunucu durduruldu. Pencereyi kapatabilirsiniz.
pause

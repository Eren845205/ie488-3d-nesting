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

echo Ollama (LLM asistani) kontrol ediliyor...
rem Port 11434 dinlenmiyorsa ollama serve arka planda baslatilir
rem (modeller D:\ollama\models — OLLAMA_MODELS kullanici env'inden gelir).
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -WindowStyle Hidden '%LOCALAPPDATA%\Programs\Ollama\ollama.exe' -ArgumentList 'serve'; Write-Host '  Ollama baslatildi (arka plan).' } else { Write-Host '  Ollama zaten calisiyor.' }"

echo Sunucu baslatiliyor; tarayici birkac saniye icinde otomatik acilacak...
echo.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://127.0.0.1:8765'"

rem Giris sifresi (ADMIN_PASSWORD) ve mail bilgileri .env dosyasindan okunur.
rem Ilk kurulum: .env.example dosyasini .env olarak kopyalayip doldurun.
python -m src.webapp.app

echo.
echo Sunucu durduruldu. Pencereyi kapatabilirsiniz.
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
cls
echo ============================================================
echo    IE 488 - AM Nesting Demo
echo ============================================================
echo.
echo Bottom-Left algoritmasi, medium parca seti (25 parca)
echo calistiriliyor...
echo.
python src/run.py --algo bl --set medium
echo.
echo ------------------------------------------------------------
echo Yerlesim gorseli aciliyor...
start "" "results\bl_medium_on.png"
echo Karsilastirma grafigi aciliyor...
start "" "results\comparison_bar.png"
echo ------------------------------------------------------------
echo.
echo Demo tamam. Gorseller acildi.
echo Bu pencereyi kapatmak icin bir tusa bas.
pause >nul

@echo off
chcp 65001 >nul
cd /d "%~dp0"
cls
echo ============================================================
echo    IE 488 - Simulated Annealing Optimizasyon Demo
echo ============================================================
echo.
echo Baseline (BL/BFD) ile Simulated Annealing optimizasyonu
echo medium parca setinde canli karsilastiriliyor...
echo (yaklasik 3 saniye surer)
echo.
python src/run_sa.py --set medium
echo.
echo ------------------------------------------------------------
echo Optimize edilmis yerlesim aciliyor...
start "" "results\sa_medium.png"
echo BL vs BFD vs SA karsilastirma grafigi aciliyor...
start "" "results\comparison_with_sa.png"
echo Yakinsama grafigi aciliyor...
start "" "results\sa_convergence.png"
echo ------------------------------------------------------------
echo.
echo Demo tamam. Optimizasyon doluluk oranini artirdi.
echo Bu pencereyi kapatmak icin bir tusa bas.
pause >nul

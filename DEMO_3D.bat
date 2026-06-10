@echo off
chcp 65001 >nul
cd /d "%~dp0"
cls
echo ============================================================
echo    IE 488 - 3D Voxel Nesting Demo (Asama 2)
echo ============================================================
echo.
echo Pipeline: 3 STL model (chair x10, bracket x5, ring x15)
echo   -^> voxelization -^> DBLF baseline -^> SA -^> .STL export
echo.

python -c "import trimesh" >nul 2>&1
if errorlevel 1 (
    echo trimesh kuruluyor...
    pip install trimesh
)

if not exist "data\models\chair.stl" (
    echo Modeller uretiliyor...
    python scripts\generate_models.py
)

echo Iki senaryo calistiriliyor (yaklasik 1 dakika)...
echo.
python -m src.nesting3d.run3d --scenario all --export-stl --iters 1000
echo.
echo ------------------------------------------------------------
echo Yerlesim gorselleri aciliyor...
start "" "results\nesting3d_default.png"
start "" "results\nesting3d_stress.png"
echo SA yakinsama grafigi aciliyor (stress)...
start "" "results\sa3d_convergence_stress.png"
echo ------------------------------------------------------------
echo.
echo STL ciktilari (3D Viewer / slicer ile acilabilir):
echo   results\nesting3d_result_default.stl
echo   results\nesting3d_result_stress.stl
echo Ozet tablo: results\summary_3d.md
echo.
echo Demo tamam. Bu pencereyi kapatmak icin bir tusa bas.
pause >nul

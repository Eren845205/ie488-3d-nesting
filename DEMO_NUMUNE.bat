@echo off
chcp 65001 >nul
cd /d "%~dp0"
cls
echo ============================================================
echo    IE 488 - Numune Seti 3D Nesting Demo (gercek parcalar)
echo ============================================================
echo.
echo Pipeline: 8 gercek STL (Numuneler/, toplam 48 parca)
echo   1x4  2x16  3x3  4x15  5x1  6x3  7x3  8x3
echo   -^> slice voxelization -^> DBLF baseline -^> SA -^> .STL export
echo Taban: 350x350 mm (4.stl = 304.8 mm), pitch 2.5 mm
echo.

python -c "import trimesh, shapely, fast_simplification" >nul 2>&1
if errorlevel 1 (
    echo Eksik paketler kuruluyor...
    pip install trimesh shapely fast-simplification networkx rtree
)

echo [1/3] DBLF baseline kosusu...
python -m src.nesting3d.run3d --scenario numune --algo dblf --voxel-method slice --plate 350 --pitch 2.5 --export-stl --out results\numune_dblf
echo.
echo [2/3] SA kosusu (1000 iterasyon, ~10 dk surebilir)...
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --voxel-method slice --plate 350 --pitch 2.5 --export-stl --out results\numune_sa
echo.
echo [3/3] Karsilastirma raporu...
python scripts\compare_numune.py
echo.
echo ------------------------------------------------------------
start "" "results\numune_overview.png"
start "" "results\numune_comparison.png"
start "" "results\numune_sa\sa3d_convergence_numune.png"
echo ------------------------------------------------------------
echo.
echo STL ciktilari (3D Viewer / slicer ile acilabilir):
echo   results\numune_dblf\nesting3d_result_numune.stl
echo   results\numune_sa\nesting3d_result_numune.stl
echo Rapor: results\numune_comparison.md
echo.
echo Demo tamam. Bu pencereyi kapatmak icin bir tusa bas.
pause >nul

"""nfv_solve.py — NFV cavity yerleştirici (opt-in "kalite modu" üretim çözücüsü).

ENGEL 1 ÇÖZÜMÜ (kanıt `scripts/c3_nfv_solve.py`): üretimin coarse→fine+drop boru hattı NFV'nin
3B-cavity pozisyonlarını BOZUYORDU. Çözüm: NFV'yi HEDEF pitch'te tam-yerleştirici koş (best_decode),
çıktıyı (part_id,oi,x,y,z) → Bin3D'ye REPLAY et (Bin3D.place TAM (x,y,z)'ye koyar, drop YOK →
Placement3D üretir + heightmap günceller). Cavity korunur; non-overlap OccupancyBin3D.place ile garanti.

Sonuç `CoarseToFineResult` (solve_coarse_to_fine ile AYNI şekil) → render/export/UI değişmeden tüketir.
Downstream `tune_result.{winning_config_name,baseline_height_mm,all_results,improvement_mm}` okuduğundan
sentetik minimal TuneResult konur. cupy yoksa best_decode CPU'ya düşer (graceful).
"""
from __future__ import annotations
import time
from types import SimpleNamespace

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.coarse_to_fine import CoarseToFineResult
from src.nesting3d.tuner import TuneResult
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.parallel_decode import best_decode


def _voxelize_nfv(instance, pitch, floor_pitch, n_orientations, margin):
    """coarse_to_fine._voxelize_with_fallback mantığı + margin (o fonksiyon margin geçmiyor).
    İnce-duvar parça pitch'te kaybolursa (ValueError) pitch'i kıs, floor'a kadar dene. (parts, used)."""
    cur = pitch
    while True:
        try:
            return to_voxel_parts(instance, cur, n_orientations=n_orientations, margin=margin), cur
        except ValueError:
            nxt = cur / 1.5
            if nxt <= floor_pitch:
                return (to_voxel_parts(instance, floor_pitch, n_orientations=n_orientations,
                                       margin=margin), floor_pitch)
            cur = nxt


def solve_nfv(instance, *, plate_w_mm, plate_d_mm, fine_pitch=None,
              n_orientations=4, margin=1, seed=42, force=None) -> CoarseToFineResult:
    """NFV cavity decode → CoarseToFineResult. force: best_decode strateji zorla (test/debug).

    fine_pitch=None (varsayılan) → NFV-farkında pitch otomatik seçilir (suggest_nfv_pitch):
    parçayı kaybetmeyen EN KABA pitch (hız/bellek min, kalite ~korunur). Çağıran açık pitch
    verirse o kullanılır (opt-in override). Ölçüm gerekçesi: instances/pitch.py + c3_pitch_curve.py.
    """
    t0 = time.perf_counter()
    nfv_reason = None
    if fine_pitch is None:
        fine_pitch, feasible, nfv_reason = suggest_nfv_pitch(
            instance, plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
            ram_bytes=probe_capabilities().ram_bytes, margin=margin,
        )
        # feasible=False → en kaba pitch bile bellek bütçesini aşıyor; yine de denenir (best_decode
        # GPU→CPU→seri graceful fallback ile en uygun yolu bulur), ama reason raporlanır (uyarı).
    parts, used_pitch = _voxelize_nfv(instance, fine_pitch, fine_pitch, n_orientations, margin)
    nx, ny = int(plate_w_mm // used_pitch), int(plate_d_mm // used_pitch)

    _, raw, strategy = best_decode(parts, nx, ny, pitch=used_pitch, force=force)

    # REPLAY → Bin3D (tek kaynak: Placement3D + heightmap). TAM (x,y,z), drop YOK → cavity korunur.
    bin3d = Bin3D(plate_w_mm, plate_d_mm, used_pitch)
    parts_by_id = {p.id: p for p in parts}
    for (pid, oi, x, y, z) in raw:
        bin3d.place(parts_by_id[pid], oi, x, y, z)
    elapsed = time.perf_counter() - t0

    h = bin3d.max_height_mm()
    density = bin3d.packing_density()
    # sentetik minimal TuneResult (downstream raporlama: all_results satırı .height_mm/.density/.time_s okur)
    row = SimpleNamespace(height_mm=h, density=density, time_s=elapsed)
    tune_result = TuneResult(result=None, winning_config_name="nfv",
                             baseline_height_mm=h, improvement_mm=0.0,
                             all_results=[("nfv", row)])

    return CoarseToFineResult(
        placements=bin3d.placements, bin3d=bin3d, height_mm=h, density=density,
        winning_config="nfv", coarse_height_mm=h, coarse_pitch=used_pitch, fine_pitch=used_pitch,
        coarse_time_s=0.0, fine_time_s=elapsed, n_placed=len(bin3d.placements),
        tune_result=tune_result, fine_voxel_parts=parts_by_id, fine_angle_used=False,
        adaptive_reason=f"nfv strategy={strategy}" + (f" | {nfv_reason}" if nfv_reason else ""),
    )

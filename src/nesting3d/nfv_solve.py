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

# NFV oryantasyon seçimi (ÖLÇÜM 2026-06-24, c3_quality_levers):
#   * n=8 default. NEDEN SABİT-DEĞİL-AMA-SABİT: n=8 oryantasyon seti n=4'ü İÇERİR (4⊂8) → NFV greedy
#     n=8'de en az n=4 kadar iyi seçer → kalite HER veride garantili >= n=4 (Plan2'ye overfit DEĞİL,
#     küme-içerme matematiği). Sweet spot: 4→8 ~%6 kazanç; 8→12 sadece ~%1.1 + 3× yavaş + RAM-riskli.
#   * Adaptif DBLF-prob DENENDİ → NO-GO: heightmap-DBLF n-getiriyi TERS tahmin etti (Plan2 trail
#     n=4:639<n=8:645 dedi ama NFV'de n=8=522<n=4=556 İYİ) + prob 919s yavaş. DBLF NFV'yi temsil etmez.
#   * quality="max": donanım-tavanına kadar aç (RAM'e göre 8→12→28). 16GB laptop→12, datacenter→28.
NFV_DEFAULT_ORIENTATIONS = 8
NFV_QUALITY_MAX_CEIL = 28  # algoritmik tavan (24 simetri + eğik açılar); ötesi boşa


def _hw_max_orientations(ram_bytes: int) -> int:
    """quality='max': donanımın güvenle kaldırabileceği en yüksek oryantasyon (RAM-tavanı).
    Ölçüm-kalibre (16GB: n=12 OK / n=28 OOM). Datacenter (>=28GB) → 28. Sabit değil, RAM'den türer."""
    gb = ram_bytes / 1e9
    if gb >= 28:
        return NFV_QUALITY_MAX_CEIL  # 28 — bol RAM (datacenter/süper bilgisayar)
    if gb >= 13:
        return 12                    # ~16GB laptop — ölçüldü: n=12 sığar, n=28 OOM
    return NFV_DEFAULT_ORIENTATIONS  # düşük RAM — güvenli taban


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
              n_orientations=None, quality="fast", margin=1, seed=42, force=None) -> CoarseToFineResult:
    """NFV cavity decode → CoarseToFineResult. force: best_decode strateji zorla (test/debug).

    fine_pitch=None (varsayılan) → NFV-farkında pitch otomatik seçilir (suggest_nfv_pitch):
    parçayı kaybetmeyen EN KABA güvenli pitch + bellek/plaka guard. Açık pitch → opt-in override.

    n_orientations seçimi:
      * Açık int verilirse o kullanılır.
      * None (varsayılan) → quality'ye göre:
          - quality="fast"  → n=8 (4⊂8 → kalite her veride >= n=4, sweet spot; ÖLÇÜM gerekçesi yukarıda).
          - quality="max"   → donanım-tavanı (RAM'e göre 8→12→28; _hw_max_orientations).
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
    n_reason = None
    if n_orientations is None:
        if quality == "max":
            n_orientations = _hw_max_orientations(probe_capabilities().ram_bytes)
            n_reason = f"quality=max n={n_orientations} (donanim-tavani)"
        else:
            n_orientations = NFV_DEFAULT_ORIENTATIONS
            n_reason = f"n={n_orientations} (default, 4subset8 garanti)"
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
        adaptive_reason=f"nfv strategy={strategy}" + (f" | {nfv_reason}" if nfv_reason else "")
        + (f" | {n_reason}" if n_reason else ""),
    )

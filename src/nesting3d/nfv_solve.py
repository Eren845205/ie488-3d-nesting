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

# NFV oryantasyon seçimi (ÖLÇÜM 2026-06-24 c3_quality_levers + 2026-07-03 K-18):
#   * n=8 default. NEDEN SABİT-DEĞİL-AMA-SABİT: n=8 oryantasyon seti n=4'ü İÇERİR (4⊂8) → NFV greedy
#     n=8'de en az n=4 kadar iyi seçer → kalite HER veride garantili >= n=4 (Plan2'ye overfit DEĞİL,
#     küme-içerme matematiği). Sweet spot: 4→8 ~%6 kazanç.
#   * Adaptif DBLF-prob DENENDİ → NO-GO: heightmap-DBLF n-getiriyi TERS tahmin etti (Plan2 trail
#     n=4:639<n=8:645 dedi ama NFV'de n=8=522<n=4=556 İYİ) + prob 919s yavaş. DBLF NFV'yi temsil etmez.
#   * quality="max" (K-18p, 2026-07-03): 24 EKSEN-HİZALI poz (AX24 = master 0..7 + 12..27).
#     Eski ilk-N merdiveni (8→12→28) EĞİK pozları (8..11) içeriyordu — K-13/K-15 kanıtı: greedy eğik
#     pozu miyop kullanır (zarar/nötr). AX24 eğiksiz; 8⊂24 küme-içerme + K-18 ölçümü: plan2
#     n24+settle 512.5 (n8 baz 522'den −%1.8; n24 baz 520.0 = K-13 A24 kontrolüyle birebir sanity).
#     Bedel decode ~3-4× → default'a DEĞİL yalnız quality=max'a. RAM<13GB → n=8 güvenli taban
#     (AX24 16GB'de plan2 226-parçada ölçülerek doğrulandı, K-18 koşusu).
NFV_DEFAULT_ORIENTATIONS = 8
NFV_AX24 = tuple(range(8)) + tuple(range(12, 28))  # 24 eksen-hizalı (eğik 8..11 HARİÇ)


def _quality_max_orientations(ram_bytes: int):
    """quality='max' poz seti: RAM yeterse AX24 (24 eksen-hizalı, K-18), yoksa None (→ n=8).
    Sabit değil: seçim RAM'den türer; set içeriği K-13 (eğik-miyopi) + K-18 ölçümüne dayanır."""
    if ram_bytes / 1e9 >= 13:
        return NFV_AX24
    return None  # düşük RAM — güvenli taban n=8


def _voxelize_nfv(instance, pitch, floor_pitch, n_orientations, margin,
                  allowed_orientations=None):
    """coarse_to_fine._voxelize_with_fallback mantığı + margin (o fonksiyon margin geçmiyor).
    İnce-duvar parça pitch'te kaybolursa (ValueError) pitch'i kıs, floor'a kadar dene. (parts, used).
    allowed_orientations verilirse (K-18p AX24) n_orientations yok sayılır."""
    cur = pitch
    while True:
        try:
            return to_voxel_parts(instance, cur, n_orientations=n_orientations, margin=margin,
                                  allowed_orientations=allowed_orientations), cur
        except ValueError:
            nxt = cur / 1.5
            if nxt <= floor_pitch:
                return (to_voxel_parts(instance, floor_pitch, n_orientations=n_orientations,
                                       margin=margin,
                                       allowed_orientations=allowed_orientations), floor_pitch)
            cur = nxt


def solve_nfv(instance, *, plate_w_mm, plate_d_mm, fine_pitch=None,
              n_orientations=None, quality="fast", margin=1, seed=42, force=None,
              fine_settle=True) -> CoarseToFineResult:
    """NFV cavity decode → CoarseToFineResult. force: best_decode strateji zorla (test/debug).

    fine_settle=True (default): K-17 pozisyon-koruyan fine z-kompaksiyon post-pass'i —
    kazanan layout used_pitch/4'te yeniden oturtulur, kuantizasyon vergisi geri alınır
    (ölçüm: plan3 +%1.6 / plan2 +%1.1 / plan1 +%0.4). Kalite yönü TEK TARAFLI: yükseklik
    iyileşmezse (veya bellek/hata) coarse sonucu AYNEN korunur → default-on güvenli.

    fine_pitch=None (varsayılan) → NFV-farkında pitch otomatik seçilir (suggest_nfv_pitch):
    parçayı kaybetmeyen EN KABA güvenli pitch + bellek/plaka guard. Açık pitch → opt-in override.

    n_orientations seçimi:
      * Açık int verilirse o kullanılır.
      * None (varsayılan) → quality'ye göre:
          - quality="fast"  → n=8 (4⊂8 → kalite her veride >= n=4, sweet spot; ÖLÇÜM gerekçesi yukarıda).
          - quality="max"   → AX24: 24 eksen-hizalı poz, eğiksiz (K-18p; RAM<13GB → n=8 taban).
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
    allowed_orients = None
    if n_orientations is None:
        if quality == "max":
            allowed_orients = _quality_max_orientations(probe_capabilities().ram_bytes)
            if allowed_orients is not None:
                n_orientations = len(allowed_orients)
                n_reason = f"quality=max AX24 n={n_orientations} (24 eksen-hizali, K-18)"
            else:
                n_orientations = NFV_DEFAULT_ORIENTATIONS
                n_reason = f"quality=max ama RAM<13GB -> n={n_orientations} guvenli taban"
        else:
            n_orientations = NFV_DEFAULT_ORIENTATIONS
            n_reason = f"n={n_orientations} (default, 4subset8 garanti)"
    parts, used_pitch = _voxelize_nfv(instance, fine_pitch, fine_pitch, n_orientations, margin,
                                      allowed_orientations=allowed_orients)
    nx, ny = int(plate_w_mm // used_pitch), int(plate_d_mm // used_pitch)

    _, raw, strategy = best_decode(parts, nx, ny, pitch=used_pitch, force=force)

    # REPLAY → Bin3D (tek kaynak: Placement3D + heightmap). TAM (x,y,z), drop YOK → cavity korunur.
    bin3d = Bin3D(plate_w_mm, plate_d_mm, used_pitch)
    parts_by_id = {p.id: p for p in parts}
    for (pid, oi, x, y, z) in raw:
        bin3d.place(parts_by_id[pid], oi, x, y, z)

    # K-17 fine-settle post-pass: kuantizasyon vergisini geri al (yalnız iyileştirirse).
    settle_note = None
    result_pitch = used_pitch
    if fine_settle:
        from src.nesting3d.fine_settle import fine_settle_raw
        s = fine_settle_raw(raw, parts_by_id,
                            plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                            pitch=used_pitch, margin=margin,
                            h_coarse_mm=bin3d.max_height_mm())
        if s is not None:
            fine_bin = Bin3D(plate_w_mm, plate_d_mm, s.fine_pitch)
            for (pid, oi, xf, yf, zf) in s.raw_fine:
                fine_bin.place(s.fine_parts[pid], oi, xf, yf, zf)
            settle_note = (f"settle {bin3d.max_height_mm():.1f}->"
                           f"{fine_bin.max_height_mm():.1f}mm @{s.fine_pitch}mm")
            bin3d, parts_by_id, result_pitch = fine_bin, s.fine_parts, s.fine_pitch
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
        winning_config="nfv", coarse_height_mm=h, coarse_pitch=used_pitch,
        fine_pitch=result_pitch,  # settle kabul edildiyse used_pitch/scale — GLB/export bu pitch'le hizalanır
        coarse_time_s=0.0, fine_time_s=elapsed, n_placed=len(bin3d.placements),
        tune_result=tune_result, fine_voxel_parts=parts_by_id, fine_angle_used=False,
        adaptive_reason=f"nfv strategy={strategy}" + (f" | {nfv_reason}" if nfv_reason else "")
        + (f" | {n_reason}" if n_reason else "")
        + (f" | {settle_note}" if settle_note else ""),
    )

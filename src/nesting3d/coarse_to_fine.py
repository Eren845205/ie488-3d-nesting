"""coarse_to_fine.py — Coarse-to-fine nesting hızlandırma katmani.

Algoritma ozeti
---------------
1. COARSE: instance'i kaba pitch ile voxelize et, tune() ile tum algoritma
   portfoyunu kos.  Kazanan coarse cozumden SIRA + ORYANTASYON cikart.
2. FINE: instance'i ince pitch ile yeniden voxelize et, coarse sirayi ve
   coarse oryantasyon indekslerini koruyarak place_in_order ile tek geciste
   yerlesim yap.

Hiz kazanimi: arama (tune) kaba voxel uzayinda yapilir (ucuz), final
kalitesi ince cozunurlukle belirlenir.

Deterministik: ayni (instance, pitchler, budget, seed) -> ayni sonuc.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import place_in_order
from src.nesting3d.instances.format import NestingInstance, to_voxel_parts
from src.nesting3d.tuner import tune


# ---------------------------------------------------------------------------
# Sonuc dataclass
# ---------------------------------------------------------------------------


@dataclass
class CoarseToFineResult:
    """solve_coarse_to_fine cikti dataclass'i.

    Fields
    ------
    placements      : Fine (ince) cozunurluklu Placement3D listesi.
    bin3d           : Fine Bin3D durumu (yerlesim sonrasi).
    height_mm       : Fine max_height_mm (minimize edilen hedef).
    density         : Fine doluluk orani (0..1).
    winning_config  : Coarse tuner'in kazanan konfig adi.
    coarse_height_mm: Coarse kazananin height_mm degeri (karsilastirma icin).
    coarse_pitch    : Coarse voxelizasyon adimi (mm).
    fine_pitch      : Fine voxelizasyon adimi (mm).
    coarse_time_s   : Coarse arama suresi (saniye).
    fine_time_s     : Fine yerlesim suresi (saniye).
    n_placed        : Yerlestirilmis parca sayisi.
    tune_result     : Coarse TuneResult (tuner kiyas tablosu/baseline icin).
    fine_voxel_parts: Fine voxel parcalari {id: VoxelPart} (3D onizleme icin).
    """

    placements: List[Placement3D]
    bin3d: Bin3D
    height_mm: float
    density: float
    winning_config: str
    coarse_height_mm: float
    coarse_pitch: float
    fine_pitch: float
    coarse_time_s: float
    fine_time_s: float
    n_placed: int
    tune_result: Any = None
    fine_voxel_parts: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ana arayuz
# ---------------------------------------------------------------------------


def solve_coarse_to_fine(
    instance: NestingInstance,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    coarse_pitch: float,
    fine_pitch: float,
    budget: int = 70,
    seed: int = 42,
    menu: Optional[Dict[str, Any]] = None,
) -> CoarseToFineResult:
    """Coarse-to-fine iki asamali nesting coz.

    Asama 1 — COARSE
    ~~~~~~~~~~~~~~~~
    Instance'i coarse_pitch ile voxelize et.  tune() ile tum algoritma
    portfoyunu (veya menu varsa o menudeki konfigleri) kos.  Kazanan
    SolveResult'tan parca sirasini (order_ids) ve oryantasyon indekslerini
    (orient_map) cikart.

    Asama 2 — FINE
    ~~~~~~~~~~~~~~
    Instance'i fine_pitch ile yeniden voxelize et.  Coarse'dan gelen siray
    ve oryantasyonlari kullanarak place_in_order ile tek geciste yerlesim
    yap.  Density hesabi bin3d.packing_density() ile yapilir.

    Parametreler
    ------------
    instance        : Cozulecek NestingInstance.
    plate_w_mm      : Tabla genisligi (mm).
    plate_d_mm      : Tabla derinligi (mm).
    coarse_pitch    : Kaba voxel adimi (mm) — arama icin.
    fine_pitch      : Ince voxel adimi (mm) — final kalitesi icin.
    budget          : Her konfig icin iterasyon sayisi.
    seed            : Deterministik tohum.
    menu            : Opsiyonel ozel tune menüsü; None ise build_menu() kullanilir.

    Returns
    -------
    CoarseToFineResult
    """
    # ------------------------------------------------------------------
    # Asama 1: COARSE arama
    # ------------------------------------------------------------------
    t0 = time.perf_counter()

    coarse_parts = to_voxel_parts(instance, coarse_pitch)

    def coarse_factory() -> Bin3D:
        return Bin3D(plate_w_mm, plate_d_mm, coarse_pitch, z_clearance=1)

    tune_result = tune(
        coarse_parts,
        coarse_factory,
        budget=budget,
        seed=seed,
        menu=menu,
    )

    coarse_time_s = time.perf_counter() - t0
    winner = tune_result.result

    # Coarse kazananindan sira ve oryantasyon cikar
    order_ids: List[str] = [p.part_id for p in winner.placements]
    orient_map: Dict[str, int] = {
        p.part_id: p.orientation_idx for p in winner.placements
    }

    # ------------------------------------------------------------------
    # Asama 2: FINE yerlesim
    # ------------------------------------------------------------------
    t1 = time.perf_counter()

    fine_parts = to_voxel_parts(instance, fine_pitch)
    fine_by_id: Dict[str, Any] = {p.id: p for p in fine_parts}

    # Coarse sirasini fine parçalara uygula; bilinmeyen id'leri atla (guvenlik)
    ordered_fine = [
        fine_by_id[pid]
        for pid in order_ids
        if pid in fine_by_id
    ]

    fine_bin = Bin3D(plate_w_mm, plate_d_mm, fine_pitch, z_clearance=1)

    def orientation_for(idx: int, part: Any) -> tuple:
        oi = orient_map.get(part.id, 0)
        return (oi,)

    fine_placements = place_in_order(ordered_fine, fine_bin, orientation_for)

    fine_time_s = time.perf_counter() - t1

    # ------------------------------------------------------------------
    # Metrikler
    # ------------------------------------------------------------------
    height_mm = fine_bin.max_height_mm()
    density = fine_bin.packing_density()

    return CoarseToFineResult(
        placements=fine_placements,
        bin3d=fine_bin,
        height_mm=height_mm,
        density=density,
        winning_config=tune_result.winning_config_name,
        coarse_height_mm=winner.height_mm,
        coarse_pitch=coarse_pitch,
        fine_pitch=fine_pitch,
        coarse_time_s=coarse_time_s,
        fine_time_s=fine_time_s,
        n_placed=len(fine_placements),
        tune_result=tune_result,
        fine_voxel_parts=fine_by_id,
    )

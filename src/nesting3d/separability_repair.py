# -*- coding: utf-8 -*-
"""separability_repair.py — R1: NFV kilit-tahliye post-pass (üretim).

A2 (2026-07-09) kilit metriği 5-yön sıralı söküm oldu; NFV yerleşimleri
kavite kullandığı için bir kısım parça 5-yönde de kilitli çıkabiliyor
(plan3 @yeni-kurallar: 20/109). Bu modül yerleşimi LEGAL'e onarır:

  döngü (max_rounds):
    1) check_separability_5dir → kilit yoksa BİTTİ
    2) kilitli parçalar sahneden çıkarılır (evict)
    3) kalan sahne Bin3D'ye AYNEN oynatılır (exact place; no-go mühürlü)
    4) 2. turdan itibaren taban sahne tavanına zorlanır — dblf'in kavite
       boşluklarına geri sokup yeni kilit üretmesi engellenir (toz yatağında
       askıda parça SLS'te meşru; iç-içe yerleşimin dayandığı zemin aynı)
    5) tahliye edilenler dblf ile yeniden yerleştirilir (parçaların dilate'li
       MEVCUT grid'leri kullanılır → clearance garantisi aynen taşınır;
       fine-settle sonrası orientations SEYREK olabilir — yalnız dolu
       indeksler denenir, K-29 dersi)

Sonuç tek taraflı DEĞİL (yükseklik artabilir) — çağıran, ham/legal ikisini
de bilir ve raporlar; amaç legallik, süsleme değil. İlk saha kanıtı:
scripts/k29_kilit_tahliye.py (K-29 probu).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import place_in_order


@dataclass
class RepairResult:
    placements: List[Placement3D]
    n_locked_before: int
    n_locked_after: int
    rounds_used: int
    height_mm: float
    repaired: bool           # True = en az bir tahliye turu kosuldu
    note: Optional[str] = None


def _dolu_indeksler(part) -> List[int]:
    return [k for k, o in enumerate(part.orientations) if o is not None]


def _yukseklik_mm(placements: Sequence[Placement3D], parts_by_id: Dict,
                  pitch: float) -> float:
    if not placements:
        return 0.0
    return max(
        (p.z + parts_by_id[p.part_id].orientations[p.orientation_idx]
         .grid.shape[2]) for p in placements) * float(pitch)


def repair_separability(
    placements: Sequence[Placement3D],
    parts_by_id: Dict,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    pitch: float,
    no_go_mask: Optional[np.ndarray] = None,
    max_rounds: int = 3,
) -> RepairResult:
    """5-yön kilitleri tahliye edip yerleşimi A2-legal'e onar (R1)."""
    pls = list(placements)
    rapor0 = check_separability_5dir(pls, parts_by_id)
    if rapor0.n_locked == 0:
        return RepairResult(pls, 0, 0, 0,
                            _yukseklik_mm(pls, parts_by_id, pitch), False)

    n_once = rapor0.n_locked
    tur = 0
    for tur in range(1, max_rounds + 1):
        rapor = check_separability_5dir(pls, parts_by_id)
        if rapor.n_locked == 0:
            break
        kilitli = {pid for grup in rapor.locked_groups for pid in grup}
        kalan = [p for p in pls if p.part_id not in kilitli]
        b = Bin3D(plate_w_mm, plate_d_mm, pitch, z_clearance=0,
                  no_go_mask=no_go_mask)
        for p in kalan:
            b.place(parts_by_id[p.part_id], p.orientation_idx, p.x, p.y, p.z)
        if tur >= 2:
            serbest = (~no_go_mask if no_go_mask is not None
                       and no_go_mask.any() else np.ones_like(b.height, bool))
            tavan = int(b.height[serbest].max()) if serbest.any() else 0
            b.height[serbest] = np.maximum(b.height[serbest], tavan)
        tahliye = [parts_by_id[pid] for pid in sorted(kilitli)]
        try:
            yeni = place_in_order(tahliye, b,
                                  lambda i, part: _dolu_indeksler(part))
        except AssertionError as e:
            return RepairResult(pls, n_once,
                                check_separability_5dir(pls, parts_by_id).n_locked,
                                tur, _yukseklik_mm(pls, parts_by_id, pitch),
                                True, note=f"tahliye yerlesemedi: {e}")
        pls = kalan + list(yeni)

    son = check_separability_5dir(pls, parts_by_id)
    return RepairResult(pls, n_once, son.n_locked, tur,
                        _yukseklik_mm(pls, parts_by_id, pitch), True)

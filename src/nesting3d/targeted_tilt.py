# -*- coding: utf-8 -*-
"""targeted_tilt — K-56b: tilt-zorunlu parcaya HEDEFLI egik poz havuzu.

Mekanizma (K-56a kaniti, 2026-07-18: plan1 uretim yolu 302.8 -> 202.2 LEGAL
serhsiz, -%33.2; eski dblf@1.0 kaniti 260 -> 141): master eksen-hizali set
(AX24 dahil) tilt-zorunlu parcayi DIK dikmek zorunda kalir; dusuk-aci x/y
tilt pozlari (5..85 @5) parca yuksekligini kirar. Filtre uclusu:
  (1) grid'e sigma (fp <= plaka),
  (2) no-go'suz plakaya GEOMETRIK yerlesebilirlik (dikdortgen serit testi —
      adaptive_params._tilt_zorunlu_parca ile AYNI formul; 2026-07-09 dersi:
      "grid'e sigan ama yerlesemeyen duz poz esigi zehirler"),
  (3) z-uzantisi < yerlesebilen-default-pozlarin min z'si.
Kabul edilen rotasyonlar solve_coarse_to_fine(extra_rot_overrides=...) ile
default poz setinin SONUNA eklenir (K-56a zinciri; indeks tutarli).

Cagiranlar (eval_gate + demo_pipeline) AYNI fonksiyonu kullanir (K-53d
uretim-parite deseni). Hata/bulunamama/kazanan-poz-yok -> None (konservatif:
cagiran tilt'siz mevcut yolla devam eder).
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def _yerlesebilir(fp_w_mm: float, fp_d_mm: float, plate_w_mm: float,
                  plate_d_mm: float, no_go_bounds) -> bool:
    """(W,D) ayak izi no-go'lu plakada EN AZ BIR konuma sigar mi?

    adaptive_params._tilt_zorunlu_parca ile ayni serit formulu (tek kaynak
    olamiyor cunku o PartSpec uzerinden tarar; formul birebir kopya + testle
    kilitli). no_go_bounds None -> yalniz plakaya sigma.
    """
    if fp_w_mm > plate_w_mm or fp_d_mm > plate_d_mm:
        return False
    if no_go_bounds is None:
        return True
    try:
        (x1, y1), (x2, y2) = no_go_bounds
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    except Exception:
        return True  # cozulmeyen format -> konservatif: engel sayma
    return bool(x1 >= fp_w_mm or x2 <= plate_w_mm - fp_w_mm
                or y1 >= fp_d_mm or y2 <= plate_d_mm - fp_d_mm)


def hedefli_tilt_overrides(instance, hedef_ad: str, *, plate_w_mm: float,
                           plate_d_mm: float, no_go_bounds=None,
                           fine_pitch: float, clearance_mm: float = 0.0,
                           acilar=None) -> Optional[dict]:
    """Hedef parcaya kabul-filtresinden gecen tilt rotasyonlari uret.

    Doner: {hedef_ad: [4x4 rot matrisi, ...]} (extra_rot_overrides sozlesmesi)
    veya None (parca yok / mesh uretilemedi / hicbir poz kazanamadi).
    Deterministik: sabit eksen+aci sirasi, sabit filtre.
    """
    import trimesh
    from src.nesting3d.coarse_to_fine import (cap_margin_to_plate,
                                              clearance_to_voxels)
    from src.nesting3d.instances.format import _make_mesh
    from src.nesting3d.voxelize import voxelize_part

    if acilar is None:
        acilar = range(5, 90, 5)

    hedef = None
    for p in getattr(instance, "parts", []) or []:
        if str(getattr(p, "name", "")) == str(hedef_ad):
            hedef = p
            break
    if hedef is None:
        return None
    try:
        mesh = _make_mesh(hedef)
    except Exception:
        return None

    margin, _zc = clearance_to_voxels(clearance_mm, fine_pitch)
    margin, _ = cap_margin_to_plate(margin, fine_pitch, instance,
                                    plate_w_mm, plate_d_mm)
    nx, ny = int(plate_w_mm // fine_pitch), int(plate_d_mm // fine_pitch)

    # z-esigi: default n4 setinde YERLESEBILEN pozlarin min z'si (yerlesemeyen
    # duz poz esigi zehirlemez — 2026-07-09 dersi)
    try:
        vp4 = voxelize_part(str(hedef_ad), mesh, fine_pitch,
                            n_orientations=4, margin=margin, method="slice")
    except Exception:
        return None
    z_esik = None
    for o in vp4.orientations:
        fw_mm = o.grid.shape[0] * fine_pitch
        fd_mm = o.grid.shape[1] * fine_pitch
        if _yerlesebilir(fw_mm, fd_mm, plate_w_mm, plate_d_mm, no_go_bounds):
            z = int(o.grid.shape[2])
            if z_esik is None or z < z_esik:
                z_esik = z
    if z_esik is None:
        return None  # hicbir default poz yerlesemiyor — esik kurulamaz

    ok = []
    for eksen_vec in ([1, 0, 0], [0, 1, 0]):
        for ang in acilar:
            R = trimesh.transformations.rotation_matrix(
                np.deg2rad(float(ang)), eksen_vec)
            try:
                vp = voxelize_part(str(hedef_ad), mesh, fine_pitch,
                                   rot_matrices=[R], method="slice",
                                   margin=margin)
            except Exception:
                continue
            g = vp.orientations[0].grid
            fw_mm = g.shape[0] * fine_pitch
            fd_mm = g.shape[1] * fine_pitch
            if (g.shape[0] <= nx and g.shape[1] <= ny
                    and _yerlesebilir(fw_mm, fd_mm, plate_w_mm, plate_d_mm,
                                      no_go_bounds)
                    and g.shape[2] < z_esik):
                ok.append(R)
    return {str(hedef_ad): ok} if ok else None

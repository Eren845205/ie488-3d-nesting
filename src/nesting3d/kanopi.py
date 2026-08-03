# -*- coding: utf-8 -*-
"""kanopi.py — K-62 C1: delikli-parca DUZ-poz GERCEK-GEOMETRI no-go
fizibilitesi.

Kok sebep (PLAN_KOK_SEBEP_VE_KISIT_V2.md KS-1): bbox serit testleri
(`adaptive_params._tilt_zorunlu_parca` / `targeted_tilt._yerlesebilir`)
parcayi DOLU dikdortgen sayar. Delikli cerceve no-go kolonunu deliginin
icine alarak duz yerlesebilir (kanit: 2026-08-03 manuel-yerlesim goruntuleri
+ results/k62_delik_fizibilite*.json on-teshisi). Bu modul ayni soruyu
gercek footprint (voxel filled maskesi) ile cevaplar.

Tasarim ilkeleri:
- Mevcut kapi kararlarina DOKUNMAZ: tilt zinciri aynen kalir; cagiran taraf
  bu sonucu EK bilgi (kanopi adayi) olarak tasir. Default'ta hicbir uretim
  yolu bu modulu cagirmaz -> bit-ozdeslik yapisal (A11).
- Tetik veri-adiyla degil geometriyle: yalniz mesh + plaka + no-go girer.
- marj_mm=0 (ham geometri) default: no-go'ya temas toleransi AYRI sozlesme
  karari (hoca 2026-07-09 c9 "cok ufak girisler kabul"); cagirana acik.
- Rasterizasyon uretim voxelizer'i ile (`voxelize_part`, margin=0) yapilir —
  ayri bir geometri yolu acilmaz; azimutlar tek voxelize + np.rot90 ile
  turetilir (footprint simetrisi, ucuz ve deterministik).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Ust sinir: donen uygun-ofset listesi (telemetri/secim icin ornek yeter;
# tam tarama sayisi ayrica raporlanir).
MAX_POZ_KAYDI = 32


def duz_rot_matrisleri(mesh) -> List[np.ndarray]:
    """Parcanin DUZ (en dusuk yukseklik) durusunun 4 azimut varyanti.

    Kalinlik ekseni (bbox extents argmin) Z'ye tasinir; ardindan Rz
    0/90/180/270 uygulanir. Donen liste 4 adet 4x4 matristir. Kalinlik
    ekseni zaten Z ise taban matrisi birimdir (poz-0 paritesi).
    """
    import trimesh.transformations as tt

    ext = np.asarray(mesh.extents, dtype=float)
    k = int(np.argmin(ext))
    if k == 2:
        taban = np.eye(4)
    elif k == 0:
        taban = tt.rotation_matrix(np.pi / 2.0, [0.0, 1.0, 0.0])
    else:
        taban = tt.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0])
    return [tt.rotation_matrix(np.deg2rad(a), [0.0, 0.0, 1.0]) @ taban
            for a in (0.0, 90.0, 180.0, 270.0)]


def _nogo_penceresi_bos_mu(fp: np.ndarray, pitch: float,
                           nogo: Tuple[Tuple[float, float],
                                       Tuple[float, float]],
                           dx: float, dy: float, marj_mm: float) -> bool:
    """(dx,dy) ofsetli yerlesimde marj-genisletilmis no-go bolgesi parca
    malzemesinden bos mu? fp: [x,y] bool footprint (parca-lokal)."""
    (gx1, gy1), (gx2, gy2) = nogo
    x1, x2 = gx1 - marj_mm - dx, gx2 + marj_mm - dx
    y1, y2 = gy1 - marj_mm - dy, gy2 + marj_mm - dy
    w, d = fp.shape
    i1 = max(0, int(np.floor(x1 / pitch)))
    i2 = min(w, int(np.ceil(x2 / pitch)))
    j1 = max(0, int(np.floor(y1 / pitch)))
    j2 = min(d, int(np.ceil(y2 / pitch)))
    if i1 >= i2 or j1 >= j2:
        return True  # no-go tamamen footprint disinda
    return not fp[i1:i2, j1:j2].any()


def duz_poz_nogo_fizibilite(
    mesh,
    plate_w_mm: float,
    plate_d_mm: float,
    no_go_bounds: Optional[Tuple[Tuple[float, float], Tuple[float, float]]],
    *,
    pitch: float = 0.5,
    marj_mm: float = 0.0,
    method: str = "subdivide",
) -> Optional[Dict[str, Any]]:
    """Parcanin DUZ pozu, GERCEK geometrisiyle no-go'lu plakaya sigar mi?

    Bbox serit testinin (dolu-dikdortgen varsayimi) gercek-geometri
    karsiligi: footprint'in delik/boslugu no-go dikdortgenini tamamen
    icine alabiliyorsa duz poz MESRUDUR.

    Args:
        no_go_bounds: ((x1,y1),(x2,y2)) plaka koordinati; None -> None doner
            (kisit yok — cagiran zincir hic tetiklenmez, bit-ozdeslik).
        pitch: rasterizasyon adimi (mm). Uretim cagrisi icin 0.5 onerilir.
        marj_mm: no-go'nun her kenarina eklenen guvenlik payi (sozlesme
            karari cagiranin).
        method: voxelize_part yontemi ("subdivide" | "slice" — buyuk gercek
            STL'lerde slice hizli yol).

    Returns:
        None (no_go_bounds yoksa) veya dict:
          doluluk        : footprint dolu-oran (0..1) — delik gostergesi
          duz_kalinlik_mm: duz pozda parca yuksekligi
          pozlar         : [{rot_deg, dx_mm, dy_mm}] uygun yerlesimler
                           (MAX_POZ_KAYDI ile sinirli ornek)
          uygun_sayisi   : tum taramada uygun ofset sayisi
          taranan_sayisi : denenen (rot, dx, dy) sayisi
    """
    if no_go_bounds is None:
        return None
    from src.nesting3d.voxelize import voxelize_part

    taban_rot = duz_rot_matrisleri(mesh)[0]
    vp = voxelize_part("_kanopi_fizibilite", mesh, float(pitch),
                       margin=0, method=method, rot_matrices=[taban_rot])
    orient = vp.orientations[0]
    grid = np.asarray(orient.grid, dtype=bool)
    fp0 = grid.any(axis=2)  # [x, y] footprint
    doluluk = float(fp0.mean()) if fp0.size else 0.0
    duz_kalinlik = float(grid.shape[2]) * float(pitch)

    pozlar: List[Dict[str, float]] = []
    uygun_sayisi = 0
    taranan = 0
    for rot_k, rot_deg in enumerate((0, 90, 180, 270)):
        fp = np.rot90(fp0, rot_k)
        w_mm = fp.shape[0] * float(pitch)
        d_mm = fp.shape[1] * float(pitch)
        if w_mm > plate_w_mm or d_mm > plate_d_mm:
            continue
        dxler = np.arange(0.0, plate_w_mm - w_mm + 1e-9, float(pitch))
        dyler = np.arange(0.0, plate_d_mm - d_mm + 1e-9, float(pitch))
        for dx in dxler:
            for dy in dyler:
                taranan += 1
                if _nogo_penceresi_bos_mu(fp, float(pitch), no_go_bounds,
                                          float(dx), float(dy), marj_mm):
                    uygun_sayisi += 1
                    if len(pozlar) < MAX_POZ_KAYDI:
                        pozlar.append({
                            "rot_deg": float(rot_deg),
                            "dx_mm": round(float(dx), 3),
                            "dy_mm": round(float(dy), 3),
                        })
    return {
        "doluluk": round(doluluk, 4),
        "duz_kalinlik_mm": round(duz_kalinlik, 3),
        "pozlar": pozlar,
        "uygun_sayisi": uygun_sayisi,
        "taranan_sayisi": taranan,
    }

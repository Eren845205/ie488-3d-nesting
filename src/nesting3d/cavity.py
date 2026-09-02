"""cavity.py — Kapali kavite (hapsolmus toz bosluğu) analizi.

DENETIM_RAPORU_2026-07-03.md #21: SLM'de ic-ice yerlesimde tamamen kapali
(disaridan erisilemez) bir boslugun ici toza hapsolur (ic toz makinede kalir,
temizlenemez). Bu modul FAZ-1: SADECE TELEMETRI/RAPOR uretir — legal/INVALID
kararina, clearance'a, separability'ye BAGLANMAZ (hoca cevabi bekleniyor,
A11/ANAYASA disiplinine gore karar-yuzeyi degistirilmeden once teyit sarti).

Algoritma
---------
1. Doluluk grid'i (occ, dolu=True/1) 1 voxel "hava" ile cevrelenir (padding).
2. Padding'ten baslayan disaridan flood-fill (6-komsuluk / yuz-komsuluk —
   scipy.ndimage.label) disaridan ERISILEBILIR bos voxelleri tek etikette
   toplar (kose/kenar komsulugu KULLANILMAZ: fiziksel toz akisi bir yuzeyden
   gecer, sadece bir koseden degil -> konservatif/dogru tercih).
3. Geriye kalan (disari-etiketiyle BAGLANMAMIS) bos voxel kumeleri = kapali
   kaviteler.

Bellek notu: grid tek `bool`/`uint8` kopyasi + padding kopyasi + int32 etiket
dizisi tutulur (scipy.ndimage.label int32 doner); ekstra kopya yaratilmaz.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Sequence

import numpy as np
from scipy import ndimage

# 3D 6-komsuluk (yuz-komsu) baglanti yapisi — kose/kenar komsulugu YOK.
_STRUCT_6 = ndimage.generate_binary_structure(3, 1)

_ZERO_RESULT_TEMPLATE: Dict[str, float] = {
    "hacim_mm3": 0.0,
    "n_bolge": 0,
    "en_buyuk_mm3": 0.0,
}


def _zero_result(sure_s: float) -> Dict[str, float]:
    out = dict(_ZERO_RESULT_TEMPLATE)
    out["sure_s"] = sure_s
    return out


def kapali_kavite_analizi(occ: np.ndarray, pitch_mm: float) -> Dict[str, float]:
    """Disaridan erisilemez (kapali) bos voxel kumelerini bul.

    Args:
        occ: 3B bool/uint8 doluluk grid'i (dolu=True/1, bos=False/0).
        pitch_mm: voxel kenar uzunlugu (mm) — hacim donusumu icin.

    Returns:
        dict: {"hacim_mm3": float, "n_bolge": int, "en_buyuk_mm3": float,
               "sure_s": float}. occ tamamen dolu veya bos ise hepsi 0
               (bos gridde disari flood-fill her seyi kapsar -> kapali kavite
               yok).

    FAZ-1 UYARI: bu fonksiyonun ciktisi legal/INVALID kararina BAGLANMAZ.
    """
    t0 = time.perf_counter()
    occ_arr = np.asarray(occ, dtype=bool)

    if occ_arr.size == 0 or occ_arr.all():
        return _zero_result(time.perf_counter() - t0)

    empty = ~occ_arr
    if not empty.any():
        return _zero_result(time.perf_counter() - t0)

    # 1 voxel hava-padding: disaridan flood-fill'in HER yuzden (grid disi =
    # hava) baslamasini garantiler; sinir kosuluna bagli ozel-durum yok.
    padded_empty = np.pad(empty, 1, mode="constant", constant_values=True)

    labels, n_labels = ndimage.label(padded_empty, structure=_STRUCT_6)
    if n_labels == 0:
        return _zero_result(time.perf_counter() - t0)

    # Padding koseleri HER ZAMAN disaridan erisilebilir bos bolgededir.
    outside_label = int(labels[0, 0, 0])

    # Padding'i geri kirp (orijinal grid koordinatlarina don).
    labels_inner = labels[1:-1, 1:-1, 1:-1]

    counts = np.bincount(labels_inner.ravel())
    # Etiket 0 = dolu bolge (ndimage.label yalniz True/bos bolgeye etiket
    # atar); disari-etiketi de kapali kavite SAYILMAZ.
    cavity_mask = np.ones(counts.shape, dtype=bool)
    cavity_mask[0] = False
    if 0 <= outside_label < cavity_mask.shape[0]:
        cavity_mask[outside_label] = False

    cavity_counts = counts[cavity_mask]
    if cavity_counts.size == 0 or cavity_counts.sum() == 0:
        return _zero_result(time.perf_counter() - t0)

    voxel_vol_mm3 = float(pitch_mm) ** 3
    hacim_mm3 = float(cavity_counts.sum()) * voxel_vol_mm3
    en_buyuk_mm3 = float(cavity_counts.max()) * voxel_vol_mm3

    return {
        "hacim_mm3": hacim_mm3,
        "n_bolge": int(np.count_nonzero(cavity_counts)),
        "en_buyuk_mm3": en_buyuk_mm3,
        "sure_s": time.perf_counter() - t0,
    }


def kaba_havuz(occ: np.ndarray, f: int) -> np.ndarray:
    """Bool doluluk grid'ini f x f x f bloklarla ANY-havuzla (kaba pitch).

    Bellek butcesi asilan buyuk gridlerde kapali-kavite TELEMETRISI icin
    (2026-09-02 p3-max dersi: 0,5 mm'de ~540M voxel label -> 16,9 GB, 55 dk
    cozum kaybi). ANY-havuz dolu=konservatif (ince duvarlar korunur, ince
    bosluklar kapanabilir -> kavite hacmi UST tahmin). Kenar f'nin katina
    False-pad (hava) ile tamamlanir. f<=1 -> aynen doner.
    """
    f = int(f)
    if f <= 1:
        return occ
    occ = np.asarray(occ, dtype=bool)
    pad = [(0, (-d) % f) for d in occ.shape]
    if any(p1 for _, p1 in pad):
        occ = np.pad(occ, pad, mode="constant", constant_values=False)
    nx, ny, nz = (d // f for d in occ.shape)
    return occ.reshape(nx, f, ny, f, nz, f).any(axis=(1, 3, 5))


def occ_grid_from_placements(placements: Sequence[object], parts,
                             nx: int, ny: int,
                             nz: Optional[int] = None) -> np.ndarray:
    """Placement3D listesi + VoxelPart kaynagindan tam 3B bin doluluk grid'i.

    accessibility.placed_voxels_from_placements ile AYNI erisim deseni
    (part.orientations[pl.orientation_idx].grid, (x,y,z) offset) — burada
    tam 3B OR-birlesimi olarak kurulur (accessibility yalniz sutun profili
    tutar, kapali-kavite icin TAM grid gerekir).

    Args:
        placements: Placement3D benzeri nesneler (part_id, x, y, z,
            orientation_idx alanlariyla).
        parts: {id: VoxelPart} sozlugu veya VoxelPart listesi.
        nx, ny: bin taban boyutlari (voxel).
        nz: bin yukseklik boyutu (voxel); None ise placement'lardan turetilir.

    Returns:
        bool (nx, ny, nz) grid — dolu=True.
    """
    lookup = parts if isinstance(parts, dict) else {p.id: p for p in parts}

    if nz is None:
        nz = 1
        for pl in placements:
            grid = lookup[pl.part_id].orientations[pl.orientation_idx].grid
            nz = max(nz, int(pl.z) + int(grid.shape[2]))

    occ = np.zeros((int(nx), int(ny), int(nz)), dtype=bool)
    for pl in placements:
        grid = lookup[pl.part_id].orientations[pl.orientation_idx].grid
        gx, gy, gz = grid.shape
        x0, y0, z0 = int(pl.x), int(pl.y), int(pl.z)
        x1, y1, z1 = x0 + gx, y0 + gy, z0 + gz
        # Bin sinirlarini asan pay (dilation/tilt kaynakli) sessizce kirpilir
        # -> kapali-kavite RAPORU icin konservatif (dis siniri asan kisim
        # zaten "disari acik" sayilirdi).
        cx0, cx1 = max(0, x0), min(occ.shape[0], x1)
        cy0, cy1 = max(0, y0), min(occ.shape[1], y1)
        cz0, cz1 = max(0, z0), min(occ.shape[2], z1)
        if cx0 >= cx1 or cy0 >= cy1 or cz0 >= cz1:
            continue
        occ[cx0:cx1, cy0:cy1, cz0:cz1] |= grid[
            cx0 - x0:cx1 - x0, cy0 - y0:cy1 - y0, cz0 - z0:cz1 - z0]
    return occ

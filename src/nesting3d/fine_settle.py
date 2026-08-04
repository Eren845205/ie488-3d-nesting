"""fine_settle.py — K-17: pozisyon-koruyan FINE z-kompaksiyon post-pass (üretim).

NFV çözümü used_pitch (örn. 2.0mm) hücrelerinde kuantizedir; her istif
arayüzünde (a) bir-sonraki-hücre-sınırına yuvarlama + (b) konservatif
yüzey-sarmanın ~1 hücrelik şişirmesi birikir. Bu modül kazanan layout'un
POZİSYONLARINI KORUYARAK kullanılan (tip, oryantasyon) çiftlerini
used_pitch/scale'de yeniden voxelize eder ve parçaları z'de temasa kadar
oturtur — kuantizasyon vergisini geri alır.

ÖLÇÜM (K-17, scripts/c1_fine_zcompact.py, 2026-07-03): plan3 844→830.5
(+%1.6) · plan2 522→516 (+%1.1) · plan1 116→115.5 (+%0.4); üçü de ≥0.

Tasarım garantileri:
  * FFT YOK → NFV'nin ince-pitch bellek duvarına (H-11) takılmaz; bellek
    yalnız fine occupancy grid'i (~yüzlerce MB, pre-flight'lı).
  * Kalite yönü TEK TARAFLI: yükseklik iyileşmezse None döner, çağıran
    coarse sonucu aynen korur. Herhangi bir hata da None (graceful skip).
  * Non-penetrasyon garantisi TİPİ değişmez: konservatif voxel modeller
    (fine'da daha az şişkin) + açık çakışma kontrolü.
  * KRİTİK sıra dersi (K-17): parçalar önce ORİJİNAL z'lerine konur,
    alçaltma YALNIZ herkes yerleşikken (settle) yapılır — iç-içe geçmiş
    parçalarda (per-kolon komşuluk ≠ min-z sırası) erken alçaltma sonra
    gelenin yerini işgal eder (plan3'te -123mm'lik bozulmayı bu ders yakaladı).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.nesting3d.voxelize import VoxelPart, voxelize_part

# Fine occupancy grid'inin bellek tavanı (bool bayt). Aşarsa scale yarıya
# düşürülür (4→2); o da aşarsa settle atlanır (None). Donanım-türevi değil
# güvenli sabit: 16GB laptop'ta ~1.4GB grid + fine parça grid'leri rahat.
MEM_BUDGET_BYTES: int = 1_500_000_000
DEFAULT_SCALE: int = 4          # fine = used_pitch / 4 (ölçümler bu oranla)
MAX_SETTLE_SWEEPS: int = 20     # yakınsama emniyet tavanı (ölçümde 1-7 yetti)
_CEILING_WINDOW_MM: float = 25.0  # tavana bu kadar yakın parçaya xy-jitter dene


@dataclass
class SettleResult:
    fine_pitch: float
    raw_fine: List[Tuple[str, int, int, int, int]]   # (pid, oi, xf, yf, zf)
    fine_parts: Dict[str, VoxelPart]                 # pid -> fine VoxelPart (padded)
    height_mm: float


def _padded_voxel_part(coarse: VoxelPart, oi: int, fine_orient) -> VoxelPart:
    """Fine VoxelPart: orientations listesi coarse ile AYNI uzunlukta ama yalnız
    kullanılan oi dolu (diğerleri None). Tüm downstream tüketiciler
    (Bin3D.place, export_stl.placed_meshes, GLB) placement.orientation_idx ile
    eriştiğinden bu yeterli; başka indekse erişim None ile GÜRÜLTÜLÜ kırılır
    (sessiz yanlış geometri yerine)."""
    orients = [None] * len(coarse.orientations)
    orients[oi] = fine_orient
    return VoxelPart(
        id=coarse.id, name=coarse.name, mesh=coarse.mesh,
        orientations=orients, volume_voxels=int(fine_orient.voxel_count),
        qty_of_model=coarse.qty_of_model, display_mesh=coarse.display_mesh,
    )


def fine_settle_raw(
    raw: List[Tuple[str, int, int, int, int]],
    parts_by_id: Dict[str, VoxelPart],
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    pitch: float,
    margin: int,
    h_coarse_mm: float,
    z_dilate: int = 0,
    scale: int = DEFAULT_SCALE,
    mem_budget_bytes: int = MEM_BUDGET_BYTES,
    no_go_bounds=None,
    onyuk_raw=None,
) -> Optional[SettleResult]:
    """NFV raw yerleşimini fine'da oturt; iyileşme yoksa/başarısızsa None.

    raw: best_decode çıktısı [(pid, oi, x, y, z)] — used_pitch hücreleri.
    margin: coarse voxelize'ın xy-dilation hücre sayısı (mm-eşdeğerlik için
    fine'da margin*scale kullanılır → yanal boşluk garantisi birebir korunur).
    z_dilate: coarse tek-taraflı z-dilation hücre sayısı (EVAL-1 NFV clearance);
    fine'da z_dilate*scale kullanılır → dikey boşluk garantisi mm-uzayda korunur.
    0 (default) -> z-dilation yok (mevcut settle davranışı BİT-ÖZDEŞ).

    onyuk_raw (K-62 v12b): SABIT nesneler (3D pin) — raw ile ayni format
    [(pid, oi, x, y, z)], parcalari parts_by_id'de. Fine occ'a HAREKETSIZ
    damgalanir (tasima/oturtma listesine girmez); hareketli parcalar
    pinlerin etrafina oturur. Damga hareketli parcalarla AYNI dilation'i
    tasir (cift-tarafli ayrim, konservatif). None (default) = BIT-OZDES.
    """
    if not raw:
        return None
    try:
        return _settle(raw, parts_by_id, plate_w_mm, plate_d_mm, pitch,
                       margin, h_coarse_mm, scale, mem_budget_bytes, z_dilate,
                       no_go_bounds, onyuk_raw)
    except MemoryError:
        return None   # bellek sıkışması → coarse sonucu korunur
    except Exception:
        return None   # her tür beklenmedik hata = graceful skip (kalite korunur)


def _settle(raw, parts_by_id, plate_w_mm, plate_d_mm, pitch, margin,
            h_coarse_mm, scale, mem_budget_bytes, z_dilate=0,
            no_go_bounds=None, onyuk_raw=None):
    # --- bellek pre-flight: occ grid boyutu bütçeyi aşarsa scale'i kıs/vazgeç
    while scale >= 2:
        fine = pitch / scale
        nxf, nyf = int(plate_w_mm // fine), int(plate_d_mm // fine)
        nzf = int(h_coarse_mm / fine * 1.2) + 64
        if float(nxf) * nyf * nzf <= mem_budget_bytes:
            break
        scale //= 2
    else:
        return None
    if scale < 2:
        return None

    # --- kullanılan (tip, oi) çiftlerini fine'da tek-oryantasyon voxelize
    #     (rot matrisi coarse orientation'dan — master-indeks varsayımı yok)
    fine_orients = {}   # (name, oi) -> fine Orientation
    for pid, oi, _x, _y, _z in raw:
        part = parts_by_id[pid]
        key = (part.name, oi)
        if key in fine_orients:
            continue
        vp = voxelize_part(part.name, part.mesh, fine,
                           rot_matrices=[part.orientations[oi].rot_matrix],
                           margin=margin * scale, z_dilate=z_dilate * scale,
                           method="slice")
        fine_orients[key] = vp.orientations[0]

    occ = np.zeros((nxf, nyf, nzf), dtype=bool)
    if no_go_bounds is not None:
        # NO-GO (2026-07-09): fine grid'de de TAM yukseklik muhur — jitter
        # halkalari parcayi yasak bolgeye mm-alti kaydiramasin.
        from src.nesting3d.bin3d import Bin3D
        _m = Bin3D.no_go_mask_from_bounds(no_go_bounds, plate_w_mm,
                                          plate_d_mm, fine)
        if _m.shape == (nxf, nyf) and _m.any():
            occ[_m, :] = True

    # K-62 v12b: SABIT on-yukler (3D pin) fine occ'a HAREKETSIZ damgalanir.
    # Damga hareketlilerle ayni dilation'i tasir (margin/z_dilate * scale);
    # dilated origin xy'de -margin*scale kayar (pin konumu margin-0 bbox),
    # damga kirpmali. pid-anahtarli ayri sozluk: ayni (name, oi) anahtarli
    # HAREKETLI kopyalarla (pin rot'u farkli grid) cakismasin.
    if onyuk_raw:
        for pid, oi, x, y, z in onyuk_raw:
            part = parts_by_id[pid]
            vp = voxelize_part(part.name, part.mesh, fine,
                               rot_matrices=[part.orientations[oi].rot_matrix],
                               margin=margin * scale,
                               z_dilate=z_dilate * scale, method="slice")
            g = vp.orientations[0].grid
            xs = x * scale - margin * scale
            ys = y * scale - margin * scale
            zs = z * scale
            fw, fd, fh = g.shape
            x0, y0, z0 = max(0, xs), max(0, ys), max(0, zs)
            x1 = min(nxf, xs + fw); y1 = min(nyf, ys + fd)
            z1 = min(nzf, zs + fh)
            if x1 <= x0 or y1 <= y0 or z1 <= z0:
                continue
            occ[x0:x1, y0:y1, z0:z1] |= g[x0 - xs:x1 - xs,
                                          y0 - ys:y1 - ys,
                                          z0 - zs:z1 - zs]

    def feasible(g, x, y, z):
        fw, fd, fh = g.shape
        if x < 0 or y < 0 or z < 0 or x + fw > nxf or y + fd > nyf or z + fh > nzf:
            return False
        return not np.logical_and(occ[x:x + fw, y:y + fd, z:z + fh], g).any()

    def lowest_z(g, x, y, z_start):
        if not feasible(g, x, y, z_start):
            return None
        z = z_start
        while z > 0 and feasible(g, x, y, z - 1):
            z -= 1
        return z

    def place(g, x, y, z):
        occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]] |= g

    def unplace(g, x, y, z):
        occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]] &= ~g

    # hücre-içi jitter halkaları (±(scale-1)): fine örnekleme coarse'un
    # kaçırdığı yüzeyi işaretleyebilir → "fine ⊆ coarse" mm-uzayda garantili
    # değil; sığmayan parça önce yana kaydırılır, son çare yukarı.
    jit = [(dx, dy) for r in range(1, scale)
           for dx in range(-r, r + 1) for dy in range(-r, r + 1)
           if max(abs(dx), abs(dy)) == r]

    # --- 1. geciş: HERKES ORİJİNAL z'sine (alçaltma YOK — K-17 dersi)
    grids = {}   # i -> fine grid
    state = {}   # i -> (xf, yf, zf)
    for i, (pid, oi, x, y, z) in enumerate(raw):
        g = fine_orients[(parts_by_id[pid].name, oi)].grid
        grids[i] = g
        xf, yf, zf = x * scale, y * scale, z * scale
        fw, fd, _fh = g.shape
        xf = min(xf, max(0, nxf - fw))
        yf = min(yf, max(0, nyf - fd))
        if not feasible(g, xf, yf, zf):
            for dx, dy in jit:
                if feasible(g, xf + dx, yf + dy, zf):
                    xf, yf = xf + dx, yf + dy
                    break
            else:
                while not feasible(g, xf, yf, zf):
                    zf += 1
                    if zf >= nzf:
                        return None   # yerleştirilemedi → settle vazgeç
        place(g, xf, yf, zf)
        state[i] = (xf, yf, zf)

    # --- settle: yakınsayana kadar yeniden-oturt (herkes yerleşikken)
    n_pass = 0
    while True:
        n_pass += 1
        moved = 0
        h_now = max(state[i][2] + grids[i].shape[2] for i in state) * fine
        for i in sorted(state, key=lambda j: state[j][2]):
            g = grids[i]
            xf, yf, zf = state[i]
            near_ceiling = (zf + g.shape[2]) * fine >= h_now - _CEILING_WINDOW_MM
            unplace(g, xf, yf, zf)
            zb = lowest_z(g, xf, yf, zf)
            best = (xf, yf, zb if zb is not None else zf)
            if near_ceiling:
                for dx, dy in jit:
                    if best[2] == 0:
                        break
                    zb2 = lowest_z(g, xf + dx, yf + dy, best[2] - 1)
                    if zb2 is not None and zb2 < best[2]:
                        best = (xf + dx, yf + dy, zb2)
            place(g, *best)
            if best[2] < zf:
                moved += 1
            state[i] = best
        if moved == 0 or n_pass >= MAX_SETTLE_SWEEPS:
            break

    h_fine = max(state[i][2] + grids[i].shape[2] for i in state) * fine
    if h_fine >= h_coarse_mm - 1e-9:
        return None   # kazanç yok → coarse korunur

    # --- çıktı: fine placements + padded fine VoxelPart'lar
    fine_parts: Dict[str, VoxelPart] = {}
    raw_fine = []
    for i, (pid, oi, _x, _y, _z) in enumerate(raw):
        part = parts_by_id[pid]
        if pid not in fine_parts:
            fine_parts[pid] = _padded_voxel_part(
                part, oi, fine_orients[(part.name, oi)])
        xf, yf, zf = state[i]
        raw_fine.append((pid, oi, xf, yf, zf))
    return SettleResult(fine_pitch=fine, raw_fine=raw_fine,
                        fine_parts=fine_parts, height_mm=h_fine)

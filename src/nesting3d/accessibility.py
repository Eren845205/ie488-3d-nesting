"""accessibility.py — F2 erisilebilirlik / sokulebilirlik denetimi (v1).

Bir 3D nesting yerlesimi bittikten SONRA calisan bagimsiz bir post-check
kutuphanesi: "her parca tek tek +Z yonunde cekilip cikarilabilir mi?"
Cikarilamayan (birbirine kilitlenmis / interlocked) parca kumelerini raporlar.

Yaklasim: SSP (SIGGRAPH 2023) 'interlocking detection' fikrinin TEK EKSENLI,
voxel-tabanli hali. Parcalar yalniz +Z yonunde ELLE (rigid) yukari cekilir.

v1 SADECE RAPOR uretir — yerlesimi DEGISTIRMEZ, reddetmez. Entegrasyon
(cozucu icine baglama) ayri dalga.

Algoritma (kaldirma-sirasi simulasyonu)
---------------------------------------
Her turda, kalan parcalardan +Z'ye cekildiginde hicbir kalan parcayla
carpismayanlar "cikarilabilir" isaretlenir ve sahneden silinir. Hicbir parca
cikamiyorsa kalan kume = kilitli grup(lar).

+Z carpisma testi (sutun-bazli, voxel-vektorize)
------------------------------------------------
P parcasi +Z'ye (yukari, tek voxel adimlarla, tavana kadar) cekilirken Q
parcasina carpar mi? P'nin ortak (x,y) sutunundaki EN ALT voxel'i s adim
yukselirken, Q'nun ayni sutundaki bir voxel'ine ancak o Q voxel'i P'nin
altindaki bir voxel'inden YUKARIDAYSA carpar. Yani:

    Q, P'yi bloke eder  <=>  ORTAK bir sutunda  max(Q_z) > min(P_z)   (global)

P serbesttir (cikarilabilir) <=> kalan hicbir Q onu bloke etmiyorsa. Bu, tum
kaydirma adimlarini tek numpy karsilastirmasina indirger (parca cifti basina
O(kesisim-ayakizi), voxel basina Python dongusu YOK).

Tavan: acik-tepe kutu (Bin3D sinirsiz yukseklik) -> +Z sonsuza kadar serbest;
ortak sutunda uzerinde bir sey yoksa parca cikar. Ayri bir tavan sinirina
gerek yok.

SAF ASCII (cp1254 guvenli) — reason/print'te sembol/Turkce harf yok.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple, Union

import numpy as np


# ---------------------------------------------------------------------------
# Sahne primitifi: yerlestirilmis bir parcanin voxel maskesi + global konumu
# ---------------------------------------------------------------------------

@dataclass(eq=False)  # eq=False: kimlik-bazli (numpy alanlari __eq__'i bozar)
class PlacedVoxels:
    """Yerlestirilmis tek parca — ortak lattice'te (x, y, z) offsetli.

    filled/colmin/colmax LOKAL (kendi grid'i) sutun profilleridir; global
    sutun z'si = colmin/colmax + self.z. bottom/top voxelize.Orientation'daki
    ile ayni anlamda ama burada ham grid'den turetilir (sentetik sahneler ham
    bool grid gecebilir).
    """

    part_id: str
    x: int
    y: int
    z: int
    filled: np.ndarray   # bool (nx, ny) — en az bir voxel iceren sutunlar
    colmin: np.ndarray   # int  (nx, ny) — sutun basina en dusuk dolu z (lokal)
    colmax: np.ndarray   # int  (nx, ny) — sutun basina en yuksek dolu z (lokal)

    @property
    def nx(self) -> int:
        return int(self.filled.shape[0])

    @property
    def ny(self) -> int:
        return int(self.filled.shape[1])


@dataclass
class AccessibilityReport:
    """+Z sokulebilirlik denetimi sonucu (v1 — salt rapor)."""

    removable_order: List[str] = field(default_factory=list)
    locked_groups: List[List[str]] = field(default_factory=list)
    n_locked: int = 0
    n_parts: int = 0

    @property
    def all_accessible(self) -> bool:
        return self.n_locked == 0

    def summary(self) -> str:
        """Tek-satir ASCII ozet (log/reason icin guvenli)."""
        if self.n_parts == 0:
            return "accessibility: empty scene (0 parts)"
        if self.all_accessible:
            return (
                f"accessibility: all {self.n_parts} parts removable in +Z "
                f"(no locked groups)"
            )
        groups = "; ".join(
            "{" + ",".join(g) + "}" for g in self.locked_groups
        )
        return (
            f"accessibility: {self.n_locked}/{self.n_parts} parts locked in +Z "
            f"across {len(self.locked_groups)} group(s): {groups}"
        )


# ---------------------------------------------------------------------------
# Grid -> PlacedVoxels (sutun profili cikarma)
# ---------------------------------------------------------------------------

def _column_profiles(grid: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bool (nx, ny, nz) grid -> (filled, colmin, colmax) lokal profilleri.

    Bos sutunlarda colmin/colmax degeri anlamsizdir (0) ama blok testinde
    her zaman `filled` maskesiyle kapatilir -> sentinele gerek yok.
    """
    filled = grid.any(axis=2)
    colmin = np.argmax(grid, axis=2).astype(np.int64)               # ilk True = min z
    colmax = (grid.shape[2] - 1 - np.argmax(grid[:, :, ::-1], axis=2)).astype(np.int64)
    return filled, colmin, colmax


def _placed_from_grid(part_id: str, grid: np.ndarray,
                      x: int, y: int, z: int) -> PlacedVoxels:
    grid = np.asarray(grid, dtype=bool)
    if grid.ndim != 3:
        raise ValueError(f"grid 3D bool olmali, gelen shape={grid.shape}")
    filled, colmin, colmax = _column_profiles(grid)
    return PlacedVoxels(str(part_id), int(x), int(y), int(z),
                        filled, colmin, colmax)


Scene = Sequence[Tuple[str, np.ndarray, int, int, int]]


def placed_voxels_from_scene(scene: Scene) -> List[PlacedVoxels]:
    """Sentetik/genel sahne adaptoru: [(part_id, grid, x, y, z), ...]."""
    return [_placed_from_grid(pid, grid, x, y, z)
            for (pid, grid, x, y, z) in scene]


# ---------------------------------------------------------------------------
# +Z blok testi (parca cifti, vektorize)
# ---------------------------------------------------------------------------

def _blocks(blocker: PlacedVoxels, mover: PlacedVoxels) -> bool:
    """`blocker`, `mover`in +Z cekilmesini engelliyor mu?

    Engel <=> ortak (x,y) sutununda  max(blocker_z) > min(mover_z)  (global).
    Sadece ayak-izi kesisiminde calisir; kesisim yoksa engel yok.
    """
    gx0 = max(blocker.x, mover.x)
    gx1 = min(blocker.x + blocker.nx, mover.x + mover.nx)
    gy0 = max(blocker.y, mover.y)
    gy1 = min(blocker.y + blocker.ny, mover.y + mover.ny)
    if gx0 >= gx1 or gy0 >= gy1:
        return False  # ayak-izi kesismiyor

    bi0, bi1 = gx0 - blocker.x, gx1 - blocker.x
    bj0, bj1 = gy0 - blocker.y, gy1 - blocker.y
    mi0, mi1 = gx0 - mover.x, gx1 - mover.x
    mj0, mj1 = gy0 - mover.y, gy1 - mover.y

    both = blocker.filled[bi0:bi1, bj0:bj1] & mover.filled[mi0:mi1, mj0:mj1]
    if not both.any():
        return False
    b_top = blocker.colmax[bi0:bi1, bj0:bj1] + blocker.z   # global max z
    m_bot = mover.colmin[mi0:mi1, mj0:mj1] + mover.z        # global min z
    return bool(np.any(both & (b_top > m_bot)))


# ---------------------------------------------------------------------------
# Kaldirma-sirasi simulasyonu + kilitli grup ayristirma
# ---------------------------------------------------------------------------

def _locked_groups(parts: List[PlacedVoxels], alive: List[int]) -> List[List[str]]:
    """Kalan (kilitli) parcalari birbirini engelleme iliskisine gore
    baglantili bilesenlere (interlock kumeleri) ayir. Yonsuz graf: i-j
    kenari <=> i, j'yi VEYA j, i'yi engelliyor."""
    pos = {idx: k for k, idx in enumerate(alive)}
    parent = list(range(len(alive)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a in range(len(alive)):
        for b in range(a + 1, len(alive)):
            pa, pb = parts[alive[a]], parts[alive[b]]
            if _blocks(pa, pb) or _blocks(pb, pa):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

    groups: Dict[int, List[str]] = {}
    for a in range(len(alive)):
        groups.setdefault(find(a), []).append(parts[alive[a]].part_id)
    # deterministik cikti: parca girdi sirasina gore, gruplar ilk-uyeye gore
    ordered = sorted(groups.values(), key=lambda g: pos_key(g, parts, alive, pos))
    return ordered


def pos_key(group: List[str], parts, alive, pos) -> int:
    """Grubu ilk (en kucuk girdi-indeksli) uyesine gore siralamak icin anahtar."""
    id_to_idx = {parts[i].part_id: i for i in alive}
    return min(id_to_idx[pid] for pid in group)


def check_accessibility(scene: Union[Scene, Sequence[PlacedVoxels]]
                        ) -> AccessibilityReport:
    """Bir yerlesim sahnesinin +Z sokulebilirligini denetle.

    scene: PlacedVoxels listesi VEYA ham (part_id, grid, x, y, z) tuple listesi.
    Naif O(N^2 * turlar) — parca cifti basina vektorize blok testi.
    """
    parts = list(scene)
    if parts and not isinstance(parts[0], PlacedVoxels):
        parts = placed_voxels_from_scene(parts)  # type: ignore[arg-type]

    n = len(parts)
    alive = list(range(n))
    removable_order: List[str] = []

    # Statik parcalar arasi +Z blok iliskisi SABIT: N x N blok matrisini BIR
    # KEZ hesapla (O(N^2) _blocks cagrisi), sonra kaldirma dongusu yalniz
    # cache'li sayaclarla soyar (peel) -> her tur tum canli ciftleri yeniden
    # hesaplayan O(N^3) davranis O(N^2)'ye iner; removable_order birebir korunur.
    blocks_list: List[List[int]] = [[] for _ in range(n)]  # blocks_list[j] = j'nin engelledigi i'ler
    n_alive_blockers = [0] * n                              # i'yi engelleyen CANLI parca sayisi
    for i in range(n):
        for j in range(n):
            if j != i and _blocks(parts[j], parts[i]):
                blocks_list[j].append(i)
                n_alive_blockers[i] += 1

    while alive:
        freed = [i for i in alive if n_alive_blockers[i] == 0]
        if not freed:
            break  # kalan herkes birbirine kilitli
        freed_set = set(freed)
        removable_order.extend(parts[i].part_id for i in freed)  # tur-ici girdi sirasi
        for j in freed:  # freed parcalarin engelledigi i'lerin canli-blok sayacini dus
            for i in blocks_list[j]:
                if i not in freed_set:
                    n_alive_blockers[i] -= 1
        alive = [i for i in alive if i not in freed_set]

    groups = _locked_groups(parts, alive) if alive else []
    return AccessibilityReport(
        removable_order=removable_order,
        locked_groups=groups,
        n_locked=len(alive),
        n_parts=n,
    )


# ---------------------------------------------------------------------------
# Cozucu-cikti adaptoru: Placement3D + VoxelPart kaynagi
# ---------------------------------------------------------------------------

PartsSource = Union[Dict[str, object], Sequence[object]]


def _parts_lookup(parts: PartsSource) -> Dict[str, object]:
    """VoxelPart dict'i veya listesini {id: part} sozlugune indir."""
    if isinstance(parts, dict):
        return dict(parts)
    return {p.id: p for p in parts}


def placed_voxels_from_placements(placements: Sequence[object],
                                  parts: PartsSource) -> List[PlacedVoxels]:
    """Cozucu ciktisi (Placement3D listesi) + VoxelPart kaynagindan sahne kur.

    Her placement icin parca voxel grid'i:
        parts[placement.part_id].orientations[placement.orientation_idx].grid
    alinir ve (x, y, z) offsetiyle PlacedVoxels'a cevrilir.

    Bu, dblf.place_in_order ve nfv_solve.solve_nfv'nin urettigi
    Placement3D + VoxelPart yapisina dogrudan uyar (bkz. modul basligi).
    """
    lookup = _parts_lookup(parts)
    out: List[PlacedVoxels] = []
    for pl in placements:
        part = lookup[pl.part_id]
        grid = part.orientations[pl.orientation_idx].grid
        out.append(_placed_from_grid(pl.part_id, grid, pl.x, pl.y, pl.z))
    return out


def check_placements(placements: Sequence[object],
                     parts: PartsSource) -> AccessibilityReport:
    """Placement3D listesi + VoxelPart kaynagini denetle (dblf/nfv adaptoru)."""
    return check_accessibility(placed_voxels_from_placements(placements, parts))


def check_result(result: object) -> AccessibilityReport:
    """CoarseToFineResult (nfv_solve) benzeri sonuc nesnesini denetle.

    Ordek-tiplemesi: result.placements + result.fine_voxel_parts bekler
    (nfv_solve.solve_nfv CoarseToFineResult'i bunlari tasir). Ikisi de yoksa
    aciklayici hata verir — cagiran check_placements'i parca kaynagiyla
    dogrudan kullanmali.
    """
    placements = getattr(result, "placements", None)
    parts = getattr(result, "fine_voxel_parts", None)
    if placements is None or parts is None:
        raise ValueError(
            "check_result icin result.placements + result.fine_voxel_parts "
            "gerekli; bunlar yoksa check_placements(placements, parts) kullanin."
        )
    return check_placements(placements, parts)

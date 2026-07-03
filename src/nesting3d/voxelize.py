"""voxelize.py — mesh -> VoxelPart (PLAN_3D.md §2.4, §3).

Each part is voxelized once per allowed axis-aligned orientation.  For every
orientation we precompute the column profiles the heightmap placement needs:

  grid    : bool (nx, ny, nz) — filled voxels, mesh min-corner at index (0,0,0)
  filled  : bool (nx, ny)     — columns that contain at least one voxel
  bottom  : int  (nx, ny)     — lowest filled z index per column (0 where empty)
  top     : int  (nx, ny)     — highest filled z index + 1 per column (0 where empty)

Heightmap drop rule (PLAN_3D.md §2.4):
  z(x, y) = max over filled columns (i, j) of  H[x+i, y+j] - bottom[i, j]

Orientations (PLAN_3D.md §2.5): 4 axis-aligned poses — z-rotation {0°, 90°}
x {upright, tipped on side (Rx 90°)}.  Not all 24 rotations: AM part stability
+ small search space.
"""

import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import trimesh

# ---------------------------------------------------------------------------
# Otomatik-eşikli paralel voxelizasyon sabitleri
#
# PARALLEL_MIN_TYPES  — tip sayısı bu değerin ALTINDAYSA seri yol kullanılır.
#   Küçük demolar (2-5 tip) paralel kurulum maliyetinden zarar görmesin.
#   Değer: 6 — benchmark: 6 tip × 4 oryantasyon thread faydasının break-even'i.
#
# PARALLEL_MIN_VOXELS — tahmini toplam hücre sayısı (tüm tipler, tek oryantasyon
#   bbox hacmi / pitch³ toplamı) bu değerin ALTINDAYSA seri yol kullanılır.
#   Çok küçük kutular (her tip 1-2 hücre) paralele geçişi hak etmez.
#   Değer: 5_000 — 5 kutu @ 20³/10³ = 8 hücre/kutu = 40 toplam → seri kalır;
#   büyük gerçek parçalarda (200³mm / 3³mm pitch ≈ 300k hücre/tip) paralel açılır.
#
# _PARALLEL_MAX_WORKERS — ThreadPoolExecutor üst sınırı.
#   numpy/trimesh C-uzantıları GIL'i çoğu zaman bırakır (özellikle trimesh
#   voxelized, _slice_voxelize içindeki numpy ops); thread'ler bu süreçte
#   gerçekten paralel çalışır. ProcessPoolExecutor daha kesin GIL çözümü
#   sağlardı ama Windows'ta spawn overhead + pickle riski (mesh nesneleri,
#   büyük numpy array'leri) kabul edilemez; thread tercih edilir.
#   Her durumda cpu_count() ile cap'lenir, max 16.
# ---------------------------------------------------------------------------

PARALLEL_MIN_TYPES: int = 6
PARALLEL_MIN_VOXELS: float = 5_000.0
_PARALLEL_MAX_WORKERS: int = 16

# _surface_cells eksen-bazlı buffer'ının (chunk_mk × n_bary) eleman tavanı —
# ~0.19 GB float64 (H-12 OOM-guard'ın C1 karşılığı; chunk sınırı sonucu
# değiştirmez, işaretleme idempotent). Test edilebilirlik için modül-seviyesi.
_SURF_CHUNK_ELEMS: int = 24_000_000

try:
    from shapely import contains_xy as _contains_xy
except ImportError:  # slice yöntemi shapely ister; subdivide onsuz çalışır
    _contains_xy = None


def rotation_matrices(n_orientations: int = 4) -> List[np.ndarray]:
    """The allowed pose set, as 4x4 homogeneous matrices.

    Order: upright 0°, upright 90°, side 0°, side 90° (ilk 4 — eski set),
    sonra upright 180°, upright 270°, ters (Rx180) 0°, ters 90° (5..8).
    180°/ters pozlar plaka-plaka geçişme (çıkıntı deliğe oturma) için
    kritik (hedef <=170 mm, 2026-06-11); toz yataklı üretimde her
    oryantasyon basılabilir.  n_orientations=1 keeps only the original pose.

    İndeks 8..11: EĞİK pozlar — dikten 20°/25°/30°/35° yatırılmış
    (Rx 70°/65°/60°/55°).  'Ekmek rafı' düzeni için (2026-06-12): dik plaka
    178-190 mm tavan üretirken eğik plaka yükseklik·cosθ + kalınlık·sinθ'ya
    iner (n3 25° ≈ 168, n8 35° ≈ 166) ve paralel eğik plakalar raf gibi
    sık dizilebilir.  Yalnız allowed_orientations ile seçilir;
    n_orientations'lı eski çağrılar ilk 8 pozu görür.

    İndeks 12..27: Kalan 16 eksen-hizalı rotasyon (Ry dahil) — küpün 24
    simetri grubu tamamlanır (R1, APP_YOL_HARITASI.md §2).  İndeks 0..7
    AYNEN korunur; yeni pozlar sona eklenir.  Yüz yönü × rulo ayrışımı:
      Yüz -y (Rx):    Rz2@Rx, Rz3@Rx          (12..13, 0..7'de 2,3 var)
      Yüz -z (Rx2):   Rz2@Rx2, Rz3@Rx2        (14..15, 0..7'de 6,7 var)
      Yüz +x (Ry):    Ry, Rz@Ry, Rz2@Ry, Rz3@Ry   (16..19)
      Yüz +y (Rx3):   Rx3, Rz@Rx3, Rz2@Rx3, Rz3@Rx3 (20..23)
      Yüz -x (Ry3):   Ry3, Rz@Ry3, Rz2@Ry3, Rz3@Ry3 (24..27)
    """
    rz = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1))
    rz2 = rz @ rz
    rz3 = rz2 @ rz
    rx = trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0))
    rx2 = rx @ rx
    rx3 = rx2 @ rx
    ry = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0))
    ry3 = ry @ ry @ ry
    tilt = [trimesh.transformations.rotation_matrix(math.radians(a), (1, 0, 0))
            for a in (70.0, 65.0, 60.0, 55.0)]  # dikten 20°/25°/30°/35°
    mats = [
        # ---- Eski 8 eksen-hizali (0..7) — DEGISMEZ ----
        np.eye(4),     # 0: dik, 0°
        rz,            # 1: dik, Rz 90°
        rx,            # 2: yan (-y yüzü), 0°
        rz @ rx,       # 3: yan (-y yüzü), Rz 90°
        rz2,           # 4: dik, Rz 180°
        rz2 @ rz,      # 5: dik, Rz 270°
        rx2,           # 6: ters (-z yüzü), 0°
        rz @ rx2,      # 7: ters (-z yüzü), Rz 90°
        # ---- Egik 4 (8..11) — DEGISMEZ ----
        *tilt,
        # ---- Yeni 16 eksen-hizali (12..27, R1) ----
        rz2 @ rx,      # 12: yan (-y yüzü), Rz 180°
        rz3 @ rx,      # 13: yan (-y yüzü), Rz 270°
        rz2 @ rx2,     # 14: ters (-z yüzü), Rz 180°
        rz3 @ rx2,     # 15: ters (-z yüzü), Rz 270°
        ry,            # 16: +x yüzü, 0°
        rz @ ry,       # 17: +x yüzü, Rz 90°
        rz2 @ ry,      # 18: +x yüzü, Rz 180°
        rz3 @ ry,      # 19: +x yüzü, Rz 270°
        rx3,           # 20: +y yüzü, 0°
        rz @ rx3,      # 21: +y yüzü, Rz 90°
        rz2 @ rx3,     # 22: +y yüzü, Rz 180°
        rz3 @ rx3,     # 23: +y yüzü, Rz 270°
        ry3,           # 24: -x yüzü, 0°
        rz @ ry3,      # 25: -x yüzü, Rz 90°
        rz2 @ ry3,     # 26: -x yüzü, Rz 180°
        rz3 @ ry3,     # 27: -x yüzü, Rz 270°
    ]
    return mats[: max(1, min(n_orientations, len(mats)))]


N_MASTER_POSES = 28  # 8 eksen-hizali + 4 egik + 16 yeni eksen-hizali (R1)


@dataclass
class Orientation:
    """Voxel data for one axis-aligned pose of a part."""

    rot_matrix: np.ndarray          # 4x4 — applied to the mesh for this pose
    voxel_origin: np.ndarray        # world xyz of voxel index (0,0,0) centre
    grid: np.ndarray                # bool (nx, ny, nz)
    filled: np.ndarray              # bool (nx, ny)
    bottom: np.ndarray              # int (nx, ny)
    top: np.ndarray                 # int (nx, ny)
    voxel_count: int = 0

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.grid.shape


@dataclass
class VoxelPart:
    """One placeable part instance (qty-expanded; orientation data is shared
    between instances of the same model — read-only)."""

    id: str
    name: str
    mesh: trimesh.Trimesh           # ORİJİNAL mesh — STL export (devoxelization) bunu kullanır
    orientations: List[Orientation]
    volume_voxels: int = 0
    qty_of_model: int = 1
    display_mesh: Optional[trimesh.Trimesh] = None  # decimated kopya — SADECE render
    extra: dict = field(default_factory=dict)


def _dilate(grid: np.ndarray, times: int) -> np.ndarray:
    """YATAY (x, y) binary dilation, `times` voxel parça arası yan boşluk.

    Dikey boşluk burada DEĞİL, Bin3D.z_clearance ile yerleştirme anında
    verilir (2026-06-11): iki taraflı z-dilation istif arayüzü başına
    2 x margin hücre harcıyordu; z_clearance aynı >=1 mm garantisini tek
    hücreyle verir — 12 plakalık numune istifinde ~30 mm tasarruf.
    Pads the array (x, y only) so the dilation never clips."""
    g = np.pad(grid, ((times, times), (times, times), (0, 0)))
    for _ in range(times):
        out = g.copy()
        for axis in (0, 1):
            out |= np.roll(g, 1, axis=axis)
            out |= np.roll(g, -1, axis=axis)
        g = out
    return g


def _slice_voxelize(
    mesh: trimesh.Trimesh, pitch: float, *, allow_empty: bool = False
) -> np.ndarray:
    """Watertight mesh -> bool grid via z-slicing at voxel centres.

    Her z-katmanında mesh kesiti alınır (section_multiplane) ve voxel
    MERKEZLERİ kesit poligonlarının içinde mi diye işaretlenir.  Yüksek
    yüz sayılı gerçek parçalarda subdivide yönteminden ~100x hızlı ve
    hacim-doğru: subdivide yüzeye değen her voxeli doldurur, ince plakaları
    ~2x şişirir (numune kalibrasyonu 2026-06-10).  Mesh min-köşesi origin'de
    olmalı (voxelize_part bunu garanti eder).

    allow_empty: True ise boş grid HATA DEĞİL — boş grid aynen döner.
    voxelize_part bunu kullanır: ince CİDARLI kabuk parçalarda (bbox dolgun
    ama et kalınlığı << pitch; gerçek örnek Deneme4 'Dugme Kilidi', bbox
    doluluğu %12) hiçbir hücre MERKEZİ malzemeye düşmez → slice boş; ama
    hemen ardından _surface_cells yüzeye değen hücreleri konservatif işaretler
    ve BİRLEŞİM dolu olur. Boş-grid kararı bu yüzden birleşimden SONRA
    verilmeli (bkz. voxelize_part). Default False: doğrudan çağıranlar için
    eski fail-fast davranışı birebir korunur.
    """
    if _contains_xy is None:
        raise ImportError("slice voxelization için shapely gerekli")
    ext = mesh.extents
    n = np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1)
    # son dilim parçadan dışarı taşmasın (kalınlık < pitch/2 kalan tepe katmanı)
    zs = np.minimum((np.arange(n[2]) + 0.5) * pitch, ext[2] - 1e-6)
    sections = mesh.section_multiplane(
        plane_origin=[0.0, 0.0, 0.0], plane_normal=[0.0, 0.0, 1.0], heights=zs
    )
    xs = (np.arange(n[0]) + 0.5) * pitch
    ys = (np.arange(n[1]) + 0.5) * pitch

    # Poligon bbox-kırpma (C1, 2026-07-02): bbox dışındaki hücre merkezi
    # strictly-outside → contains False; test etmemek maskeyi DEĞİŞTİRMEZ
    # (birebir, H-03 xy-kırpmanın 2D analoğu). searchsorted left/right bbox
    # SINIRINDAKİ (==) merkezleri dahil eder — konservatif. Grid tek geçişte
    # k-başına yazıldığından |= tam eski "mask or + ata" ile özdeş.
    # P155308 @0.5mm: contains_xy döngüsü 20.4s → bbox-kırpma ile slice
    # toplamı 25.8→8.1s (3.2×).
    grid = np.zeros((n[0], n[1], n[2]), dtype=bool)
    for k, sec in enumerate(sections):
        if sec is None:
            continue
        for poly in sec.polygons_full:
            minx, miny, maxx, maxy = poly.bounds
            i0 = int(np.searchsorted(xs, minx, side="left"))
            i1 = int(np.searchsorted(xs, maxx, side="right"))
            j0 = int(np.searchsorted(ys, miny, side="left"))
            j1 = int(np.searchsorted(ys, maxy, side="right"))
            if i0 >= i1 or j0 >= j1:
                continue
            sxx, syy = np.meshgrid(xs[i0:i1], ys[j0:j1], indexing="ij")
            m = _contains_xy(poly, sxx.ravel(), syy.ravel())
            grid[i0:i1, j0:j1, k] |= m.reshape(i1 - i0, j1 - j0)
    if not grid.any() and not allow_empty:
        # Fail-fast tanı: sessiz/şifreli assert yerine açık, aksiyon alınabilir
        # hata. Boş grid = pitch parçanın en küçük özelliği için fazla kaba;
        # hiçbir dilim merkezi parçaya düşmemiş. Ana çözüm clamp DEĞİL, adaptif
        # pitch (instances/pitch.py suggest_pitch) — bu guard onu zorlar.
        # (allow_empty=True yolunda karar voxelize_part'ta, yüzey birleşimi
        # SONRASINDA verilir — ince cidarlı kabuk parçalar orada kurtulur.)
        ext = mesh.extents  # bounding-box boyutları (mm)
        min_feat = float(min(ext))
        raise ValueError(
            f"Voxelizasyon boş grid üretti: pitch={pitch:.3f} mm, parçanın en "
            f"küçük boyutu ({min_feat:.3f} mm) için fazla kaba "
            f"(min_dim/pitch={min_feat / pitch:.2f}, ~0.5 altı kaybolur). "
            f"Pitch'i <= {min_feat / 2.0:.3f} mm yapın veya adaptif pitch "
            f"kullanın (instances.pitch.suggest_pitch). bbox_extents={ext}"
        )
    return grid


def _surface_cells(mesh: trimesh.Trimesh, pitch: float,
                   shape: Tuple[int, int, int]) -> np.ndarray:
    """Yüzeyin değdiği hücreleri işaretle — slice grid'ini KONSERVATİF yapar.

    Slice yöntemi merkez-içi testtir (underapproximation): pitch'ten ince
    duvar/detay hiçbir hücre merkezini içermezse grid'de GÖRÜNMEZ ve margin
    dilation onu koruyamaz (numune kalibrasyonu 2026-06-11: ölçülen 0.77 mm
    ihlal, n3<->n1).  Bu fonksiyon her üçgeni ~pitch/2 aralıklı barycentric
    ızgarayla örnekleyip noktaların düştüğü hücreleri işaretler; slice
    iç-hacim grid'iyle birleşince voxel model gerçek parçayı dışarıdan sarar
    -> margin=1 gerçek >=1 mm boşluğu garanti eder.

    AABB sınırındaki noktalar son hücreye clip edilir (grid şekli ceil ile
    zaten tüm AABB'yi kapsıyor) — 20 mm kutu @ pitch 5 hâlâ 4x4x4 kalır.

    C1 hız yeniden-yazımı (2026-07-02): pts (mk, n_bary, 3) broadcast zinciri
    yerine EKSEN-BAZLI hesap + önceden ayrılmış buffer'lar (out=) + int32
    indeks. Eleman başına AYNI çarpım ve AYNI toplama sırası korunur
    ((A·w + B·u) + C·v, sonra /pitch, floor, clip) → IEEE çift-duyarlık
    deterministik = eski kodla BİT-DÜZEYİ aynı grid (tests/test_voxelize_c1_
    exact.py donmuş-referans kapısı + 9 gerçek parça cross-dataset doğrulandı).
    Kazanç taze S-boyutlu tahsislerin (page-fault) + int64 indeks trafiğinin +
    reshape kopyalarının kalkması: P155308 @0.5mm 125.9→40.7s (3.1×).
    """
    tri = mesh.triangles  # (m, 3, 3)
    edge = np.linalg.norm(
        tri - np.roll(tri, 1, axis=1), axis=2
    ).max(axis=1)  # üçgen başına en uzun kenar
    k_per_tri = np.maximum(np.ceil(edge / (pitch / 2.0)).astype(int), 1)

    grid = np.zeros(shape, dtype=bool)
    lims = [np.int32(int(s) - 1) for s in shape]

    # Bellek tavanı: eksen-bazlı buffer (chunk_mk, n_bary) bu eleman sayısını
    # aşmaz (~0.19 GB float64). Eski pts'in 1/3 bellek ayak izi → aynı tavanla
    # 3× büyük chunk. Chunk sınırı sonucu DEĞİŞTİRMEZ (işaretleme idempotent);
    # OOM-guard H-12 korunur (Plan2 P155308 356mm @0.5mm tek-array 4.87GB çöküşü).
    chunk_elems = _SURF_CHUNK_ELEMS
    for k in np.unique(k_per_tri):
        sub = tri[k_per_tri == k]  # (mk, 3, 3)
        # barycentric ızgara: (i/k, j/k, 1-i/k-j/k), i+j <= k
        ii, jj = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (ii + jj) <= k
        u1 = ii[keep] / k          # (n_bary,)
        v1 = jj[keep] / k
        w1 = (1.0 - u1) - v1       # eski (1.0 - u - v) ile aynı eleman-sırası
        n_bary = int(u1.size)
        chunk_mk = max(1, chunk_elems // max(1, n_bary))

        rows = min(chunk_mk, sub.shape[0])
        buf = np.empty((rows, n_bary), dtype=np.float64)
        tmp = np.empty_like(buf)
        idx = [np.empty(buf.shape, dtype=np.int32) for _ in range(3)]

        for s0 in range(0, sub.shape[0], chunk_mk):
            chunk = sub[s0:s0 + chunk_mk]  # (<=chunk_mk, 3, 3)
            mk = chunk.shape[0]
            b, t = buf[:mk], tmp[:mk]
            for c in range(3):
                np.multiply(chunk[:, 0, c, None], w1[None, :], out=b)
                np.multiply(chunk[:, 1, c, None], u1[None, :], out=t)
                np.add(b, t, out=b)
                np.multiply(chunk[:, 2, c, None], v1[None, :], out=t)
                np.add(b, t, out=b)
                np.divide(b, pitch, out=b)
                np.floor(b, out=b)
                ic = idx[c][:mk]
                ic[...] = b                      # integral float → int32 (özdeş)
                np.clip(ic, np.int32(0), lims[c], out=ic)
            grid[idx[0][:mk], idx[1][:mk], idx[2][:mk]] = True
    return grid


def _column_profiles(grid: np.ndarray):
    """(filled, bottom, top) column profiles of a bool (nx, ny, nz) grid."""
    nz = grid.shape[2]
    filled = grid.any(axis=2)
    bottom = np.where(filled, np.argmax(grid, axis=2), 0).astype(np.int32)
    top = np.where(filled, nz - np.argmax(grid[:, :, ::-1], axis=2), 0).astype(
        np.int32
    )
    return filled, bottom, top


def voxelize_part(
    name: str,
    mesh: trimesh.Trimesh,
    pitch: float,
    *,
    n_orientations: int = 4,
    margin: int = 0,
    method: str = "subdivide",
    display_mesh: Optional[trimesh.Trimesh] = None,
    allowed_orientations: Optional[Tuple[int, ...]] = None,
    rot_matrices: Optional[List[np.ndarray]] = None,
) -> VoxelPart:
    """Voxelize one model into a VoxelPart with per-orientation profiles.

    fill() is essential: surface-only grids would break both volume metrics
    and the bottom/top profiles (PLAN_3D.md risk #1).

    method="slice" yüksek yüz sayılı gerçek STL'ler için hızlı yol (bkz.
    _slice_voxelize).  display_mesh verilirse VoxelPart.display_mesh olarak
    saklanır ve SADECE render'da kullanılır; STL export her zaman orijinal
    mesh'ten gider (hoca feedback 2026-06-11: decimation kabartma yazıları
    siliyordu — devoxelization çıktısı orijinal çözünürlükte olmalı).

    allowed_orientations: 8-pozluk master sete indeks listesi — parça-bazlı
    poz kısıtı (örn. plakalar dik duramaz: dik plaka tek başına 178-190 mm,
    <=170 mm hedefini imkânsız kılar).  Verilirse n_orientations yok sayılır.

    rot_matrices: AÇIK 4x4 rotasyon matrisi listesi — verilirse hem
    n_orientations hem allowed_orientations YOK SAYILIR; oryantasyonlar tam
    olarak bu matrislerden üretilir. İnce-açı refinement (Faz 2b, coarse_to_fine)
    kazanan ayrık pozun ±açı çevresinde sürekli (ör. 1° adım) rotasyonlar
    üretmek için kullanır (master sette olmayan keyfi açılar).
    """
    if rot_matrices is not None:
        rots = list(rot_matrices)
    elif allowed_orientations is not None:
        master = rotation_matrices(N_MASTER_POSES)
        rots = [master[i] for i in allowed_orientations]
    else:
        rots = rotation_matrices(n_orientations)
    orientations: List[Orientation] = []
    for rot in rots:
        m = mesh.copy()
        m.apply_transform(rot)
        m.apply_translation(-m.bounds[0])

        if method == "slice":
            # allow_empty: ince CİDARLI kabuk parçada (et kalınlığı << pitch,
            # bbox dolgun — Deneme4 'Dugme Kilidi' %12 doluluk) slice boş
            # dönebilir; yüzey hücreleri konservatif işaretleyince birleşim
            # dolar. Boş-grid kararı bu yüzden BİRLEŞİMDEN SONRA verilir.
            grid = _slice_voxelize(m, pitch, allow_empty=True)
            grid |= _surface_cells(m, pitch, grid.shape)  # konservatif sarma
            if not grid.any():
                ext_m = m.extents
                min_feat = float(min(ext_m))
                raise ValueError(
                    f"Voxelizasyon boş grid üretti (slice + yüzey birleşimi "
                    f"sonrası): pitch={pitch:.3f} mm, parçanın en küçük boyutu "
                    f"({min_feat:.3f} mm) için fazla kaba. Pitch'i küçültün "
                    f"veya adaptif pitch kullanın "
                    f"(instances.pitch.suggest_pitch). bbox_extents={ext_m}"
                )
            origin = np.full(3, pitch / 2.0)
        else:
            vg = m.voxelized(pitch).fill()
            grid = np.asarray(vg.matrix, dtype=bool)
            origin = vg.indices_to_points(np.array([[0, 0, 0]]))[0]

        if margin > 0:
            grid = _dilate(grid, margin)
            origin = origin - np.array([margin * pitch, margin * pitch, 0.0])

        filled, bottom, top = _column_profiles(grid)
        orientations.append(
            Orientation(
                rot_matrix=rot,
                voxel_origin=np.asarray(origin, dtype=float),
                grid=grid,
                filled=filled,
                bottom=bottom,
                top=top,
                voxel_count=int(grid.sum()),
            )
        )

    return VoxelPart(
        id=name,
        name=name,
        mesh=mesh,
        orientations=orientations,
        volume_voxels=orientations[0].voxel_count,
        display_mesh=display_mesh,
    )


def _should_parallelize(model_set: List[tuple], pitch: float) -> bool:
    """Paralel yolun maliyet/kazancını heuristik ile değerlendir.

    Tip sayısı PARALLEL_MIN_TYPES'tan az veya tahmini toplam voxel
    PARALLEL_MIN_VOXELS'tan az ise seri yol tercih edilir.

    Tahmini voxel: her tip için bbox hacmi / pitch³ (yuvarlak — gerçek
    doldurma oranını değil ham üst sınırı kullanır; yine de küçük/büyük
    ayrımı için yeterince güvenilir).
    """
    n_types = len(model_set)
    if n_types < PARALLEL_MIN_TYPES:
        return False
    pitch3 = pitch ** 3
    estimated_voxels = 0.0
    for entry in model_set:
        mesh = entry[1]
        ext = mesh.extents  # (wx, wy, wz)
        estimated_voxels += float(ext[0] * ext[1] * ext[2]) / pitch3
    return estimated_voxels >= PARALLEL_MIN_VOXELS


def expand_quantities(
    model_set: List[tuple],
    pitch: float,
    *,
    n_orientations: int = 4,
    margin: int = 0,
    method: str = "subdivide",
    orientation_overrides: Optional[dict] = None,
) -> List[VoxelPart]:
    """Voxelize each model ONCE, then expand to qty part instances.

    Instances share the (read-only) orientation data, so 30 parts cost
    3 voxelizations.  IDs follow the 2D loader suffix convention: name_01..

    model_set girdileri 3'lü (name, mesh, qty) veya 4'lü
    (name, mesh, qty, display_mesh) olabilir.

    orientation_overrides: {model adı -> 8-poz master sete indeks tuple'ı};
    eşleşmeyen modeller n_orientations default setini kullanır.

    Otomatik-eşikli paralellik:
      - İş yükü küçükse (tip sayısı < PARALLEL_MIN_TYPES veya tahmini
        toplam voxel < PARALLEL_MIN_VOXELS) seri yol kullanılır.
      - Büyük iş yükünde ThreadPoolExecutor ile tip voxelizasyonları
        paralel çalışır.  Executor.map sırayı garanti eder → deterministik.
      - ValueError (boş grid, ince parça) executor içinden propagate eder.
    """
    overrides = orientation_overrides or {}

    # Her tip için voxelize_part argümanlarını hazırla (sıra korunur).
    entries = []
    for entry in model_set:
        name, mesh, qty = entry[:3]
        display = entry[3] if len(entry) > 3 else None
        entries.append((name, mesh, qty, display))

    def _voxelize_entry(entry: tuple) -> VoxelPart:
        name, mesh, qty, display = entry
        return voxelize_part(
            name, mesh, pitch,
            n_orientations=n_orientations,
            margin=margin,
            method=method,
            display_mesh=display,
            allowed_orientations=overrides.get(name),
        )

    if _should_parallelize(model_set, pitch):
        max_workers = min(len(entries), os.cpu_count() or 1, _PARALLEL_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # map() preserves order and re-raises exceptions from workers.
            templates = list(executor.map(_voxelize_entry, entries))
    else:
        templates = [_voxelize_entry(e) for e in entries]

    # Qty genişletme — sıra korunur, oryantasyon verisi paylaşılır.
    parts: List[VoxelPart] = []
    for template, (name, _mesh, qty, _display) in zip(templates, entries):
        width = max(2, len(str(qty)))
        for k in range(1, qty + 1):
            parts.append(
                VoxelPart(
                    id=f"{name}_{k:0{width}d}",
                    name=name,
                    mesh=template.mesh,
                    orientations=template.orientations,
                    volume_voxels=template.volume_voxels,
                    qty_of_model=qty,
                    display_mesh=template.display_mesh,
                )
            )
    return parts

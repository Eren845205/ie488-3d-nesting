"""continuous_settle.py — R11: SUREKLI (alt-voxel) z-kompaksiyon post-pass.

fine_settle (K-17) kuantizasyonu used_pitch/4 kafesine indirir; R11 kafesi
tamamen birakir: parcalar MESH-gercek mesafelerle, surekli z'de asagi oturtulur.
Geri alinan vergi: (a) kalan kafes yuvarlamasi (<pitch/4/katman), (b) voxel
yuzey-sarmasinin sismesi (voxel model >= gercek mesh her yerde).

Tasarim (v1 — YALNIZ z, asagi):
  * Mesafeler min_clearance ile AYNI makine: yuzey-orneklem + cKDTree
    (kendi-icinde tutarli legalite; ayni tohum ailesi).
  * Kural (kritik): bir parca duserken HICBIR komsu ciftinin mesafesi
    min(hedef, mevcut_mesafe) - 1e-3 altina inemez. Boylece kafesin tam-2.0mm
    yan bosluklari dusmeyi BLOKLAMAZ (mesafe azalmiyorsa serbest), ama hicbir
    cift hedef altina yeni girmez -> legalite korunur, iyilesme tek yonlu.
  * Yasak bolge = analitik kutu-mesafesi (orneklem yok, kesin).
  * Taban temasi serbest (parca plakaya oturur; clearance parca-ARASI kural).
  * Adim taramasi kaba->ince (binary search DEGIL: yan komsu mesafesi dz'de
    monoton olmayabilir; ilk-ihlalde-dur taramasi guvenli ve deterministik).
  * Deterministik: sabit tohumlar (seed+i), sabit sira (alt-z artan, esitlikte
    girdi sirasi), sabit adimlar. Canli donanim durumu OKUNMAZ.
  * Ornekleme kusuru riski (en yakin nokta kacirilir) -> pay_mm tamponu +
    cagiran tarafta final min_clearance(6000) kapisi ZORUNLU (A2). Iyilesme
    yoksa cagiran sonucu atar (fine_settle ile ayni tek-tarafli sozlesme).

KANIT yolu: tests/test_r11_continuous_settle.py (mekanizma) + K-48 deneyi
(gercek setlerde kazanc olcumu — YONTEM_HARITASI'na islenir).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import cKDTree

DEFAULT_PAY_MM = 0.1          # hedef = clearance + pay (orneklem kusuru tamponu)
KABA_ADIM_MM = 0.5
INCE_ADIM_MM = 0.02
MAX_SWEEPS = 8
_EPS_KORU = 1e-3              # "mevcut mesafeyi koru" toleransi
_DUR_EPS_MM = 0.01            # sweep toplam hareketi bunun altindaysa yakinsadi


@dataclass
class ContinuousSettleResult:
    dz: np.ndarray                    # parca basina toplam dusme (mm, >=0)
    height_mm: float                  # dusme SONRASI tavan
    height_before_mm: float
    n_moved: int
    sweeps_used: int
    telemetri: dict = field(default_factory=dict)

    @property
    def gain_mm(self) -> float:
        return self.height_before_mm - self.height_mm


def _surface_cloud(mesh, n: int, seed: int) -> np.ndarray:
    """Yuzey orneklemi (clearance._surface_samples ile AYNI mekanizma/tohumlama)
    + kose noktalari (ekstremler garanti)."""
    import trimesh as _tm
    pts, _face = _tm.sample.sample_surface(mesh, n, seed=seed)
    return np.vstack([np.asarray(pts, dtype=np.float64),
                      np.asarray(mesh.vertices, dtype=np.float64)])


def _box_dist(pts: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> float:
    """Nokta bulutunun sonsuz-yukseklikli [x0,x1]x[y0,y1] kolonuna min mesafesi
    (z serbest — kolon tum yukseklik boyunca yasak; analitik, kesin)."""
    dx = np.maximum(np.maximum(x0 - pts[:, 0], pts[:, 0] - x1), 0.0)
    dy = np.maximum(np.maximum(y0 - pts[:, 1], pts[:, 1] - y1), 0.0)
    return float(np.sqrt(dx * dx + dy * dy).min())


def continuous_z_settle(
    meshes: Sequence,                      # placed_meshes ciktisi (dunya mm)
    *,
    clearance_mm: float = 2.0,
    pay_mm: float = DEFAULT_PAY_MM,
    no_go_bounds: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None,
    samples_per_mesh: int = 4000,
    seed: int = 0,
    kaba_adim_mm: float = KABA_ADIM_MM,
    ince_adim_mm: float = INCE_ADIM_MM,
    max_sweeps: int = MAX_SWEEPS,
) -> ContinuousSettleResult:
    """Yerlesik mesh listesini surekli z'de oturt. Mesh'ler DEGISTIRILMEZ;
    donen dz uygulanacak dusmelerdir (m.apply_translation([0,0,-dz[i]]))."""
    n = len(meshes)
    req = clearance_mm + pay_mm
    clouds = [_surface_cloud(m, samples_per_mesh, seed + i) for i, m in enumerate(meshes)]
    trees = [cKDTree(c) for c in clouds]
    bounds = [np.array(m.bounds, dtype=np.float64) for m in meshes]  # (2,3) orijinal
    dz = np.zeros(n, dtype=np.float64)
    h0 = max(float(b[1, 2]) for b in bounds) if n else 0.0

    ngo = None
    if no_go_bounds is not None:
        (nx0, ny0), (nx1, ny1) = no_go_bounds
        ngo = (float(nx0), float(ny0), float(nx1), float(ny1))

    # sira: orijinal alt-z artan, esitlikte girdi sirasi (deterministik)
    sira = sorted(range(n), key=lambda i: (bounds[i][0, 2], i))

    def _pair_min(i: int, j: int, dzi: float) -> float:
        """i (dzi kadar dusmus) ile j (mevcut dz[j]) arasi min mesafe.
        Bulutlar ORIJINAL koordinatta; goreli kaydirma sorguya verilir."""
        goreli = dzi - dz[j]
        d, _ = trees[j].query(clouds[i] - np.array([0.0, 0.0, goreli]), k=1)
        return float(np.min(d))

    def _komsular(i: int) -> List[int]:
        bi = bounds[i]
        out = []
        for j in range(n):
            if j == i:
                continue
            bj = bounds[j]
            # xy'de (req + kaba adim) payli AABB kesisimi; z: i'nin altinda VEYA
            # yaninda olan herkes (i asagi kayarken yanindan gececekleri dahil)
            pad = req + kaba_adim_mm
            if (bi[0, 0] - pad < bj[1, 0] and bj[0, 0] < bi[1, 0] + pad and
                    bi[0, 1] - pad < bj[1, 1] and bj[0, 1] < bi[1, 1] + pad and
                    bj[0, 2] - dz[j] < bi[1, 2] - dz[i] + pad):
                out.append(j)
        return out

    sweeps = 0
    toplam_hareket = np.inf
    while sweeps < max_sweeps and toplam_hareket > _DUR_EPS_MM:
        toplam_hareket = 0.0
        for i in sira:
            taban = float(bounds[i][0, 2]) - dz[i]
            if taban <= 1e-9:
                continue  # plakada oturuyor
            dz_tavan = taban  # en fazla tabana kadar
            komsu = _komsular(i)
            # her komsu icin korunacak esik: min(hedef, mevcut) - eps
            esikler = {}
            for j in komsu:
                d0 = _pair_min(i, j, dz[i])
                esikler[j] = min(req, d0) - _EPS_KORU
            # NOT: yasak-bolge kolonu TAM yukseklik boyunca yasak oldugundan
            # xy-mesafesi z-dusmesiyle DEGISMEZ — baslangicta legal olan layout
            # dusmeyle ihlale giremez; kolon icin ek kontrol gerekmez (ngo
            # parametresi API'de gelecekteki yanal hamleler icin tutulur).

            def _uygun(dzi: float) -> bool:
                for j in komsu:
                    if _pair_min(i, j, dzi) < esikler[j]:
                        return False
                return True

            # kaba tarama: ilk ihlale kadar
            kaba = 0.0
            adim = kaba_adim_mm
            while kaba + adim <= dz_tavan + 1e-12:
                if _uygun(dz[i] + kaba + adim):
                    kaba += adim
                else:
                    break
            # ince tarama: kalan araligi ince adimlarla ilerlet
            ince = 0.0
            kalan = min(adim, dz_tavan - kaba)
            while ince + ince_adim_mm <= kalan + 1e-12:
                if _uygun(dz[i] + kaba + ince + ince_adim_mm):
                    ince += ince_adim_mm
                else:
                    break
            dusme = kaba + ince
            if dusme > 0.0:
                dz[i] += dusme
                toplam_hareket += dusme
        sweeps += 1

    h1 = max(float(bounds[i][1, 2]) - dz[i] for i in range(n)) if n else 0.0
    return ContinuousSettleResult(
        dz=dz, height_mm=h1, height_before_mm=h0,
        n_moved=int((dz > _DUR_EPS_MM).sum()), sweeps_used=sweeps,
        telemetri={"req_mm": req, "samples": samples_per_mesh,
                   "toplam_dusme_mm": float(dz.sum())},
    )


def apply_settle(meshes: Sequence, result: ContinuousSettleResult) -> List:
    """Dusmeleri uygulanmis mesh KOPYALARI (export/clearance-gate icin)."""
    out = []
    for m, d in zip(meshes, result.dz):
        c = m.copy()
        if d > 0.0:
            c.apply_translation([0.0, 0.0, -float(d)])
        out.append(c)
    return out

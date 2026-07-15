# -*- coding: utf-8 -*-
"""rotation_extract.py — R10: dondurme-sokum sertifikasi (hoca kriteri (c)).

5-yon sirali sokumun (accessibility.check_separability_5dir) ustune ROTASYON
asamasi ekler. Hoca kabul kriteri (b)+(c): "operator kenara cekip VEYA
DONDUREREK cikariyor" — (b) 5 duz dogrultuyla modellendi (A2 2026-07-09);
bu modul (c)'yi modeller.

Fizik modeli: "mikro-kaldir + yerinde dondur + duz cek"
------------------------------------------------------
Peel (sirali sokum) takildiginda, kilitli her parca icin sertifika aranir:
  0) istege bagli mikro-kaldirma (lift): parca +Z'de `lift` voxel serbestce
     yukselebiliyorsa oradan denenir (operatorun "hafif kaldirip cevirme"
     hareketi; lift yolu adim adim carpismasiz olmali).
  1) parca kendi merkezi etrafinda (eksen, aci) dondurulur. Donme yolu bir
     ACI MERDIVENIYLE (adaptif adim) taranir: her basamakta ara-poz canli
     parcalarla ve masayla (z<0) carpismamali. Basamakta carpisma varsa o
     eksen+yonun daha buyuk acilari da OLU (yol ayni prefixten gecer) -> kes.
  2) her temiz basamakta dondurulmus poz 5 duz dogrultudan (+Z,+X,-X,+Y,-Y)
     biriyle 0 engelli cekilebiliyorsa SERTIFIKA: (eksen, aci, yon, lift).
Sertifikali parca sahneden dusurulur, peel devam eder. Hicbir kilitli parca
sertifika alamazsa kalanlar "rotasyonla da kilitli" raporlanir.

KONSERVATIFLIK (sound sertifika — yanlis-serbest'e karsi):
- Aci merdiveni adimi adaptif: adim_deg ~ degrees(TUNEL_TOL_VOX / r_max)
  (parcanin en uzak voxeli basamaklar arasi en cok TUNEL_TOL_VOX voxel yol
  alir -> ince duvarlarin "icinden gecme" tunellemesi sinirlanir).
- Cagiranin verdigi grid'ler oldugu gibi kullanilir: uretim yolunda bunlar
  CLEARANCE-DILATE'LI fine grid'lerdir (>= 2-3 voxel supersetlik zaten
  tasinir; nearest-neighbor dondurmenin ~yarim voxel kaybini fazlasiyla
  ortmektedir). Ham (dilate'siz) grid verilirse sertifika payi caller'a aittir.
- Masa kurali: donme/kaldirma sirasinda hicbir voxel z<0'a inemez (yigin
  masada durur). Duz yatay cekmeler masayla catismaz; -Z cekme zaten yok.
Yanlis-kilitli MUMKUNDUR (gercek operator daha yaratici olabilir) — metrik
(c) icin ALT-SINIR verir; (b)-metrigi 5dir'in ustune yalniz kilit ACAR,
asla kilit eklemez (rot asamasi sadece peel takildiginda devreye girer).

Perf notu: buyuk grid'li parcalarda scipy.ndimage.rotate pahali; kenar
uzunlugu `max_grid_vox`'u asan parcalar rotasyon adayligindan MUAF tutulur
(kilitli kalirlar — konservatif) ve raporda isaretlenir.

SAF ASCII (cp1254). Salt-rapor: yerlesimi degistirmez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .accessibility import (AccessibilityReport, PartsSource, _blocks,
                            _locked_groups, _parts_lookup, _yonlu_sahne,
                            _YON_5)

# eksen -> scipy.ndimage.rotate duzlemi (X etrafinda donus = (y,z) duzlemi...)
_EKSEN_DUZLEM = {"X": (1, 2), "Y": (0, 2), "Z": (0, 1)}

# eksen -> maksimum tarama acisi (derece). Z (dikey eksen) etrafinda tam
# ceyrek tur serbest (yatay cevirme); X/Y tilt'leri operator icin kucuk tutulur.
DEFAULT_MAX_ACI = {"Z": 90.0, "X": 30.0, "Y": 30.0}

# basamaklar arasi izin verilen azami voxel yolu (tunelleme toleransi).
# Uretim grid'leri clearance-dilate'li (>=2-3 voxel duvar kalinligi) oldugundan
# 2.5 voxel guvenli; ham grid'de caller dusurmeli.
TUNEL_TOL_VOX = 2.5

_ADIM_MIN_DEG = 1.0    # merdiven adimi alt siniri (asiri ince taramayi kes)
_ADIM_MAX_DEG = 15.0   # ve ust siniri (kucuk parcada bile ara-poz denetle)


@dataclass
class RotCertificate:
    """Tek parcanin dondurme-sokum sertifikasi (telemetri/rapor)."""

    eksen: str      # "X" | "Y" | "Z"
    aci_deg: float  # isaretli (+/-) donus acisi
    yon: str        # cekme dogrultusu (+Z/+X/-X/+Y/-Y)
    lift_vox: int   # donusten onceki mikro-kaldirma (voxel)


@dataclass
class RotSeparabilityReport:
    """5-yon + rotasyon sirali sokum sonucu."""

    removable_order: List[str] = field(default_factory=list)
    locked_groups: List[List[str]] = field(default_factory=list)
    n_locked: int = 0
    n_parts: int = 0
    certificates: Dict[str, RotCertificate] = field(default_factory=dict)
    skipped_large: List[str] = field(default_factory=list)  # max_grid_vox muaflari
    # teshis telemetrisi: pid -> denenen her (lift,eksen,isaret) icin kisa
    # basarisizlik ozeti ("Z+ rung2/6 carpisma", "X- pull-bloklu 6/6", "butce")
    fail_telemetri: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def all_accessible(self) -> bool:
        return self.n_locked == 0

    def summary(self) -> str:
        rot = len(self.certificates)
        if self.n_parts == 0:
            return "rot-separability: empty scene (0 parts)"
        if self.all_accessible:
            return (f"rot-separability: all {self.n_parts} removable "
                    f"({rot} via rotation)")
        return (f"rot-separability: {self.n_locked}/{self.n_parts} locked "
                f"even with rotation ({rot} freed via rotation)")


def _krop(grid: np.ndarray, pos: Tuple[int, int, int]
          ) -> Tuple[np.ndarray, Tuple[int, int, int]]:
    """Bos kenar dilimlerini at; pozu kaydir (collision perf + dogru bbox)."""
    if not grid.any():
        return grid[:0, :0, :0], pos
    idx = np.nonzero(grid)
    lo = [int(a.min()) for a in idx]
    hi = [int(a.max()) + 1 for a in idx]
    g = grid[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    return g, (pos[0] + lo[0], pos[1] + lo[1], pos[2] + lo[2])


def _dondur(grid: np.ndarray, pos: Tuple[int, int, int], eksen: str,
            aci_deg: float) -> Tuple[np.ndarray, Tuple[int, int, int]]:
    """Grid'i kendi merkezi etrafinda dondur (sahne merkezi sabit kalir).

    scipy.ndimage.rotate(reshape=True) girisin merkezini cikisin merkezine
    esler -> yeni poz = poz + (eski_shape - yeni_shape)/2 (eksen basina).
    order=0 (nearest) bool icin; prefilter kapatilir.
    """
    from scipy.ndimage import rotate as nd_rotate

    r = nd_rotate(grid.astype(np.uint8), aci_deg,
                  axes=_EKSEN_DUZLEM[eksen], order=0,
                  reshape=True, prefilter=False) > 0
    pos2 = tuple(int(round(p + (s0 - s1) / 2.0))
                 for p, s0, s1 in zip(pos, grid.shape, r.shape))
    return _krop(r, pos2)  # type: ignore[return-value]


def _carpisma(grid: np.ndarray, pos: Tuple[int, int, int],
              digerleri: Sequence[Tuple[np.ndarray, Tuple[int, int, int]]]
              ) -> bool:
    """Tam-3D voxel kesisimi: grid@pos, digerlerinden herhangi biriyle
    ortusuyor mu? (bbox kesisimi -> dilim -> AND)."""
    ax0, ay0, az0 = pos
    ax1 = ax0 + grid.shape[0]
    ay1 = ay0 + grid.shape[1]
    az1 = az0 + grid.shape[2]
    for g, (bx0, by0, bz0) in digerleri:
        bx1 = bx0 + g.shape[0]
        by1 = by0 + g.shape[1]
        bz1 = bz0 + g.shape[2]
        ix0, ix1 = max(ax0, bx0), min(ax1, bx1)
        iy0, iy1 = max(ay0, by0), min(ay1, by1)
        iz0, iz1 = max(az0, bz0), min(az1, bz1)
        if ix0 >= ix1 or iy0 >= iy1 or iz0 >= iz1:
            continue
        a = grid[ix0 - ax0:ix1 - ax0, iy0 - ay0:iy1 - ay0, iz0 - az0:iz1 - az0]
        b = g[ix0 - bx0:ix1 - bx0, iy0 - by0:iy1 - by0, iz0 - bz0:iz1 - bz0]
        if np.any(a & b):
            return True
    return False


# _dilate'in (voxelize) xy-cross yapisinin aynisi — erode bunun tersi olmali
_CROSS_XY = np.zeros((3, 3, 1), dtype=bool)
_CROSS_XY[1, :, 0] = True
_CROSS_XY[:, 1, 0] = True


def _erode_clearance(grid: np.ndarray, xy_vox: int, z_up_vox: int) -> np.ndarray:
    """Clearance-dilate'li grid'den SOKUM-FIZIGI grid'i uret (K-34 v3).

    Yerlestirme grid'leri voxelize._dilate (xy-cross x`xy_vox`) +
    _dilate_z_up (tek-tarafli +z x`z_up_vox`) ile sismistir: 2mm bosluk
    KURALI tasinir. Ekstraksiyon fiziginde ise yalniz GERCEK geometri
    carpismasi onemlidir — hareket sirasinda 2mm sart kosulmaz (hoca (c):
    operator dondururken parcalar birbirine yaklasabilir).

    Ayni yapiyla erozyon = morfolojik CLOSING >= ORIJINAL geometri (kanit:
    erode(dilate(X)) superset X; xy ve z operatorleri dik eksenlerde,
    siralari degistirilebilir). Yani sonuc gercek parcanin SUPERSETI kalir
    -> sertifika sound. Bos kalirsa (teorik olarak imkansiz, orijinal bos
    degilse) orijinale donulur (daha siki taraf).
    """
    from scipy.ndimage import binary_erosion

    g = np.asarray(grid, dtype=bool)
    e = (binary_erosion(g, structure=_CROSS_XY, iterations=xy_vox,
                        border_value=0) if xy_vox else g.copy())
    if z_up_vox:
        acc = e.copy()
        for d in range(1, z_up_vox + 1):
            sh = np.zeros_like(e)
            sh[:, :, :-d] = e[:, :, d:]
            acc &= sh
        e = acc
    if not e.any():
        return g
    return e


def _merdiven(max_aci: float, r_max_vox: float) -> List[float]:
    """Adaptif aci merdiveni: adim ~ TUNEL_TOL_VOX / r_max (radyan) -> derece.

    max_aci her zaman merdivenin SON basamagi olur (hedef acinin kendisi
    denetlenir); ara basamaklar esit adimlarla.
    """
    if r_max_vox <= 0:
        return [max_aci]
    adim = math.degrees(TUNEL_TOL_VOX / r_max_vox)
    adim = min(max(_ADIM_MIN_DEG, adim), _ADIM_MAX_DEG)
    n = max(1, int(math.ceil(max_aci / adim)))
    return [max_aci * (k + 1) / n for k in range(n)]


def check_separability_rot(placements: Sequence[object],
                           parts: PartsSource,
                           max_aci: Optional[Dict[str, float]] = None,
                           lifts: Sequence[int] = (0, 1, 2, 3),
                           max_grid_vox: int = 220,
                           sure_butcesi_s: Optional[float] = None,
                           erode_clearance_vox: Tuple[int, int] = (0, 0),
                           ) -> RotSeparabilityReport:
    """5-yon sirali sokum + rotasyon-fallback denetimi (A2 + (c) kriteri).

    placements/parts: check_separability_5dir ile ayni sozlesme
    (Placement3D benzeri .part_id/.orientation_idx/.x/.y/.z + VoxelPart
    kaynagi). 5-yonde takilan her parca icin dondurme sertifikasi aranir.

    Kilitli sahnede rot asamasi TUR BASINA EN FAZLA BIR parca dusurur
    (dusen parca digerlerinin sayaclarini degistirir; yeniden once ucuz duz
    peel denenir). Deterministiktir: girdi sirasi + eksen (Z,X,Y) + kucuk
    aci once + yon sirasi sabit.
    """
    if isinstance(erode_clearance_vox, (int, np.integer)):
        # K-52 dersi: ciplak int, _ensure_eroded unpack'inde TypeError'du —
        # lazy yol yalniz kilitli sahnede kosuldugundan hata saatler sonra
        # patlar; burada normalize edilir.
        erode_clearance_vox = (int(erode_clearance_vox),
                               int(erode_clearance_vox))
    lookup = _parts_lookup(parts)
    n = len(placements)
    pids: List[str] = []
    grids: List[np.ndarray] = []
    poz: List[Tuple[int, int, int]] = []
    for pl in placements:
        g = np.asarray(
            lookup[pl.part_id].orientations[pl.orientation_idx].grid,
            dtype=bool)
        pids.append(str(pl.part_id))
        grids.append(g)
        poz.append((int(pl.x), int(pl.y), int(pl.z)))

    # --- 5-yon kurulum (check_separability_5dir ile birebir ayni mekanik) ---
    sahneler = {yon: [_yonlu_sahne(pids[k], grids[k], *poz[k], yon)
                      for k in range(n)] for yon in _YON_5}
    blocks: Dict[Tuple[str, int], List[int]] = {}
    sayac = {yon: [0] * n for yon in _YON_5}
    for yon in _YON_5:
        sc = sahneler[yon]
        for i in range(n):
            for j in range(n):
                if j != i and _blocks(sc[j], sc[i]):
                    blocks.setdefault((yon, j), []).append(i)
                    sayac[yon][i] += 1

    if max_aci is None:
        max_aci = DEFAULT_MAX_ACI
    alive = set(range(n))
    removable_order: List[str] = []
    certs: Dict[str, RotCertificate] = {}
    skipped_large: List[str] = []
    fail_telemetri: Dict[str, List[str]] = {}

    # SOKUM-FIZIGI grid'leri (K-34 v3): rot asamasi carpisma/cekme testleri
    # icin erode'lu kopyalar — LAZY kurulur (kilit yoksa hic maliyet yok).
    # Peel sayaclari ((b) metrigi) ORIJINAL dilate'li grid'lerde kalir.
    egrids: Optional[List[np.ndarray]] = None
    esahneler: Optional[Dict[str, list]] = None

    def _ensure_eroded() -> None:
        nonlocal egrids, esahneler
        if egrids is not None:
            return
        exy, ez = erode_clearance_vox
        if exy or ez:
            egrids = [_erode_clearance(g, exy, ez) for g in grids]
        else:
            egrids = grids
        esahneler = {yon: [_yonlu_sahne(pids[k], egrids[k], *poz[k], yon)
                           for k in range(n)] for yon in _YON_5}

    def _dusur(i: int) -> None:
        removable_order.append(pids[i])
        alive.discard(i)
        for yon in _YON_5:
            for k in blocks.get((yon, i), []):
                if k in alive:
                    sayac[yon][k] -= 1

    def _duz_cekilir(rg: np.ndarray, rpos: Tuple[int, int, int],
                     i: int) -> Optional[str]:
        """Dondurulmus poz 5 duz dogrultudan biriyle cekilebilir mi?

        NN dondurmenin ~1 voxel BUZULMESI yalanci-serbest uretebilir ->
        cekme testinde parca +1 voxel dilate edilir (superset; yalniz kilit
        EKLER, acamaz — konservatif). Supurme testinde dilate YOK: destek
        temasi (parca komsunun ustunde oturuyor) yalanci carpismaya donerdi.
        """
        from scipy.ndimage import binary_dilation

        dg = binary_dilation(np.pad(rg, 1))
        dpos = (rpos[0] - 1, rpos[1] - 1, rpos[2] - 1)
        for yon in _YON_5:
            rp = _yonlu_sahne(pids[i], dg, *dpos, yon)
            if not any(_blocks(esahneler[yon][j], rp)
                       for j in alive if j != i):
                return yon
        return None

    def _rot_sertifika(i: int) -> Optional[RotCertificate]:
        import time as _time
        t0 = _time.perf_counter()
        tel: List[str] = []
        _ensure_eroded()
        g0, p0 = _krop(egrids[i], poz[i])
        digerleri = [(egrids[j], poz[j]) for j in sorted(alive) if j != i]
        # r_max: en uzak voxelin merkeze mesafesi ~ yarim kosegen
        r_max = 0.5 * math.sqrt(sum(s * s for s in g0.shape))
        for lift in lifts:
            if lift:
                # kaldirma yolu adim adim carpismasiz olmali (monoton:
                # s bloklu ise s+1 de bloklu -> break dis dongude)
                bloklu = any(
                    _carpisma(g0, (p0[0], p0[1], p0[2] + s), digerleri)
                    for s in range(1, lift + 1))
                if bloklu:
                    tel.append(f"lift{lift} bloklu")
                    break
            pl0 = (p0[0], p0[1], p0[2] + lift)
            for eksen in ("Z", "X", "Y"):
                for isaret in (1.0, -1.0):
                    merdiven = _merdiven(max_aci[eksen], r_max)
                    n_rung = len(merdiven)
                    pull_blok = 0
                    for k, aci in enumerate(merdiven):
                        if (sure_butcesi_s is not None
                                and _time.perf_counter() - t0 > sure_butcesi_s):
                            tel.append("SURE-BUTCESI doldu")
                            fail_telemetri[pids[i]] = tel
                            return None
                        rg, rpos = _dondur(g0, pl0, eksen, isaret * aci)
                        if rg.size == 0:
                            # NN yeniden-orneklemesi kucuk grid'i yuttu:
                            # bu rung KULLANILAMAZ (sertifika da carpisma
                            # kaniti da uretmez) -> atla; buyuk acida grid
                            # yeniden olusabilir (orn. 90 derece exact).
                            continue
                        if rpos[2] < 0:      # masa: z<0'a voxel indi
                            tel.append(f"L{lift} {eksen}{'+' if isaret > 0 else '-'}"
                                       f" rung{k + 1}/{n_rung} masa")
                            break            # daha buyuk acilar da iner/yol olu
                        if _carpisma(rg, rpos, digerleri):
                            tel.append(f"L{lift} {eksen}{'+' if isaret > 0 else '-'}"
                                       f" rung{k + 1}/{n_rung} carpisma")
                            break            # yol prefix'i carpisti -> eksen+yon olu
                        yon = _duz_cekilir(rg, rpos, i)
                        if yon is not None:
                            return RotCertificate(eksen, float(isaret * aci),
                                                  yon, int(lift))
                        pull_blok += 1
                    else:
                        tel.append(f"L{lift} {eksen}{'+' if isaret > 0 else '-'}"
                                   f" pull-bloklu {pull_blok}/{n_rung}")
        fail_telemetri[pids[i]] = tel
        return None

    while alive:
        # 1) ucuz duz peel (5dir ile ozdes; P1: sorted-alive determinizmi —
        # sira persist edildigi icin tur-ici sira garanti, n_locked degismez)
        freed = []
        for i in sorted(alive):
            for yon in _YON_5:
                if sayac[yon][i] == 0:
                    freed.append(i)
                    break
        if freed:
            for i in freed:
                _dusur(i)
            continue
        # 2) rot asamasi: kilitliler arasinda ilk sertifika (tur basina 1)
        cert_bulundu = False
        for i in sorted(alive):
            if max(grids[i].shape) > max_grid_vox:
                if pids[i] not in skipped_large:
                    skipped_large.append(pids[i])
                continue
            cert = _rot_sertifika(i)
            if cert is not None:
                certs[pids[i]] = cert
                _dusur(i)
                cert_bulundu = True
                break
        if not cert_bulundu:
            break  # rotasyonla da acilamiyor

    kalan = sorted(alive)
    groups = _locked_groups(sahneler["+Z"], kalan) if kalan else []
    return RotSeparabilityReport(
        removable_order=removable_order,
        locked_groups=groups,
        n_locked=len(kalan),
        n_parts=n,
        certificates=certs,
        skipped_large=skipped_large,
        fail_telemetri=fail_telemetri,
    )

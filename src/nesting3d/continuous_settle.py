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

# K-55 (2026-07-16): cKDTree.query cok-cekirdek. AYNI matematik — kesin NN
# mesafeleri worker sayisindan bagimsiz, min indirgemesi sira-bagimsiz ->
# dz BIT-OZDES (kanit: k55_bench_settle dz_md5 + d4 K-52 replay paritesi).
# OLCUM (16-cekirdek, 48p@12000): orijinal 97.1s -> w=4 30.8 / w=6 21.0 /
# w=8 24.7 / w=-1 35.9 (asiri-abonelik ZARAR) -> tavan 6. Worker sayisi
# SONUCU degistirmez (yalniz hiz) — determinizm sozlesmesi bozulmaz.
# Politika TEK KAYNAK clearance.py'de (R11_WORKERS env + min(6, cores)).
from src.nesting3d.clearance import DEFAULT_WORKERS, _default_workers  # noqa: F401


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


VERTEX_CAP = 1500  # v3 (K-49a dersi): yuksek-yuzlu STL'lerde TUM koseler bulutu
#                    patlatiyor (p3'te sweep basina saatler) — deterministik
#                    stride alt-orneklemesiyle sinirla; ekstremler yine temsil
#                    edilir (orneklem + kose alt-kumesi), pay_mm tamponu ve
#                    6000-ornekli final kapi legaliteyi zaten koruyor.


def _surface_cloud(mesh, n: int, seed: int) -> np.ndarray:
    """Yuzey orneklemi (clearance._surface_samples ile AYNI mekanizma/tohumlama)
    + kose noktalari (VERTEX_CAP'e deterministik stride ile sinirli)."""
    import trimesh as _tm
    pts, _face = _tm.sample.sample_surface(mesh, n, seed=seed)
    v = np.asarray(mesh.vertices, dtype=np.float64)
    if len(v) > VERTEX_CAP:
        stride = int(np.ceil(len(v) / VERTEX_CAP))
        v = v[::stride]
    return np.vstack([np.asarray(pts, dtype=np.float64), v])


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
    workers: int = DEFAULT_WORKERS,
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
        d, _ = trees[j].query(clouds[i] - np.array([0.0, 0.0, goreli]), k=1,
                              workers=workers)
        return float(np.min(d))

    def _esik_alti(i: int, j: int, dzi: float, esik: float) -> bool:
        """min_mesafe(i,j) < esik testi — distance_upper_bound=esik budamali.

        KESIN esdeger (K-55): bound disindaki noktalar inf doner; sonlu donen
        her d kesin mesafedir. min(d)<esik <=> (d<esik).any() — strict
        karsilastirma oldugundan sinirdaki (d==esik) nokta iki yolda da False.
        Karar bit-ozdes, sorgu agaci erken budandigi icin cok daha ucuz."""
        goreli = dzi - dz[j]
        d, _ = trees[j].query(clouds[i] - np.array([0.0, 0.0, goreli]), k=1,
                              distance_upper_bound=esik, workers=workers)
        return bool((d < esik).any())

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
            # K-55: en dar esik once — _uygun AND'inde red en cok oradan
            # gelir, erken cikis sorgu sayisini dusurur. Karar AND uzerinden
            # sira-bagimsiz -> dz BIT-OZDES; tie-break j (deterministik).
            komsu = sorted(komsu, key=lambda j: (esikler[j], j))
            # NOT: yasak-bolge kolonu TAM yukseklik boyunca yasak oldugundan
            # xy-mesafesi z-dusmesiyle DEGISMEZ — baslangicta legal olan layout
            # dusmeyle ihlale giremez; kolon icin ek kontrol gerekmez (ngo
            # parametresi API'de gelecekteki yanal hamleler icin tutulur).

            def _uygun(dzi: float) -> bool:
                for j in komsu:
                    if _esik_alti(i, j, dzi, esikler[j]):
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
    return apply_dz(meshes, result.dz)


def apply_dz(meshes: Sequence, dz) -> List:
    out = []
    for m, d in zip(meshes, dz):
        c = m.copy()
        if float(d) > 0.0:
            c.apply_translation([0.0, 0.0, -float(d)])
        out.append(c)
    return out


def rapor_5yon_meshes(meshes: Sequence, pitch: float = 1.0):
    """Mesh listesinde 5-yon sokum RAPORU (margin-0, @pitch re-voxelize, slice).

    P1 (Sokum Konsolu): kilit_5yon_meshes'in rapor-donduren esi — TEK dogruluk
    kaynagi (kilit_5yon_meshes bunun .n_locked'ina indirger; davranis
    bit-ozdes). AccessibilityReport.removable_order pid'leri "m{i}" = meshes
    listesi sirasi. slice yontemi zorunlu (K-49a: subdivide yuksek-yuzlu
    STL'de 52M ucgen MemErr)."""
    import numpy as _np
    from types import SimpleNamespace as _NS
    from src.nesting3d.accessibility import check_separability_5dir
    from src.nesting3d.voxelize import voxelize_part
    parts = {}
    pls = []
    for i, m in enumerate(meshes):
        pid = f"m{i}"
        parts[pid] = voxelize_part(pid, m, pitch, n_orientations=1, margin=0,
                                   z_dilate=0, rot_matrices=[_np.eye(4)],
                                   method="slice")
        org = m.bounds[0]
        pls.append(_NS(part_id=pid, orientation_idx=0,
                       x=int(round(org[0] / pitch)),
                       y=int(round(org[1] / pitch)),
                       z=int(round(org[2] / pitch))))
    return check_separability_5dir(pls, parts)


def kilit_5yon_meshes(meshes: Sequence, pitch: float = 1.0) -> int:
    """Mesh listesinde 5-yon kilit sayisi (rapor_5yon_meshes indirgemesi).

    R11 uretim kapisinin uyesi (K-50 metrigi ile AYNI): pozisyon kafese
    yuvarlanir (<=pitch/2), pre/post ayni metrik -> delta durust."""
    return int(rapor_5yon_meshes(meshes, pitch).n_locked)


def kilit_rot_meshes(meshes: Sequence, pitch: float = 1.0,
                     max_grid_vox: int = 800,
                     sure_butcesi_s: Optional[float] = 1200.0,
                     erode_clearance_vox=(2, 2)):
    """Mesh listesinde rot-sokum denetimi (K-52 tabani; kilit_5yon_meshes ile
    AYNI re-voxelize: margin-0 @pitch, slice). RotSeparabilityReport doner.

    erode_clearance_vox default (2,2) = clearance_to_voxels(2.0, 1.0): rot
    mekanigi (K-34 v3 sokum fizigi) 2mm kuralinin voxel karsiligiyla kosar.
    Butce dolan / max_grid_vox asan parca sertifikasiz kalir -> n_locked'a
    sayilir (konservatif: kabul tarafina sizamaz)."""
    import numpy as _np
    from types import SimpleNamespace as _NS
    from src.nesting3d.rotation_extract import check_separability_rot
    from src.nesting3d.voxelize import voxelize_part
    parts = {}
    pls = []
    for i, m in enumerate(meshes):
        pid = f"m{i}"
        parts[pid] = voxelize_part(pid, m, pitch, n_orientations=1, margin=0,
                                   z_dilate=0, rot_matrices=[_np.eye(4)],
                                   method="slice")
        org = m.bounds[0]
        pls.append(_NS(part_id=pid, orientation_idx=0,
                       x=int(round(org[0] / pitch)),
                       y=int(round(org[1] / pitch)),
                       z=int(round(org[2] / pitch))))
    return check_separability_rot(pls, parts, max_grid_vox=max_grid_vox,
                                  sure_butcesi_s=sure_butcesi_s,
                                  erode_clearance_vox=erode_clearance_vox)


def uretim_r11(
    meshes: Sequence,
    *,
    clearance_mm: float = 2.0,
    no_go_bounds=None,
    pay_mm: float = 0.15,
    samples_kompakt: int = 12000,
    samples_dogrula: int = 6000,
    rot_kabul=False,
    rot_butce_s: float = 1200.0,
    _kilit_fn=None,
    _rot_fn=None,
) -> Optional[dict]:
    """R11 v4'un TEK-TARAFLI uretim sarmalayicisi (K-50 dagilim dosyasi temeli).

    Kompakt (kucuk pay) + dogrula-ve-rafine + kapilar. DORT kapinin
    HERHANGI biri gecilemezse None doner — cagiran mevcut sonucu AYNEN korur
    (fine_settle sozlesmesi): (1) rafine yakinsadi, (2) clearance >= kural,
    (3) kilit artmadi (K-50 d4 dersi: kazanc 8.64 vardi, kilit 11->12 -> RED),
    (4) kazanc > 0.01mm. Basarida dict: dz/height_mm/min_clearance_mm/
    kilit_pre/kilit_post/kazanc_mm/rafine_tur.

    rot_kabul (hoca 2026-07-14 kriteri; K-52 probu): kapi-3 kilit-artisi
    reddi yerine rot-sokum denetimine sorulur — "zor cikan ama cikabilen"
    red sebebi DEGILDIR. rot kilit=0 ise SOKUM-PLANLI kabul (dict'e
    sokum_planli/rot_kilit/rot_cert eklenir); rot kilit>0 / hata -> eski RED
    (tek-tarafli sozlesme korunur). Default False = BIT-OZDES eski davranis.
    Kilit artmadiysa rot denetimi HIC kosulmaz (K-42 maliyet dersi).
    _kilit_fn/_rot_fn test enjeksiyonu (A9 bayat-mock tuzagina karsi imzalar
    gercekle ayni: meshes -> sayi / meshes -> rapor)."""
    if not meshes:
        return None
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    res = continuous_z_settle(meshes, clearance_mm=clearance_mm, pay_mm=pay_mm,
                              samples_per_mesh=samples_kompakt,
                              no_go_bounds=no_go_bounds)
    dz4, rapor4, tur4, ok4 = dogrula_ve_rafine(
        meshes, res.dz, clearance_mm=clearance_mm,
        samples_per_mesh=samples_dogrula)
    if not ok4 or rapor4 is None or rapor4.min_mm < clearance_mm:
        return None
    shifted = apply_dz(meshes, dz4)
    h4 = max(float(m.bounds[1][2]) for m in shifted)
    kazanc = h0 - h4
    if kazanc <= 0.01:
        return None
    kilit = _kilit_fn or kilit_5yon_meshes
    try:
        kilit_pre = kilit(meshes)
        kilit_post = kilit(shifted)
    except MemoryError:
        return None  # denetlenemeyen sonuc uretime giremez (A2)
    rot_bilgi = None
    if kilit_post > kilit_pre:
        if not rot_kabul:
            return None
        rot_check = _rot_fn or (
            lambda ms: kilit_rot_meshes(ms, sure_butcesi_s=rot_butce_s))
        try:
            rot = rot_check(shifted)
        except Exception:
            return None  # rot denetimi kurulamadi -> kabul tarafina sizamaz
        if int(rot.n_locked) > 0:
            return None
        # K-52 musteri-yuzu: sokum talimatlari (eksen/aci/yon/lift) atilmaz —
        # mesh_idx cagiran katmanda parca adina eslenir (pid = "m{i}").
        plan = []
        for pid, cert in rot.certificates.items():
            s = str(pid)
            try:
                idx = int(s[1:]) if s.startswith("m") else None
            except ValueError:
                idx = None
            plan.append({"mesh_idx": idx,
                         "eksen": getattr(cert, "eksen", None),
                         "aci_deg": float(getattr(cert, "aci_deg", 0.0) or 0.0),
                         "yon": getattr(cert, "yon", None),
                         "lift_vox": int(getattr(cert, "lift_vox", 0) or 0)})
        rot_bilgi = {"sokum_planli": True, "rot_kilit": 0,
                     "rot_cert": len(rot.certificates),
                     "sokum_plani": plan}
    out = {
        "dz": [float(d) for d in dz4],
        "height_mm": h4,
        "height_before_mm": h0,
        "kazanc_mm": round(kazanc, 3),
        "min_clearance_mm": float(rapor4.min_mm),
        "kilit_pre": int(kilit_pre),
        "kilit_post": int(kilit_post),
        "rafine_tur": int(tur4),
    }
    if rot_bilgi:
        out.update(rot_bilgi)
    return out


def dogrula_ve_rafine(
    meshes: Sequence,
    dz,
    *,
    clearance_mm: float = 2.0,
    ek_pay_mm: float = 0.05,
    samples_per_mesh: int = 6000,
    max_tur: int = 12,
):
    """R11 v4 — dogrula-ve-rafine: pay tamponu yerine KESIN oturma (K-49c dersi).

    Buyuk pay (1.2mm) saf kalite kaybi: parcalar gercek 2.0 sinirina degil
    tampona yaslanir. v4 tersini yapar: kucuk payla agresif kompakt edilmis
    dz alinir; URETIM METRIGI (min_clearance, ayni orneklem ailesi) ihlalci
    cifti soyler; ciftin COK DUSMUS uyesi eksik kadar GERI KALDIRILIR
    (dz azaltilir, asla <0 olmaz -> orijinal-legal pozisyon dogal alt-sinir);
    yakinsayana dek tekrarlanir. Boylece sonuc tam 2.00x'e oturur.

    Doner: (yeni_dz, son_rapor, tur, converged). converged=False ise cagiran
    v3 (payli) sonucu korumali — kapi zaten reddeder (tek-tarafli sozlesme).
    """
    import numpy as _np
    from src.nesting3d.clearance import min_clearance as _mc
    dz = _np.asarray(dz, dtype=float).copy()
    rapor = None
    for tur in range(max_tur):
        shifted = apply_dz(meshes, dz)
        rapor = _mc(shifted, samples_per_mesh=samples_per_mesh)
        if rapor.min_mm >= clearance_mm:
            return dz, rapor, tur, True
        if rapor.worst_pair is None:
            return dz, rapor, tur, False
        i, j = rapor.worst_pair
        eksik = (clearance_mm - float(rapor.min_mm)) + ek_pay_mm
        k = i if dz[i] >= dz[j] else j
        if dz[k] <= 0.0:
            k = j if k == i else i          # dusmemis parca kaldirilamaz; digerini dene
            if dz[k] <= 0.0:
                return dz, rapor, tur, False  # ikisi de orijinalde — R11 disi ihlal
        dz[k] = max(0.0, dz[k] - eksik)
    return dz, rapor, max_tur, False

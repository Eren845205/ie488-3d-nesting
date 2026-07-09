"""parallel_decode.py — paralel NFV greedy decode (CPU orient-thread + GPU-resident + dispatcher).

NFV greedy: dış döngü (parçalar, hacim-azalan) ZORUNLU SIRALI; bir parçanın oryantasyonları BAĞIMSIZ.
Kol A (CPU): oryantasyonlar ThreadPoolExecutor'da paralel feasibility, ana-thread'de `oi`-sıralı
min(key) reduce → tamamlanma sırasından bağımsız → SERİ İLE BİREBİR. GPU-resident: occupancy cihazda
kalır (transfer tuzağı yok), place in-device, host'a yalnız 3-int. dispatcher: GPU→OOM/hata→CPU→seri.

Birebir: hangi yol seçilirse seçilsin AYNI yükseklik+placements (kalite-koruma). set_workers WORKER
İÇİNDE scoped (ThreadPool contextvar propagate ETMEZ); per_fft=cpu//n_threads (oversubscribe yok).
"""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import numpy as np
import scipy.fft as _sfft

from src.nesting3d.fft_backend import get_backend, blb, blb_xybbox
from src.nesting3d.capabilities import probe_capabilities, probe_cupy
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

RawPlacement = Tuple[str, int, int, int, int]  # (part_id, orientation_idx, x, y, z)


def _nz_limit(pitch: float) -> int:
    return int(800 * 2.0 / max(pitch, 1e-6))


def _eligible_orients(part, nx, ny):
    """Plakaya sığan oryantasyonlar [(oi, orient)]. Seri+paralel AYNI süzgeç."""
    out = []
    for oi, orient in enumerate(part.orientations):
        fw, fd, _ = orient.grid.shape
        if fw > nx or fd > ny:
            continue
        out.append((oi, orient))
    return out


def _reduce_best(results, cur_max):
    """oi-sıralı deterministik min(key). results: [(oi, o, fh)]. Birebir tie-break."""
    best_key = None; best = None
    for oi, o, fh in results:
        if o is None:
            continue
        key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
        if best_key is None or key < best_key:
            best_key, best = key, (oi, o[0], o[1], o[2])
    return best


def _has_exit(occ, orient, x, y, z) -> bool:
    """R2 cikis testi: (orient @ x,y,z) MEVCUT occupancy'ye karsi 5 duz
    dogrultudan (+Z, +-X, +-Y) en az birinde engelsiz cikabilir mi?

    KONSERVATIF (guvenli yon): yanal testler parcanin seyahat-golgesini
    kullanir ve bbox baslangicindan itibaren tarar — arkada kalan engel
    nadiren fazladan RED uretir, asla sahte GECER uretmez. Plaka kenari =
    cikis (toz hacmi duvarsiz). occ parca HENUZ yerlesmeden test edilir.

    DEGISMEZ (K-29 kaniti): her parca yerlestigi anda o ana kadarki sahneye
    karsi cikisliysa, TERS yerlestirme sirasi gecerli sirali sokumdur ->
    nihai sahnede 5-yon kilit = 0 GARANTI.
    """
    g = orient.grid
    fw, fd, fh = g.shape
    nx, ny, nz = occ.shape
    z2 = min(z + fh, nz)
    if z2 <= z:
        return True                       # tamamen tahsis ustu -> gokyuzu acik
    filled = orient.filled                # (fw, fd)
    # +Z: dolu kolonlarin ustunde occupancy var mi
    if not (occ[x:x + fw, y:y + fd, z2:].any(axis=2) & filled).any():
        return True
    zs = slice(z, z2)
    kesit = slice(0, z2 - z)
    golge_yz = g.any(axis=0)[:, kesit]    # (fd, z2-z)
    if x + fw >= nx or not (occ[x + fw:, y:y + fd, zs].any(axis=0) & golge_yz).any():
        return True                       # +X
    if x <= 0 or not (occ[:x, y:y + fd, zs].any(axis=0) & golge_yz).any():
        return True                       # -X
    golge_xz = g.any(axis=1)[:, kesit]    # (fw, z2-z)
    if y + fd >= ny or not (occ[x:x + fw, y + fd:, zs].any(axis=1) & golge_xz).any():
        return True                       # +Y
    if y <= 0 or not (occ[x:x + fw, :y, zs].any(axis=1) & golge_xz).any():
        return True                       # -Y
    return False


class _GuardScene:
    """R2 v2: 5 yon-sahnesini (eksen-takasli PlacedVoxels listeleri) artimli
    tutar; cikis testi accessibility._blocks ile YAPILIR (tek dogruluk
    kaynagi — K-32 dersi: bbox-slab yaklasik testi ic-ice gecmis parmaklari
    goremedi, yanlis-GECER uretti)."""

    def __init__(self):
        from src.nesting3d.accessibility import _YON_5, _yonlu_sahne, _blocks
        self._yonler = _YON_5
        self._yonlu = _yonlu_sahne
        self._blocks = _blocks
        self.sahneler = {y: [] for y in self._yonler}

    def ekle(self, part_id, orient, x, y, z):
        for yon in self._yonler:
            self.sahneler[yon].append(
                self._yonlu(part_id, orient.grid, x, y, z, yon))

    def cikisli_mi(self, orient, x, y, z) -> bool:
        """Aday poz mevcut sahneye karsi >=1 yonde engelsiz mi (EXACT)."""
        for yon in self._yonler:
            aday = self._yonlu("_aday", orient.grid, x, y, z, yon)
            if not any(self._blocks(mevcut, aday)
                       for mevcut in self.sahneler[yon]):
                return True
        return False


def _reduce_best_guarded(results, cur_max, scene: "_GuardScene", part):
    """_reduce_best'in R2 hali: AYNI anahtar siralamasi, cikissiz adaylar
    ATLANIR (ilk cikisli aday kazanir). Hicbiri cikisli degilse None ->
    caller drop-fallback'e duser (tepe yerlesimi +Z-cikisli by construction)."""
    adaylar = []
    for oi, o, fh in results:
        if o is None:
            continue
        key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
        adaylar.append((key, oi, o))
    adaylar.sort(key=lambda t: t[0])
    for _key, oi, o in adaylar:
        if scene.cikisli_mi(part.orientations[oi], o[0], o[1], o[2]):
            return (oi, o[0], o[1], o[2])
    return None


def _worth_threading(ob, n_eligible) -> bool:
    """SADECE hız heuristiği (sonucu DEĞİŞTİRMEZ). Boş/erken bin'de FFT trivial → seri ucuz."""
    return n_eligible >= 2 and ob.max_height_voxels() > 0


# --------------------------------------------------------------------------
# Kol A — CPU orient-thread decode
# --------------------------------------------------------------------------

def decode(parts, nx, ny, *, feasible_mask=None, parallel=False, n_threads=None, pitch=2.0,
           return_placements=False, fft_workers=None, time_budget_sec=None, budget_status=None,
           skip_status=None, no_go_mask=None, exit_guard=False,
           exit_guard_retries=2):
    """NFV-greedy decode. parallel=False → seri; True → Kol A orient-thread. İki yol AYNI blb_xybbox +
    AYNI reduce → BİREBİR. Döner: height_mm veya (height_mm, [RawPlacement]).

    time_budget_sec=None (default) → DAVRANIS AYNEN (butce kontrolu YOK, sifir ek yuk). Verilirse:
    her parca dis-donguden ONCE gecen sure kontrol edilir; asilirsa o ana kadarki KISMI en iyi layout
    ile temiz dusus (istisna YOK) + budget_status (dict verilirse) 'budget_exceeded'=True isaretlenir.

    skip_status (dict verilirse): _drop_fallback bile None donerse (parca hicbir
    oryantasyonda plakaya SIGMIYOR — ornegin clearance-dilation'li grid plakadan
    buyuk) o parca ATLA-VE-SAY edilir; id'si skip_status['dropped']'a yazilir
    (SESSIZ yutma YOK, n_placed duser). None (default) -> parca yine atlanir ama
    kayit tutulmaz (dogrudan cagiranlar icin; uretim yolu best_decode dict gecirir).
    Eski davranis: None unpack -> TypeError cokme; artik graceful."""
    if feasible_mask is None:
        feasible_mask, _ = get_backend()
    cpu = probe_capabilities().cpu_count
    nt = (n_threads or min(4, cpu)) if parallel else 1
    if fft_workers is not None:
        per_fft = fft_workers
    elif parallel:
        per_fft = max(1, cpu // nt)
    else:
        per_fft = cpu

    def _blb_w(occ, grid):
        with _sfft.set_workers(per_fft):  # WORKER İÇİNDE (contextvar propagate etmez)
            return blb_xybbox(occ, grid, feasible_mask)

    # no_go_mask (2026-07-09): yasak kolonlar occupancy'de TAM yukseklik muhur
    # -> FFT + is_feasible + drop-fallback otomatik kacinir (Bin3D seal esdegeri)
    ob = OccupancyBin3D(nx, ny, nz_limit=_nz_limit(pitch), pitch=pitch,
                        no_go_mask=no_go_mask)
    placements: List[RawPlacement] = []
    guard_scene = _GuardScene() if exit_guard else None
    # K-33b telemetri (A4 olc-once): vergi nerede yasiyor?
    guard_stats = {"ilk_gecti": 0, "retry_kurtardi": 0, "fallback": 0}
    sorted_parts = sorted(parts, key=lambda vp: -vp.volume_voxels)

    executor = None
    t0 = time.perf_counter()
    try:
        if parallel:
            executor = ThreadPoolExecutor(max_workers=nt)
        for part in sorted_parts:
            if time_budget_sec is not None and (time.perf_counter() - t0) >= time_budget_sec:
                if budget_status is not None:
                    budget_status["budget_exceeded"] = True
                break  # temiz kismi dusus: o ana kadar yerlesenler korunur
            cur_max = ob.max_height_voxels()
            elig = _eligible_orients(part, nx, ny)
            if parallel and _worth_threading(ob, len(elig)):
                occ = ob.occupancy  # paylaşımlı READ-ONLY (place join sonrası ana-thread'de)

                def work(item):
                    oi, orient = item
                    return (oi, _blb_w(occ, orient.grid), orient.grid.shape[2])
                results = list(executor.map(work, elig))  # sıra-koruyan
            else:
                results = [(oi, _blb_w(ob.occupancy, orient.grid), orient.grid.shape[2])
                           for oi, orient in elig]
            # R2 exit_guard: cikissiz aday atlanir (ayni anahtar siralamasi);
            # kapali (default) -> _reduce_best BIREBIR eski davranis.
            best = (_reduce_best_guarded(results, cur_max, guard_scene, part)
                    if exit_guard else _reduce_best(results, cur_max))
            if exit_guard and best is not None:
                guard_stats["ilk_gecti"] += 1
            if exit_guard and best is None and exit_guard_retries > 0:
                # K-33 COKLU-ADAY: reddedilen pozisyonlar HAYALET isgalle
                # kapatilip BLB o oryantasyon icin YENIDEN sorulur -> ikinci/
                # ucuncu en-iyi kavite adaylari da guard'dan gecirilir.
                # (tek-aday v2'de red = parca tepeye kacisi = 74mm vergi)
                hayaletler = {}   # oi -> [(slice3, eklenen_bits)]
                cur = {oi: o for oi, o, _fh in results if o is not None}
                for _deneme in range(exit_guard_retries):
                    yeni_results = []
                    for oi, o, fh in results:
                        o_son = cur.get(oi)
                        if o_son is None:
                            yeni_results.append((oi, None, fh))
                            continue
                        g = part.orientations[oi].grid
                        sl = (slice(o_son[0], o_son[0] + g.shape[0]),
                              slice(o_son[1], o_son[1] + g.shape[1]),
                              slice(o_son[2], o_son[2] + g.shape[2]))
                        ob._ensure_z_capacity(o_son[2] + g.shape[2])
                        eklenen = g & ~ob.occupancy[sl]
                        ob.occupancy[sl] |= eklenen
                        hayaletler.setdefault(oi, []).append((sl, eklenen))
                        o2 = _blb_w(ob.occupancy, g)
                        cur[oi] = o2
                        yeni_results.append((oi, o2, fh))
                    best = _reduce_best_guarded(yeni_results, cur_max,
                                                guard_scene, part)
                    if best is not None:
                        guard_stats["retry_kurtardi"] += 1
                        break
                for oi, kayitlar in hayaletler.items():   # hayaletleri geri al
                    for sl, eklenen in kayitlar:
                        ob.occupancy[sl] &= ~eklenen
            if best is None:
                if exit_guard:
                    guard_stats["fallback"] += 1
                fb = _drop_fallback(ob, part)
                if fb is None:
                    # dilated parca hicbir oryantasyonda plakaya SIGMADI ->
                    # atla-ve-say (SESSIZ yutma YOK: skip_status'a id yaz).
                    if skip_status is not None:
                        skip_status.setdefault("dropped", []).append(part.id)
                    continue
                (x, y, z), oi = fb
                best = (oi, x, y, z)
            oi, x, y, z = best
            ob.place(part.orientations[oi], x, y, z)
            if guard_scene is not None:
                # fallback dahil HER yerlesim sahneye islenir (fallback tepe
                # yerlesimi +Z-cikisli by construction — exact _blocks'ta da)
                guard_scene.ekle(part.id, part.orientations[oi], x, y, z)
            if return_placements:
                placements.append((part.id, oi, x, y, z))
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    if exit_guard and skip_status is not None:
        skip_status["guard"] = dict(guard_stats)   # telemetri (K-33b)
    h = ob.height_mm()
    return (h, placements) if return_placements else h


# --------------------------------------------------------------------------
# GPU-resident decode (occupancy cihazda; transfer tuzağı yok)
# --------------------------------------------------------------------------

def _blb_gpu(cp, mask):
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(cp.argmax(sl.any(axis=0)))
    xstar = int(cp.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _blb_xybbox_gpu(cp, occ, grid_flip, gshape):
    fw, fd, fh = gshape
    nx, ny, nz = occ.shape
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        sub = occ[:, :, :z_lim]
        mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
        if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
            o = None
        elif not bool(sub.any()):
            o = (0, 0, 0)
        else:
            xs = cp.where(sub.any(axis=(1, 2)))[0]
            ys = cp.where(sub.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            cx0 = max(0, x0 - (fw - 1)); cx1 = min(nx, x1 + (fw - 1))
            cy0 = max(0, y0 - (fd - 1)); cy1 = min(ny, y1 + (fd - 1))
            crop = sub[cx0:cx1, cy0:cy1, :]
            mask = cp.ones(mshape, dtype=cp.bool_)
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                full = (crop.shape[0] + fw - 1, crop.shape[1] + fd - 1, crop.shape[2] + fh - 1)
                C = cp.fft.irfftn(cp.fft.rfftn(crop.astype(cp.float64), s=full) *
                                  cp.fft.rfftn(grid_flip, s=full), s=full)
                Cc = (C[fw - 1:crop.shape[0], fd - 1:crop.shape[1], fh - 1:crop.shape[2]] < 0.5)
                gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                bx = gx1 - cx0; by = gy1 - cy0
                if bx > 0 and by > 0:
                    mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
            o = _blb_gpu(cp, mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def decode_gpu(parts, nx, ny, pitch=2.0, return_placements=False, *,
               time_budget_sec=None, budget_status=None, no_go_mask=None):
    """GPU-resident NFV decode. occupancy tek seferlik cihazda; grid'ler cache'li; feasible+BLB GPU'da;
    place in-device; host'a yalnız (oi,x,y,z). BİREBİR (CPU seri). cupy yoksa RuntimeError (dispatcher
    yakalar). Drop fallback gerekirse RuntimeError (dispatcher CPU'ya düşer).

    time_budget_sec=None (default) → davranis AYNEN. Verilirse butce asiminda o ana kadarki kismi
    layout ile temiz dusus + budget_status['budget_exceeded']=True."""
    cp = probe_cupy()
    if cp is None:
        raise RuntimeError("cupy/GPU yok")
    try:
        cp.fft.config.get_plan_cache().set_size(4)  # plan birikimi=OOM kaynağı; sayıca sınırla
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()

    occ = cp.zeros((nx, ny, _nz_limit(pitch)), dtype=cp.bool_)  # RESIDENT
    if no_go_mask is not None and np.asarray(no_go_mask).any():
        # yasak kolonlar cihazda TAM yukseklik muhur (CPU ile ayni semantik);
        # cur_max occupancy'den DEGIL yerlesimlerden izlenir -> zehirlenmez.
        occ[cp.asarray(np.asarray(no_go_mask, dtype=bool))] = True
    grid_cache = {}

    def _grids(orient):
        k = id(orient)
        g = grid_cache.get(k)
        if g is None:
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, orient.grid.shape)
            grid_cache[k] = g
        return g

    placements: List[RawPlacement] = []
    cur_max = 0
    n_placed = 0
    t0 = time.perf_counter()
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        if time_budget_sec is not None and (time.perf_counter() - t0) >= time_budget_sec:
            if budget_status is not None:
                budget_status["budget_exceeded"] = True
            break  # temiz kismi dusus
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            _, gf, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            o = _blb_xybbox_gpu(cp, occ, gf, gshape)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            raise RuntimeError(f"GPU decode drop fallback gerekti (parça {part.id})")
        oi, x, y, z = best
        gb, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb  # in-device mutasyon (transfer YOK)
        cur_max = max(cur_max, z + fh)
        n_placed += 1
        if return_placements:
            placements.append((part.id, oi, x, y, z))
        if n_placed % 4 == 0:
            mempool.free_all_blocks()

    cp.cuda.Stream.null.synchronize()
    h = cur_max * pitch
    return (h, placements) if return_placements else h


# --------------------------------------------------------------------------
# Dispatcher — probe→en hızlı KANITLANMIŞ yol + graceful fallback
# --------------------------------------------------------------------------

def choose_strategy(caps=None) -> str:
    caps = caps or probe_capabilities()
    if caps.gpu and caps.gpu_fp64:
        return "gpu-resident"
    if caps.cpu_count > 2:
        return "cpu-kolA"
    return "serial"


def _mark_budget(strategy: str, status: dict) -> str:
    """Butce asildiysa strateji string'ine ASCII iz ekle (reason'a/adaptive_reason'a akar)."""
    return f"{strategy} budget_exceeded" if status.get("budget_exceeded") else strategy


def best_decode(parts, nx, ny, pitch=2.0, *, force=None, verbose=False, time_budget_sec=None,
                no_go_mask=None, exit_guard=False, exit_guard_retries=2):
    """En hızlı KANITLANMIŞ yolu seç + graceful fallback. Döner: (height_mm, [RawPlacement], strategy).
    GPU-resident → OOM/exception → CPU Kol A → serial. NAIVE backend KULLANMAZ.

    time_budget_sec=None (default) → davranis AYNEN (strategy string DEGISMEZ). Butce asilirsa kismi
    en iyi sonuc dondurulur ve strategy'ye ' budget_exceeded' izi eklenir (iz string'de gorunur)."""
    caps = probe_capabilities()
    strat = force or choose_strategy(caps)
    status: dict = {}

    if exit_guard and strat == "gpu-resident":
        # R2 v1 yalniz CPU yolunda (GPU BLB'de aday-eleme yok) -> CPU'ya in.
        strat = "cpu-kolA"

    if strat == "gpu-resident":
        try:
            h, raw = decode_gpu(parts, nx, ny, pitch=pitch, return_placements=True,
                                time_budget_sec=time_budget_sec, budget_status=status,
                                no_go_mask=no_go_mask)
            return h, raw, _mark_budget("gpu-resident", status)
        except Exception as e:
            if verbose:
                print(f"  [dispatch] GPU-resident basarisiz ({type(e).__name__}) -> CPU Kol A")
            strat = "cpu-kolA"

    fm, _ = get_backend("scipy")  # CPU yolunda scipy (naive GPU ölçekte kaybediyor)
    parallel = strat == "cpu-kolA"
    skip: dict = {}
    h, raw = decode(parts, nx, ny, feasible_mask=fm, parallel=parallel, pitch=pitch,
                    return_placements=True, time_budget_sec=time_budget_sec,
                    budget_status=status, skip_status=skip, no_go_mask=no_go_mask,
                    exit_guard=exit_guard, exit_guard_retries=exit_guard_retries)
    strat_str = _mark_budget(("cpu-kolA" if parallel else "serial"), status)
    g = skip.get("guard")
    if g:
        strat_str += (f" guard[ilk={g['ilk_gecti']} retry={g['retry_kurtardi']}"
                      f" fallback={g['fallback']}]")
    dropped = skip.get("dropped")
    if dropped:
        # SESSIZ yutma YOK: atlanan parcalar strateji izine (-> adaptive_reason) yazilir.
        ids = ",".join(dropped[:5]) + ("..." if len(dropped) > 5 else "")
        strat_str += f" dropped={len(dropped)} (plaka-asimi: {ids})"
    return h, raw, strat_str

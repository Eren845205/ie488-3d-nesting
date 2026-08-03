# -*- coding: utf-8 -*-
"""k62_kanopi_plan1.py — K-62 C2: DUZ-KANOPI iki-asama olcumu (SERHLI on-olcum).

Mekanizma (PLAN_KOK_SEBEP_VE_KISIT_V2.md B/C2; hoca 110.41 goruntu-kaniti):
insan cozumu delikli buyuk cerceveyi EN SONA, yiginin USTUNE (kanopi) koyar;
dik parcalar deliklerden gecer. Motor temelleri test-pinli
(tests/test_k62_kanopi.py): drop ustune-inme + delik-gecisi + no-go muhru.

Bu olcum NAIF kanopi kolu:
  asama-1: kanopi adayi CIKARILMIS set, sampiyon recete ile cozulur
           (eg._run_champion; extra_rot_overrides={} — tilt havuzu sussun).
  asama-2: asama-1 sahnesi Bin3D'ye replay edilir (acik z; parite asserti),
           kanopi parcasi DUZ 4-azimut pozla drop edilir (no-go muhurlu),
           dikey bosluk icin z_gap = ceil(2mm/pitch) eklenir.
  telemetri: en iyi ofsette dolu-kolon / delik-kolon alti yigin yukseklik
           dagilimi — "delik-farkindali asama-1" (gelecek adim) ne kazandirir.

SERHLER (A11 + A2):
  - Tek-set on-olcum; mekanizma genellemesi k59-deseni dagilimsal olcumle.
  - Kilit (5-yon/rot) BURADA olculmez (kanopi en-ustte, +Z ilk sokulen —
    yapisal dusuk risk); tam legalite kapi/evaluate_set asamasinda.
  - Clearance merged-mesh min_clearance ile OLCULUR (rapor edilir).
  - Kanopi adayi GEOMETRIK secilir (veri-adi yok): duz footprint alani >=
    plaka alaninin %35'i VE doluluk < 0.6 VE duz poz no-go-fizibil.

Kosum: python -m scripts.detach_run k62_kanopi_plan1   (D:\\ie488'den,
sakin makine; asama-1 tam plan1-eksi-kanopi cozumu kosar). SAF ASCII stdout.
"""
from __future__ import annotations

import copy
import gc
import json
import math
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

import scripts.eval_gate as eg
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_poz_nogo_fizibilite, duz_rot_matrisleri
from src.nesting3d.voxelize import voxelize_part
from scripts.k56_plan1_uretim_tilt import SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k62_kanopi_plan1.log"
OUT = _ROOT / "results" / "k62_kanopi_plan1.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))  # K-56c Eren-onayli soft sozlesme
REF = {"hard": 202.18468017578127, "raw": 170.68857421875,
       "pin_k56f": 140.21, "manuel": 110.41, "taban111": 101.17}
CLEAR_MM = 2.0
# Geometrik kanopi tetigi (A11: veri-adi yok)
ALAN_ORAN_ESIK = 0.35
DOLULUK_ESIK = 0.6

# --- V6 modu (K62_V6=1 veya --v6): zorunlu-kuleler asama-1'den ONCE
# kanopi-DELIK/dis bolgesine pinlenir (cok-kopya pin destegi ile), solver
# kalan kisa parcalari pinli sahnede cozer. Amac: kanopi-altini kuleden
# temiz tutmak (v4/v5 dersi: sonradan tasima 136.5 tavanina takiliyor).
import os
V6 = os.environ.get("K62_V6") == "1" or "--v6" in sys.argv
# V7 (2026-08-04 aksam, C2-derin yol plani): suclu tiplere YATAY poz-kilidi
# — orientation_overrides NFV dalinda destekli (v6'yi dusuren guard yalniz
# pinned/extra_rot icindi). Faz-A sayimi ortak; pin YOK, rota zorlamasi YOK.
V7 = os.environ.get("K62_V7") == "1" or "--v7" in sys.argv
V6_KULE_BUTCE_MM = 69.0   # min bbox-ekseni bunu asan tip yatamaz = kule
V6_PIN_MARGIN_VOX = 4     # kule-drop dilated (2mm/0.5) — pin-pin boslugu


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def inst2_onhazir(inst, p0):
    """Kanopi-haric instance kopyasi (V6 faz-A ve asama-1 ortak)."""
    i2 = copy.copy(inst)
    try:
        i2.parts = [p for p in inst.parts if p is not p0]
    except Exception:
        object.__setattr__(i2, "parts",
                           [p for p in inst.parts if p is not p0])
    return i2


def _kanopi_adayi(inst, pitch):
    """Geometrik tetik: duz footprint alani buyuk + delikli + no-go-fizibil.
    Doner: (part_spec, mesh, fizibilite) veya None."""
    pw, pd = eg.PLATE_STD
    en_iyi = None
    for p in inst.parts:
        if not getattr(p, "stl_path", None):
            continue
        try:
            mesh = trimesh.load(p.stl_path, force="mesh")
        except Exception as e:
            log(f"  uyari: {p.name} mesh yuklenemedi ({e})")
            continue
        ext = sorted(float(x) for x in mesh.extents)[::-1]  # buyukten kucuge
        alan_oran = (ext[0] * ext[1]) / (pw * pd)
        if alan_oran < ALAN_ORAN_ESIK:
            continue
        fiz = duz_poz_nogo_fizibilite(mesh, pw, pd, eg.NOGO_STD,
                                      pitch=pitch, method="slice")
        if fiz is None or not fiz["pozlar"] or fiz["doluluk"] >= DOLULUK_ESIK:
            log(f"  aday-eleme: {p.name} alan_oran={alan_oran:.2f}"
                f" doluluk={fiz['doluluk'] if fiz else '-'}"
                f" poz={len(fiz['pozlar']) if fiz else 0}")
            continue
        skor = alan_oran
        if en_iyi is None or skor > en_iyi[0]:
            en_iyi = (skor, p, mesh, fiz)
    if en_iyi is None:
        return None
    _, p, mesh, fiz = en_iyi
    return p, mesh, fiz


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 C2 DUZ-KANOPI iki-asama olcumu (SERHLI on-olcum)")
    log(f"ref: {REF}")

    eg.NOGO_STD = NOGO_SOFT  # K-56f ile ayni zemin (soft sozlesme)
    pw, pd = eg.PLATE_STD

    inst = eg._load_instance("plan1")
    fine_pitch, _w = _uretim_fine_pitch(inst)
    log(f"fine_pitch={fine_pitch}  plaka={pw}x{pd}  nogo={eg.NOGO_STD}")

    aday = _kanopi_adayi(inst, fine_pitch)
    if aday is None:
        log("HATA: geometrik kanopi adayi bulunamadi — olcum anlamsiz")
        log("BITTI")
        return
    p0, mesh, fiz = aday
    log(f"kanopi adayi: {p0.name}  doluluk={fiz['doluluk']}"
        f"  duz_kalinlik={fiz['duz_kalinlik_mm']}mm"
        f"  uygun_ofset={fiz['uygun_sayisi']}")

    # ---- V6: zorunlu-kuleleri delik/dis bolgeye ON-PINLE ------------------
    # ---- V7: suclu tiplere YATAY poz-kilidi (faz-A ortak) -----------------
    v6_pins = None
    v7_overrides = None
    if V6 or V7:
        import trimesh.transformations as _tt
        _pitch6 = 0.5  # champion fine pitch'i (pin mm-cinsinden, guvenli)
        # hedef kanopi ofseti: rot0 orneklerinden medyan-dy (deterministik)
        _r0 = [pz for pz in fiz["pozlar"] if pz["rot_deg"] == 0.0]
        if not _r0:
            _r0 = fiz["pozlar"]
        _r0s = sorted(_r0, key=lambda pz: (pz["dy_mm"], pz["dx_mm"]))
        _hedef = _r0s[len(_r0s) // 2]
        log(f"[V6] hedef kanopi ofseti: rot={_hedef['rot_deg']}"
            f" dx={_hedef['dx_mm']} dy={_hedef['dy_mm']}")
        # kanopi dolu-bolge maskesi (hedef ofsette) + no-go -> kule-yasak
        _vpk6 = voxelize_part("_v6_kanopi", mesh, _pitch6, margin=0,
                              method="slice",
                              rot_matrices=[duz_rot_matrisleri(mesh)[0]])
        _fp6 = np.asarray(_vpk6.orientations[0].grid, dtype=bool).any(axis=2)
        _b6 = Bin3D(pw, pd, _pitch6,
                    no_go_mask=Bin3D.no_go_mask_from_bounds(
                        eg.NOGO_STD, pw, pd, _pitch6))
        _ix = int(round(_hedef["dx_mm"] / _pitch6))
        _iy = int(round(_hedef["dy_mm"] / _pitch6))
        _sub = _b6.height[_ix:_ix + _fp6.shape[0], _iy:_iy + _fp6.shape[1]]
        np.copyto(_sub, np.maximum(_sub, Bin3D.NO_GO_SEAL), where=_fp6)
        # FAZ-A (2026-08-04 revize): "zorunlu kule" tipi YOK cikti (tum
        # tipler yatabilir bbox'ta) — kule kumesi COZUM-guduml u belirlenir:
        # normal on-cozum kosulur, hedef-ofsetteki cerceve-dolu bolge altinda
        # tepesi butceyi asan yerlesimlerin TIPLERI sayilir; o kadar kopya
        # faz-B'de delik/dis bolgeye pinlenir. (A11: tetik cozumden turur,
        # veri-adi yok.)
        log("[V6 faz-A] on-cozum (pinsiz) — suclu tipleri belirlenecek ...")
        _rA, _telA = eg._run_champion("plan1", inst2_onhazir(inst, p0), SEED,
                                      extra_rot_overrides={})
        _pitchA = float(getattr(_rA, "fine_pitch", _pitch6))
        _butceA = int((REF["manuel"] - fiz["duz_kalinlik_mm"]) / _pitchA)
        _fpA = _fp6  # hedef-ofset cerceve dolu maskesi (0.5 gridinde)
        _cdA = np.zeros((int(pw / _pitchA), int(pd / _pitchA)), dtype=bool)
        _sx = int(round(_hedef["dx_mm"] / _pitchA))
        _sy = int(round(_hedef["dy_mm"] / _pitchA))
        _w = min(_fpA.shape[0], _cdA.shape[0] - _sx)
        _h = min(_fpA.shape[1], _cdA.shape[1] - _sy)
        _cdA[_sx:_sx + _w, _sy:_sy + _h] = _fpA[:_w, :_h]
        _sayim: dict = {}
        _fvpA = _rA.fine_voxel_parts
        _vpsA = {v.id: v for v in
                 (_fvpA.values() if isinstance(_fvpA, dict) else _fvpA)}
        for pl in _rA.placements:
            vpA = _vpsA.get(pl.part_id)
            if vpA is None:
                continue
            oA = vpA.orientations[pl.orientation_idx]
            if oA is None:
                continue
            fA = oA.filled
            tepeA = int(pl.z + oA.top[fA].max()) if fA.any() else 0
            if tepeA <= _butceA:
                continue
            bolge = _cdA[pl.x:pl.x + fA.shape[0], pl.y:pl.y + fA.shape[1]]
            if (bolge & fA).any():
                _ad = getattr(vpA, "name", None) or str(pl.part_id)
                _sayim[_ad] = _sayim.get(_ad, 0) + 1
        log(f"[V6 faz-A] suclu tip sayimi: {_sayim}")
        del _rA, _telA, _fvpA, _vpsA
        gc.collect()

        if V7:
            from src.runtime.constraint_compiler import yon_poz_tablosu
            _yatay = tuple(yon_poz_tablosu()["yatay"])
            v7_overrides = {ad: _yatay for ad in _sayim}
            log(f"[V7] yatay poz-kilidi ({len(_yatay)} poz) -> tipler:"
                f" {sorted(v7_overrides)}")

        v6_pins = [] if not V7 else None
    if V6 and not V7:
        for p in inst.parts:
            if p is p0 or not getattr(p, "stl_path", None):
                continue
            _adet_pin = _sayim.get(p.name, 0)
            if _adet_pin <= 0:
                continue
            try:
                _m = trimesh.load(p.stl_path, force="mesh")
            except Exception:
                continue
            # dik poz: en uzun ekseni Z'ye getir
            _ext = np.asarray(_m.extents, dtype=float)
            _k = int(np.argmax(_ext))
            if _k == 2:
                _R = np.eye(4)
            elif _k == 0:
                _R = _tt.rotation_matrix(np.pi / 2.0, [0.0, 1.0, 0.0])
            else:
                _R = _tt.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0])
            _vk = voxelize_part(p.name, _m, _pitch6,
                                margin=V6_PIN_MARGIN_VOX, method="slice",
                                rot_matrices=[_R])
            _o = _vk.orientations[0]
            for _kopya in range(min(_adet_pin, int(p.qty))):
                Zp = _b6.drop_map(_o)
                if Zp is None:
                    raise RuntimeError(f"v6: kule sigmiyor {p.name}")
                Zpm = np.where(Zp >= Bin3D.NO_GO_SEAL,
                               np.iinfo(np.int32).max, Zp)
                if int(Zpm.min()) >= np.iinfo(np.int32).max:
                    raise RuntimeError(f"v6: kule yeri yok {p.name}")
                _px, _py = np.unravel_index(int(Zpm.argmin()), Zpm.shape)
                _pz = int(Zpm.min())
                _b6.place(_vk, 0, int(_px), int(_py), _pz)
                v6_pins.append({"ad": p.name,
                                "x_mm": float(_px) * _pitch6,
                                "y_mm": float(_py) * _pitch6,
                                "z_mm": float(_pz) * _pitch6,
                                "rot": _R.tolist()})
            log(f"[V6] kule tipi {p.name}: {min(_adet_pin, int(p.qty))}"
                f" kopya pinlendi (faz-A sayimi {_adet_pin})")
        log(f"[V6] toplam pin: {len(v6_pins)}")
        del _b6, _vpk6, _fp6
        gc.collect()

    # ---- asama-1: kanopi-haric set, sampiyon recete -----------------------
    inst2 = copy.copy(inst)
    try:
        inst2.parts = [p for p in inst.parts if p is not p0]
    except Exception:
        object.__setattr__(inst2, "parts",
                           [p for p in inst.parts if p is not p0])
    log(f"[ASAMA-1] {sum(int(p.qty) for p in inst2.parts)} parca"
        " (kanopi haric) cozuluyor ...")
    t1 = time.perf_counter()
    # V6: pin yalniz heightmap dalinda gecerli (K-56 guard) — kanopisiz
    # set NFV'ye yonlenirse rota script-ICI heightmap'e zorlanir (gecici
    # monkeypatch; uretim davranisi degismiyor, yalniz bu olcum prosesi).
    _pnb_orig = None
    if V6 and v6_pins:
        import src.nesting3d.adaptive_params as _ap
        _pnb_orig = _ap.predict_nfv_benefit

        def _pnb_zorla(*a, **k):
            d = _pnb_orig(*a, **k)
            try:
                d.mode = "heightmap"
                d.reason = (getattr(d, "reason", "") or "") + \
                    " | v6-pin: heightmap zorlamasi"
            except Exception:
                pass
            return d

        _ap.predict_nfv_benefit = _pnb_zorla
        log("[V6] rota zorlamasi: heightmap (pin uyumu)")
    try:
        r1, nfv_tel = eg._run_champion("plan1", inst2, SEED,
                                       extra_rot_overrides={},
                                       pinned_placements=v6_pins,
                                       orientation_overrides=v7_overrides)
    finally:
        if _pnb_orig is not None:
            import src.nesting3d.adaptive_params as _ap
            _ap.predict_nfv_benefit = _pnb_orig
    h1 = float(r1.height_mm)
    pitch = float(getattr(r1, "fine_pitch", fine_pitch))
    log(f"[ASAMA-1] h={h1:.2f}mm  n={getattr(r1, 'n_placed', '?')}"
        f"  sure={(time.perf_counter() - t1) / 60:.1f}dk  pitch={pitch}")

    # ---- asama-1 sonucundan HAFIF durum cek + agir nesneleri birak --------
    # OOM dersi (2026-08-04 ilk kosu + plan7 2026-07-21 runner dersi):
    # asama-1'in 3D gridleri bellekteyken asama-2 tahsisleri prosesi
    # olduruyor. Replay yalniz 2D (filled, top) profil ister; clearance
    # meshleri simdi kur, sonra r1 SERBEST birakilir.
    _fvp = r1.fine_voxel_parts
    _fvp_iter = _fvp.values() if isinstance(_fvp, dict) else _fvp
    prof = {}
    for vp in _fvp_iter:
        # NFV yolu orientations listesini SEYREK tutabiliyor (kullanilmayan
        # poz None) — None slotlar korunur, yalniz kullanilan indeks gerekir.
        prof[vp.id] = [None if o is None else
                       (np.array(o.filled, dtype=bool, copy=True),
                        np.array(o.top, copy=True))
                       for o in vp.orientations]
    pls = [(pl.part_id, pl.orientation_idx, int(pl.x), int(pl.y), int(pl.z))
           for pl in r1.placements]
    meshes = list(placed_meshes(r1.placements, r1.fine_voxel_parts, pitch))
    # v5 clearance icin mutasyonsuz yedek (v4 meshleri tasiyabilir)
    meshes_orig = [m.copy() for m in meshes]
    del r1, nfv_tel, _fvp, _fvp_iter
    gc.collect()
    log(f"[ASAMA-2] hafif durum cekildi: {len(pls)} yerlesim,"
        f" {len(prof)} parca profili, {len(meshes)} mesh; agir nesneler"
        " birakildi (gc)")

    # ---- asama-2: replay (saf height kompozisyonu) + kanopi drop ----------
    mask = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, pw, pd, pitch)
    b = Bin3D(pw, pd, pitch, no_go_mask=mask)
    for pid_, oi_, x_, y_, z_ in pls:
        if (pid_ not in prof or oi_ >= len(prof[pid_])
                or prof[pid_][oi_] is None):
            log(f"HATA: replay profili yok: {pid_} oi={oi_}")
            log("BITTI")
            return
        f_, top_ = prof[pid_][oi_]
        sub = b.height[x_:x_ + f_.shape[0], y_:y_ + f_.shape[1]]
        np.copyto(sub, np.maximum(sub, z_ + top_), where=f_)
    log(f"[ASAMA-2] replay tamam ({len(pls)} yerlesim)")

    mesh0 = mesh.copy()
    mesh0.apply_translation(-mesh0.bounds[0])
    rots = duz_rot_matrisleri(mesh0)
    vpk = voxelize_part(p0.name, mesh0, pitch, margin=0, method="slice",
                        rot_matrices=rots)
    z_gap = int(math.ceil(CLEAR_MM / pitch))
    en_iyi = None  # (toplam_vox, oi, x, y, z)
    for oi, o in enumerate(vpk.orientations):
        Z = b.drop_map(o)
        if Z is None:
            continue
        Zm = np.where(Z >= Bin3D.NO_GO_SEAL, np.iinfo(np.int32).max, Z)
        zmin = int(Zm.min())
        if zmin >= np.iinfo(np.int32).max:
            continue
        x, y = np.unravel_index(int(Zm.argmin()), Zm.shape)
        fz = o.grid.shape[2]
        z = zmin + z_gap
        toplam = z + fz
        if en_iyi is None or toplam < en_iyi[0]:
            en_iyi = (toplam, oi, int(x), int(y), z, fz)
    if en_iyi is None:
        log("HATA: kanopi hicbir azimutta drop edilemedi")
        log("BITTI")
        return
    toplam_vox, oi, x, y, z, fz = en_iyi
    kanopi_mm = {"rot_deg": [0, 90, 180, 270][oi],
                 "x_mm": x * pitch, "y_mm": y * pitch, "z_mm": z * pitch}
    toplam_mm = max(h1, toplam_vox * pitch)
    log(f"[KANOPI] rot={kanopi_mm['rot_deg']}  x={kanopi_mm['x_mm']:.1f}"
        f"  y={kanopi_mm['y_mm']:.1f}  z={kanopi_mm['z_mm']:.1f}"
        f"  kalinlik={fz * pitch:.1f}mm")
    log(f"[SONUC-naif] toplam={toplam_mm:.2f}mm  (asama-1 {h1:.2f}"
        f" | kanopi tepe {(toplam_vox) * pitch:.2f})")

    # ---- telemetri: delik-farkindali asama-1 ne kazandirirdi? -------------
    o = vpk.orientations[oi]
    f = o.filled
    fw, fh = f.shape
    H = np.where(b.height >= Bin3D.NO_GO_SEAL, 0, b.height)
    sub = H[x:x + fw, y:y + fh].astype(float) * pitch
    dolu_alt = sub[f]
    delik_alt = sub[~f]
    tel = {
        "dolu_kolon_alti_max_mm": float(dolu_alt.max()) if dolu_alt.size else 0,
        "dolu_kolon_alti_p95_mm": float(np.percentile(dolu_alt, 95)) if dolu_alt.size else 0,
        "dolu_kolon_alti_ort_mm": float(dolu_alt.mean()) if dolu_alt.size else 0,
        "delik_kolon_alti_max_mm": float(delik_alt.max()) if delik_alt.size else 0,
        "ideal_alt_butce_mm": REF["manuel"] - fz * pitch,
    }
    log(f"[TELEMETRI] dolu-alti max={tel['dolu_kolon_alti_max_mm']:.1f}"
        f" p95={tel['dolu_kolon_alti_p95_mm']:.1f}"
        f" ort={tel['dolu_kolon_alti_ort_mm']:.1f}"
        f" | delik-alti max={tel['delik_kolon_alti_max_mm']:.1f}"
        f" | ideal alt-butce ~{tel['ideal_alt_butce_mm']:.1f}mm")
    log("  (yorum: dolu-alti max, kanopinin z'sini belirler; delik-farkindali"
        "   asama-1 yuksek kuleleri delik bolgesine toplarsa kanopi asagi iner)")

    # ---- clearance (naif; MESHLER TASINMADAN once olculmeli) --------------
    clear = None
    try:
        mk = mesh0.copy()
        mk.apply_transform(rots[oi])
        mk.apply_translation(-mk.bounds[0])
        mk.apply_translation([kanopi_mm["x_mm"], kanopi_mm["y_mm"],
                              kanopi_mm["z_mm"]])
        rep = min_clearance(list(meshes) + [mk], samples_per_mesh=6000)
        clear = float(rep.min_mm)
        log(f"[CLEARANCE] merged min={clear:.3f}mm (esik {CLEAR_MM})")
    except Exception as e:
        log(f"[CLEARANCE] olculemedi: {type(e).__name__}: {e}")

    # ---- ITERASYON: suclu-tasima (telemetri kazanci >= 5mm ise degerli) ---
    # Naifin siniri: cerceve DOLU kolonlarinin altinda kalan az sayida kule
    # (p95 ~ asama-1 tepesi). Tasima: suclu kuleler sahneden cikar, kanopi
    # alcalir, kuleler kanopi SONRASI tekrar drop edilir (delikten gecis
    # drop_map'te dogal). Saf script-ici; uretim koduna dokunmaz.
    iter_sonuc = None
    try:
        fN = vpk.orientations[oi].filled  # naif kazanan azimut footprint'i
        # plaka koordinatinda cerceve dolu-kolon maskesi (naif ofsette)
        cerceve_dolu = np.zeros_like(b.height, dtype=bool)
        cerceve_dolu[x:x + fN.shape[0], y:y + fN.shape[1]] = fN
        butce_vox = int(tel["ideal_alt_butce_mm"] / pitch)
        suclular = []
        for k_, (pid_, oi_, x_, y_, z_) in enumerate(pls):
            f_, top_ = prof[pid_][oi_]
            tepe = int(z_ + top_[f_].max()) if f_.any() else 0
            if tepe <= butce_vox:
                continue
            bolge = cerceve_dolu[x_:x_ + f_.shape[0], y_:y_ + f_.shape[1]]
            if (bolge & f_).any():
                suclular.append(k_)
        log(f"[ITERASYON] suclu kule: {len(suclular)} yerlesim"
            f" (tepe > {butce_vox * pitch:.1f}mm ve cerceve-dolu altinda)")
        if suclular:
            sucset = set(suclular)
            b2 = Bin3D(pw, pd, pitch, no_go_mask=mask)
            for k_, (pid_, oi_, x_, y_, z_) in enumerate(pls):
                if k_ in sucset:
                    continue
                f_, top_ = prof[pid_][oi_]
                sub = b2.height[x_:x_ + f_.shape[0], y_:y_ + f_.shape[1]]
                np.copyto(sub, np.maximum(sub, z_ + top_), where=f_)
            # kanopi yeniden-argmin (tum azimutlar)
            en2 = None
            for oi2, o2 in enumerate(vpk.orientations):
                Z2 = b2.drop_map(o2)
                if Z2 is None:
                    continue
                Z2m = np.where(Z2 >= Bin3D.NO_GO_SEAL,
                               np.iinfo(np.int32).max, Z2)
                if Z2m.min() >= np.iinfo(np.int32).max:
                    continue
                x2, y2 = np.unravel_index(int(Z2m.argmin()), Z2m.shape)
                z2 = int(Z2m.min()) + z_gap
                t2 = z2 + o2.grid.shape[2]
                if en2 is None or t2 < en2[0]:
                    en2 = (t2, oi2, int(x2), int(y2), z2)
            if en2 is None:
                raise RuntimeError("iterasyonda kanopi drop edilemedi")
            t2, oi2, x2, y2, z2 = en2
            o2 = vpk.orientations[oi2]
            f2, top2 = o2.filled, o2.top
            sub = b2.height[x2:x2 + f2.shape[0], y2:y2 + f2.shape[1]]
            np.copyto(sub, np.maximum(sub, z2 + top2), where=f2)
            log(f"[ITERASYON] kanopi: rot={[0, 90, 180, 270][oi2]}"
                f" x={x2 * pitch:.1f} y={y2 * pitch:.1f} z={z2 * pitch:.1f}")
            # suclulari kanopi SONRASI tek tek drop et (kendi pozuyla)
            yeni_konum = {}
            for k_ in suclular:
                pid_, oi_, x_, y_, z_ = pls[k_]
                f_, top_ = prof[pid_][oi_]
                bot_ = None  # profilde bottom yok; drop_map orient ister —
                # sahte Orientation yerine: kendi drop'umuz (bottom=0 kabulu,
                # KONSERVATIF: parca tabani duz sayilir, z fazla tahmin
                # edilebilir — serh).
                w_, d_ = f_.shape
                H = b2.height
                nx2, ny2 = H.shape[0] - w_ + 1, H.shape[1] - d_ + 1
                if nx2 <= 0 or ny2 <= 0:
                    raise RuntimeError(f"suclu sigmiyor: {pid_}")
                # vektorize maskeli kayan-max (satir parcali; bottom=0
                # duz-kabul — SERH, clearance dogrular)
                sw = np.lib.stride_tricks.sliding_window_view(H, (w_, d_))
                best = None
                blok = 64
                for x0 in range(0, nx2, blok):
                    x1 = min(x0 + blok, nx2)
                    Zb = sw[x0:x1, :ny2][:, :, f_].max(axis=2)
                    Zb = np.where(Zb >= Bin3D.NO_GO_SEAL,
                                  np.iinfo(np.int32).max, Zb)
                    zi = int(Zb.min())
                    if zi >= np.iinfo(np.int32).max:
                        continue
                    bx, by = np.unravel_index(int(Zb.argmin()), Zb.shape)
                    if best is None or zi < best[0]:
                        best = (zi, x0 + int(bx), int(by))
                if best is None:
                    raise RuntimeError(f"suclu drop edilemedi: {pid_}")
                zi, xx, yy = best
                zz = zi + z_gap
                tt = zz + int(top_[f_].max())
                sub = b2.height[xx:xx + w_, yy:yy + d_]
                np.copyto(sub, np.maximum(sub, zz + top_), where=f_)
                yeni_konum[k_] = (xx, yy, zz)
            Hs = np.where(b2.height >= Bin3D.NO_GO_SEAL, 0, b2.height)
            iter_toplam = float(Hs.max()) * pitch
            log(f"[ITERASYON] SONUC toplam={iter_toplam:.2f}mm"
                f" (naif {toplam_mm:.2f} -> kazanc"
                f" {toplam_mm - iter_toplam:+.2f}mm; SERH: suclu-drop taban"
                " profili duz-kabul, clearance asagida dogrulanir)")
            # clearance icin mesh guncelle: tasinanlar delta-cevrilir
            for k_, (xx, yy, zz) in yeni_konum.items():
                pid_, oi_, x_, y_, z_ = pls[k_]
                meshes[k_].apply_translation([
                    (xx - x_) * pitch, (yy - y_) * pitch, (zz - z_) * pitch])
            mk2 = mesh0.copy()
            mk2.apply_transform(rots[oi2])
            mk2.apply_translation(-mk2.bounds[0])
            mk2.apply_translation([x2 * pitch, y2 * pitch, z2 * pitch])
            rep2 = min_clearance(list(meshes) + [mk2], samples_per_mesh=6000)
            log(f"[ITERASYON] clearance min={float(rep2.min_mm):.3f}mm")
            iter_sonuc = {
                "toplam_mm": iter_toplam, "suclu_sayisi": len(suclular),
                "kanopi": {"rot_deg": [0, 90, 180, 270][oi2],
                           "x_mm": x2 * pitch, "y_mm": y2 * pitch,
                           "z_mm": z2 * pitch},
                "clearance_mm": float(rep2.min_mm),
                "serh": "suclu-drop bottom-duz kabulu (konservatif-degil, "
                        "clearance olcumu dogrular)",
            }
            # iterasyon mesh'leri tasidi — naif clearance artik OLCULMEZ
            # (naif clearance yukarida zaten loglandi ilk kosuda; burada
            # yalniz iterasyon dogrulanir).
    except Exception as e:
        log(f"[ITERASYON] atlandi/hata: {type(e).__name__}: {e}")
        log(traceback.format_exc())

    # ---- V5: cok-turlu + boy-sirali + azimutlu kule-drop ------------------
    # v4'un kalan makas adresleri (Eren: "plan 1'i gelistir", 2026-08-04):
    # (1) tasinan kule kendi TEK pozuyla dusuyordu -> 4 rot90 azimut denenir
    #     (profil rot90 = fiziksel Rz; mesh tarafi da Rz ile birebir),
    # (2) boy-sirali tasima (uzun once, iyi delikleri uzunlar alir),
    # (3) cok-tur: tasima sonrasi yeni tavan sucluysa o da tasinir (maks 4).
    iter2_sonuc = None
    try:
        butce_vox = int(tel["ideal_alt_butce_mm"] / pitch)
        INTMAX = np.iinfo(np.int32).max

        def _tepe_vox(k_):
            pid_, oi_, _x, _y, z_ = pls[k_]
            f_, top_ = prof[pid_][oi_]
            return int(z_ + top_[f_].max()) if f_.any() else 0

        def _swdrop(H, f_, top_):
            """Vektorize maskeli kayan-min-drop; (tepe,x,y,z) veya None."""
            w_, d_ = f_.shape
            nx2, ny2 = H.shape[0] - w_ + 1, H.shape[1] - d_ + 1
            if nx2 <= 0 or ny2 <= 0 or not f_.any():
                return None
            sw = np.lib.stride_tricks.sliding_window_view(H, (w_, d_))
            tm = int(top_[f_].max())
            best = None
            for x0 in range(0, nx2, 64):
                x1 = min(x0 + 64, nx2)
                Zb = sw[x0:x1, :ny2][:, :, f_].max(axis=2)
                Zb = np.where(Zb >= Bin3D.NO_GO_SEAL, INTMAX, Zb)
                zi = int(Zb.min())
                if zi >= INTMAX:
                    continue
                bx, by = np.unravel_index(int(Zb.argmin()), Zb.shape)
                if best is None or zi < best[3] - z_gap:
                    best = (zi + z_gap + tm, x0 + int(bx), int(by),
                            zi + z_gap)
            return best

        cikar: set = set()
        final = None
        for tur in range(1, 5):
            # (a) cikar-haric replay
            b5 = Bin3D(pw, pd, pitch, no_go_mask=mask)
            for k_, (pid_, oi_, x_, y_, z_) in enumerate(pls):
                if k_ in cikar:
                    continue
                f_, top_ = prof[pid_][oi_]
                sub = b5.height[x_:x_ + f_.shape[0], y_:y_ + f_.shape[1]]
                np.copyto(sub, np.maximum(sub, z_ + top_), where=f_)
            # (b) kanopi argmin
            en5 = None
            for oik, ok in enumerate(vpk.orientations):
                Zk = b5.drop_map(ok)
                if Zk is None:
                    continue
                Zkm = np.where(Zk >= Bin3D.NO_GO_SEAL, INTMAX, Zk)
                if int(Zkm.min()) >= INTMAX:
                    continue
                xk, yk = np.unravel_index(int(Zkm.argmin()), Zkm.shape)
                zk = int(Zkm.min()) + z_gap
                tk = zk + ok.grid.shape[2]
                if en5 is None or tk < en5[0]:
                    en5 = (tk, oik, int(xk), int(yk), zk)
            if en5 is None:
                raise RuntimeError("v5: kanopi drop edilemedi")
            _tk, oik, xk, yk, zk = en5
            # (c) guncel kanopi dolu-bolgesine gore yeni suclular
            fK = vpk.orientations[oik].filled
            cd = np.zeros_like(b5.height, dtype=bool)
            cd[xk:xk + fK.shape[0], yk:yk + fK.shape[1]] = fK
            yeni = []
            for k_, (pid_, oi_, x_, y_, z_) in enumerate(pls):
                if k_ in cikar or _tepe_vox(k_) <= butce_vox:
                    continue
                f_, _t = prof[pid_][oi_]
                if (cd[x_:x_ + f_.shape[0], y_:y_ + f_.shape[1]] & f_).any():
                    yeni.append(k_)
            if yeni and tur < 4:
                cikar |= set(yeni)
                log(f"[V5 tur-{tur}] kanopi z={zk * pitch:.1f}; +{len(yeni)}"
                    f" suclu (toplam {len(cikar)}) -> sonraki tur")
                continue
            # (d) final kompozisyon: kanopi place + boy-sirali azimutlu drop
            ok = vpk.orientations[oik]
            sub = b5.height[xk:xk + fK.shape[0], yk:yk + fK.shape[1]]
            np.copyto(sub, np.maximum(sub, zk + ok.top), where=fK)
            konum = {}
            for k_ in sorted(cikar, key=_tepe_vox, reverse=True):
                pid_, oi_, _x, _y, _z = pls[k_]
                fS, tS = prof[pid_][oi_]
                best = None
                for rk in range(4):
                    fr, tr = np.rot90(fS, rk), np.rot90(tS, rk)
                    d_ = _swdrop(b5.height, fr, tr)
                    if d_ is not None and (best is None or d_[0] < best[0]):
                        best = (d_[0], rk, d_[1], d_[2], d_[3])
                if best is None:
                    raise RuntimeError(f"v5: kule drop edilemedi {pid_}")
                _tt, rk, xx, yy, zz = best
                fr, tr = np.rot90(fS, rk), np.rot90(tS, rk)
                sub = b5.height[xx:xx + fr.shape[0], yy:yy + fr.shape[1]]
                np.copyto(sub, np.maximum(sub, zz + tr), where=fr)
                konum[k_] = (rk, xx, yy, zz)
            H5 = np.where(b5.height >= Bin3D.NO_GO_SEAL, 0, b5.height)
            v5_toplam = float(H5.max()) * pitch
            log(f"[V5] SONUC tur={tur} toplam={v5_toplam:.2f}mm"
                f" (tasinan {len(cikar)}; kanopi z={zk * pitch:.1f}"
                f" rot={[0, 90, 180, 270][oik]})")
            # (e) clearance — orijinal mesh yedeklerinden kesin kurulum
            v5_meshes = []
            for k_, m0 in enumerate(meshes_orig):
                m = m0.copy()
                if k_ in konum:
                    pid_, oi_, x_, y_, z_ = pls[k_]
                    rk, xx, yy, zz = konum[k_]
                    m.apply_translation([-x_ * pitch, -y_ * pitch,
                                         -z_ * pitch])
                    if rk:
                        import trimesh.transformations as tt
                        m.apply_transform(
                            tt.rotation_matrix(np.deg2rad(90 * rk),
                                               [0, 0, 1]))
                        b0 = m.bounds[0]
                        m.apply_translation([-b0[0], -b0[1], 0.0])
                    m.apply_translation([xx * pitch, yy * pitch, zz * pitch])
                v5_meshes.append(m)
            mk5 = mesh0.copy()
            mk5.apply_transform(rots[oik])
            mk5.apply_translation(-mk5.bounds[0])
            mk5.apply_translation([xk * pitch, yk * pitch, zk * pitch])
            rep5 = min_clearance(v5_meshes + [mk5], samples_per_mesh=6000)
            log(f"[V5] clearance min={float(rep5.min_mm):.3f}mm")
            iter2_sonuc = {
                "toplam_mm": v5_toplam, "tur": tur,
                "tasinan": len(cikar),
                "kanopi": {"rot_deg": [0, 90, 180, 270][oik],
                           "x_mm": xk * pitch, "y_mm": yk * pitch,
                           "z_mm": zk * pitch},
                "clearance_mm": float(rep5.min_mm),
                "serh": "kule-drop bottom-duz kabulu; azimut rot90; "
                        "clearance mesh-kesin olculdu",
            }
            break
    except Exception as e:
        log(f"[V5] atlandi/hata: {type(e).__name__}: {e}")
        log(traceback.format_exc())

    OUT.write_text(json.dumps({
        "serh": "kanopi on-olcumu; kilit olculmedi; tek-set (A11)",
        "kanopi_parca": str(p0.name), "fizibilite": fiz,
        "asama1_h_mm": h1, "kanopi": kanopi_mm,
        "toplam_mm": toplam_mm, "clearance_mm": clear,
        "iterasyon": iter_sonuc,
        "iterasyon_v5": iter2_sonuc,
        "v6_modu": bool(V6),
        "v6_pin_sayisi": (len(v6_pins) if v6_pins else 0),
        "v7_modu": bool(V7),
        "v7_kilitli_tipler": (sorted(v7_overrides) if v7_overrides else []),
        "telemetri": tel, "ref": REF, "seed": SEED,
        "pitch": pitch, "nogo": eg.NOGO_STD,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"KIYAS: hard {REF['hard']:.1f} | raw {REF['raw']:.1f} | pin"
        f" {REF['pin_k56f']:.1f} | NAIF-KANOPI {toplam_mm:.2f} | manuel"
        f" {REF['manuel']}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


def _guvenli_main():
    """Sessiz-olum kalkani: her istisna LOG dosyasina yazilir (stderr'in
    detach yapilandirmasinda kaybolabildigi 2026-08-04 dersi)."""
    try:
        main()
    except BaseException as e:  # MemoryError dahil
        try:
            log(f"FATAL: {type(e).__name__}: {e}")
            log(traceback.format_exc())
            log("BITTI")
        finally:
            raise


if __name__ == "__main__":
    _guvenli_main()

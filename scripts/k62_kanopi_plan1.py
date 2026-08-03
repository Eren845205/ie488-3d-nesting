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
import json
import math
import sys
import time
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


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


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
    r1, nfv_tel = eg._run_champion("plan1", inst2, SEED,
                                   extra_rot_overrides={})
    h1 = float(r1.height_mm)
    pitch = float(getattr(r1, "fine_pitch", fine_pitch))
    log(f"[ASAMA-1] h={h1:.2f}mm  n={getattr(r1, 'n_placed', '?')}"
        f"  sure={(time.perf_counter() - t1) / 60:.1f}dk  pitch={pitch}")

    # ---- asama-2: replay + kanopi drop ------------------------------------
    mask = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, pw, pd, pitch)
    b = Bin3D(pw, pd, pitch, no_go_mask=mask)
    vps = {vp.id: vp for vp in r1.fine_voxel_parts}
    replay_uyusmaz = 0
    for pl in r1.placements:
        vp = vps.get(pl.part_id)
        if vp is None:
            log(f"HATA: replay part bulunamadi: {pl.part_id}")
            log("BITTI")
            return
        b.place(vp, pl.orientation_idx, pl.x, pl.y, pl.z)
    log(f"[ASAMA-2] replay tamam ({len(r1.placements)} yerlesim)")

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

    # ---- clearance (serhli tam-olcum) -------------------------------------
    clear = None
    try:
        meshes = placed_meshes(r1.placements, r1.fine_voxel_parts, pitch)
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

    OUT.write_text(json.dumps({
        "serh": "naif kanopi on-olcumu; kilit olculmedi; tek-set (A11)",
        "kanopi_parca": str(p0.name), "fizibilite": fiz,
        "asama1_h_mm": h1, "kanopi": kanopi_mm,
        "toplam_mm": toplam_mm, "clearance_mm": clear,
        "telemetri": tel, "ref": REF, "seed": SEED,
        "pitch": pitch, "nogo": eg.NOGO_STD,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"KIYAS: hard {REF['hard']:.1f} | raw {REF['raw']:.1f} | pin"
        f" {REF['pin_k56f']:.1f} | NAIF-KANOPI {toplam_mm:.2f} | manuel"
        f" {REF['manuel']}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()

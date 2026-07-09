# -*- coding: utf-8 -*-
"""ax24_kuyruk_335.py — EKSEN-HIZALI SIKMA KUYRUGU @335+NOGO (kullanici karari
2026-07-07: 'rotasyona suc atmadan once eksen-hizali tavani OLC').

Sirayla (tek surec = RAM guvenli):
  0) BEKLE: plan1_uretim335 + plan3_replan_sq BITTI olana kadar (RAM cakismasi
     onceki plan1 kosusunu oldurdu — ders alindi).
  1) deneme5 n24  (n8 ref 329.4 / Magics 209)
  2) plan1   n24  (fit-guard pitch 1.0; n8 uretim kosusu ayri olculdu)
  3) plan2   n8   (335+nogo BASELINE — hic sayi yok; Magics 492.39)
  4) plan2   n24
  5) plan3   n24  (n8 ref 747 / Magics 593)
Her sette: uretim zinciri + no-go + legal metrik + STL (legal ise) +
HEIGHT-DRIVER ilk-10 dokumu + placements pickle (ayrilabilirlik probu icin).
Kosum: python -m scripts.ax24_kuyruk_335   SAF ASCII.
"""
from __future__ import annotations
import gc, pickle, sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.adaptive_params import predict_nfv_benefit
from src.nesting3d.tuner import build_menu
from scripts.eval_gate import legal_of
from scripts.c3_generality import DATASETS
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM, COARSE_BUDGET

LOG = Path(__file__).parent / "ax24_kuyruk_335.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
BEKLE = [Path(__file__).parent / "plan1_uretim335.log",
         Path(__file__).parent / "plan3_replan_sq.log"]
REF = {"deneme5": (329.4, 209.0), "plan1": (None, 110.41),
       "plan2": (None, 492.39), "plan3": (747.0, 593.0)}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _load(name, plate):
    if name == "deneme5":
        D = _ROOT / "data" / "mail_stl" / "deneme5"
        qty = {}
        for line in (D / "_adet_listesi.txt").read_text(encoding="utf-8").splitlines():
            if " - " in line:
                ad, s = line.rsplit(" - ", 1)
                qty[ad.strip()] = int(s)
        stl_map = {f.stem: f.read_bytes() for f in sorted(D.glob("*.stl"))
                   if not f.stem.startswith("_")}
    else:
        cfg = DATASETS[name]
        stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
        qty = cfg["qty"]
    res = build_instance_from_order(
        stl_map, qty, persist_dir=_ROOT / "data" / "mail_stl" / f"gen_{name}_335",
        container_w_mm=plate[0], container_d_mm=plate[1])
    return res.instance


def kos(name, n_or, pitch_force=None, clearance_mm=None):
    etiket = f"{name}_n{n_or}"
    t = time.perf_counter()
    inst = _load(name, PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    dec = predict_nfv_benefit(inst, family_routing=True)
    wall = bool(getattr(dec, "wall_aware", False))
    onerilen = suggest_pitch(inst, wall_aware=wall)
    pitch = pitch_force if (pitch_force is not None and onerilen > pitch_force) else onerilen
    log(f"[{etiket}] n_total={n_total} wall={wall} pitch={pitch}"
        f"{' (fit-guard)' if pitch != onerilen else ''}")
    # fit-guard aktifse coarse asamaya da uygula (plan1 baseplate dersi:
    # otomatik kaba pitch'te sigmayan parca coarse'da AssertionError'la olduruyor)
    # drop_cache HER SETTE acik (2026-07-08 hizlanma karari): H-16 dirty-region
    # onbellegi BIT-OZDES kanitli (K-19 282.0 birebir, %90.3 hit) — wall_aware
    # kapisi bellek gerekcesiydi, 300MB cap zaten var. Kaliteye etki SIFIR.
    kw = dict(coarse_pitch=(pitch if pitch != onerilen else None),
              fine_pitch=pitch, budget=COARSE_BUDGET,
              seed=42, n_orientations=n_or, drop_cache=True,
              skip_fine_angle=wall,
              clearance_mm=(clearance_mm if clearance_mm is not None else WEB_MIN_CLEARANCE_MM),
              no_go_bounds=NOGO)
    if wall or pitch != onerilen:
        # fit-guard'li sette tam-portfoy@ince-pitch 8h+ yakti (plan1 dersi,
        # 2026-07-08 gece) -> dblf_only menusu zorunlu
        kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
    try:
        r = solve_coarse_to_fine(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1], **kw)
    except Exception as e:
        log(f"[{etiket}] EXCEPTION: {e}")
        return
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    ref8, magics = REF.get(name, (None, None))
    kiyas = ""
    if legal is not None:
        if ref8:
            kiyas += f"  n8'e: {legal - ref8:+.1f}"
        if magics:
            kiyas += f"  Magics'e: +%{(legal / magics - 1) * 100:.1f}"
    log(f"[{etiket}] h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}{kiyas}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    # HEIGHT-DRIVER: tepe kuleyi kuran ilk-10 parca
    px = float(r.fine_pitch)
    tops = []
    for p in r.placements:
        g = r.fine_voxel_parts[p.part_id].orientations[p.orientation_idx].grid
        ad = getattr(r.fine_voxel_parts[p.part_id], "name", p.part_id)
        tops.append(((p.z + g.shape[2]) * px, str(ad)))
    tops.sort(reverse=True)
    log(f"[{etiket}] height-driver ilk10: "
        + " | ".join(f"{h:.0f}:{a[:28]}" for h, a in tops[:10]))
    out = _ROOT / "results" / f"{etiket}_placements.pkl"
    with out.open("wb") as fh:
        pickle.dump({"placements": r.placements, "pitch": px,
                     "n_or": n_or, "set": name}, fh)
    if legal is not None:
        stl = _ROOT / "results" / f"{etiket}_nogo335_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(stl)
        log(f"[{etiket}] STL: {stl}")
    del r, meshes, inst
    gc.collect()


def main():
    # 2026-07-08 devam: deneme5_n24 (280.8) + plan1_n24 (260.0) ILK turda OLCULDU;
    # PC kapaninca plan2_n8 yarim kaldi. BEKLE on-kosullari BITTI (loglar duruyor).
    LOG.write_text("", encoding="utf-8")
    # sira 2026-07-08: plan3_n24 ONE alindi (n24 kablolama teyidini en erken
    # verir; plan2_n8 tam-portfoy@0.5 suresi belirsiz — en sona)
    # plan3_n24 OLCULDU (719.0 legal, None.exterior fix'li kosu) — cikarildi.
    # Yeniden baslatma nedeni (2026-07-08 16:5x): coarse drop_cache kablosu
    # (py-spy kaniti) — plan2 bacaklari cache'li kodla kosacak.
    log("AX24 KUYRUK @335+NOGO — plan2 turu (n24 -> n8), coarse drop_cache ACIK")
    kos("plan2", 24)
    kos("plan2", 8)
    log("BITTI")


if __name__ == "__main__":
    main()

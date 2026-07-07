# -*- coding: utf-8 -*-
"""plan3_fine_arama.py — PLAN3 FINE-ASAMA YEREL ARAMA PROTOTIPI (D basamagi).

SORUN
-----
coarse_to_fine yolunda arama (tuner/SA) YALNIZ coarse pitch'te yapiliyor; FINE
asama coarse'un sira+pozlarini greedy replay ediyor (place_in_order). Yani ince
cozunurlukte hicbir yerel arama YOK. Bu prototip hipotezi test eder: fine
yerlesim uzerinde yerel arama (sira-swap + poz-degisim, hill-climb) legal
sampiyon 693'u anlamli dusurur mu?

YAKLASIM (uretim src'ye DOKUNMADAN)
----------------------------------
1. solve_coarse_to_fine kazanan configle BIR KEZ kosulur (w90 step15 n8 b70
   seed13 -> beklenen 693). Donen fine_voxel_parts (ince-aci adaylariyla) +
   yerlesim-sirasi + poz-secimi cikartilir.
2. Fine yerlesim DISARIDA yeniden ifade edilir: order (parca-id dizisi) +
   orient_choice (parca basi poz-indeksi). place_in_order tek sabit poz ile
   cagrilinca kazanan cozum BIREBIR yeniden uretilir (correctness anchor).
3. Yerel arama: rastgele
     - sira-swap (iki parca yer degistirir), veya
     - poz-degisim (bir parcanin poz-indeksi degisir)
   -> place_in_order yeniden -> (max_height_voxels, rms) lexicografik iyilesirse
   KABUL (sicaklsiz hill-climb; esitlikte rms plato-yuruyusu). Sure butcesi
   parametreli (default 30 dk).
4. Her iyilesmede log satiri: h=...  Sonda en iyi cozum legal dogrulanir
   (min_clearance>=1 + 0 kilit + 109/109) ve STL results/ altina yazilir.

Kosum: python -m scripts.plan3_fine_arama [--budget-min 30] [--seed 13]
SAF ASCII stdout (cp1254 guvenli); log scripts/plan3_fine_arama.log.
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
import time
from pathlib import Path

import trimesh

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import place_in_order
from src.nesting3d.coarse_to_fine import (
    solve_coarse_to_fine, clearance_to_voxels)
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.pitch import suggest_pitch
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "plan3_fine_arama.log"
OUT_DIR = _ROOT / "results" / "plan3_fine_arama"
PLATE = (328.74, 328.19)          # plan3_acili_prob ile ayni
CLEARANCE_MM = 1.0
# Kazanan config (plan3_acili_prob: w90_b70_seed13 OLCULDU 693.0 LEGAL)
CHAMP = dict(n_orientations=8, budget=70, seed=13,
             fine_angle_window=90.0, fine_angle_step=15.0, fine_angle_axes="z")
REF_HEIGHT = 693.0
MAGICS = 593.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


# ---------------------------------------------------------------------------
# Fine yerlesim degerlendirici (uretim src'ye dokunmadan, disarida)
# ---------------------------------------------------------------------------

def _place(order, orient_choice, parts_by_id, pw, pd, fine_pitch, fine_zc):
    """order + poz-secimiyle fine yerlesim -> (bin, placements).

    Sabit tek-poz place_in_order: her parca yalniz orient_choice[id] pozunu
    dener (_best_position argmin ile x/y/z secer). Poz sigmazsa place_in_order
    guvenli-fallback ile tum pozlari dener (robustluk) -> asla cokmez.
    """
    ordered = [parts_by_id[pid] for pid in order]
    b = Bin3D(pw, pd, fine_pitch, z_clearance=fine_zc, drop_cache=True)
    pls = place_in_order(ordered, b, lambda i, part: (orient_choice[part.id],))
    return b, pls


def _obj(b):
    """Lexicografik hedef: (max_height_voxels, rms_height_mm). Kucuk = iyi.
    Yukseklik birincil; esitlikte rms plato-yuruyusu (yiginn duzlesmesi)."""
    return (int(b.max_height_voxels()), round(float(b.rms_height_mm()), 6))


def _sync_state(pls):
    """Yerlesimden guncel (order, orient_choice) durumunu turet (fallback dahil)."""
    order = [pl.part_id for pl in pls]
    orient = {pl.part_id: int(pl.orientation_idx) for pl in pls}
    return order, orient


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

CACHE = OUT_DIR / "champion_cache.pkl"


def build_champion(use_cache=True):
    """Kazanan configi kos -> (r, n_total, fine_pitch, fine_zc).

    ~50 dk suren fine-angle cozumu (window=90/step=15) TEK KEZ kosulur ve
    pickle'lanir; sonraki kosular onbellekten yukler (place/orient/parts).
    """
    # NOT (guvenlik): pickle YALNIZ bu scriptin kendi yazdigi yerel onbellek
    # dosyasini okur/yazar (guvenilir, kendi urettigi veri) — dis girdi DEGIL.
    if use_cache and CACHE.exists():
        try:
            d = pickle.loads(CACHE.read_bytes())
            log(f"[cache] champion onbellekten yuklendi ({CACHE.name}): "
                f"h={d['height_mm']:.1f}mm  fine_pitch={d['fine_pitch']:.4f}")
            return (d["r"], d["n_total"], float(d["fine_pitch"]),
                    int(d["fine_zc"]))
        except Exception as e:  # onbellek bozuksa yeniden coz
            log(f"[cache] onbellek okunamadi ({e}) — yeniden cozuluyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    log(f"[coarse-to-fine] plan3 kosuluyor (n={n_total}, fine_pitch={pitch:.4f}, "
        f"config={CHAMP}) ...")
    t = time.perf_counter()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        coarse_pitch=None, fine_pitch=pitch, clearance_mm=CLEARANCE_MM, **CHAMP)
    dt = (time.perf_counter() - t) / 60.0
    _fm, fine_zc = clearance_to_voxels(CLEARANCE_MM, pitch)
    log(f"[coarse-to-fine] bitti: h={r.height_mm:.1f}mm  n_placed={r.n_placed}  "
        f"aci_kullanildi={r.fine_angle_used}  fine_zc={fine_zc}  ({dt:.1f} dk)")

    if use_cache:  # local search icin yeterli alt kume; bozulursa sessiz gec
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "r": r, "n_total": n_total, "fine_pitch": float(pitch),
                "fine_zc": int(fine_zc), "height_mm": float(r.height_mm),
            }
            CACHE.write_bytes(pickle.dumps(payload, protocol=4))
            log(f"[cache] champion onbellege yazildi: {CACHE} "
                f"({CACHE.stat().st_size / 1e6:.0f}MB)")
        except Exception as e:
            log(f"[cache] onbellege yazilamadi ({e}) — atlaniyor")
    return r, n_total, float(pitch), int(fine_zc)


def local_search(r, n_total, fine_pitch, fine_zc, seed, budget_s):
    """Fine yerlesim uzerinde hill-climb. En iyi (order, orient, bin, pls) doner."""
    parts_by_id = r.fine_voxel_parts
    pw, pd = PLATE

    # --- baslangic durumu = kazanan cozum (correctness anchor) ---
    order = [pl.part_id for pl in r.placements]
    orient = {pl.part_id: int(pl.orientation_idx) for pl in r.placements}
    b0, pls0 = _place(order, orient, parts_by_id, pw, pd, fine_pitch, fine_zc)
    cur_key = _obj(b0)
    h0_mm = b0.max_height_mm()
    log(f"[anchor] yeniden-yerlesim: h={h0_mm:.1f}mm  key={cur_key}  "
        f"(kazanan {r.height_mm:.1f}mm ile fark={abs(h0_mm - r.height_mm):.3f})")
    if abs(h0_mm - r.height_mm) > 1e-6:
        log("[anchor] UYARI: yeniden-yerlesim kazanani birebir uretmedi "
            "(beklenmedik) — yine de en iyi taban olarak devam.")

    # calisilan durum
    order = list(order)
    orient = dict(orient)
    ids = list(order)
    # her parcanin secilebilir poz sayisi
    n_orients = {pid: len(parts_by_id[pid].orientations) for pid in ids}
    multi_pos_ids = [pid for pid in ids if n_orients[pid] > 1]

    best_key = cur_key
    best_order, best_orient = list(order), dict(orient)
    best_bin, best_pls = b0, pls0
    # iyilesme kontrol-noktalari (legal fallback icin): (key, order, orient)
    checkpoints = [(best_key, list(best_order), dict(best_orient))]

    rng = random.Random(seed)
    t0 = time.perf_counter()
    it = 0
    accepts = 0
    last_report = t0
    while time.perf_counter() - t0 < budget_s:
        it += 1
        # --- komsu uret ---
        cand_order, cand_orient = list(order), dict(orient)
        do_swap = (not multi_pos_ids) or rng.random() < 0.7
        if do_swap:
            i = rng.randrange(len(cand_order))
            j = rng.randrange(len(cand_order))
            if i == j:
                continue
            cand_order[i], cand_order[j] = cand_order[j], cand_order[i]
        else:
            pid = rng.choice(multi_pos_ids)
            k = n_orients[pid]
            new_oi = rng.randrange(k)
            if new_oi == cand_orient[pid]:
                new_oi = (new_oi + 1) % k
            cand_orient[pid] = new_oi

        b, pls = _place(cand_order, cand_orient, parts_by_id,
                        pw, pd, fine_pitch, fine_zc)
        cand_key = _obj(b)

        if cand_key < cur_key:
            # KABUL — durumu gercek yerlesimle senkronla (fallback dahil)
            order, orient = _sync_state(pls)
            cur_key = cand_key
            accepts += 1
            if cand_key < best_key:
                best_key = cand_key
                best_order, best_orient = list(order), dict(orient)
                best_bin, best_pls = b, pls
                checkpoints.append((best_key, list(order), dict(orient)))
                log(f"  [iter {it}] IYILESME  h={b.max_height_mm():.1f}mm  "
                    f"key={cand_key}  (kabul#{accepts}, "
                    f"{(time.perf_counter() - t0) / 60:.1f} dk)")

        if time.perf_counter() - last_report > 120:
            last_report = time.perf_counter()
            log(f"  ... iter={it}  kabul={accepts}  en_iyi={best_key[0]} vox "
                f"({best_bin.max_height_mm():.1f}mm)  "
                f"({(time.perf_counter() - t0) / 60:.1f} dk)")

    log(f"[arama] bitti: iter={it}  kabul={accepts}  "
        f"en_iyi_key={best_key}  h={best_bin.max_height_mm():.1f}mm  "
        f"({(time.perf_counter() - t0) / 60:.1f} dk)")
    return best_order, best_orient, best_bin, best_pls, checkpoints, parts_by_id


def main():
    ap = argparse.ArgumentParser(description="PLAN3 fine-asama yerel arama prototipi")
    ap.add_argument("--budget-min", type=float, default=30.0,
                    help="yerel arama sure butcesi (dakika, default 30)")
    ap.add_argument("--seed", type=int, default=13, help="arama rastgele tohumu")
    ap.add_argument("--solve-only", action="store_true",
                    help="yalniz ~50dk kazanan cozumu uret+onbellekle, arama YAPMA "
                         "(arka-plan sure limitine takilmadan cache uretmek icin)")
    args = ap.parse_args()

    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("PLAN3 FINE-ASAMA YEREL ARAMA PROTOTIPI (D)")
    log(f"ref legal={REF_HEIGHT} / Magics={MAGICS} / plaka={PLATE} / "
        f"clearance={CLEARANCE_MM}mm / butce={args.budget_min}dk / seed={args.seed}"
        + ("  [SOLVE-ONLY]" if args.solve_only else ""))
    log("=" * 78)

    r, n_total, fine_pitch, fine_zc = build_champion()

    if args.solve_only:
        log("[solve-only] champion uretildi + onbelleklendi; arama atlaniyor.")
        log("BITTI")
        return

    (best_order, best_orient, best_bin, best_pls,
     checkpoints, parts_by_id) = local_search(
        r, n_total, fine_pitch, fine_zc, args.seed, args.budget_min * 60.0)

    # --- legal dogrulama: en iyiden geriye kontrol-noktalari (kilit/clearance
    #     sira ile degisebilir -> ilk LEGAL olan secilir) ---
    log("-" * 78)
    log("[legal] en iyiden geriye kontrol-noktalari dogrulaniyor...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chosen = None
    # checkpoints artan key sirasinda -> tersten (en iyi once)
    for key, c_order, c_orient in reversed(checkpoints):
        b, pls = _place(c_order, c_orient, parts_by_id,
                        *PLATE, fine_pitch, fine_zc)
        h_mm = b.max_height_mm()
        meshes = placed_meshes(pls, parts_by_id, fine_pitch)
        rep = min_clearance(meshes)
        acc = check_placements(pls, parts_by_id)
        legal, reason = legal_of(h_mm, len(pls), n_total,
                                 float(rep.min_mm), int(acc.n_locked),
                                 clearance_req=CLEARANCE_MM)
        tag = f"{legal:.1f}" if legal is not None else f"INVALID({reason})"
        log(f"  key={key} h={h_mm:.1f}mm  legal={tag}  "
            f"clear={rep.min_mm:.3f}  kilit={acc.n_locked}")
        if legal is not None:
            chosen = (h_mm, pls, meshes, rep, acc)
            break

    log("-" * 78)
    if chosen is None:
        log("[SONUC] hicbir kontrol-noktasi LEGAL degil — prototip legal "
            "iyilesme bulamadi. Baslangic 693 legal sampiyon KORUNUR.")
        log("BITTI")
        return

    h_mm, pls, meshes, rep, acc = chosen
    stl_path = OUT_DIR / "plan3_fine_arama_best.stl"
    combined = trimesh.util.concatenate(meshes)
    combined.export(str(stl_path))
    summary = {
        "ref_baseline_legal_mm": REF_HEIGHT,
        "magics_mm": MAGICS,
        "achieved_legal_mm": round(float(h_mm), 3),
        "delta_vs_baseline_mm": round(float(h_mm) - REF_HEIGHT, 3),
        "delta_vs_baseline_pct": round((float(h_mm) - REF_HEIGHT)
                                       / REF_HEIGHT * 100.0, 2),
        "min_clearance_mm": round(float(rep.min_mm), 4),
        "n_locked": int(acc.n_locked),
        "n_placed": len(pls),
        "n_total": n_total,
        "plate": list(PLATE),
        "fine_pitch": fine_pitch,
        "seed": args.seed,
        "budget_min": args.budget_min,
        "stl": str(stl_path),
    }
    json_path = OUT_DIR / "plan3_fine_arama_best.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True),
                         encoding="utf-8")

    log(f"[SONUC] baslangic {REF_HEIGHT:.1f}mm -> ulasilan LEGAL {h_mm:.1f}mm  "
        f"(delta {summary['delta_vs_baseline_mm']:+.1f}mm / "
        f"{summary['delta_vs_baseline_pct']:+.2f}%)")
    log(f"[legal-kanit] clearance={rep.min_mm:.3f}mm>=1  kilit={acc.n_locked}=0  "
        f"yerlesim={len(pls)}/{n_total}")
    log(f"[yazildi] STL: {stl_path}")
    log(f"[yazildi] ozet: {json_path}")
    log("BITTI")


if __name__ == "__main__":
    main()

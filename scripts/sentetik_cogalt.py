# -*- coding: utf-8 -*-
"""sentetik_cogalt.py — sentetik cogaltma kosucusu (ML plani / 01_VERI §6).

Amac: mod-secici ogrenmenin veri darbogazini kirmak. Egitim tablosunda
kabuk (shell_bells), boru (hollow_tubes) ve tekrarli-cubuk (repeat_rod_mix)
ailelerinin SIFIR ornegi vardi (d4/d5-tipi siparisleri model hic goremiyordu);
mevcut 6 ailenin de mod-duzeyi (heightmap-vs-nfv) satiri yoktu (v1 yalniz
solver-duzeyi). Bu kosucu:
  1. Deterministik sweep listesi kurar (yeni 3 aile + cekirdek ailelerin
     perturb varyantlari; sabit seed'ler).
  2. Her instance'ta IKI arm kosar:
       heightmap = eval_gate._run_champion (URETIM PARITESI: F5 routing +
                   suggest_pitch + c2f — elle config yok)
       nfv       = solve_nfv_kalite (quality=fast, r11=False — saf mod olcumu)
  3. Legal metrik (min_clearance 3000 + 5-yon kilit) + kxx_telemetri.kaydet
     ile runs_v2 satiri (kaynak-izli, ozellik-vektorlu).
Sure guard'i: arm basina time_budget; tek instance asamaz. Idempotens:
kosu_id deterministik — tekrar kosumda mevcut kosu_id'ler atlanir.
Kosum: python -m scripts.detach_run sentetik_cogalt    SAF ASCII.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.synthetic import (
    few_large_many_small, high_qty_repeat, hollow_tubes, long_rods,
    perturb_instance, random_boxes, repeat_rod_mix, shell_bells, thin_plates)
from src.nesting3d.nfv_solve import solve_nfv_kalite
from src.nesting3d.telemetry import V2_DEFAULT_PATH, load_telemetry
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "sentetik_cogalt.log"
ARM_BUDGET_S = 300.0
CLEAR_REQ = 2.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def sweep_listesi():
    """Deterministik (iid, instance) listesi. Hedef ~66 yeni instance."""
    out = []
    # YENI 3 aile (kapsam bosluklari) — 8'er varyant
    for s in range(8):
        out.append((f"syn_sb_s{s}", shell_bells(n_parts=6 + s % 4, seed=s)))
        out.append((f"syn_ht_s{s}", hollow_tubes(n_parts=6 + s % 4, seed=s)))
        out.append((f"syn_rrm_s{s}",
                    repeat_rod_mix(qty_per_rod=25 + 5 * s, seed=s)))
    # cekirdek ailelerin perturb varyantlari (2 baz x 3 jitter-seed)
    bazlar = [
        ("rb", lambda s: random_boxes(n_parts=12, seed=s)),
        ("flms", lambda s: few_large_many_small(seed=s)),
        ("hqr", lambda s: high_qty_repeat(seed=s)),
        ("tp", lambda s: thin_plates(seed=s)),
        ("lr", lambda s: long_rods(seed=s)),
    ]
    for ad, yap in bazlar:
        for bs in (0, 1):
            baz = yap(bs)
            for ps in (11, 22):
                out.append((f"syn_{ad}_b{bs}_p{ps}",
                            perturb_instance(baz, seed=ps)))
    return out


def _olc_ve_kaydet(iid, inst, arm, res, sure_s):
    parts = res.fine_voxel_parts
    pls = list(res.placements)
    n_total = sum(int(p.qty) for p in inst.parts)
    px = float(res.fine_pitch)
    try:
        kilit = int(check_separability_5dir(pls, parts).n_locked)
    except Exception:
        kilit = None
    try:
        rep = min_clearance(placed_meshes(pls, parts, px), samples_per_mesh=3000)
        clear = float(rep.min_mm)
    except Exception:
        clear = None
    kaydet(iid, ("nfv" if arm == "nfv" else "heightmap"),
           ("kalite" if arm == "nfv" else "champion"),
           float(res.height_mm), len(pls), n_total, clear, kilit, sure_s,
           kosu_id=f"SYNTH/{iid}/{arm}", log_yolu="scripts/sentetik_cogalt.log",
           pitch=px, seed=42, instance=inst, clearance_req_mm=CLEAR_REQ)
    log(f"[{iid}] {arm}: h={res.height_mm:.1f} clear={clear} kilit={kilit} "
        f"({sure_s/60:.1f} dk)")


def main():
    LOG.write_text("", encoding="utf-8")
    log("SENTETIK COGALTMA — yeni aileler + perturb; her instance 2 arm")
    mevcut = {r.get("kosu_id") for r in load_telemetry(_ROOT / V2_DEFAULT_PATH)}
    liste = sweep_listesi()
    log(f"sweep: {len(liste)} instance (~{2*len(liste)} arm kosusu)")
    n_yeni = n_atlanan = n_hata = 0
    for iid, inst in liste:
        for arm in ("heightmap", "nfv"):
            if f"SYNTH/{iid}/{arm}" in mevcut:
                n_atlanan += 1
                continue
            t = time.perf_counter()
            try:
                if arm == "nfv":
                    res, _tel = solve_nfv_kalite(
                        inst, plate_w_mm=float(inst.container.width_mm),
                        plate_d_mm=float(inst.container.depth_mm),
                        clearance_mm=CLEAR_REQ, quality="fast", seed=42,
                        time_budget_sec=ARM_BUDGET_S, r11=False)
                else:
                    from scripts.eval_gate import _run_champion
                    res = _run_champion(iid, inst, 42)
                _olc_ve_kaydet(iid, inst, arm, res,
                               time.perf_counter() - t)
                n_yeni += 1
            except Exception as e:
                n_hata += 1
                log(f"[{iid}] {arm} HATA: {type(e).__name__}: {e}")
    log(f"OZET: {n_yeni} yeni satir, {n_atlanan} atlanan, {n_hata} hata")
    log("BITTI")


if __name__ == "__main__":
    main()

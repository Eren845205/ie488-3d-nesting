# -*- coding: utf-8 -*-
"""plan13_tarama.py — Birlesik Plan1+Plan3 LEGAL yol konfig taramasi + kazanan STL.

Amac: hocaya yanlis (NFV-illegal: 0.083mm bosluk + kilitler) giden birlesik
Plan1+Plan3 STL'sinin DUZELTILMIS halini uretmek — ama tek atisla degil,
legal yol (heightmap + clearance_mm=1.0) uzerinde kucuk bir konfig taramasiyla
"elimizden gelen en iyi legal"i secip STL'sini yazmak.

Konfigler (SIRALI kosulur — RAM disiplinli; her biri legal-dogrulamali):
  ref   : budget=25  n=4  seed=42   (uretim webin bugunku default'u — referans)
  A     : budget=70  n=4  seed=42   (solve_coarse_to_fine gercek default butcesi)
  B     : budget=70  n=8  seed=42   (poz zenginlestirme)
  C     : budget=150 n=8  seed=42   (derin arama)
  + en iyi konfig seed 13 ve 7 ile tekrar (cesitlilik; en iyi LEGAL kazanir)

Metrik: legal_height (yerlesen==N ve min_clearance>=1.0 ve 0 kilit); INVALID
konfig ELENIR (yuksekligi kac olursa olsun). Kazanan: results/ altina STL +
JSON tablo. Plaka: hoca gercek plakasi 325x325 (335 - 2x5 kenar).

Kosum: python -m scripts.plan13_tarama   (~1.5-2.5 saat, 6 kosu)  SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh  # noqa: E402

from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.pitch import suggest_pitch  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402
from scripts.eval_gate import legal_of  # noqa: E402

LOG = Path(__file__).parent / "plan13_tarama.log"
OUT_DIR = _ROOT / "results"
PLATE = (325.0, 325.0)   # hoca 335x335x600, kenar 5mm
CLEARANCE = 1.0

BASE_CONFIGS = [
    ("ref_b25_n4_s42", dict(budget=25, n_orientations=4, seed=42)),
    ("A_b70_n4_s42", dict(budget=70, n_orientations=4, seed=42)),
    ("B_b70_n8_s42", dict(budget=70, n_orientations=8, seed=42)),
    ("C_b150_n8_s42", dict(budget=150, n_orientations=8, seed=42)),
]
EXTRA_SEEDS = (13, 7)


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _combined_instance():
    """Plan1 + Plan3 birlesik siparis (hocaya giden mail ile ayni icerik)."""
    stl_map = {}
    qty = {}
    for ds in ("plan1", "plan3"):
        cfg = DATASETS[ds]
        for f in sorted(cfg["stl_dir"].glob("*.stl")):
            stl_map[f.stem] = f.read_bytes()
        for k, v in cfg["qty"].items():
            if k in qty:
                raise RuntimeError(f"isim cakismasi: {k}")
            qty[k] = v
    res = build_instance_from_order(
        stl_map, qty,
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_plan13",
        container_w_mm=PLATE[0], container_d_mm=PLATE[1])
    return res.instance


def _run(inst, name, budget, n_orientations, seed, n_total):
    t = time.perf_counter()
    pitch = suggest_pitch(inst, wall_aware=False)
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        coarse_pitch=None, fine_pitch=pitch, budget=budget, seed=seed,
        n_orientations=n_orientations, clearance_mm=CLEARANCE)
    n_placed = int(getattr(r, "n_placed", len(r.placements)))
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), n_placed, n_total,
                             float(rep.min_mm), int(acc.n_locked),
                             clearance_req=CLEARANCE)
    dt = time.perf_counter() - t
    log(f"  [{name}] h={float(r.height_mm):7.1f}mm  legal="
        f"{(f'{legal:.1f}' if legal is not None else 'INVALID(' + str(reason) + ')')}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  pitch={pitch:.3f}"
        f"  ({dt / 60:.1f} dk)")
    return {"name": name, "budget": budget, "n_orientations": n_orientations,
            "seed": seed, "height_mm": float(r.height_mm),
            "legal_height_mm": legal, "invalid_reason": reason,
            "min_clearance_mm": float(rep.min_mm), "n_locked": int(acc.n_locked),
            "n_placed": n_placed, "pitch": float(pitch),
            "duration_min": round(dt / 60, 1)}, r, meshes


def main():
    LOG.write_text("", encoding="utf-8")
    t_all = time.perf_counter()
    log("=" * 78)
    log("PLAN1+PLAN3 BIRLESIK — legal yol konfig taramasi (duzeltilmis STL)")
    log(f"plaka {PLATE[0]:.0f}x{PLATE[1]:.0f}  clearance>={CLEARANCE}mm  "
        f"basladi {datetime.now().isoformat(timespec='seconds')}")
    log("=" * 78)
    inst = _combined_instance()
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"birlesik siparis: {len(inst.parts)} tip, {n_total} parca")

    rows = []
    best = None  # (legal_height, row, result, meshes)
    for name, kw in BASE_CONFIGS:
        try:
            row, r, meshes = _run(inst, name, n_total=n_total, **kw)
        except Exception as e:
            log(f"  [{name}] EXCEPTION: {e} — konfig atlandi")
            rows.append({"name": name, "invalid_reason": f"EXCEPTION: {e}"})
            continue
        rows.append(row)
        if row["legal_height_mm"] is not None and (
                best is None or row["legal_height_mm"] < best[0]):
            best = (row["legal_height_mm"], row, r, meshes)

    if best is not None:
        bk = dict(budget=best[1]["budget"],
                  n_orientations=best[1]["n_orientations"])
        for sd in EXTRA_SEEDS:
            name = f"best_{bk['budget']}_{bk['n_orientations']}_s{sd}"
            try:
                row, r, meshes = _run(inst, name, seed=sd, n_total=n_total, **bk)
            except Exception as e:
                log(f"  [{name}] EXCEPTION: {e} — atlandi")
                continue
            rows.append(row)
            if row["legal_height_mm"] is not None and row["legal_height_mm"] < best[0]:
                best = (row["legal_height_mm"], row, r, meshes)

    log("")
    log("-" * 78)
    if best is None:
        log("SONUC: HICBIR konfig legal cikmadi — INVALID sebepleri yukarida. STL YAZILMADI.")
    else:
        h, row, r, meshes = best
        OUT_DIR.mkdir(exist_ok=True)
        stl_path = OUT_DIR / f"plan13_duzeltilmis_{h:.1f}mm_{row['name']}.stl"
        combined = trimesh.util.concatenate(meshes)
        combined.export(stl_path)
        log(f"KAZANAN: {row['name']}  legal_height={h:.1f}mm  "
            f"clear={row['min_clearance_mm']:.3f}mm  kilit=0  "
            f"yerlesen={row['n_placed']}/{n_total}")
        log(f"STL yazildi: {stl_path}  ({stl_path.stat().st_size / 1e6:.1f} MB)")
    doc = {"created": datetime.now().isoformat(timespec="seconds"),
           "plate": PLATE, "clearance_req": CLEARANCE, "rows": rows,
           "winner": (best[1] if best else None)}
    (OUT_DIR / "plan13_tarama.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    log(f"tablo: {OUT_DIR / 'plan13_tarama.json'}")
    log(f"TOPLAM {(time.perf_counter() - t_all) / 60:.0f} dk")


if __name__ == "__main__":
    main()

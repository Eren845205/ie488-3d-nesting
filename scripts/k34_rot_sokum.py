# -*- coding: utf-8 -*-
"""k34_rot_sokum.py — K-34: R10 dondurme-sokum sertifikasi SAHADA (plan3).

Hedef: plan3 NFV @yeni-kurallar HAM cozumu (618.1mm, 5-yon kilit 20/109 =
INVALID) hoca kriteri (c) "dondurerek cikarma" modeliyle yeniden denetlemek:
check_separability_rot kilitli 20 parcaya "mikro-kaldir + yerinde dondur +
duz cek" sertifikasi arar. Kilit 0'a inerse 618.1 LEGAL olur -> yeni
sampiyon (exit_guard 680.0'i -62mm, Magics-manuel 593'u +%4.2'ye indirir).

Kiyas seti: NFV+exit_guard 680.0 legal / heightmap sq 735 / manuel 593.
Raporlama A2 geregi IKI kriterle: (b) 5-yon kilit + (b+c) rot kilit.

RAM zinciri: ayrilabilirlik_probu.log son satiri BITTI olana kadar bekler
(gece3 zincirinin son halkasi; tek-agir-surec kurali).
Kosum: python -m scripts.detach_run k34_rot_sokum
Duman: python -m scripts.k34_rot_sokum smoke   (kapisiz, sentetik, saniyeler)
SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.accessibility import check_placements, check_separability_5dir
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "k34_rot_sokum.log"
BEKLE = Path(__file__).parent / "ayrilabilirlik_probu.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bekle_probu():
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            return
        if tur % 10 == 0:
            log(f"ayrilabilirlik_probu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)


def _duman():
    """Kapi-SONRASI yolun duman testi (9-saat dersi): sentetik 2 kutu ile
    rot denetimi + clearance + legal_of + rapor hatti uctan uca kosulur."""
    from src.nesting3d.voxelize import voxelize_part
    from src.nesting3d.bin3d import Placement3D
    b = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    b.apply_translation(-b.bounds[0])
    parts = {pid: voxelize_part(pid, b.copy(), 1.0, n_orientations=1,
                                method="slice") for pid in ("a", "b")}
    pls = [Placement3D("a", "a", 0, 0, 0, 0), Placement3D("b", "b", 14, 0, 0, 0)]
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts)
    meshes = placed_meshes(pls, parts, 1.0)
    rep = min_clearance(meshes)
    hv = 10.0
    legal, reason = legal_of(hv, len(pls), 2, float(rep.min_mm),
                             int(rot.n_locked), clearance_req=2.0)
    log(f"DUMAN: 5yon={r5.n_locked} rot={rot.n_locked} certs="
        f"{len(rot.certificates)} clear={rep.min_mm:.2f} legal={legal}")
    assert r5.n_locked == 0 and rot.n_locked == 0 and legal == 10.0
    log("DUMAN OK")


def main():
    if "smoke" in sys.argv[1:]:
        LOG.write_text("", encoding="utf-8")
        _duman()
        return
    LOG.write_text("", encoding="utf-8")
    log("K-34 ROT-SOKUM — plan3 NFV ham (618.1 / 20 kilit) @R10 (c)-kriteri")
    _bekle_probu()
    log("zincir bitti — NFV cozumu basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0, no_go_bounds=NOGO)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"NFV: h={float(r.height_mm):.1f} (grid-tavan {hv:.1f})  pitch={px}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    r5 = check_separability_5dir(pls, parts)
    kilitli = sorted(pid for grup in r5.locked_groups for pid in grup)
    log(f"(b) 5-yon kilit={r5.n_locked}/{len(pls)}  ({kilitli[:6]}...)")

    t = time.perf_counter()
    rot = check_separability_rot(pls, parts)
    log(f"(b+c) rot kilit={rot.n_locked}/{len(pls)}  "
        f"sertifika={len(rot.certificates)}  "
        f"buyuk-muaf={len(rot.skipped_large)}  "
        f"({(time.perf_counter() - t) / 60:.1f} dk)")
    for pid, c in rot.certificates.items():
        log(f"  CERT {pid}: eksen={c.eksen} aci={c.aci_deg:+.1f} "
            f"yon={c.yon} lift={c.lift_vox}")
    if rot.skipped_large:
        log(f"  MUAF (max_grid_vox): {rot.skipped_large}")
    if rot.n_locked:
        kalan = sorted(pid for grup in rot.locked_groups for pid in grup)
        log(f"  KALAN KILIT: {kalan}")

    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    accz = check_placements(pls, parts)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  "
        f"legal(b)={legal_b if legal_b is not None else 'INVALID'}  "
        f"legal(b+c)={legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}"
        f"  (+Z telemetri {accz.n_locked})")
    log(f"HUKUM-VERISI: NFV ham {hv:.1f} (b)kilit={r5.n_locked} -> "
        f"(b+c)kilit={rot.n_locked} | exit_guard 680.0 | heightmap 735 | "
        f"manuel 593 -> "
        f"{'GO: R10 sokulebilirlik vergisini sildi, YENI SAMPIYON' if (legal_bc is not None and hv < 680.0) else 'sonuca gore degerlendir'}")
    if legal_bc is not None:
        out = _ROOT / "results" / f"plan3_nfv_rotsokum_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()

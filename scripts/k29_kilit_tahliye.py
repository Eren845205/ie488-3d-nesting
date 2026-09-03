# -*- coding: utf-8 -*-
"""k29_kilit_tahliye.py — K-29: NFV KILIT-TAHLIYE probu (kullanici karari
2026-07-09: 'NFV icin bu kilitleri acalim artik').

Hedef: plan3 NFV @yeni-kurallar (618.1, 5-yon kilit 20/109) -> kilitleri
TAHLIYE edip A2-legal sonuc: kilitli parcalar sahneden cikarilir, kalan
sahnenin heightmap'i uzerine dblf ile yeniden yerlestirilir (ayni dilate'li
grid'ler -> clearance korunur), 5-yon sokum yeniden dogrulanir. Kilit
kalirsa yineleme; son turda z-tabani sahne tavanina zorlanir (toz yataginda
askida durmak SLS'te sorun degil — ic-ice yerlesimin mesruiyet zemini ayni).

Kiyas: NFV ham 618.1 (INVALID 20 kilit) / heightmap sq ~735 / manuel 593.
Beklenti: legal ~620-660 arasi cikarsa GO (735'i yener).

RAM zinciri: ax24_kuyruk_335.log son satiri BITTI (rekor v2 s7 bacagi).
Kosum: python -m scripts.detach_run k29_kilit_tahliye   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import place_in_order
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.accessibility import check_separability_5dir, check_placements
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "k29_kilit_tahliye.log"
BEKLE = Path(__file__).parent / "ax24_kuyruk_335.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
MAX_TUR = 3


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _sokum(pls, parts):
    r = check_separability_5dir(pls, parts)
    return r.n_locked, {pid for grup in r.locked_groups for pid in grup}


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-29 KILIT-TAHLIYE — plan3 NFV @yeni-kurallar (ham 618.1 / 20 kilit)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"rekor v2 (s7) bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — NFV cozumu + tahliye basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0, no_go_bounds=NOGO)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts          # dilate'li grid'ler -> clearance tasinir
    pls = list(r.placements)
    log(f"NFV: h={float(r.height_mm):.1f}  pitch={px}  "
        f"({(time.perf_counter() - t) / 60:.1f} dk)")

    mask = Bin3D.no_go_mask_from_bounds(NOGO, PLATE[0], PLATE[1], px)
    for tur in range(1, MAX_TUR + 1):
        n_kilit, kilitli = _sokum(pls, parts)
        log(f"[tur{tur}] 5-yon kilit={n_kilit}  ({sorted(kilitli)[:6]}...)"
            if n_kilit else f"[tur{tur}] 5-yon kilit=0 — TAHLIYE TAMAM")
        if n_kilit == 0:
            break
        kalan_pls = [p for p in pls if p.part_id not in kilitli]
        # kalan sahneyi heightmap'e AYNEN oynat (exact place)
        b = Bin3D(PLATE[0], PLATE[1], px, z_clearance=0, no_go_mask=mask)
        for p in kalan_pls:
            b.place(parts[p.part_id], p.orientation_idx, p.x, p.y, p.z)
        if tur >= 2:
            # 2. turdan itibaren: dblf'in bosluklara sokmasini engelle —
            # tabani sahne tavanina cek (askida = SLS'te mesru)
            tavan = int(np.max(b.height[~mask] if mask is not None and mask.any()
                               else b.height))
            b.height[~mask] = np.maximum(b.height[~mask], tavan)
            log(f"[tur{tur}] z-tabani tavana zorlandi ({tavan * px:.0f}mm)")
        tahliye = [parts[pid] for pid in sorted(kilitli)]
        # fine-settle sonrasi orientations SEYREK (yalniz kullanilan indeks
        # dolu, gerisi None — pozisyon-koruma tasarimi) -> yalniz dolu
        # indeksler denenir (None'a drop_map cakilir; bu kosunun ilk dersi)
        yeni = place_in_order(
            tahliye, b,
            lambda i, part: [k for k, o in enumerate(part.orientations)
                             if o is not None])
        if len(yeni) != len(tahliye):
            log(f"[tur{tur}] UYARI: {len(tahliye) - len(yeni)} parca yeniden "
                f"yerlesemedi — dusus")
            break
        pls = kalan_pls + list(yeni)

    n_kilit, _ = _sokum(pls, parts)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx].grid.shape[2])
             for p in pls) * px
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    accz = check_placements(pls, parts)   # +Z telemetri
    legal, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                             int(n_kilit), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit_5yon={n_kilit} (+Z telemetri "
        f"{accz.n_locked})  yerlesen={len(pls)}/{n_total}")
    log(f"HUKUM-VERISI: NFV ham 618.1 (20 kilit) -> tahliye {hv:.1f} "
        f"({n_kilit} kilit)  | heightmap sq ~735 | manuel 593"
        f"  -> {'GO: tahliye NFV legal ve heightmapi yener' if (legal is not None and hv < 735) else 'sonuca gore degerlendir'}")
    if legal is not None:
        out = _ROOT / "results" / f"plan3_nfv_tahliye_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()

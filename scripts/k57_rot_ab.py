# -*- coding: utf-8 -*-
"""k57_rot_ab.py — rot-memo ADIL A/B (tek proses; onceki iki ayri-kosu
kiyasi HUKUMSUZ — makine kosullari esit degildi: 240s vs 410s celiskisi).

A = kilit_rot_meshes(_rot_memo=False)  (eski yol birebir)
B = kilit_rot_meshes(_rot_memo=True)
Ayni proses, ayni sahne (pickle cache), art arda. GECER sayilir eger:
  - rapor BIT-OZDES: n_locked + removable_order listesi + cert detaylari
    (eksen, aci, yon, lift) birebir
  - B < A ise kazanc raporlanir; degilse memo NOTR/ZARARLI -> revert adayi
    (durust kayit — A5).
Kosum: python -m scripts.detach_run k57_rot_ab    SAF ASCII.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_rot_ab.log"
# GUVENLIK NOTU: pickle yalniz k57_rot_profil'in kendi urettigi lokal teshis
# cache'i (ayni makine/kullanici; untrusted kaynak yok, uretim yolu degil).
PKL = _ROOT / "results" / "k57_plan2_meshes.pkl"


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _ozet(rep):
    certs = {pid: (c.eksen, round(float(c.aci_deg), 6), c.yon,
                   int(c.lift_vox))
             for pid, c in (rep.certificates or {}).items()}
    return {"n_locked": int(rep.n_locked),
            "order": list(rep.removable_order), "certs": certs}


def main():
    LOG.write_text("", encoding="utf-8")
    from src.nesting3d.continuous_settle import kilit_rot_meshes
    log("K-57 ROT-MEMO ADIL A/B (tek proses, plan2 pickle sahnesi)")
    meshes = pickle.loads(PKL.read_bytes())
    log(f"sahne: {len(meshes)} mesh")

    t = time.perf_counter()
    rep_a = kilit_rot_meshes(meshes, _rot_memo=False)
    ta = time.perf_counter() - t
    log(f"[A memo'suz] {ta:.1f}s  n_locked={rep_a.n_locked}"
        f"  cert={len(rep_a.certificates or {})}")

    t = time.perf_counter()
    rep_b = kilit_rot_meshes(meshes, _rot_memo=True)
    tb = time.perf_counter() - t
    log(f"[B memo'lu ] {tb:.1f}s  n_locked={rep_b.n_locked}"
        f"  cert={len(rep_b.certificates or {})}")

    oa, ob = _ozet(rep_a), _ozet(rep_b)
    ozdes = oa == ob
    log(f"BIT-OZDESLIK: {'BIREBIR' if ozdes else 'FARKLI!!'}")
    if not ozdes:
        log(f"  A: {oa['n_locked']} kilit, {len(oa['order'])} order,"
            f" certs={oa['certs']}")
        log(f"  B: {ob['n_locked']} kilit, {len(ob['order'])} order,"
            f" certs={ob['certs']}")
    log(f"KIYAS: A={ta:.1f}s -> B={tb:.1f}s  ({tb - ta:+.1f}s,"
        f" %{(tb / ta - 1) * 100:+.1f})"
        f"  HUKUM: {'KAZANC' if (ozdes and tb < ta * 0.95) else ('NOTR' if ozdes else 'FARKLI-INCELE')}")
    log("BITTI")


if __name__ == "__main__":
    main()

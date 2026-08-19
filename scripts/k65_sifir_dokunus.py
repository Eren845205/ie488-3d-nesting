# -*- coding: utf-8 -*-
"""k65_sifir_dokunus.py — K-65 tetiginin dev-setlerde SIFIR-DOKUNUS kaniti.

A11 geregi: yeni tetik (ince-plaka dalinda plaka-asan parca -> NFV) mevcut
dev-setlerin yonlendirme kararini DEGISTIRMEMELI. Bu script uretim karar
zincirini (family_routing + mode_model + no-go) dev-setlerde kosar ve
karar/gerekce dokumunu verir; gerekcede "K-65" gecen set = DOKUNUS (fail).

Held-out setler (plan7, deneme6, fsm610) BILEREK dahil degil (A3).
Kosum: python -m scripts.k65_sifir_dokunus   (hizli, cozum kosmaz)
SAF ASCII stdout.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.eval_gate as eg
from src.nesting3d.adaptive_params import (
    predict_nfv_benefit, _duz_yatista_sigmayan_parca)

DEV_SETLER = ["plan1", "plan2", "plan3", "deneme4", "boxy"]


def main() -> int:
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    dokunus = 0
    for ad in DEV_SETLER:
        inst = eg._load_instance(ad)
        uzun = _duz_yatista_sigmayan_parca(inst)
        dec = predict_nfv_benefit(
            inst, family_routing=True, mode_model=mm,
            no_go_bounds=eg.NOGO_STD)
        k65 = "K-65" in dec.reason
        if k65:
            dokunus += 1
        print(f"{ad:10s} mod={dec.mode:9s} plaka_asan="
              f"{(uzun[0] if uzun else '-'):12s} K65_tetik={k65} "
              f"| {dec.reason[:90]}")
    print()
    if dokunus:
        print(f"SONUC: FAIL — {dokunus} dev-sette K-65 karari degistirdi")
        return 1
    print("SONUC: PASS — dev-setlerde SIFIR dokunus (kararlar eski yolda)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

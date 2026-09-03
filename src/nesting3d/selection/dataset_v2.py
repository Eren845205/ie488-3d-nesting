"""dataset_v2.py — telemetri v2'den MOD-duzeyi egitim tablosu (ML plani C1).

Karar-yuzeyi gocu (03_SECIM_MODELI §2): eski tablo dblf/sa3d/ga/tabu solver
etiketi tasiyordu; uretimin gercek karari MOD/receteydi (heightmap-vs-NFV /
guard / pitch). Bu modul v2 satirlarini (backfill_v2 + kxx_telemetri +
uretim pipeline'i) mevcut `TrainingRow` tipine dokerek TUM eski makineyi
(loo_regret, compute_generalization_gap, gate, model siniflari) SIFIR
degisiklikle mod-duzeyine tasir — "cozucu" slotu ARM adi tasir.

ARM kanonu (tek kaynak; regret_raporu + mod_yarismasi buradan import eder):
  heightmap ailesi TEK arm (dik/tilt/sq ic-strateji tuner'in isi) ·
  heightmap+wall_aware ayri arm (F5 karari) · nfv ham/guard PITCH'LI ayri
  armlar (K-38: 2mm kuralinda tam pitch'ler 2.0/1.0; plan gerekce: pitch
  varyantlari ilk surumde ayri arm, az-olcumlu olan kotumser cezayla yarisir) ·
  kalite/uretim recetesi (ham-mi-guard-mi bilinmiyor) -> nfv_kalite.

Y-7: legal_height_mm None (INVALID) satir o arm icin ADAY OLAMAZ — tabloya
yukseklik olarak asla girmez. Held-out dislama cagirandan
(heldout_instance_ids) gelir; feature'siz satirlar atlanir ve SAYILIR
(sessiz iyimserlik yok).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from src.nesting3d.selection.dataset import TrainingRow

HEIGHTMAP_ARM = "heightmap"


def arm_of(mode: str, recete: Optional[str], pitch: Optional[float]) -> str:
    """(mode, recete, pitch) -> kanonik arm adi. Deterministik, tek kaynak."""
    if mode == "heightmap":
        return HEIGHTMAP_ARM
    if mode == "heightmap+wall_aware":
        return "heightmap+wall_aware"
    # mode == "nfv"
    r = (recete or "").lower()
    if r in ("kalite", "uretim") or r.startswith("kalite"):
        return "nfv_kalite"
    mekanizma = "guard" if "guard" in r else "ham"  # derin/ham/auto -> ham mekanizmasi
    if pitch is not None:
        return f"nfv_{mekanizma}@{float(pitch):g}"
    return f"nfv_{mekanizma}"


def build_training_table_v2(
    rows: List[dict],
    *,
    epsilon_mm: float = 0.5,
    exclude_instance_ids: Optional[set] = None,
    istatistik: Optional[dict] = None,
) -> List[TrainingRow]:
    """v2 satirlari -> instance-basi TrainingRow listesi (mod-duzeyi).

    winner = argmin legal (esitlikte alfabetik — mevcut determinizm
    sozlesmesi); per_solver_heights = {arm: en iyi legal}; dblf_height slotu
    heightmap arm'inin legal'i (baseline analojisi), yoksa None + is_easy
    False. is_easy: hicbir arm heightmap'i epsilon'dan fazla gecememis.
    """
    exclude = exclude_instance_ids or set()
    ist = istatistik if istatistik is not None else {}
    ist.setdefault("n_heldout_dislanan", 0)
    ist.setdefault("n_featuresiz_satir", 0)
    ist.setdefault("n_invalid_satir", 0)
    ist.setdefault("n_legal_armsiz_instance", 0)

    gruplar: Dict[str, dict] = {}
    dislanan_heldout = set()
    for r in rows:
        if int(r.get("schema", 0)) != 2:
            continue
        iid = r.get("instance_id")
        if iid is None:
            continue
        if iid in exclude:
            dislanan_heldout.add(iid)
            continue
        g = gruplar.setdefault(iid, {"armlar": {}, "fv": None, "fn": None,
                                     "aile": None})
        fv = r.get("feature_vector")
        fn = r.get("feature_names")
        if fv and fn and g["fv"] is None:
            g["fv"] = [float(x) for x in fv]
            g["fn"] = list(fn)
            g["aile"] = r.get("family_f1") or "unknown"
        legal = r.get("legal_height_mm")
        if legal is None:
            ist["n_invalid_satir"] += 1
            continue
        if not fv or not fn:
            ist["n_featuresiz_satir"] += 1  # legal olcum ama ozelliksiz satir
        arm = arm_of(r.get("mode", ""), r.get("recete"), r.get("pitch_fine"))
        mevcut = g["armlar"].get(arm)
        if mevcut is None or float(legal) < mevcut:
            g["armlar"][arm] = float(legal)
    ist["n_heldout_dislanan"] = len(dislanan_heldout)

    tablo: List[TrainingRow] = []
    for iid in sorted(gruplar):
        g = gruplar[iid]
        armlar = g["armlar"]
        if not armlar:
            ist["n_legal_armsiz_instance"] += 1
            continue
        if g["fv"] is None:
            continue  # hicbir satirinda ozellik yok (satir-sayaci yukarida)
        best = min(armlar.values())
        winner = min(a for a, h in armlar.items() if h == best)
        hm = armlar.get(HEIGHTMAP_ARM)
        is_easy = (hm is not None) and (hm - best < epsilon_mm)
        tablo.append(TrainingRow(
            instance_id=iid, is_easy=is_easy, winner=winner,
            dblf_height=hm, best_height=best,
            feature_vector=g["fv"], feature_names=g["fn"],
            aile=g["aile"], per_solver_heights=dict(sorted(armlar.items())),
        ))
    return tablo

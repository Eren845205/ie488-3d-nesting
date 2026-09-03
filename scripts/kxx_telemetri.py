# -*- coding: utf-8 -*-
"""kxx_telemetri.py — K-xx deney scriptleri icin mod-duzeyi telemetri v2 kaydi.

ML plani Faz A1 (2026-07-13): olcum kosulari (K-38..) simdiye dek yalniz log +
YONTEM_HARITASI'na yaziyordu; ogrenme tablosuna hic girmiyordu. Bu sarmalayici
her SONUC satirinin yanina tek cagriyla runs_v2.jsonl satiri ekler.

Neden script-tarafi (solver-hook DEGIL): legal alanlar (6000-ornek clearance,
rot-kilit) solve dondukten SONRA script katmaninda hesaplaniyor — solver bu
degerleri bilemez; append_run_v2'nin A2-turetimi ancak burada dogru calisir.

Kaynak-izi ZORUNLU: kosu_id + log_yolu olmadan satir yazilamaz (denetlenebilirlik
— her v2 satiri hangi kosudan geldigini tasir; A7 kayit disiplini).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.family import classify_prelim
from src.nesting3d.instances.features import (
    EXTENDED_FEATURE_NAMES,
    extract_features_extended,
)
from src.nesting3d.telemetry import V2_DEFAULT_PATH, append_run_v2

GECERLI_MODLAR = ("heightmap", "heightmap+wall_aware", "nfv")


def ozellik_cikar(instance) -> dict:
    """Instance'tan v2 satirina gomulecek ozellik/aile alanlarini cikar.

    backfill_v2 ve canli K-xx kayitlari AYNI cikarimi kullanir (tek kaynak)."""
    fv = extract_features_extended(instance)
    fam, conf = classify_prelim(instance)
    return {
        "feature_vector": [float(x) for x in fv.values],
        "feature_names": list(EXTENDED_FEATURE_NAMES),
        "family_f1": fam,
        "family_conf": float(conf),
    }


def kaydet(
    instance_id: str,
    mode: str,
    recete: str,
    height_mm: float,
    n_placed: int,
    n_total: int,
    min_clearance_mm: Optional[float],
    n_locked: Optional[int],
    duration_s: Optional[float],
    *,
    kosu_id: str,
    log_yolu: str,
    pitch: Optional[float] = None,
    seed: Optional[int] = None,
    clearance_req_mm: float = 2.0,
    instance=None,
    path=None,
    **extra: Any,
) -> dict:
    """Tek olcum bacaginin v2 satirini yaz; yazilan satiri dondur.

    mode: kanon ("heightmap" | "heightmap+wall_aware" | "nfv") — recete ayrimi
    (ham@2.0 / guard@2.0 / ham@1.0 / kalite) `recete` alaninda tasinir.
    instance verilirse ozellik vektörü + aile satira gomulur (C1 tablo kurucusu
    yeniden yukleme yapmadan okur)."""
    if not kosu_id:
        raise ValueError("kxx_telemetri.kaydet: kosu_id ZORUNLU (kaynak-izi).")
    if not log_yolu:
        raise ValueError("kxx_telemetri.kaydet: log_yolu ZORUNLU (kaynak-izi).")
    if mode not in GECERLI_MODLAR:
        raise ValueError(
            f"kxx_telemetri.kaydet: mode={mode!r} kanon-disi; gecerli: "
            f"{GECERLI_MODLAR} (recete ayrimi 'recete' alaninda tasinir).")
    alanlar: dict = {}
    if instance is not None:
        alanlar.update(ozellik_cikar(instance))
    alanlar.update(extra)  # cagiran extra'si ozellik cikarimini ezebilir (bilincli)
    fam = alanlar.pop("family_f1", None)
    fam_conf = alanlar.pop("family_conf", None)
    return append_run_v2(
        path if path is not None else (_ROOT / V2_DEFAULT_PATH),
        kaynak="deney",
        instance_id=instance_id,
        mode=mode,
        height_mm=height_mm,
        n_placed=n_placed,
        n_total=n_total,
        min_clearance_mm=min_clearance_mm,
        n_locked=n_locked,
        family_f1=fam,
        family_conf=fam_conf,
        pitch_fine=pitch,
        seed=seed,
        duration_s=duration_s,
        clearance_req_mm=clearance_req_mm,
        recete=recete,
        kosu_id=kosu_id,
        log=log_yolu,
        **alanlar,
    )

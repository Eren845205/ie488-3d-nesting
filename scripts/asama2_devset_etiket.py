# -*- coding: utf-8 -*-
"""asama2_devset_etiket.py — Asama-2 dev-set etiket kampanyasi (Eren onayi
2026-08-22 karar paketi madde-4; ML plani §2.1 + §4 Asama-2 on-kosulu).

Her dev-set icin karsi-olgusal portfoy etiketi uretir (fsm610 deseninin
dev-set genellemesi): uretim kollari (heightmap / nfv_fast / nfv_max;
kafes_zinciri KAPALI — saflik) + tetikli kafes kollari. Satirlar
`results/m4_portfoy_etiket.jsonl`'a APPEND (aile=devset_<set>).

p2/d4 SIFIR-DOKUNUS kaniti YAN URUN: kafes kolu tetik atesLEMEZSE satirda
kol yoktur = kafes bu seti degistirmiyor (KIRMIZI serh kapanir).

Disiplin: setler SIRALI (K-57a munhasir); her set oncesi RAM kapisi
(bos < 4GB -> bekle, 30dk asilirsa atla + kayit). SAF ASCII stdout.
Kosum: D:\\ie488'den detach; setler A2_SETS env ile secilir
(default: plan1,plan2,plan3,deneme4,deneme5).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import (  # noqa: E402
    ARMS, FAMILY_BUILDERS, KAFES_ARMS, OUT_ETIKET, _kol_kafes, _kol_kos,
    etiket_hesapla)

RAM_ESIK_GB = 4.0
RAM_BEKLE_S = 1800


def log(m: str = "") -> None:
    print(m, flush=True)


def _bos_ram_gb() -> float:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / (1024 ** 3)


def _ram_kapisi(set_adi: str) -> bool:
    t0 = time.time()
    while True:
        gb = _bos_ram_gb()
        if gb >= RAM_ESIK_GB:
            return True
        if time.time() - t0 > RAM_BEKLE_S:
            log(f"{set_adi}: RAM kapisi ASILAMADI ({gb:.1f}GB < "
                f"{RAM_ESIK_GB}) — set atlandi (sonraki dalgaya)")
            return False
        log(f"{set_adi}: RAM bekleniyor ({gb:.1f}GB) ...")
        time.sleep(60)


def main() -> int:
    from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
    clearance_req = float(WEB_MIN_CLEARANCE_MM)
    setler = [s.strip() for s in os.environ.get(
        "A2_SETS", "plan1,plan2,plan3,deneme4,deneme5").split(",")
        if s.strip()]
    log("=" * 70)
    log("ASAMA-2 DEV-SET ETIKET KAMPANYASI (karar paketi madde-4)")
    log(f"setler={setler}  clearance_req={clearance_req}mm")
    log("NOT: etiket uretimi — kazanc ilani DEGILDIR (A11); nfv kollari")
    log("     kafes_zinciri KAPALI (karsi-olgusal saflik); no-go/pin")
    log("     uretim kosullari tasinmaz (SERH — kollar ic-tutarli).")
    log("=" * 70)
    t0 = time.time()
    n_hata = 0
    for set_adi in setler:
        aile = f"devset_{set_adi}"
        builder = FAMILY_BUILDERS.get(aile)
        if builder is None:
            log(f"{set_adi}: builder yok — atlandi")
            n_hata += 1
            continue
        if not _ram_kapisi(set_adi):
            n_hata += 1
            continue
        ts = time.time()
        try:
            inst = builder(42, "gercek", None)
        except Exception as exc:
            log(f"{set_adi}: INSTANCE KURULAMADI: {exc}")
            n_hata += 1
            continue
        n_total = sum(int(p.qty) for p in inst.parts)
        log(f"\n[{set_adi}] {n_total} parca")
        arms = {}
        for ad, mode, q in ARMS:
            log(f"  kol {ad} ...")
            kol = _kol_kos(inst, mode, q, seed=42,
                           kaynak=f"asama2:{set_adi}")
            arms[ad] = kol
            log(f"    h={kol.get('height_mm')} "
                f"cl={kol.get('min_clearance_mm')} "
                f"kilit5={kol.get('n_locked_5dir')} "
                f"sure={kol.get('wall_s')}s"
                + (f" HATA={kol['hata']}" if kol.get("hata") else ""))
        for ad, durus in KAFES_ARMS:
            kol = _kol_kafes(inst, durus, clearance_req)
            if kol is None:
                log(f"  kol {ad}: tetik YOK (sifir-dokunus kaniti)")
                continue
            arms[ad] = kol
            log(f"  kol {ad}: h={kol.get('height_mm')} "
                f"cl={kol.get('min_clearance_mm')} "
                f"sure={kol.get('wall_s')}s"
                + (f" HATA={kol['hata']}" if kol.get("hata") else ""))
        et = etiket_hesapla(arms, clearance_req)
        satir = {"ts": time.time(), "instance_id": f"devset_{set_adi}",
                 "aile": aile, "seed": 42, "scale": "gercek",
                 "n_total": n_total, "clearance_req_mm": clearance_req,
                 "arms": arms, **et}
        OUT_ETIKET.parent.mkdir(exist_ok=True)
        with OUT_ETIKET.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(satir, ensure_ascii=False) + "\n")
        log(f"  ETIKET: winner={et['winner_mode']} n_legal={et['n_legal']}"
            f"  ({(time.time()-ts)/60:.1f} dk)")
    log(f"\nKAMPANYA BITTI ({(time.time()-t0)/60:.1f} dk; hata/atlanan="
        f"{n_hata}) -> {OUT_ETIKET}")
    return 0 if n_hata == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""deneme6_stl_paketi.py — Deneme6 kor-test yerlesiminin STL+sokum paketi.

Hoca istegi 2026-07-22: "sokum plani ve her iki yerlesimin STL dosyalarini
iletebilir misiniz" — dunku kor-test (deneme6_heldout_final kol-1, 68.5mm)
placements saklamadigi icin AYNI uretim yolu ayni seed'le deterministik
yeniden kosulur (~29s) ve bu kez export kancasiyla paket uretilir:
multi-solid ASCII STL + placements JSON + sokum plani JSON/MD.

A3: held-out bakisi registry'ye ONCE loglanir. Sonuc 68.5'ten saparsa
determinizm UYARISI loglanir (k47c deseni) — paket yine yazilir, karar
raporda verilir. Tuning/secim YOK.

Kosum (D'den): python -m scripts.detach_run deneme6_stl_paketi   SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "deneme6_stl_paketi.log"
OUT = _ROOT / "results" / "deneme6_stl_paketi.json"
PAKET_DIR = _ROOT / "results" / "hoca_paketi_2026-07"
BEKLENEN_MM = 68.5   # dunku kol-1 (deneme6_heldout_final.json)
SEED = 42


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bos_ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        pass
    try:
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
    except Exception:
        return None


def main():
    LOG.write_text("", encoding="utf-8")
    log("DENEME6 STL PAKETI — kor-test 68.5 yerlesiminin deterministik "
        "replay'i + hoca paketi (STL/sokum)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < 4.0:
            log("DURDURULDU: bos RAM < 4GB (K-57a) — sakin makinede baslat.")
            sys.exit(3)

    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    from scripts._hoca_paket import paket_uret
    _log_heldout_bakis(["deneme6"], "STL+sokum paketi icin kor-test kol-1 "
                       "deterministik replay (hoca istegi 2026-07-22; "
                       "tuning/secim yok)")
    log("bakis registry'ye loglandi (A3)")

    yollar = {}

    def _cb(paket):
        yollar.update(paket_uret(paket, PAKET_DIR, "deneme6_68p5"))

    t0 = time.perf_counter()
    r = evaluate_set("deneme6", SEED, export_cb=_cb)
    sure = time.perf_counter() - t0
    lh = r.get("legal_height_mm")
    log(f"[deneme6/replay] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  sure={sure:.0f}s"
        f"  invalid={r.get('invalid_reason')}")
    if r.get("export_hata"):
        log(f"EXPORT HATASI: {r['export_hata']}")
    if lh is not None and abs(lh - BEKLENEN_MM) > 1e-6:
        log(f"UYARI: replay {lh} != beklenen {BEKLENEN_MM} — determinizm "
            "sapmasi; paket yine yazildi, rapora tasi")
    for k, v in yollar.items():
        log(f"paket.{k} = {v}")

    OUT.write_text(json.dumps({
        "set": "deneme6", "seed": SEED, "beklenen_mm": BEKLENEN_MM,
        "sonuc": r, "paket": yollar, "sure_s": round(sure, 1),
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=True, indent=2), encoding="utf-8")
    log(f"yazildi: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()

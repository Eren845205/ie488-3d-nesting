# -*- coding: utf-8 -*-
"""plan7_stl_paketi.py — Plan7 kor-test 488.4 yerlesiminin STL+sokum paketi.

Hoca istegi 2026-07-22: her iki yerlesimin STL'i + sokum plani. Dunku
kor-test (plan7_heldout_final kol-1, 488.4mm, r11'li) placements
saklamadigi icin AYNI uretim yolu ayni seed'le deterministik yeniden
kosulur (~1.7h) ve export kancasiyla paket uretilir. STL sahnesi olculen
sahneyle AYNI (r11 dz'li — 7add014 uretim paritesi).

A3: bakis registry'ye ONCE loglanir; tuning/secim YOK. Sonuc 488.4'ten
saparsa determinizm UYARISI (k47c deseni) — paket yine yazilir.

TEK KOL / TEK PROSES (2026-07-21 CEVRESEL-OOM dersi). RAM guard 6GB
(plan7-olcek cozum+olcum zirvesi; 2026-07-22 dersi x2).

Kosum (D'den): python -m scripts.detach_run plan7_stl_paketi    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "plan7_stl_paketi.log"
OUT = _ROOT / "results" / "plan7_stl_paketi.json"
PAKET_DIR = _ROOT / "results" / "hoca_paketi_2026-07"
BEKLENEN_MM = 488.4  # dunku kol-1 (plan7_heldout_final.json / max_kolu ayni)
REF_MM = 595.0       # hoca referansi (2mm mutabakatli, S1 2026-07-22)
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
    log("PLAN7 STL PAKETI — kor-test 488.4 yerlesiminin deterministik "
        "replay'i + hoca paketi (STL/sokum; r11 dz'li sahne)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < 6.0:
            log("DURDURULDU: bos RAM < 6GB (K-57a; plan7-olcek NFV+olcum "
                "zirvesi) — makinede yer acip yeniden baslat.")
            sys.exit(3)

    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    from scripts._hoca_paket import paket_uret
    _log_heldout_bakis(["plan7"], "STL+sokum paketi icin kor-test kol-1 "
                       "deterministik replay (hoca istegi 2026-07-22; "
                       "tuning/secim yok)")
    log("bakis registry'ye loglandi (A3)")

    yollar = {}

    def _cb(paket):
        yollar.update(paket_uret(paket, PAKET_DIR, "plan7_488p4"))

    t0 = time.perf_counter()
    r = evaluate_set("plan7", SEED, export_cb=_cb)
    sure = time.perf_counter() - t0
    lh = r.get("legal_height_mm")
    log(f"[plan7/replay] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r.get('r11_uygulandi')}"
        f"  sure={sure:.0f}s  invalid={r.get('invalid_reason')}")
    if r.get("export_hata"):
        log(f"EXPORT HATASI: {r['export_hata']}")
    if lh is not None and abs(lh - BEKLENEN_MM) > 0.05:
        log(f"UYARI: replay {lh} != beklenen {BEKLENEN_MM} — determinizm "
            "sapmasi; paket yine yazildi, rapora tasi")
    if lh is not None:
        log(f"KIYAS ref-595 (2mm mutabakatli): {lh:.2f} -> "
            f"{(lh - REF_MM) / REF_MM * 100.0:+.2f}%")
    for k, v in yollar.items():
        log(f"paket.{k} = {v}")

    OUT.write_text(json.dumps({
        "set": "plan7", "seed": SEED, "beklenen_mm": BEKLENEN_MM,
        "ref_mm": REF_MM, "sonuc": r, "paket": yollar,
        "sure_s": round(sure, 1),
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=True, indent=2), encoding="utf-8")
    log(f"yazildi: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()

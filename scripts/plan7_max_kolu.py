# -*- coding: utf-8 -*-
"""plan7_max_kolu.py — Plan7 held-out MAX/AX24 gozcu kolu (TAZE PROSES retry).

TARIHCE 2026-07-21: iki-kollu plan7_heldout_final.py'de kol-2 (max) COZUMU
BITIRDI ama olcum fazinda (placed_meshes, 345 parca mesh sahnesi) OOM'la
dustu — kok neden runner tasarimi: kol-1'in agir sonuc nesneleri bellekte
tutulurken kol-2 ayni proseste kosuldu. DERS: cok-kollu held-out kosulari
KOL BASINA AYRI PROSES ister. Bu script yalniz max kolunu taze proseste kosar.

Kol-1 (uretim default) sonucu GECERLI ve kayitli: 488.40 LEGAL, -%17.9
(results/plan7_heldout_final.json + _kol1.log). Bu kosu ONU DEGISTIRMEZ;
karneye max-gozcu sutununu doldurur. Held-out uzerinde secim/tuning YOK.

Kosum (D'den): python -m scripts.detach_run plan7_max_kolu
MUNHASIRLIK: baska olcum kosusuyla cakistirilmaz (K-57a).    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "plan7_max_kolu.log"
OUT = _ROOT / "results" / "plan7_max_kolu.json"
REF_MM = 595.0
KOL1_MM = 488.4  # uretim kolu (kiyas icin sabit referans, degistirilmez)
SEED = 42
RAM_ESIK_GB = 5.5  # AX24 345p + 345-mesh olcum sahnesi; 4GB yetmedi (OOM dersi)


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
    log("PLAN7 MAX/AX24 GOZCU KOLU (taze-proses retry; ref 595mm A10-serhli;"
        f" uretim kolu {KOL1_MM} sabit)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < RAM_ESIK_GB:
            log(f"DURDURULDU: bos RAM < {RAM_ESIK_GB}GB (OOM dersi 2026-07-21)"
                " — sakin makinede yeniden baslat.")
            sys.exit(3)

    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    _log_heldout_bakis(["plan7"], "held-out max/AX24 gozcu kolu RETRY "
                       "(2026-07-21 cevresel-OOM sonrasi taze proses; "
                       "uretim kolu 488.40 kayitli, degismez)")
    log("bakis registry'ye loglandi (A3)")

    t0 = time.perf_counter()
    r = evaluate_set("plan7", SEED, n_orientations="ax24")
    sure = time.perf_counter() - t0
    lh = r.get("legal_height_mm")
    log(f"[plan7/max] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r.get('r11_uygulandi')}"
        f"  sure={sure:.0f}s  invalid={r.get('invalid_reason')}")
    kiyas = None
    if lh is not None:
        kiyas = round((lh - REF_MM) / REF_MM * 100.0, 2)
        log(f"KIYAS/max (A10 SERHLI): {lh:.2f} vs ref {REF_MM:.1f}"
            f" -> {kiyas:+.2f}%  (uretim kolu {KOL1_MM}: "
            f"{round((KOL1_MM - REF_MM) / REF_MM * 100.0, 2):+.2f}%)")

    payload = {
        "set": "plan7", "seed": SEED, "kol": "max_ax24_retry",
        "ref_mm_a10_serhli": REF_MM, "kol1_uretim_mm": KOL1_MM,
        "kiyas_pct": kiyas, "sure_s": round(sure, 1), "sonuc": r,
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")


if __name__ == "__main__":
    main()

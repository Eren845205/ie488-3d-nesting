# -*- coding: utf-8 -*-
"""deneme6_heldout_final.py — Deneme6 HELD-OUT kor-test kosusu (R11 protokolu).

Deneme6 = 2026-07-09 hoca maili; 15 parca x1; referans 86.32mm MANUEL
(A10 serhli). DOGUSTAN held-out — 2026-07-21'e dek COZUM HIC KOSULMADI
(Eren elestirisi 2026-07-21: "onlem aliyoruz ama uygulamiyoruz" — hakli;
bu script o boslugu kapatir). Plan7 kosusuyla ayni iki-kollu desen:

  Kol 1 (ESAS): uretim default — out-of-the-box sinav; "held-out ilk-kosu
    acigi" metriginin veri noktasi (mekanizma envanteri yakinsiyor mu?).
  Kol 2 (GOZCU): quality=max/AX24 — yalniz NFV dalinda (heightmap'te K-53
    gerekcesiyle atlanir).

Iki kol da AYNEN raporlanir; held-out uzerinde secim/tuning YOK (A3/A5).
Kor-test sonucu gorulunce mekanizma gelistirme YAPILMAZ — acik olculur,
kaydedilir; gelistirme ancak aile dev'e terfi ederse (B1 >=2 kurali).

Kosum (D'den): python -m scripts.detach_run deneme6_heldout_final
MUNHASIRLIK: plan7 kosusu bitmeden BASLATILMAZ (K-57a).    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "deneme6_heldout_final.log"
OUT = _ROOT / "results" / "deneme6_heldout_final.json"
REF_MM = 86.32  # hoca maili 2026-07-09, MANUEL yerlesim (A10 serhli)
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
    log("DENEME6 HELD-OUT KOR-TEST (R11 protokolu; ref 86.32mm MANUEL"
        " A10-serhli; 15 parca x1)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < 4.0:
            log("DURDURULDU: bos RAM < 4GB (kosu disiplini K-57a) — sakin "
                "makinede yeniden baslat.")
            sys.exit(3)

    # A3 sert: bakis logu ONCE — yazilamazsa kosu olmaz.
    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    _log_heldout_bakis(["deneme6"], "held-out FINAL kor-test (ILK cozum "
                       "kosusu; R11 protokolu; ref 86.32mm; iki kol: "
                       "uretim-default + max-gozcu — ikisi de raporlanir, "
                       "secim yok)")
    log("bakis registry'ye loglandi (A3)")

    def _kol(etiket, **kw):
        t0 = time.perf_counter()
        r = evaluate_set("deneme6", SEED, **kw)
        sure = time.perf_counter() - t0
        lh = r.get("legal_height_mm")
        log(f"[deneme6/{etiket}] legal={lh}  clear={r.get('min_clearance_mm')}"
            f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
            f"  r11_uygulandi={r.get('r11_uygulandi')}"
            f"  sure={sure:.0f}s  invalid={r.get('invalid_reason')}")
        kiyas = None
        if lh is not None:
            kiyas = round((lh - REF_MM) / REF_MM * 100.0, 2)
            log(f"KIYAS/{etiket} (A10 SERHLI): {lh:.2f} vs ref {REF_MM:.2f}"
                f" -> {kiyas:+.2f}%")
        return {"sonuc": r, "kiyas_pct": kiyas, "sure_s": round(sure, 1)}

    log("--- KOL 1: uretim default (sozlesme; routing canli) ---")
    kol_uretim = _kol("uretim")

    log("--- KOL 2: quality=max / AX24 gozcu ---")
    kol_max = None
    kol_max_atlama = None
    try:
        kol_max = _kol("max", n_orientations="ax24")
    except ValueError as exc:
        kol_max_atlama = f"atlandi: {exc}"
        log(f"KOL 2 {kol_max_atlama}")

    payload = {
        "set": "deneme6", "seed": SEED, "ref_mm_a10_serhli": REF_MM,
        "kol_uretim": kol_uretim,
        "kol_max": kol_max,
        "kol_max_atlama": kol_max_atlama,
        "serhler": [
            "A10: referans 86.32mm MANUEL — kosullari yaklasik",
            "iki kol da rapor edilir; held-out uzerinde secim/tuning yok (A3/A5)",
            "kor-test sonucuna mekanizma yazilmaz; gelistirme aile dev'e "
            "terfi ederse (B1 >=2)",
        ],
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""plan7_heldout_final.py — Plan7 HELD-OUT kor-test kosusu (R11 protokolu).

Plan7 = 2026-07-20 hoca maili (Drive Plan7.zip; 10 tip / 345 adet).
DOGUSTAN held-out (A3/B1). Bu script:
  1. Bakisi registry'ye ONCE loglar (A3 sert: log yazilamazsa kosu OLMAZ).
  2. evaluate_set("plan7") — URETIM DEFAULT yolu (routing canli cozulur).
  3. Referans 595mm ile kiyas yazar (A10 SERHLI: hazirlanis yontemi +
     bosluk/kenar kosulu mailde yok).

IKI KOL (Eren istegi 2026-07-21 "quality max kosacaksin degil mi"):
  Kol 1 (ESAS, protokol): uretim default — sozlesme sonucu, urunun verecegi.
  Kol 2 (GOZCU): quality=max / AX24 poz seti — yalniz routing NFV dalina
    duserse (heightmap dalinda poz artirimi kaldirac DEGIL, K-53 kaniti;
    ax24 orada ValueError verir -> gerekceli atlanir). Iki kol da AYNEN
    raporlanir; held-out uzerinde secim/tuning YAPILMAZ (A3/A5).

SERHLER (sonuc rapora aynen tasinir):
  - Mail kisiti "288101642-a2 konumu degismeyecek" UYGULANMADI (pin
    semantigi hoca netligi bekliyor: 6 kopyali parcada sabit konum muglak;
    K-56g uretim kablosu da bagli degil). Kiyas bu yuzden cift-serhli.
  - RAM guard: bos RAM < 4GB ise baslamaz (kosu disiplini; K-57a munhasirlik).

Kosum (D'den): python -m scripts.detach_run plan7_heldout_final    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "plan7_heldout_final.log"
OUT = _ROOT / "results" / "plan7_heldout_final.json"
REF_MM = 595.0  # hoca maili 2026-07-20 "Uretim yuksekligi 595 mm" (A10 serhli)
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
    try:  # Windows fallback (psutil yoksa)
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
        return None  # olculemedi -> guard atlanir (kosuya engel degil)


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN7 HELD-OUT KOR-TEST (R11 protokolu; ref 595mm A10-serhli)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < 4.0:
            log("DURDURULDU: bos RAM < 4GB (kosu disiplini K-57a) — sakin "
                "makinede yeniden baslat.")
            sys.exit(3)

    # A3 sert: bakis logu ONCE — yazilamazsa kosu olmaz.
    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    _log_heldout_bakis(["plan7"], "held-out FINAL kor-test (ilk cozum kosusu; "
                       "R11 protokolu; ref 595mm; iki kol: uretim-default + "
                       "max-gozcu — ikisi de raporlanir, secim yok)")
    log("bakis registry'ye loglandi (A3)")

    def _kol(etiket, **kw):
        t0 = time.perf_counter()
        r = evaluate_set("plan7", SEED, **kw)
        sure = time.perf_counter() - t0
        lh = r.get("legal_height_mm")
        log(f"[plan7/{etiket}] legal={lh}  clear={r.get('min_clearance_mm')}"
            f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
            f"  r11_uygulandi={r.get('r11_uygulandi')}"
            f"  sure={sure:.0f}s  invalid={r.get('invalid_reason')}")
        kiyas = None
        if lh is not None:
            kiyas = round((lh - REF_MM) / REF_MM * 100.0, 2)
            log(f"KIYAS/{etiket} (A10 SERHLI): {lh:.2f} vs ref {REF_MM:.1f}"
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
        # heightmap dalina dustu: ax24 orada tanimsiz VE poz artirimi
        # kaldirac degil (K-53: plan3 heightmap n12/16 KOTU) -> gerekceli atla.
        kol_max_atlama = f"atlandi: {exc}"
        log(f"KOL 2 {kol_max_atlama}")

    payload = {
        "set": "plan7", "seed": SEED, "ref_mm_a10_serhli": REF_MM,
        "kol_uretim": kol_uretim,
        "kol_max": kol_max,
        "kol_max_atlama": kol_max_atlama,
        "serhler": [
            "A10: referans 595mm'in hazirlanis yontemi/bosluk kosulu bilinmiyor",
            "pin kisiti (288101642-a2 konumu degismeyecek) UYGULANMADI — "
            "hoca netligi + K-56g bekliyor",
            "iki kol da rapor edilir; held-out uzerinde secim/tuning yok (A3/A5)",
        ],
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")


if __name__ == "__main__":
    main()

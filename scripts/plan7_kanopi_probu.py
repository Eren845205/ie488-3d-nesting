# -*- coding: utf-8 -*-
"""plan7_kanopi_probu.py — Plan1'de kanitlanan KANOPI/RELOKASYON zincirini
Plan7 ustunde dene (Eren istegi 2026-08-17: "plan1'deki kazanci p7'de test").

AKIS: uretim sampiyon recetesiyle REF coz (_run_champion; r11 dahil) ->
kanopi_zinciri_uretim (geometrik tetik + 3D-pin z-adaylari + kule-onceligi;
TEK-TARAFLI: ref'ten kotu donemez, tetik yoksa ref AYNEN) -> kiyas + JSON.

BEKLENTI YONETIMI: tetik plan7 geometrisinde ateslemeyebilir (dagilimsal
smoke dersi: tetikli sette bile 2W/5T) — TIE de gecerli olcumdur.
Tarihsel karne DEGISMEZ (488.40 held-out ilk-kosu kaydi kalir); bu kosu
ayri satirda raporlanir (plan7_max_kolu deseni).

SURE: ref ~100dk + zincir adaylari -> toplam 2.5-5 saat sinifi.
KOSUM (D'den, RAM >= 5.5GB bosken, MUNHASIR — K-57a):
    python -m scripts.detach_run plan7_kanopi_probu
SAF ASCII log.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "plan7_kanopi_probu.log"
OUT = _ROOT / "results" / "plan7_kanopi_probu.json"
D_OUT = Path(r"D:\ie488\results\plan7_kanopi_probu.json")
REF_HELDOUT_MM = 488.4   # tarihsel karne kaydi (degistirilemez, kiyas icin)
MANUEL_MM = 595.0        # A10 serhli manuel referans
SEED = 42
RAM_ESIK_GB = 5.5        # plan7 345p OOM dersi (2026-07-21)


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
    log("PLAN7 KANOPI/RELOKASYON PROBU (K-62 sinifi; ref=uretim recetesi;"
        f" tarihsel karne {REF_HELDOUT_MM} sabit)")

    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < RAM_ESIK_GB:
            log(f"DURDURULDU: bos RAM < {RAM_ESIK_GB}GB (K-57a + OOM dersi)"
                " — Chrome/uygulamalari kapatip yeniden baslat.")
            sys.exit(3)

    from scripts.eval_gate import (NOGO_STD, PLATE_STD, _load_instance,
                                   _log_heldout_bakis, _run_champion)
    _log_heldout_bakis(["plan7"], "kanopi/relokasyon probu (K-62 sinifi; "
                       "tarihsel 488.40 kaydi degismez, ayri satir raporu)")
    log("bakis registry'ye loglandi (A3)")

    inst = _load_instance("plan7")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"instance: {len(inst.parts)} tip / {n_total} parca")

    # --- REF: uretim sampiyon recetesi (r11 dahil) ---
    t0 = time.perf_counter()
    ref, nfv_tel = _run_champion("plan7", inst, SEED)
    ref_s = time.perf_counter() - t0
    ref_h = float(ref.height_mm)
    log(f"REF hazir: {ref_h:.2f}mm  sure={ref_s / 60:.1f}dk  "
        f"(nfv secilen={nfv_tel.get('secilen')})")

    # --- KANOPI ZINCIRI (tek-tarafli; tetiksizse ref AYNEN doner) ---
    from src.nesting3d.kanopi_zincir import kanopi_zinciri_uretim
    t1 = time.perf_counter()
    kz_res, kz_tel = kanopi_zinciri_uretim(
        inst,
        plate_w_mm=PLATE_STD[0], plate_d_mm=PLATE_STD[1],
        no_go_bounds=NOGO_STD, clearance_mm=2.0, seed=SEED,
        quality="fast",  # olculen zincir recetesi (k62)
        ref_res=ref, ref_height_mm=None)
    kz_s = time.perf_counter() - t1
    kz_h = float(kz_res.height_mm)
    tetikledi = kz_res is not ref
    log(f"ZINCIR bitti: {kz_h:.2f}mm  sure={kz_s / 60:.1f}dk  "
        f"tetikledi={tetikledi}  tel={json.dumps(kz_tel, ensure_ascii=True, default=str)[:400]}")

    kazanc = ref_h - kz_h
    log("")
    log(f"OZET: ref {ref_h:.2f} -> zincir {kz_h:.2f}  kazanc {kazanc:+.2f}mm"
        f"  (tarihsel karne {REF_HELDOUT_MM} DEGISMEZ; manuel {MANUEL_MM} A10-serhli)")

    payload = {
        "amac": "plan1 K-62 kanopi/relokasyon sinifinin plan7 probu",
        "set": "plan7", "seed": SEED,
        "n_parca": n_total,
        "ref_uretim_mm": round(ref_h, 3), "ref_sure_dk": round(ref_s / 60, 1),
        "zincir_mm": round(kz_h, 3), "zincir_sure_dk": round(kz_s / 60, 1),
        "kazanc_mm": round(kazanc, 3),
        "tetikledi": tetikledi,
        "zincir_telemetri": kz_tel,
        "tarihsel_karne_mm": REF_HELDOUT_MM,
        "manuel_ref_a10_serhli_mm": MANUEL_MM,
        "serhler": [
            "tek-set probu (A11: GO cikarsa dagilimsal + cok-set kaniti gerekir)",
            "tarihsel held-out karnesi degismez (ilk-kosu kurali)",
        ],
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str),
                   encoding="utf-8")
    try:
        D_OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2,
                                    default=str), encoding="utf-8")
        log(f"yazildi: {OUT} + {D_OUT}")
    except OSError as exc:
        log(f"yazildi: {OUT} (D kopyasi HATA: {exc})")


if __name__ == "__main__":
    main()

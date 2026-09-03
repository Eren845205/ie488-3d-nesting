# -*- coding: utf-8 -*-
"""plan7_kisitli_cozum.py — Plan7 a2-DURUS-KILITLI uretim cozumu (hoca S3 istegi).

Bagla: HOCA_CEVAPLARI 2026-07-22 —
  S2: "konumu degismeyecek" = DURUS ACISI kilidi (yatay imal; z/x-y serbest).
  S3: Plan7'de tek kisit 288101642-a2 (6 kopya); kalan 339 parca serbest.
  Eren 2026-07-22: "plan 7'yi deneyelim son hale gore".

Kosu: dunku kor-testin (plan7_heldout_final kol-1) BIREBIR uretim yolu
(evaluate_set uretim default; ayni seed) + TEK fark: 288101642-a2 icin
orientation_overrides = durus_koru poz kumesi (K-56g NFV kolu, bugun
baglandi). Kiyaslar: ref 595 (hoca; 2mm mutabakatli, A10 serhi kalkti) +
kisitsiz 488.4 (kisit maliyeti gorunur olsun).

TEK KOL / TEK PROSES (dunku CEVRESEL-OOM dersi: iki kol ayni proseste
kosulmaz). RAM guard: bos RAM < 4GB ise baslamaz (K-57a).

Kosum (D'den): python -m scripts.detach_run plan7_kisitli_cozum   SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "plan7_kisitli_cozum.log"
OUT = _ROOT / "results" / "plan7_kisitli_cozum.json"
REF_MM = 595.0          # hoca 2026-07-20; 2mm mutabakati 2026-07-22 (S1)
KISITSIZ_MM = 488.4     # dunku kor-test kol-1 (kisitsiz)
KISIT_PARCA = "288101642-a2"
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
    log("PLAN7 a2-DURUS-KILITLI COZUM (hoca S2/S3 2026-07-22; K-56g NFV kolu)")

    # Esik 6GB (2026-07-22 dersi x2): 4.3GB ve 9.2GB baslangicla iki olum —
    # ilki cozum zirvesinde (~9GB), ikincisi COZUM BITTIKTEN SONRA olcum
    # fazinda (placed_meshes 345 mesh; dunku kol-2 ile ayni imza). Plan7
    # olceginde cozum+olcum zirvesi icin baslangicta >= 6GB bos sart.
    ram = _bos_ram_gb()
    if ram is not None:
        log(f"bos RAM: {ram:.1f} GB")
        if ram < 6.0:
            log("DURDURULDU: bos RAM < 6GB (K-57a; plan7-olcek NFV+olcum "
                "zirvesi) — makinede yer acip yeniden baslat.")
            sys.exit(3)

    # Durus-koru poz kumesi TEK KAYNAKTAN (constraint_compiler geometrik
    # tablo — elle sabit yok, A11).
    from src.runtime.constraint_compiler import yon_poz_tablosu
    pozlar = yon_poz_tablosu()["durus_koru"]
    overrides = {KISIT_PARCA: pozlar}
    log(f"kisit: {KISIT_PARCA} -> durus_koru pozlari {list(pozlar)} "
        "(Rz serbest; z/x-y serbest — hoca S2)")

    # A3 sert: bakis logu ONCE.
    from scripts.eval_gate import _log_heldout_bakis, evaluate_set
    from scripts._hoca_paket import paket_uret
    _log_heldout_bakis(["plan7"], "a2-durus-kilitli URETIM cozumu (hoca S3 "
                       "istegi; kisit disinda kor-test kol-1 ile ayni yol/"
                       "seed; held-out uzerinde tuning YOK — musteri kisitli "
                       "teslim kosusu)")
    log("bakis registry'ye loglandi (A3)")

    # Export kancasi: kisitli cozum de hoca paketine girer (STL + sokum) —
    # 1.5h'lik kosudan yalniz sayi degil teslim dosyasi da ciksin.
    yollar = {}

    def _cb(paket):
        yollar.update(paket_uret(paket, _ROOT / "results" /
                                 "hoca_paketi_2026-07", "plan7_a2_kilitli"))

    t0 = time.perf_counter()
    r = evaluate_set("plan7", SEED, orientation_overrides=overrides,
                     export_cb=_cb)
    sure = time.perf_counter() - t0
    lh = r.get("legal_height_mm")
    log(f"[plan7/kisitli] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r.get('r11_uygulandi')}"
        f"  sure={sure:.0f}s  invalid={r.get('invalid_reason')}")

    if r.get("export_hata"):
        log(f"EXPORT HATASI: {r['export_hata']}")
    for k, v in yollar.items():
        log(f"paket.{k} = {v}")

    kiyas_ref = kiyas_kisitsiz = None
    if lh is not None:
        kiyas_ref = round((lh - REF_MM) / REF_MM * 100.0, 2)
        kiyas_kisitsiz = round(lh - KISITSIZ_MM, 2)
        log(f"KIYAS ref-595 (2mm mutabakatli): {lh:.2f} -> {kiyas_ref:+.2f}%")
        log(f"KISIT MALIYETI (vs kisitsiz {KISITSIZ_MM}): "
            f"{kiyas_kisitsiz:+.2f} mm")

    payload = {
        "set": "plan7", "seed": SEED, "kosu": "a2_durus_kilitli",
        "kisit": {KISIT_PARCA: list(pozlar)},
        "ref_mm": REF_MM, "kisitsiz_mm": KISITSIZ_MM,
        "sonuc": r, "kiyas_ref_pct": kiyas_ref,
        "kisit_maliyeti_mm": kiyas_kisitsiz,
        "paket": yollar,
        "sure_s": round(sure, 1),
        "notlar": [
            "hoca S1 2026-07-22: 2mm mutabakati + no-go dahil -> A10 serhi "
            "kalkti (bosluk 'firmaca bilinmiyor' notuyla)",
            "hoca S2: konumu-degismeyecek = durus kilidi (z/x-y serbest)",
            "tek kol tek proses (dunku cevresel-OOM dersi)",
        ],
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=2),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")


if __name__ == "__main__":
    main()

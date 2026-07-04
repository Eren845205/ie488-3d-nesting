# -*- coding: utf-8 -*-
"""k21_nfv_fine_kabuk.py — K-21: kabukta NFV@orta-ince pitch (probe).

SORU: NFV cavity-packing, K-19 heightmap sampiyonunun (282.0mm, LEGAL/0 kilit)
altina LEGAL (sokulabilir) inebilir mi?

Kiyas cetveli (Deneme4, 588 parca, auto-plaka 301.6):
  - K-19 heightmap @0.5 cidar-pitch : 282.0mm / 0 kilit (LEGAL sampiyon)
  - NFV-max @kaba 1.25             : 386.4mm / 506 kilit (kismen illegal)
  - Magics referansi               : 250.24mm (plaka bilinmiyor)

Yontem: Deneme4 instance (c3_generality DATASETS + build_instance_from_order,
f4a ile ayni kanonik kurulum) -> solve_nfv(fine_pitch=ARG, quality="max",
time_budget_sec=7200, fine_settle default-on) -> accessibility.check_result.
Ilk deneme pitch=1.0 (H-11 on-hesap: ~302^2 x z FFT ~0.5GB = sigar);
ikinci deneme 0.8 (sinirda) AYRI kosu olarak.

Karar kurali (RESUME Sprint 3 §2):
  yukseklik < 282 VE kilit ~ 0  -> yeni kabuk sampiyonu
  yukseklik < 282 VE kilitli    -> "illegal kazanc" (F2 v2 gundemine)
  yukseklik >= 282              -> K-19 hukmu pekisir
Sonuc -> YONTEM_HARITASI K-21 kunyesi.

AYRIK surecte kos (Start-Process; RAM icin agir uygulamalar kapali iyi):
    python -m scripts.k21_nfv_fine_kabuk [pitch=1.0]
SAF ASCII cikti (cp1254 guvenli). Uretime DOKUNMAZ.
"""
from __future__ import annotations

import pickle
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

PITCH_ARG = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
N_OR = int(sys.argv[2]) if len(sys.argv) > 2 else 8       # 2. kosu karari: n=8
TIME_BUDGET_SEC = int(sys.argv[3]) if len(sys.argv) > 3 else 10800  # 3 saat
LOG = Path(__file__).parent / f"k21_olcum_p{PITCH_ARG:g}_n{N_OR}.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


import psutil  # noqa: E402

_proc = psutil.Process()
_peak = {"rss": 0}
_stop = threading.Event()


def _sampler() -> None:
    while not _stop.is_set():
        _peak["rss"] = max(_peak["rss"], _proc.memory_info().rss)
        _stop.wait(2.0)


from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.nfv_solve import solve_nfv  # noqa: E402
from src.nesting3d.accessibility import check_result  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402


def main() -> None:
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    inst = res.instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)

    vm = psutil.virtual_memory()
    t = threading.Thread(target=_sampler, daemon=True)
    t.start()
    log(f"K-21 BASLADI — solve_nfv fine_pitch={PITCH_ARG} n_orientations={N_OR} "
        f"time_budget={TIME_BUDGET_SEC}s fine_settle=default(True)")
    log(f"plaka (auto) {pw:.1f}x{pd:.1f}mm | RAM musait={vm.available / 1e9:.1f}GB")

    t0 = time.perf_counter()
    try:
        result = solve_nfv(
            inst, plate_w_mm=pw, plate_d_mm=pd,
            fine_pitch=PITCH_ARG,        # opt-in override (K-21 olcum noktasi)
            n_orientations=N_OR,         # 2. kosu: n=8 (1. kosu quality=max 2h'de 193/588 kaldi)
            time_budget_sec=TIME_BUDGET_SEC,
        )
    except Exception as exc:
        log(f"HATA ({time.perf_counter() - t0:.0f}s): {type(exc).__name__}: {exc}")
        _stop.set(); t.join(timeout=5)
        log(f"TEPE RAM process={_peak['rss'] / 1e9:.2f}GB")
        sys.exit(1)

    el = time.perf_counter() - t0
    log(f"SOLVE BITTI — {el:.0f}s ({el / 60:.1f} dk)")
    log(f"  height={result.height_mm:.1f}mm | uygulanan pitch={result.fine_pitch} "
        f"| density={result.density:.3f} | n_placed={len(result.placements)}")
    for attr in ("winning_config", "coarse_height_mm", "coarse_pitch",
                 "adaptive_reason"):
        log(f"  {attr}={getattr(result, attr, None)}")

    # --- Erisilebilirlik (LEGALLIK) denetimi ---------------------------------
    ta = time.perf_counter()
    rep = check_result(result)
    log(f"ERISILEBILIRLIK ({time.perf_counter() - ta:.1f}s): "
        f"kilitli={rep.n_locked}/{rep.n_parts} | grup={len(rep.locked_groups)}")

    # --- Yerlesimleri kalici kaydet (F4-A tarzi sonradan-analiz icin) --------
    out = _ROOT / "data" / "mail_stl" / f"k21_placements_p{PITCH_ARG:g}_n{N_OR}.pkl"
    with out.open("wb") as fh:
        pickle.dump({"placements": result.placements,
                     "pitch_mm": result.fine_pitch,
                     "height_mm": result.height_mm}, fh)
    log(f"yerlesimler kaydedildi: {out.name}")

    # --- Karar kurali --------------------------------------------------------
    # ON-KAPI: kismi yerlesim hukum uretemez (1. kosu dersi: butce decode'da
    # bitti -> 193/588 parca, 225.0mm KIYASLANAMAZDI ama "illegal kazanc"
    # basilmisti). Beklenen adet = DATASETS qty toplami.
    expected = sum(cfg["qty"].values())
    h = result.height_mm
    log("KIYAS: K-19 hm@0.5=282.0 (0 kilit) | nfv-max@1.25=386.4 (506 kilit) "
        "| Magics=250.24")
    if len(result.placements) < expected:
        log(f"HUKUM YOK — KISMI YERLESIM: {len(result.placements)}/{expected} "
            f"parca (butce yetmedi). Yukseklik {h:.1f} KIYASLANAMAZ; kilit "
            f"({rep.n_locked}/{rep.n_parts}) yalnizca YON sinyali.")
    elif h < 282.0 and rep.n_locked == 0:
        log(f"HUKUM: YENI KABUK SAMPIYONU ADAYI — {h:.1f} < 282.0 ve 0 kilit (LEGAL).")
    elif h < 282.0:
        log(f"HUKUM: ILLEGAL KAZANC — {h:.1f} < 282.0 ama {rep.n_locked} kilit "
            "(F2 v2 gundemine).")
    else:
        log(f"HUKUM: K-19 HUKMU PEKISTI — NFV-fine {h:.1f} >= 282.0.")

    _stop.set(); t.join(timeout=5)
    log(f"TEPE RAM process={_peak['rss'] / 1e9:.2f}GB")


if __name__ == "__main__":
    main()

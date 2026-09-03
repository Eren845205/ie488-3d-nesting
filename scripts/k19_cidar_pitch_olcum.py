# -*- coding: utf-8 -*-
"""K-19 olcumu: Deneme4 heightmap yolu, CIDAR-DUYARLI fine pitch (0.5mm).

Baseline'lar (ayni parcalar, ayni auto-plaka):
  - heightmap fast @2.90mm  : 377.3mm / 34.7s
  - NFV max @coarse         : 386.4mm / 288s
Hipotez: 0.5mm'de kabuk canlar cozunur -> bardak-istifi (telescoping) -> yukseklik duser.
Yontem: pitch.min_feature_mm'i cidar-tahminli degerle yamala (probe-only), mode=heightmap.
"""
import io
import sys
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
sys.path.insert(0, str(ROOT))
LOG = Path(__file__).parent / "k19_olcum.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


import psutil  # noqa: E402
_proc = psutil.Process()
_peak = {"rss": 0}
_stop = threading.Event()


def _sampler():
    while not _stop.is_set():
        _peak["rss"] = max(_peak["rss"], _proc.memory_info().rss)
        _stop.wait(2.0)


# --- CIDAR-DUYARLI min_feature yamasi (yalniz bu probe) ---------------------
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
import src.nesting3d.instances.pitch as pitch_mod  # noqa: E402

FILL_GATE = 0.5
_orig_min_feature = pitch_mod.min_feature_mm


def _wall_est_from_path(stl_path):
    m = trimesh.load(stl_path, force="mesh")
    ext = m.extents
    bbox_min = float(min(ext))
    try:
        vol = float(abs(m.volume)); area = float(m.area)
        bbox_vol = float(np.prod(ext))
        if vol > 0 and area > 0 and bbox_vol > 0 and vol / bbox_vol < FILL_GATE:
            return min(bbox_min, 2.0 * vol / area)
    except Exception:
        pass
    return bbox_min


_wall_cache = {}


def _wall_aware_min_feature(instance):
    vals = []
    for p in instance.parts:
        sp = getattr(p, "stl_path", None)
        if sp and sp not in _wall_cache:
            try:
                _wall_cache[sp] = _wall_est_from_path(sp)
            except Exception:
                _wall_cache[sp] = min(p.width_mm, p.depth_mm, p.height_mm)
        vals.append(_wall_cache.get(sp) or min(p.width_mm, p.depth_mm, p.height_mm))
    mf = min(vals)
    log(f"  [yama] min_feature: bbox={_orig_min_feature(instance):.2f} -> cidar={mf:.2f}")
    return mf


pitch_mod.min_feature_mm = _wall_aware_min_feature
# ---------------------------------------------------------------------------

from src.runtime.mail_ingest import Attachment, RawMail, ingest_order  # noqa: E402
from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline  # noqa: E402

SRC = ROOT / "data" / "mail_stl" / "mail_stl_AD786DF3"
GOVDE = """588 parça için imalat yüksekliği 250,24 mm'dir.

ASY-0176446 - 62
ASY-0176446-1 - 126
part239392_ROBT UST v27 - 1
part239391_ROBT ALT v27 - 1
01_202201790014_00-K179 Dugme Aksesuari - 12
02_202201790002_T00-K179 Dugme Cift Fonksiyonlu - 12
02_T00-K179 Dugme Cift Fonksiyonlu -26
03_00-K179 Dugme Tek Fonksiyonlu - 200
04_T00-K179 Dugme Fonksiyonsuz - 56
05_00-K179 WBT Dugme - 20
09_00-K179 Dugme Kilidi - 27
10_T00-K179 Kilitli Dugme - 25
17_00-K179 SSB Dugme - 20
"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for stl in sorted(SRC.glob("*.stl")):
        z.writestr(stl.name, stl.read_bytes())

mail = RawMail(
    gonderen="mcoskun@fsm.edu.tr", konu="Deneme4-k19", govde=GOVDE,
    tarih="2026-07-03T16:11:14+03:00", message_id="<k19-cidar-pitch@offline>",
    ekler=[Attachment("Deneme 4 STL.zip", buf.getvalue(), "application/x-zip-compressed")],
)
order = ingest_order(mail, parser_role=None,
                     persist_root=str(Path(__file__).parent / "k19_stl"))
assert order and not order.get("needs_review"), f"ingest bozuk: {order}"
order["deadline"] = "2026-07-13"

scenario = {**RICH_SCENARIO, "orders": [order], "container": order.get("container"),
            "nesting_mode": "heightmap"}

t = threading.Thread(target=_sampler, daemon=True)
t.start()
vm = psutil.virtual_memory()
log(f"BASLADI — heightmap + cidar-duyarli pitch; RAM musait={vm.available/1e9:.1f}GB")
t0 = time.perf_counter()
try:
    result = run_pipeline(scenario)
    el = time.perf_counter() - t0
    log(f"BITTI — {el:.1f}s ({el/60:.1f} dk)")
    for bid, nr in result.get("nesting_results", {}).items():
        log(f"[{bid}] height={nr.get('height_mm')} density={nr.get('density')} "
            f"n_parts={nr.get('n_parts')} elapsed={nr.get('elapsed_sec')} "
            f"note={nr.get('note') or '-'}")
    log("KIYAS: heightmap@2.9=377.3 | nfvmax@coarse=386.4 | Magics=250.24")
except Exception as exc:
    log(f"HATA ({time.perf_counter()-t0:.1f}s): {type(exc).__name__}: {exc}")
finally:
    _stop.set(); t.join(timeout=5)
    log(f"TEPE RAM process={_peak['rss']/1e9:.2f}GB")

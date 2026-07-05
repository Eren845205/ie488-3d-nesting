# -*- coding: utf-8 -*-
"""h16_kapi.py — H-16 KAPI OLCUMU: dirty-region drop_map onbellegi.

Deneme4 @0.5 wall_aware FINE gecisi (uretim kabuk yolu) cache'siz vs cache'li:
  (a) yukseklik 282.0 BIREBIR + yerlesimler birebir (kalite garantisi),
  (b) gercek fine yerlesim suresi (place_in_order dongusu) ikisi icin,
  (c) tepe RAM (psutil),
  (d) cache istatistikleri (hit orani, anahtar sayisi, tepe cache MB, eviction).

FINE gecis modeli (coarse_to_fine._run_fine): her parca TEK secilen oryantasyonu
(coarse kazanani) dener -> parca basi ~1 drop_map cagrisi. order_ids + orient_map
K-19 v2 kalici pkl'inden okunur (kendi kosumuzun ciktisi) -> coarse tune KOSMAZ,
yalniz fine gecis olculur. Cache=False kosusu 282.0 uretmeli (referans dogrulama);
Cache=True ayni yerlesimi BIREBIR uretmeli, sadece hizli.

H-15 dersi: sure atfi sentez-orani ~1.0 ister. Olculen cache-siz fine suresi
[KANITLI-ATIF] 514s ile karsilastirilir; cache-li fine ON-ANALIZ bandiyla
(~14..38s) karsilastirilir; uyusmazlik RAPOR EDILIR.

Kosum: python -m scripts.h16_kapi [off|on|both]   SAF ASCII.
"""
from __future__ import annotations

import pickle
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402
import psutil  # noqa: E402

from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.nesting3d.dblf import place_in_order  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "h16_kapi.log"
PITCH = 0.5
N_ORIENT = 4
GERCEK_FINE_S = 514.0     # [KANITLI-ATIF] uretim fine dblf payi
ONANALIZ_LOW = 14.0       # on-analiz alt band (ort kirlilik)
ONANALIZ_HIGH = 38.0      # on-analiz ust band (p90 kirlilik)
MODE = sys.argv[1] if len(sys.argv) > 1 else "both"


def log(msg: str = "") -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


class PeakRAM:
    """Arka planda RSS orneklem -> tepe RAM (GB)."""

    def __init__(self):
        self.proc = psutil.Process()
        self.peak = 0
        self._stop = threading.Event()
        self._t = None

    def __enter__(self):
        self.peak = self.proc.memory_info().rss

        def loop():
            while not self._stop.is_set():
                self.peak = max(self.peak, self.proc.memory_info().rss)
                self._stop.wait(1.0)
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        if self._t:
            self._t.join(timeout=3)

    @property
    def gb(self):
        return self.peak / 1e9


def build_fine_parts():
    """Deneme4 instance -> fine voxel parcalari (id->part), @0.5 n=4."""
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes()
               for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"],
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    pw = float(res.instance.container.width_mm)
    pd = float(res.instance.container.depth_mm)
    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_ORIENT)
    log(f"voxelize @0.5 n={N_ORIENT} ({time.perf_counter() - t:.0f}s) "
        f"plaka={pw:.1f}x{pd:.1f}mm")
    return parts, pw, pd


def run_fine(ordered, orient_map, pw, pd, *, drop_cache: bool):
    """Uretim _run_fine ile ozdes: TEK secilen oryantasyon/parca, order sirasi.
    Doner: (placements, bin, fine_time_s, peak_ram_gb)."""
    def base_orient(_idx, part):
        return (orient_map.get(part.id, 0),)

    b = Bin3D(pw, pd, PITCH, z_clearance=1, drop_cache=drop_cache)
    with PeakRAM() as ram:
        t0 = time.perf_counter()
        pls = place_in_order(ordered, b, base_orient)
        ft = time.perf_counter() - t0
    return pls, b, ft, ram.gb


def key_of(pls):
    return [(p.part_id, p.x, p.y, p.z, p.orientation_idx) for p in pls]


def main():
    log("=" * 78)
    log(f"H-16 KAPI OLCUMU — dirty-region drop_map onbellegi (mode={MODE})")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    src_pls = data["placements"]
    tgt_h = float(data["height_mm"])
    order_ids = [p.part_id for p in src_pls]
    orient_map = {p.part_id: p.orientation_idx for p in src_pls}
    log(f"K-19 v2 fine plani: {len(order_ids)} parca, hedef height={tgt_h}mm, "
        f"pitch={data['pitch_mm']}")

    parts, pw, pd = build_fine_parts()
    by_id = {p.id: p for p in parts}
    ordered = [by_id[pid] for pid in order_ids if pid in by_id]
    assert len(ordered) == len(order_ids), (
        f"parca eslesme eksik: {len(ordered)}/{len(order_ids)}")

    res = {}

    if MODE in ("off", "both"):
        log("")
        log("--- CACHE=OFF (referans, uretim default yolu) ---")
        pls, b, ft, ram = run_fine(ordered, orient_map, pw, pd, drop_cache=False)
        h = b.max_height_mm()
        log(f"  height={h:.1f}mm  fine_time={ft:.1f}s ({ft/60:.1f}dk)  "
            f"tepe_RAM={ram:.2f}GB  n_placed={len(pls)}")
        assert abs(h - tgt_h) < 1e-6, f"referans height {h} != {tgt_h}"
        res["off"] = {"key": key_of(pls), "h": h, "ft": ft, "ram": ram}
        log(f"  282.0 DOGRULANDI: {abs(h - tgt_h) < 1e-6}")

    if MODE in ("on", "both"):
        log("")
        log("--- CACHE=ON (H-16 dirty-region) ---")
        pls, b, ft, ram = run_fine(ordered, orient_map, pw, pd, drop_cache=True)
        h = b.max_height_mm()
        st = b.drop_cache_stats()
        log(f"  height={h:.1f}mm  fine_time={ft:.1f}s ({ft/60:.1f}dk)  "
            f"tepe_RAM={ram:.2f}GB  n_placed={len(pls)}")
        log(f"  cache: hit_orani=%{100*st['hit_ratio']:.1f} "
            f"hits={st['hits']} miss={st['misses']} fallback={st['fallbacks']} "
            f"full={st['full_computes']}")
        log(f"  cache: anahtar={st['keys']} tepe_anahtar={st['peak_keys']} "
            f"tepe_cache={st['peak_mb']:.1f}MB (tavan={st['cap_mb']:.0f}MB) "
            f"eviction={st['evictions']}")
        assert abs(h - tgt_h) < 1e-6, f"cache height {h} != {tgt_h}"
        res["on"] = {"key": key_of(pls), "h": h, "ft": ft, "ram": ram, "st": st}
        log(f"  282.0 DOGRULANDI: {abs(h - tgt_h) < 1e-6}")

    # -- birebirlik + hiz + sentez orani --------------------------------------
    if "off" in res and "on" in res:
        log("")
        log("--- KIYAS ---")
        birebir = res["off"]["key"] == res["on"]["key"]
        log(f"  (a) YERLESIM BIREBIR (cache==ref): {birebir}")
        if not birebir:
            diffs = [(a, c) for a, c in zip(res["off"]["key"], res["on"]["key"])
                     if a != c]
            log(f"      UYUSMAZLIK! ilk fark: {diffs[0] if diffs else '?'} "
                f"(toplam {len(diffs)})")
        off_ft, on_ft = res["off"]["ft"], res["on"]["ft"]
        sp = off_ft / on_ft if on_ft else 0.0
        log(f"  (b) FINE SURE: off={off_ft:.1f}s  on={on_ft:.1f}s  "
            f"hizlanma={sp:.1f}x")
        log(f"  (c) TEPE RAM: off={res['off']['ram']:.2f}GB  "
            f"on={res['on']['ram']:.2f}GB  "
            f"delta={res['on']['ram']-res['off']['ram']:+.2f}GB")
        st = res["on"]["st"]
        log(f"  (d) CACHE: hit_orani=%{100*st['hit_ratio']:.1f} "
            f"tepe_cache={st['peak_mb']:.1f}MB anahtar={st['peak_keys']}")

        # -- SENTEZ ORANI (H-15 dersi) ----------------------------------------
        log("")
        log("--- SENTEZ ORANI DEGERLENDIRMESI (H-15 dersi) ---")
        log(f"  [KANITLI-ATIF] uretim fine dblf = {GERCEK_FINE_S:.0f}s")
        atif_oran = off_ft / GERCEK_FINE_S if GERCEK_FINE_S else 0.0
        log(f"  olculen cache-siz fine = {off_ft:.1f}s -> atif-sentez orani "
            f"= {atif_oran:.2f} (1.0 = atif tam ortusuyor)")
        if atif_oran < 0.7:
            log(f"      UYARI: olculen fine ({off_ft:.0f}s) atiftan ({GERCEK_FINE_S:.0f}s) "
                f"belirgin dusuk -> 514s atfi bu izole gecis DEGIL (coarse/voxelize "
                f"dahil olabilir). Hiz kazanci OLCULEN taban uzerinden raporlanir.")
        elif atif_oran > 1.3:
            log(f"      UYARI: olculen fine atiftan yuksek -> makine/yuk farki.")
        else:
            log(f"      OK: olculen fine atifla uyumlu (~1.0).")
        log(f"  [ON-ANALIZ] cache-li fine tahmin bandi = {ONANALIZ_LOW:.0f}..{ONANALIZ_HIGH:.0f}s")
        if on_ft <= ONANALIZ_HIGH * 1.3:
            log(f"  olculen cache-li fine = {on_ft:.1f}s -> ON-ANALIZ bandiyla "
                f"UYUMLU (model dogrulandi).")
        else:
            model_oran = on_ft / ONANALIZ_HIGH
            log(f"  olculen cache-li fine = {on_ft:.1f}s -> bandin ({ONANALIZ_HIGH:.0f}s) "
                f"{model_oran:.1f}x USTUNDE. Sebep adaylari: per-cagri sabit ek-yuk "
                f"(argmin full-Z + kopya), dusuk hit orani, fallback payi. RAPOR: "
                f"hit=%{100*st['hit_ratio']:.0f} fallback={st['fallbacks']}.")

    log("")
    log("H-16 KAPI OLCUMU BITTI.")


if __name__ == "__main__":
    main()

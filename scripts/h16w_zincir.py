# -*- coding: utf-8 -*-
"""h16w_zincir.py — H-16w E2E KAPI: dirty-region drop_map onbellegini URETIME
bagladiktan sonra Deneme4 uctan-uca zincir.

zincir_testi_optin.py'nin AYNI offline-mail kurulumu (nesting_mode=auto +
auto_family_routing=True; monkeypatch YOK, uretim yolu kendi karar verir).
FARK: H-16w cache'i (wall_aware tetiginde drop_cache=True) canli kabloda olculur.

Basari kriterleri (loglanir):
  [A] height_mm == 282.0 (K-19 v2 birebir — cache dogruluk-notr)
  [B] uygulanan pitch 0.5 + kabuk-ailesi + wall_aware izi (zincir kuruldu)
  [C] telemetride drop_cache_* istatistikleri GORUNUR (hit_ratio/keys/peak_mb)
  [D] toplam sure ~150-200s bandinda (fine 119s + coarse 39s + vox/settle)
      -> H-15p tek basina ~553s bandindaydi; H-16w fine'i 4x kisaltir.
  [E] tepe RAM makul (<6GB civari)

Kosum (~3-4 dk): python -m scripts.h16w_zincir
SAF ASCII cikti (cp1254 guvenli). Uretime DOKUNMAZ (yalniz opt-in bayraklar).
"""
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = Path(__file__).parent / "h16w_zincir.log"

# Beklenti bandi (rapor-only degerlendirme)
SURE_LOW = 120.0
SURE_HIGH = 260.0   # ust band biraz genis (makine/vox degiskenligi)
RAM_CAP_GB = 6.5


def log(msg=""):
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


from src.runtime.mail_ingest import Attachment, RawMail, ingest_order  # noqa: E402
from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline  # noqa: E402

SRC = ROOT / "data" / "mail_stl" / "mail_stl_AD786DF3"
GOVDE = """588 parca icin imalat yuksekligi 250,24 mm'dir.

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


def main():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for stl in sorted(SRC.glob("*.stl")):
            z.writestr(stl.name, stl.read_bytes())

    mail = RawMail(
        gonderen="mcoskun@fsm.edu.tr", konu="Deneme4-h16w", govde=GOVDE,
        tarih="2026-07-05T12:00:00+03:00", message_id="<h16w-zincir@offline>",
        ekler=[Attachment("Deneme 4 STL.zip", buf.getvalue(),
                          "application/x-zip-compressed")],
    )
    order = ingest_order(mail, parser_role=None,
                         persist_root=str(Path(__file__).parent / "zincir_stl"))
    assert order and not order.get("needs_review"), f"ingest bozuk: {order}"
    order["deadline"] = "2026-07-13"

    scenario = {**RICH_SCENARIO, "orders": [order],
                "container": order.get("container"),
                "nesting_mode": "auto", "auto_family_routing": True}

    t = threading.Thread(target=_sampler, daemon=True)
    t.start()
    vm = psutil.virtual_memory()
    log("=" * 74)
    log("H-16w E2E KAPI — nesting_mode=auto + auto_family_routing=True "
        "(wall_aware'i F5 acmali, drop_cache uretim tetigi)")
    log(f"RAM musait={vm.available / 1e9:.1f}GB | beklenti: 282.0mm @0.5, "
        f"sure {SURE_LOW:.0f}..{SURE_HIGH:.0f}s")
    log("=" * 74)
    t0 = time.perf_counter()
    try:
        result = run_pipeline(scenario)
        el = time.perf_counter() - t0
        log(f"BITTI — {el:.0f}s ({el / 60:.1f} dk)")
        for bid, nr in result.get("nesting_results", {}).items():
            log(f"[{bid}] --- nesting sonucu (skaler alanlar) ---")
            for k in sorted(nr):
                v = nr[k]
                if isinstance(v, (str, int, float, bool)) or v is None:
                    log(f"[{bid}]   {k} = {v}")
            blob = json.dumps(nr, default=str, ensure_ascii=False)
            h = float(nr.get("height_mm") or 0)
            chk_a = abs(h - 282.0) < 1e-6
            chk_b = ("wall_aware" in blob) and (("thin_shell" in blob)
                                                or ("kabuk" in blob))
            hr = nr.get("drop_cache_hit_ratio")
            keys = nr.get("drop_cache_keys")
            pmb = nr.get("drop_cache_peak_mb")
            fb = nr.get("drop_cache_fallbacks")
            chk_c = hr is not None and keys is not None
            log(f"[{bid}] KRITER A (282.0 birebir): "
                f"{'PASS' if chk_a else 'FAIL'} (height={h})")
            log(f"[{bid}] KRITER B (kabuk+wall_aware izi): "
                f"{'PASS' if chk_b else 'FAIL'}")
            log(f"[{bid}] KRITER C (cache telemetri gorunur): "
                f"{'PASS' if chk_c else 'FAIL'} -> "
                f"hit_orani=%{100 * hr:.1f} anahtar={keys} "
                f"tepe_cache={pmb:.1f}MB fallback={fb}"
                if chk_c else f"[{bid}] KRITER C: FAIL (cache alanlari yok — "
                              f"wall_aware/drop_cache tetiklenmemis olabilir)")
        el_ok = SURE_LOW <= el <= SURE_HIGH
        log(f"KRITER D (sure {SURE_LOW:.0f}..{SURE_HIGH:.0f}s bandi): "
            f"{'PASS' if el_ok else 'DIKKAT'} (olculen={el:.0f}s)")
        log("KIYAS: K-19 v2=282.0 | H-15p tek basina ~553s | Magics=250.24")
    except Exception as exc:
        import traceback
        log(f"HATA ({time.perf_counter() - t0:.0f}s): "
            f"{type(exc).__name__}: {exc}")
        log(traceback.format_exc())
    finally:
        _stop.set()
        t.join(timeout=5)
        ram_gb = _peak["rss"] / 1e9
        log(f"KRITER E (tepe RAM <{RAM_CAP_GB:.1f}GB): "
            f"{'PASS' if ram_gb < RAM_CAP_GB else 'DIKKAT'} "
            f"(process={ram_gb:.2f}GB)")


if __name__ == "__main__":
    main()

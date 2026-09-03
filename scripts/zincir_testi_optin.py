# -*- coding: utf-8 -*-
"""zincir_testi_optin.py — Sprint 3 madde 3: uctan-uca OPT-IN ZINCIR TESTI.

SORU (rollout on-kaniti): nesting_mode="auto" + auto_family_routing=True
bayraklariyla URETIM YOLU kendi basina su zinciri kuruyor mu?
  predict_nfv_benefit(family_routing=True)
    -> kabuk-ailesi tespiti (deneme4 thin_shell 0.87)
    -> mod-flip (nfv yerine heightmap) + wall_aware onerisi
    -> suggest_pitch(wall_aware=True) -> 0.5mm cidar-pitch
    -> K-19 sonucu: 282.0mm BIREBIR (beklenen)

Basari kriterleri (loglanir):
  [A] height_mm == 282.0 (K-19 v2 birebir)
  [B] uygulanan pitch 0.5 (applied_pitch_mm / pitch izleri)
  [C] auto gerekce izinde kabuk-ailesi + wall_aware gorunur
Fark cikarsa zincirin HANGI halkasi koptu loglardan okunur.

k19_cidar_pitch_olcum.py'nin AYNI offline-mail kurulumu; FARKI: monkeypatch
YOK (uretim yolu kendi karar verir) + mode=auto + family_routing acik.
AYRIK surecte kos (~2 saat): python -m scripts.zincir_testi_optin
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
LOG = Path(__file__).parent / "zincir_testi.log"


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
    gonderen="mcoskun@fsm.edu.tr", konu="Deneme4-zincir", govde=GOVDE,
    tarih="2026-07-03T16:11:14+03:00", message_id="<zincir-optin@offline>",
    ekler=[Attachment("Deneme 4 STL.zip", buf.getvalue(), "application/x-zip-compressed")],
)
order = ingest_order(mail, parser_role=None,
                     persist_root=str(Path(__file__).parent / "zincir_stl"))
assert order and not order.get("needs_review"), f"ingest bozuk: {order}"
order["deadline"] = "2026-07-13"

# ZINCIR: mode=auto + F5 aile-yonlendirme ACIK (wall_aware'i F5 kendisi acmali!)
scenario = {**RICH_SCENARIO, "orders": [order], "container": order.get("container"),
            "nesting_mode": "auto", "auto_family_routing": True}

t = threading.Thread(target=_sampler, daemon=True)
t.start()
vm = psutil.virtual_memory()
log("ZINCIR TESTI BASLADI — nesting_mode=auto + auto_family_routing=True "
    "(wall_aware bayragi BILEREK verilmedi; F5 acmali)")
log(f"RAM musait={vm.available / 1e9:.1f}GB | beklenen: heightmap@0.5 -> 282.0mm")
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
        chk_a = abs(float(nr.get("height_mm") or 0) - 282.0) < 1e-6
        chk_c = ("wall_aware" in blob) and (("thin_shell" in blob) or ("kabuk" in blob))
        log(f"[{bid}] KRITER A (282.0 birebir): {'PASS' if chk_a else 'FAIL'} "
            f"(height={nr.get('height_mm')})")
        log(f"[{bid}] KRITER C (kabuk+wall_aware izi): {'PASS' if chk_c else 'FAIL'}")
    log("KIYAS: K-19 v2=282.0 | eski hm@2.9=377.3 | Magics=250.24")
except Exception as exc:
    log(f"HATA ({time.perf_counter() - t0:.0f}s): {type(exc).__name__}: {exc}")
finally:
    _stop.set()
    t.join(timeout=5)
    log(f"TEPE RAM process={_peak['rss'] / 1e9:.2f}GB")

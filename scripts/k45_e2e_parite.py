# -*- coding: utf-8 -*-
"""k45_e2e_parite.py — K-45 UCTAN-UCA PARITE KANITI (A1 eval kapisi).

SORU: uygulamanin GERCEK yolu (mail ingest -> run_pipeline -> NFV kalite modu)
K-44 sampiyon sonucunu (deneme5 223.5 cift-legal) KENDI BASINA uretiyor mu?

Zincir (hicbir monkeypatch yok — uretim yolu kendi karar verir):
  plate.local.json (335x335x600 + no_go) -> ingest_order -> run_pipeline
  {nesting_mode:"nfv", nfv_quality:"max"} -> solve_nfv_kalite recetesi
  (pitch=clearance=2.0; ham kilitsizse guard yok) -> 223.5 birebir.

Basari kriterleri:
  [A] height_mm == 223.5 (+/-0.1; K-44 birebir)
  [B] nfv_kalite izi: pitch_mm=2.0, secilen=ham, guard_kosuldu=False,
      ham_n_locked=0
  [C] no-go maskesi etkin (plate.local.json'dan cozuldu — iz yoksa FAIL degil,
      yukseklik pariteyi zaten kanitlar; yine de loglanir)
Kosum: python -m scripts.detach_run k45_e2e_parite    SAF ASCII.
"""
from __future__ import annotations
import io
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = Path(__file__).parent / "k45_e2e_parite.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


LOG.write_text("", encoding="utf-8")
log("K-45 E2E PARITE — deneme5 mail-yolu @nfv/max (beklenen 223.5 birebir)")

from src.runtime.mail_ingest import Attachment, RawMail, ingest_order  # noqa: E402
from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline  # noqa: E402

SRC = ROOT / "data" / "mail_stl" / "deneme5"
adet = (SRC / "_adet_listesi.txt").read_text(encoding="utf-8")
# GOVDE deneme4 gercek-mail formatini izler: beyan toplami = liste toplami
# (ilk deneme "Deneme5" kelimesindeki 5'i beyan sanip quantity_conflict verdi).
GOVDE = "352 parca icin yerlestirme rica ederim.\n\n" + adet

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for stl in sorted(SRC.glob("*.stl")):
        if not stl.stem.startswith("_"):
            z.writestr(stl.name, stl.read_bytes())

mail = RawMail(
    gonderen="mcoskun@fsm.edu.tr", konu="Deneme5-K45-parite", govde=GOVDE,
    tarih="2026-07-11T18:00:00+03:00", message_id="<k45-parite@offline>",
    ekler=[Attachment("Deneme5.zip", buf.getvalue(), "application/x-zip-compressed")],
)
order = ingest_order(mail, parser_role=None,
                     persist_root=str(Path(__file__).parent / "k45_stl"))
if not order or order.get("needs_review"):
    log(f"INGEST HATA: needs_review={order.get('needs_review') if order else None} "
        f"reason={order.get('review_reason') if order else 'order=None'}")
    log("BITTI")
    sys.exit(1)
log(f"ingest OK: {order.get('order_id')} — parca kaynagi dogrulandi")
order["deadline"] = "2026-07-20"
n_beklenen = 352

scenario = {**RICH_SCENARIO, "orders": [order], "container": order.get("container"),
            "nesting_mode": "nfv", "nfv_quality": "max"}
log(f"container(order): {order.get('container')}")
t0 = time.perf_counter()
try:
    result = run_pipeline(scenario)
    el = time.perf_counter() - t0
    log(f"run_pipeline BITTI — {el / 60:.1f} dk")
    for bid, nr in result.get("nesting_results", {}).items():
        h = float(nr.get("height_mm") or 0)
        tel = nr.get("nfv_kalite") or {}
        log(f"[{bid}] h={h}  n_parts={nr.get('n_parts')}  "
            f"mode={nr.get('nesting_mode_used')}  pitch={nr.get('pitch_mm')}")
        log(f"[{bid}] nfv_kalite={json.dumps(tel, ensure_ascii=False)}")
        log(f"[{bid}] min_clearance={nr.get('min_clearance_mm')}  "
            f"n_locked={nr.get('n_locked')}  note={nr.get('note')!r}")
        chk_a = abs(h - 223.5) <= 0.1 and int(nr.get("n_parts") or 0) == n_beklenen
        chk_b = (tel.get("pitch_mm") == 2.0 and tel.get("secilen") == "ham"
                 and tel.get("guard_kosuldu") is False
                 and tel.get("ham_n_locked") == 0)
        log(f"[{bid}] KRITER A (223.5 birebir + 352/352): "
            f"{'PASS' if chk_a else 'FAIL'}")
        log(f"[{bid}] KRITER B (recete izi ham/2.0/guardsuz/kilitsiz): "
            f"{'PASS' if chk_b else 'FAIL'}")
    log("KIYAS: K-44 ham=223.5 cift-legal | heightmap eski=338.4 | manuel=209")
except Exception as exc:
    import traceback
    log(f"HATA ({time.perf_counter() - t0:.0f}s): {type(exc).__name__}: {exc}")
    log(traceback.format_exc()[-1500:])
log("BITTI")

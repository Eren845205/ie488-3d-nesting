# -*- coding: utf-8 -*-
"""p7_r11_onolcum.py — Plan7 488.4 HAZIR yerlesimini uretim R11'iyle YASAL
sikistir: motor degisikligi yok, yalniz olcum (Eren istegi 2026-08-17,
A4 olc-once: "algoritmaya dokunmadan nereye inecegini raporla").

Kaynak sahne: arsiv GLB (345 parca-dugumlu, gercek mesh geometrisi,
rehberli-sokum paketinden). Arac: continuous_settle.uretim_r11 —
TEK-TARAFLI 4-kapili sozlesme (yakinsama + min_clearance>=2.0 + kilit
artmaz [rot-sokum aklamasi acik] + kazanc>0). Kapilar gecilemezse None =
"mevcut 488.4 zaten R11-oturmus" bulgusu olur; o da rapor.
"""
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

GLB = _ROOT / "data" / "otonom_gecmis" / "glb" / "f04187471970_B001.glb"
NOGO = ((152.5, 0.2), (185.5, 33.0))  # eval_gate NOGO_HARD (tarihsel sabit)
CLEAR = 2.0

print("GLB yukleniyor...", flush=True)
sc = trimesh.load(str(GLB), file_type="glb")
meshes = []
for ad in sc.graph.nodes_geometry:
    T, gname = sc.graph[ad]
    m = sc.geometry[gname].copy()
    m.apply_transform(T)
    meshes.append(m)
print(f"{len(meshes)} parca acildi", flush=True)

h0 = max(float(m.bounds[1][2]) for m in meshes)
z_min = min(float(m.bounds[0][2]) for m in meshes)
print(f"baslangic: tepe={h0:.2f}mm taban_min={z_min:.2f}mm", flush=True)

from src.nesting3d.continuous_settle import uretim_r11

t0 = time.perf_counter()
res = uretim_r11(
    meshes,
    clearance_mm=CLEAR,
    no_go_bounds=NOGO,
    rot_kabul=True,  # kilit artarsa rot-sokum denetimiyle aklama (K-52)
)
sure = time.perf_counter() - t0

cikti = {
    "amac": "p7 488.4 hazir-yerlesim R11 on-olcumu (motor degisikligi yok)",
    "kaynak": str(GLB.name),
    "n_parca": len(meshes),
    "h0_mm": round(h0, 3),
    "clearance_kural_mm": CLEAR,
    "no_go": NOGO,
    "sure_s": round(sure, 1),
    "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
if res is None:
    cikti["sonuc"] = "KAPI-RED (None)"
    cikti["yorum"] = ("R11 4-kapili sozlesmede kazanc bulamadi/aklayamadi — "
                     "488.4 mevcut aracla zaten oturmus; kazanc icin "
                     "relokasyon/yeniden-istif sinifi gerekir")
else:
    cikti["sonuc"] = "KAZANC"
    cikti["h_yeni_mm"] = round(float(res["height_mm"]), 3)
    cikti["kazanc_mm"] = round(float(res["kazanc_mm"]), 3)
    cikti["kazanc_pct"] = round(100.0 * float(res["kazanc_mm"]) / h0, 2)
    cikti["min_clearance_mm"] = round(float(res["min_clearance_mm"]), 3)
    cikti["kilit_pre"] = res.get("kilit_pre")
    cikti["kilit_post"] = res.get("kilit_post")
    cikti["sokum_planli"] = bool(res.get("sokum_planli"))
    cikti["rot_cert"] = res.get("rot_cert")
    cikti["rafine_tur"] = res.get("rafine_tur")

print(json.dumps(cikti, ensure_ascii=False, indent=2), flush=True)

out = _ROOT / "results" / "p7_r11_onolcum.json"
out.write_text(json.dumps(cikti, ensure_ascii=False, indent=2),
               encoding="utf-8")
d_out = Path(r"D:\ie488\results\p7_r11_onolcum.json")
try:
    d_out.write_text(json.dumps(cikti, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"yazildi: {out} + {d_out}")
except OSError as exc:
    print(f"yazildi: {out} (D kopyasi HATA: {exc})")

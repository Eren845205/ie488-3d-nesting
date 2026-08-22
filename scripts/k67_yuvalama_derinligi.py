# -*- coding: utf-8 -*-
"""k67_yuvalama_derinligi.py - K-67 SINDIL on-olcumu: yuvalama derinligi.

Mekanizma kaynagi: PLAN8 anatomisi (MK-04; 118 braket ~17mm z-adimla
ic ice, %65 z-tasarrufu). K-67 tetigi GEOMETRIK olmali (A11): parca
kendi kopyasinin uzerine EN DERIN cakismasiz + clearance'li oturma
derinligi GERCEK geometriden olculur; z_adim < 0.7 x parca-yuksekligi
ise yuvalanabilir sinifi.

Olcum (dakikalik on-hesap, A4): parca voxelize edilir (raw, slice);
alt kopya tek-tarafli z-dilation (clearance) tasir; ust kopya xy-HIZALI
raw grid. En kucuk z-ofset o bulunur ki iki grid cakismasin ->
z_adim = o x pitch (kademeli istif plan-adimi; bosluk >= clearance
z-dilation'dan gelir, K-66-d pin sozlesmesiyle ayni).

NOT: xy-hizali ayni-oryantasyon taramasidir (PLAN8 deseni birebir);
yaw/ofsetli yuvalama v2 isi. Kablo DEGIL - olcum harness'i (A11 serhli).

Kosum: D:\\ie488'den python -m scripts.detach_run k67_yuvalama_derinligi
Env: K67_STL (tek STL yolu) veya K67_STL_DIR (dizindeki tum STL'ler);
     K67_PITCH (default 1.0) / K67_CLEAR (default 2.0)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k67_yuvalama_derinligi.log"
OUT = _ROOT / "results" / "k67_yuvalama_derinligi.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def yuvalama_derinligi_grid(grid: np.ndarray, pitch: float,
                            clear: float) -> Dict:
    """Voxel grid'inden xy-hizali yuvalama olcumu (saf mantik, testli).

    grid: parcanin RAW (dilation'siz) bool grid'i (x, y, z).
    Alt kopya z_dilate(ceil(clear/pitch)) tasir; ust kopya raw.
    Donen: z_adim_mm (kademeli istif adimi), h_mm, tasarruf_orani,
    yuvalanabilir (z_adim < 0.7*h).
    """
    from src.nesting3d.voxelize import _dilate_z_up
    h_vox = int(grid.shape[2])
    zc = max(1, int(np.ceil(clear / pitch)))
    alt = _dilate_z_up(grid, zc)          # tepe clearance bandi
    h_alt = int(alt.shape[2])
    # ust kopyanin taban-ofseti o: alt[:, :, o:o+h_vox] ile raw cakismamali
    z_adim_vox: Optional[int] = None
    for o in range(1, h_alt + 1):
        n = min(h_vox, h_alt - o)
        if n <= 0:                         # tamamen ustunde -> cakisamaz
            z_adim_vox = o
            break
        if not np.logical_and(alt[:, :, o:o + n], grid[:, :, :n]).any():
            z_adim_vox = o
            break
    if z_adim_vox is None:                 # teorik olarak imkansiz (emniyet)
        z_adim_vox = h_alt
    h_mm = h_vox * pitch
    z_adim_mm = z_adim_vox * pitch
    return {"h_mm": round(h_mm, 2), "z_adim_mm": round(z_adim_mm, 2),
            "zc_vox": zc,
            "tasarruf_orani": round(max(0.0, 1.0 - z_adim_mm / h_mm), 3),
            "yuvalanabilir": bool(z_adim_mm < 0.7 * h_mm)}


def sindil_adimi_grid(grid: np.ndarray, pitch: float, clear: float,
                      dy_max_mm: Optional[float] = None) -> Dict:
    """SINDIL taramasi (MK-04 birebir): (dy, dz) ofset ciftleri taranir,
    her dy icin minimum cakismasiz dz bulunur; en dusuk dz'li cift doner.

    xy-hizali yuvalama (dy=0) ozel haldir; fsm braketinde dy=0 yuvalanmaz
    (2026-08-20 gece olcumu) ama PLAN8 mühendisi (dy~16, dz~17) diziyor.
    Alt kopya once xy-dilate(margin) sonra z-up(zc) tasir -> kompoze
    dilation (y,z) capraz kosesini de kapsar (olcum konservatif; kosegen
    sizinti sinifi burada yapisal kapali).

    dy siniri: default d/2 (anlamli footprint ortusmesi sarti) - dy ~ d
    dejenere "yan-yana" cozumune kacar (dz -> 0 sahte kazanci); sindil =
    ic-ice dizim, bitisik yerlesim degil (PLAN8: dy/d ~ 0.2).
    """
    from src.nesting3d.voxelize import _dilate, _dilate_z_up
    w, d, h_vox = grid.shape
    zc = max(1, int(np.ceil(clear / pitch)))
    mc = max(1, int(np.ceil(clear / pitch)))
    alt = _dilate_z_up(_dilate(grid, mc), zc)   # pad mc (x,y) + zc (üst)
    h_alt = alt.shape[2]
    dy_max = d // 2 if dy_max_mm is None else min(
        d, int(np.ceil(dy_max_mm / pitch)))
    en_iyi = None
    for dy in range(0, dy_max + 1):
        # ust kopya +y'ye dy kaydirilir; alt grid mc-pad'li -> hizalama:
        # ust raw hucre (x, y) ~ alt hucre (x+mc, y+mc+dy)
        for o in range(1, h_alt + 1):
            n = min(h_vox, h_alt - o)
            if n <= 0:
                cakisma = False
            else:
                y0 = mc + dy
                ny = min(d, alt.shape[1] - y0)
                if ny <= 0:
                    cakisma = False
                else:
                    cakisma = bool(np.logical_and(
                        alt[mc:mc + w, y0:y0 + ny, o:o + n],
                        grid[:, :ny, :n]).any())
            if not cakisma:
                if en_iyi is None or o < en_iyi[1]:
                    en_iyi = (dy, o)
                break
    dy_v, dz_v = en_iyi if en_iyi else (0, h_alt)
    h_mm = h_vox * pitch
    dz_mm = dz_v * pitch
    return {"h_mm": round(h_mm, 2), "dy_mm": round(dy_v * pitch, 2),
            "dz_mm": round(dz_mm, 2),
            "tasarruf_orani": round(max(0.0, 1.0 - dz_mm / h_mm), 3),
            "yuvalanabilir": bool(dz_mm < 0.7 * h_mm)}


def yuvalama_derinligi_mesh(mesh, pitch: float, clear: float) -> Dict:
    """Mesh'ten olcum: en buyuk boyut z'ye degil GELDIGI durusta olculur
    (PLAN8 braketleri yatik yuvalaniyor; durus secimi cagiranin isi)."""
    from src.nesting3d.voxelize import voxelize_part
    vp = voxelize_part("k67", mesh, pitch, n_orientations=1, method="slice")
    return yuvalama_derinligi_grid(vp.orientations[0].grid, pitch, clear)


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    import trimesh
    pitch = float(os.environ.get("K67_PITCH", "1.0"))
    clear = float(os.environ.get("K67_CLEAR", "2.0"))
    tek = os.environ.get("K67_STL")
    dizin = os.environ.get("K67_STL_DIR")
    yollar = []
    if tek:
        yollar = [Path(tek)]
    elif dizin:
        yollar = sorted(Path(dizin).glob("*.stl"))
    if not yollar:
        log("HATA: K67_STL veya K67_STL_DIR verilmeli")
        return 2
    log("K-67 YUVALAMA DERINLIGI OLCUMU (A11 serhli on-olcum; kablo degil)")
    log(f"pitch={pitch} clear={clear} n_stl={len(yollar)}")
    t0 = time.time()
    sonuclar = {}
    for p in yollar:
        try:
            mesh = trimesh.load(str(p), force="mesh")
            r = yuvalama_derinligi_mesh(mesh, pitch, clear)
            sonuclar[p.stem] = r
            log(f"  {p.stem[:44]:46s} h={r['h_mm']:7.1f} "
                f"z_adim={r['z_adim_mm']:6.1f} "
                f"tasarruf={r['tasarruf_orani']:.0%} "
                f"{'YUVALANABILIR' if r['yuvalanabilir'] else '-'}")
        except Exception as exc:
            sonuclar[p.stem] = {"hata": str(exc)}
            log(f"  {p.stem[:44]:46s} HATA: {exc}")
    doc = {"olcum": "k67_yuvalama_derinligi", "tarih": str(date.today()),
           "ayarlar": {"pitch": pitch, "clear": clear},
           "sonuclar": sonuclar, "sure_s": round(time.time() - t0, 1),
           "a11_not": "on-olcum; K-67 dizim prototipi ve kapi ayri adim"}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
    except Exception as exc:
        log(f"uyari: OneDrive kopyasi yazilamadi ({exc})")
    log(f"KAYIT: {OUT}")
    log(f"BITTI sure={time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

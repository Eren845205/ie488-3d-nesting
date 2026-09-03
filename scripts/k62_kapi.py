# -*- coding: utf-8 -*-
"""k62_kapi.py — K-62 kanopi zinciri 4-SET KAPI olcumu (A11 GO-ilani adimi).

Iki kanit tek koşuda:
  1. SIFIR-DOKUNUS: tetiksiz dev-setlerde (plan2/plan3/deneme4) geometrik
     tetik ATESLEMIYOR kaniti — cozumsuz, yalniz kanopi_adayi() cagrisi
     (A4 olc-once: mekanizma opt-in oldugundan yapisal bit-ozdeslik zaten
     var; burada tetigin kendisinin de sessiz kaldigi OLCULUR).
  2. OTOMATIK ZINCIR (plan1): kanopi_zinciri_coz greedy_r1=True, elle
     z / elle rutbe YOK — kablonun v13b el-recetesi sinifini (130.80;
     pin-yalniz 140.21) KENDI BASINA bulmasi. Kazanan cozumde A2 tam
     legalite: clearance + 5-yon kilit (+ gerekirse rot-sokum).

Kosum: python -m scripts.detach_run k62_kapi   (D:\\ie488, MUNHASIR —
K-57a; plan1 zinciri ~30-50dk). SAF ASCII.
Env: K62KAPI_GREEDY (6) - K62KAPI_ROT_BUTCE_S (1200).
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.eval_gate as eg
from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import kilit_5yon_meshes, kilit_rot_meshes
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi_zincir import kanopi_adayi, kanopi_zinciri_coz

LOG = Path(__file__).parent / "k62_kapi.log"
OUT = _ROOT / "results" / "k62_kapi.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF = {"v13b_el_recetesi": 130.80, "pin_k56f": 140.21, "manuel": 110.41}
MAX_GREEDY = int(os.environ.get("K62KAPI_GREEDY", "6"))
ROT_BUTCE_S = float(os.environ.get("K62KAPI_ROT_BUTCE_S", "1200"))
TETIKSIZ_SETLER = ["plan2", "plan3", "deneme4"]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 4-SET KAPI: sifir-dokunus tetik kaniti + plan1 otomatik zincir")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} greedy={MAX_GREEDY}")

    # ---- 1) tetiksiz setlerde tetik sessiz mi? -----------------------
    log("[1] tetik taramasi (cozumsuz)")
    tetik_sonuc = {}
    ihlal = 0
    for ad in TETIKSIZ_SETLER:
        try:
            inst = eg._load_instance(ad)
            aday = kanopi_adayi(inst, eg.PLATE_STD[0], eg.PLATE_STD[1],
                                eg.NOGO_STD)
            ates = aday is not None
            det = (None if aday is None else
                   {"parca": aday["part"].name,
                    "alan_oran": aday["alan_oran"],
                    "doluluk": aday["fiz"]["doluluk"]})
            tetik_sonuc[ad] = {"ates": ates, "detay": det}
            if ates:
                ihlal += 1  # "ek tetiklenen set" sayaci (ihlal degil —
                # tetik geometrik kosul; atesleyen set etki-olcumu ister)
            log(f"  {ad}: ates={int(ates)}"
                f"{'  <<< TETIK ATESLEDI (etki-olcumu ayri kosuda): ' + str(det) if ates else ''}")
            del inst
            gc.collect()
        except Exception:
            tetik_sonuc[ad] = {"ates": None,
                               "hata": traceback.format_exc(limit=2)}
            log(f"  {ad}: TARAMA HATASI (kayitta)")
    log(f"[1] SONUC: tetik-atesleyen ek set={ihlal}/3"
        " (bunlar 'tetikli' sinifina gecer; zincir etkisi ayri munhasir"
        " kosuda olculur — tek-taraflilik geregi yukseklik kotulesemez)")

    # ---- 2) plan1 otomatik zincir ------------------------------------
    log("[2] plan1 otomatik zincir (elle z/rutbe YOK, greedy acik)")
    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    res, tel = kanopi_zinciri_coz(
        inst, plate_w_mm=eg.PLATE_STD[0], plate_d_mm=eg.PLATE_STD[1],
        no_go_bounds=eg.NOGO_STD, clearance_mm=CLEAR_MM, seed=SEED,
        greedy_r1=True, max_greedy=MAX_GREEDY)
    h = float(res.height_mm)
    for a in tel["adimlar"]:
        log(f"  adim: {a}")
    log(f"[2] zincir: h={h:.2f} n={int(res.n_placed)}/{n_total}"
        f" etiket={tel.get('etiket')} tetik={tel['tetik']}"
        f" z={tel.get('z_secilen')} rutbeler={tel.get('rutbeler')}")
    log(f"[2] referanslar: el-recetesi {REF['v13b_el_recetesi']}"
        f" / pin {REF['pin_k56f']} / manuel {REF['manuel']}")

    # ---- 3) A2 tam legalite + GERI-DUSUS -----------------------------
    # Kapi-v2 dersi (2026-08-05): kazanan 132.60 clearance 1.961 (39 mikron
    # ihlal) -> INVALID. Uretim-sinifi davranis: kazanan gecemezse siradaki
    # adaya dus (oncelik-r0 -> yalniz-pin), her aday tam A2 olculur.
    def a2_olc(r):
        cl_mm = None
        kilit5 = rot_kilit = rot_cert = None
        sokum_planli = False
        try:
            meshes = list(placed_meshes(list(r.placements),
                                        r.fine_voxel_parts,
                                        float(r.fine_pitch)))
            cl = min_clearance(meshes)
            cl_mm = float(cl.min_mm)
            log(f"  clearance min={cl_mm:.3f}mm (kural >= {CLEAR_MM})")
            kilit5 = kilit_5yon_meshes(meshes)
            log(f"  kilit 5-yon={kilit5}")
            if kilit5 and kilit5 > 0:
                rapor = kilit_rot_meshes(meshes, sure_butcesi_s=ROT_BUTCE_S)
                rot_kilit = int(rapor.n_locked)
                rot_cert = len(getattr(rapor, "certificates", {}) or {})
                sokum_planli = (rot_kilit == 0)
                log(f"  kilit rot={rot_kilit} cert={rot_cert}")
        except Exception:
            log(f"  LEGALITE OLCUM HATASI:\n{traceback.format_exc()}")
        yer_ok = int(r.n_placed) == n_total
        cl_ok = cl_mm is not None and cl_mm >= CLEAR_MM
        kilit_ok = (kilit5 == 0) or sokum_planli
        return {"min_clearance_mm": cl_mm, "kilit_5yon": kilit5,
                "rot_kilit": rot_kilit, "rot_cert": rot_cert,
                "sokum_planli": sokum_planli,
                "legal": yer_ok and cl_ok and kilit_ok}

    log("[3] A2 legalite (kazanan)")
    a2 = a2_olc(res)
    legal = a2["legal"]
    log(f"[3] kazanan: {'LEGAL' if legal else 'INVALID'} h={h:.2f}")

    geri_dusus = []
    if not legal and tel.get("tetik"):
        from src.nesting3d.kanopi_zincir import kanopi_adayi as _ka, kanopi_pin
        from src.nesting3d.nfv_solve import solve_nfv
        aday = _ka(inst, eg.PLATE_STD[0], eg.PLATE_STD[1], eg.NOGO_STD)
        z = tel.get("z_secilen")
        r0_rutbe = {ad: 0 for ad in (tel.get("asan_tipler") or {})}
        adaylar = []
        if r0_rutbe and tel.get("rutbeler") != r0_rutbe:
            adaylar.append(("oncelik-r0", r0_rutbe))
        adaylar.append(("yalniz-pin", None))
        for etiket_gd, rutbe in adaylar:
            if legal or aday is None or z is None:
                break
            log(f"[3-gd] geri-dusus adayi: {etiket_gd} (z={z} rutbe={rutbe})")
            r_gd = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                             plate_d_mm=eg.PLATE_STD[1], fine_pitch=None,
                             seed=SEED, quality="fast",
                             clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                             pinned_placements=[kanopi_pin(aday, z)],
                             pin_3d=True, oncelik_adlari=rutbe)
            h_gd = float(r_gd.height_mm)
            log(f"[3-gd] {etiket_gd}: h={h_gd:.2f} n={int(r_gd.n_placed)}")
            a2_gd = a2_olc(r_gd)
            geri_dusus.append({"etiket": etiket_gd, "height_mm": h_gd,
                               "n_placed": int(r_gd.n_placed),
                               "rutbeler": rutbe, **a2_gd})
            if a2_gd["legal"]:
                res, h, a2, legal = r_gd, h_gd, a2_gd, True
                tel["geri_dusus_kazandi"] = etiket_gd
                log(f"[3-gd] LEGAL bulundu: {etiket_gd} h={h_gd:.2f}")
                break
            del r_gd
            gc.collect()
    log(f"[3] SONUC: {'LEGAL' if legal else 'INVALID'} h={h:.2f}")
    cl_mm, kilit5 = a2["min_clearance_mm"], a2["kilit_5yon"]
    rot_kilit, rot_cert = a2["rot_kilit"], a2["rot_cert"]
    sokum_planli = a2["sokum_planli"]

    doc = {
        "olcum": "k62_kapi", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("4-set kapi paketi: tetiksiz setlerde cozumsuz tetik "
                 "taramasi (mekanizma opt-in — yapisal sifir-dokunus ayrica "
                 "testli); plan1 otomatik zincir + A2 tam legalite. "
                 "held-out DAHIL DEGIL (A3)."),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED},
        "tetik_taramasi": tetik_sonuc,
        "plan1": {"height_mm": h, "n_placed": int(res.n_placed),
                  "n_total": n_total, "telemetri": tel,
                  "min_clearance_mm": cl_mm, "kilit_5yon": kilit5,
                  "rot_kilit": rot_kilit, "rot_cert": rot_cert,
                  "sokum_planli": sokum_planli, "legal": legal,
                  "geri_dusus": geri_dusus},
        "referanslar": REF,
        "ozet": {"tetiksiz_ihlal": ihlal, "plan1_h": h, "plan1_legal": legal},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
            log(f"kopya: {ek}")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")

    log(f"OZET: tetiksiz_ihlal={ihlal} plan1_h={h:.2f} legal={legal}")
    log(f"WALL_S={time.perf_counter() - t0:.1f}"
        f"  ({(time.perf_counter() - t0) / 60:.1f} dk)")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise

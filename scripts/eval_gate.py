# -*- coding: utf-8 -*-
"""eval_gate.py — STRATEJI Faz-0: tek-komut degerlendirme kapisi.

Amac (STRATEJI/02_EVAL_KAPISI.md §2, §5 Faz-0): her "iyilestirme iddiasi"
sonrasi TUM dev-set'leri URETIM sampiyonu yollarindan kosar, DURUST metrigi
(legal_height: yerlesen==N ve min_clearance>=2mm ve 0 kilit — 5-yon kilit>0
ise rot-sokum denetimi kilitleri yeniden yargilar, rot kilit=0 -> SOKUM-PLANLI
legal; A2 katmani Eren karari 2026-07-15) olcer, baseline
ile kiyaslar, ANAYASA B2 esikleriyle verdict basar. Yeni algoritma YOK —
mevcut parcalarin konsolidasyonu (c3_generality DATASETS + clearance.
min_clearance + accessibility.check_placements + uretim solve yollari).

Kullanim:
  python -m scripts.eval_gate --save-baseline          # ilk koşu: baseline yaz
  python -m scripts.eval_gate                          # kiyas + verdict
  python -m scripts.eval_gate --sets deneme4           # tek set (smoke)
  python -m scripts.eval_gate --heldout-final --sets boxy   # held-out FINAL kosusu
                                                       # (bakisi 01_VERI registry'ye YAZ!)
Esikler (00_ANAYASA B2): herhangi bir set >%2 kotu veya INVALID -> FAIL;
+-%0.5 gurultu bandi; hicbiri kotulesmeden >=1 set iyilesme -> PASS; arasi
-> INSAN KARARI. Held-out setler --heldout-final bayragi olmadan REDDEDILIR.

Sampiyon yollar (uretim paritesi = URETIM DEFAULT'U — routing karari
predict_nfv_benefit(family_routing=True, mode_model, rot_sokum=True) ile
her set icin CANLI cozulur; elle yol listesi tutulmaz):
  NFV'ye dusen setler   : solve_nfv_kalite (fast/2mm/nogo/r11-auto/rot-auto)
                          — 2026-07-15 itibariyle deneme4 de burada (rot-sokum
                          dunyasi, K-46/K-52; eski "d4 NFV kapali" hukmu
                          TERSINE). r11 uygulanirsa kapi dz-kaymis sahneyi
                          olcer (musteri STL paritesi, 7add014).
  heightmap'e dusenler  : solve_coarse_to_fine (wall_aware onerisiyle) —
                          kabuk-tube + net-kutu/ince-plaka aileleri.
  boxy (held-out)       : auto-plaka, ayni routing.

Cikti: ASCII tablo + results/eval_gate_last.json (+ --save-baseline ile
results/eval_gate_baseline.json). Stdout SAF ASCII (cp1254).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.tuner import build_menu  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from scripts.c3_generality import DATASETS, _boxy_stl_map_and_qty  # noqa: E402

BASELINE = _ROOT / "results" / "eval_gate_baseline.json"
LAST = _ROOT / "results" / "eval_gate_last.json"

CLEARANCE_REQ_MM = 2.0  # A2 guncellemesi 2026-07-09 (hoca: "2mm daha guvenli");
#                         Sprint-3'te eval_gate'e islendi (eskisi 1.0'di)
FAIL_PCT = 2.0    # B2: bir sette bundan fazla kotulesme -> FAIL
NOISE_PCT = 0.5   # B2: voxel-kuantizasyon gurultu bandi

# Sprint-3 v2 sozlesmesi (2026-07-14): kapi GERCEK URETIM KOSULLARINDA kosar —
# hocanin yazicisi 335x335 + yasak-bolge kolonu (K-38..50 sampiyonlarinin
# olculdugu kosullar). Eski 325/328.74 config plakalari ve no-go'suz kosum
# tarihseldir; baseline ILK KEZ bu sozlesmeyle kilitlenir (A8 gerekceli).
PLATE_STD = (335.0, 335.0)
NOGO_STD = ((152.5, 0.2), (185.5, 45.0))

# Faz-1: roller data/registry.json'dan (tek dogruluk kaynagi; 01_VERI §2).
# Registry yoksa/bozuksa guvenli fallback sabitler.
REGISTRY = _ROOT / "data" / "registry.json"
_KOSULABILIR = {"plan1", "plan2", "plan3", "deneme4", "boxy"}  # config'i olanlar


def _load_roles():
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        sets = reg.get("sets", {})
        dev = [s for s, v in sets.items()
               if v.get("rol") == "dev" and s in _KOSULABILIR]
        held = [s for s, v in sets.items()
                if v.get("rol") == "held-out" and s in _KOSULABILIR]
        if dev:
            return dev, held
    except Exception:
        pass
    return (["plan1", "plan2", "plan3", "deneme4"], ["boxy"])


def _log_heldout_bakis(set_names, reason):
    """A3: held-out'a her bakis registry'ye tarihle islenir (yapisal, unutulmaz)."""
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        reg.setdefault("bakislar", []).append({
            "setler": list(set_names),
            "tarih": datetime.now().isoformat(timespec="seconds"),
            "sebep": reason or "belirtilmedi",
        })
        REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    except Exception as exc:  # bakis loglanamiyorsa kosu da OLMAZ (A3 sert)
        raise RuntimeError(f"held-out bakisi registry'ye yazilamadi: {exc}")


DEV_SETS, HELDOUT_SETS = _load_roles()


# ---------------------------------------------------------------------------
# Sampiyon kosucular
# ---------------------------------------------------------------------------

def _load_instance(name):
    if name == "boxy":
        stl_map, qty = _boxy_stl_map_and_qty()
        plate = None  # sentetik stres seti: auto-plaka
    else:
        cfg = DATASETS[name]
        stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
        qty = cfg["qty"]
        plate = PLATE_STD  # v2 sozlesmesi: gercek yazici plakasi (config degil)
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"gen_{name}"}
    if plate is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = plate
    res = build_instance_from_order(stl_map, qty, **kwargs)
    return res.instance


def _poz_seti_cevir(n_orientations):
    """K-53c: n_orientations="ax24" -> (quality, n_orientations) cifti.

    K-53 dersi (2026-07-16): "kac poz" degil "HANGI pozlar" — ilk-N master
    seti (egik 8..11 dahil) d4'te AX24'ten ~18mm geri (250.0 vs ham 231.5).
    "ax24" = quality=max poz seti (24 eksen-hizali, egiksiz; RAM freni
    nfv_solve icinde). int/None birebir eski davranis (fast).
    """
    if isinstance(n_orientations, str):
        if n_orientations.lower() != "ax24":
            raise ValueError(f"bilinmeyen poz seti: {n_orientations!r}")
        return "max", None
    return "fast", n_orientations


def _run_champion(name, inst, seed, budget=None, n_orientations=None):
    """Set'in URETIM DEFAULT yolunu kosar -> (result, nfv_tel | None).

    nfv_tel yalniz NFV dalinda doner (solve_nfv_kalite telemetrisi) — kapi
    r11 dz'sini dz-kaymis sahne olcumu icin kullanir (uretim paritesi:
    musteri STL'i dz'li, 7add014).

    Uretim paritesi demo_pipeline zinciriyle BIREBIR (elle config YOK):
      wall_aware = predict_nfv_benefit(family_routing=True).wall_aware  (F5)
      pitch      = suggest_pitch(instance, wall_aware=...)              (K-19)
      solve_coarse_to_fine(budget=COARSE_BUDGET, menu=dblf_only|None,
                           skip_fine_angle=wall, drop_cache=wall,
                           clearance_mm=WEB_MIN_CLEARANCE_MM)
    Sprint-3 v2 (2026-07-14, K-45 sonrasi parite): dec.mode=="nfv" artik
    solve_nfv_kalite kosar (uretim DEFAULT'lari: quality="fast", 2mm kural,
    NOGO_STD; r11=False — r11 height_mm'i degistirmez, kapida CPU israfi
    olurdu). heightmap dallari no_go_bounds tasir. Eski "NFV disarida"
    hukmu EVAL-1 donemine aitti; K-45 recetesi uretim yolu olali gecersiz."""
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.instances.pitch import suggest_pitch
    from scripts.demo_pipeline import COARSE_BUDGET, WEB_MIN_CLEARANCE_MM

    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    # C4: uretim paritesi — pipeline'in yukledigi mod-modeli kapida da yuklenir
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    # d4 routing (Eren 2026-07-15): uretim default'u rot-sokum dunyasi
    # (demo_pipeline rot_sokum_routing=True) — kapi ayni routing'le kosar.
    dec = predict_nfv_benefit(inst, family_routing=True, mode_model=_mm,
                              rot_sokum=True, no_go_bounds=NOGO_STD)
    if getattr(dec, "mode", "heightmap") == "nfv":
        from src.nesting3d.nfv_solve import solve_nfv_kalite
        print(f"    [{name}] routing: NFV kalite (uretim default: "
              f"fast/2mm/nogo/r11-auto/rot-auto)", flush=True)
        # Uretim paritesi (2026-07-15): pipeline r11="auto" + rot_kabul="auto"
        # kosuyor ve dz-export (7add014) r11 kazancini musteri STL/GLB'sine
        # yansitiyor — kapi da AYNI default'larla olcer. (Eski r11=False
        # karari dz'nin height'a yansimadigi Sprint-3 donemine aitti.)
        _quality, _n_or = _poz_seti_cevir(n_orientations)
        # K-53c uretim paritesi: acik override YOKSA aile poz-seti onerisi
        # (rot-sokum thin_shell -> "max"/AX24) kapida da gecerli — pipeline
        # ile ayni default'la olculur. Override (int/"ax24") HER ZAMAN ezer.
        if n_orientations is None:
            _quality = getattr(dec, "nfv_quality", "fast")
        res, _tel = solve_nfv_kalite(
            inst, plate_w_mm=pw, plate_d_mm=pd,
            clearance_mm=WEB_MIN_CLEARANCE_MM, no_go_bounds=NOGO_STD,
            quality=_quality, seed=seed,
            n_orientations=_n_or, r11="auto", rot_kabul="auto")
        return res, _tel
    if isinstance(n_orientations, str):
        raise ValueError(
            f"poz seti adi ({n_orientations!r}) yalniz NFV dalinda gecerli; "
            f"{name} heightmap'e yonlendi")
    wall = bool(getattr(dec, "wall_aware", False))
    pitch = suggest_pitch(inst, wall_aware=wall)
    kw = dict(coarse_pitch=None, fine_pitch=pitch,
              budget=(budget if budget is not None else COARSE_BUDGET),
              seed=seed, drop_cache=wall, skip_fine_angle=wall,
              clearance_mm=WEB_MIN_CLEARANCE_MM,
              no_go_bounds=NOGO_STD)
    if n_orientations is not None:
        kw["n_orientations"] = n_orientations  # tune_bo override (04 §1)
    if wall:
        kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
    print(f"    [{name}] routing: wall_aware={wall}  pitch={pitch}", flush=True)
    return solve_coarse_to_fine(inst, plate_w_mm=pw, plate_d_mm=pd, **kw), None


# ---------------------------------------------------------------------------
# Durust metrik (SAF fonksiyonlar — test edilir)
# ---------------------------------------------------------------------------

def legal_of(height_mm, n_placed, n_total, min_clear_mm, n_locked,
             clearance_req=CLEARANCE_REQ_MM, n_locked_rot=None):
    """(legal_height | None, invalid_reason | None) — ANAYASA A2 tanimi.

    min_clear_mm None = olculemedi -> INVALID (kanitsizlik gecer not verilmez);
    --skip-clearance ile bilerek atlanirsa cagiran bunu isaretler.

    n_locked_rot (A2 rot-sokum katmani, Eren karari 2026-07-15; hoca kabulu
    2026-07-14): 5-yon kilit>0 tek basina RED degil — rot-sokum denetimi
    kilitleri yeniden yargilar. rot kilit=0 -> SOKUM-PLANLI legal (kilit
    kosulu aklanir; diger kosullar aklanmaz). None = denetim yok/olculmedi ->
    eski davranis bit-ozdes.
    """
    reasons = []
    if n_placed != n_total:
        reasons.append(f"eksik yerlesim {n_placed}/{n_total}")
    if min_clear_mm is None:
        reasons.append("clearance olculemedi")
    elif min_clear_mm < clearance_req:
        reasons.append(f"clearance {min_clear_mm:.3f}<{clearance_req}")
    if n_locked is None:
        reasons.append("erisilebilirlik olculemedi")
    elif n_locked > 0:
        if n_locked_rot is None:
            reasons.append(f"{n_locked} kilit")
        elif n_locked_rot > 0:
            reasons.append(f"{n_locked} kilit (rot-sokum {n_locked_rot} kilit)")
        # n_locked_rot == 0 -> sokum-planli LEGAL: kilit sebebi yazilmaz
    if reasons:
        return None, "; ".join(reasons)
    return float(height_mm), None


def compare_verdict(cur, base, fail_pct=FAIL_PCT, noise_pct=NOISE_PCT):
    """{set: legal|None} x2 -> (overall, {set: (delta_pct|None, durum)}).

    overall: PASS | FAIL | INSAN-KARARI | NOOP | BASELINE-YOK
    Yukseklik kucuk=iyi. delta_pct = (cur-base)/base*100 (pozitif = KOTU).
    """
    if base is None:
        return "BASELINE-YOK", {s: (None, "baseline yok") for s in cur}
    per = {}
    any_fail = any_worse = any_better = False
    for s, c in cur.items():
        b = base.get(s)
        if c is None:
            per[s] = (None, "INVALID -> FAIL")
            any_fail = True
        elif b is None:
            per[s] = (None, "baseline INVALID/yok -> iyilesme")
            any_better = True
        else:
            d = (c - b) / b * 100.0
            if d > fail_pct:
                per[s] = (d, f"> +%{fail_pct} -> FAIL")
                any_fail = True
            elif d > noise_pct:
                per[s] = (d, "kotulesme (gurultu ustu)")
                any_worse = True
            elif d < -noise_pct:
                per[s] = (d, "iyilesme")
                any_better = True
            else:
                per[s] = (d, "degisim yok (gurultu bandi)")
    if any_fail:
        return "FAIL", per
    if any_worse:
        return "INSAN-KARARI", per
    if any_better:
        return "PASS", per
    return "NOOP", per


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def evaluate_set(name, seed, skip_clearance=False, budget=None,
                 n_orientations=None, _rot_fn=None, _kilit5_fn=None):
    t0 = time.perf_counter()
    inst = _load_instance(name)
    n_total = sum(int(p.qty) for p in inst.parts)
    r, nfv_tel = _run_champion(name, inst, seed, budget=budget,
                               n_orientations=n_orientations)
    n_placed = int(getattr(r, "n_placed", len(r.placements)))
    height = float(r.height_mm)

    # r11 dz (uretim paritesi, 2026-07-15): r11 uygulandiysa musteri STL'i
    # dz-kaymis (7add014) — kapi da AYNI sahneyi olcer: yukseklik r11-sonrasi,
    # meshes dz'li, kilit dz'li meshlerde K-50 metrigi (kilit_5yon_meshes;
    # voxel placements dz'yi bilmez, bayat olurdu). r11 yoksa eski yol
    # BIT-OZDES. _kilit5_fn test enjeksiyonu (meshes -> kilit sayisi).
    _r11 = ((nfv_tel or {}).get("r11") or {})
    r11_dz = _r11.get("dz") if _r11.get("uygulandi") else None
    if r11_dz is not None:
        height = float(_r11.get("height_mm", height))

    min_clear = None
    meshes = None
    if not skip_clearance:
        pitch = float(getattr(r, "fine_pitch"))
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch,
                               dz=r11_dz)
        rep = min_clearance(meshes, samples_per_mesh=6000)  # d4 dersi: 3000 iyimser
        min_clear = float(rep.min_mm)

    if r11_dz is not None and meshes is not None:
        try:
            from src.nesting3d.continuous_settle import kilit_5yon_meshes
            n_locked = int((_kilit5_fn or kilit_5yon_meshes)(meshes))
        except Exception:
            n_locked = None  # olculemedi -> INVALID (kanitsizlik gecer not degil)
    else:
        n_locked = int(check_placements(r.placements, r.fine_voxel_parts).n_locked)

    # A2 rot-sokum katmani (Eren karari 2026-07-15; hoca kabulu 2026-07-14):
    # 5-yon kilit>0 tek basina RED degil — kilit_rot_meshes (K-52 tabani,
    # @1.0 re-voxelize) kilitleri yeniden yargilar; rot kilit=0 -> SOKUM-PLANLI
    # legal. Yalniz kilit varken kosar (K-42 maliyet dersi: kilitsizde HIC);
    # hata/butce-asimi konservatif -> eski RED. _rot_fn test enjeksiyonu
    # (A9: imza gercekle ayni, meshes -> RotSeparabilityReport).
    n_locked_rot = None
    rot_cert = None
    rot_hata = None
    if n_locked > 0 and meshes is not None:
        try:
            from src.nesting3d.continuous_settle import kilit_rot_meshes
            rot_rep = (_rot_fn or kilit_rot_meshes)(meshes)
            n_locked_rot = int(rot_rep.n_locked)
            rot_cert = len(getattr(rot_rep, "certificates", None) or [])
        except Exception as exc:
            rot_hata = f"{type(exc).__name__}: {exc}"

    legal, reason = legal_of(height, n_placed, n_total, min_clear, n_locked,
                             n_locked_rot=n_locked_rot)
    sokum_planli = bool(legal is not None and n_locked > 0
                        and n_locked_rot == 0)
    if skip_clearance and reason == "clearance olculemedi":
        reason += " (--skip-clearance)"
    return {
        "legal_height_mm": legal, "invalid_reason": reason,
        "height_mm": height, "n_placed": n_placed, "n_total": n_total,
        "min_clearance_mm": min_clear, "n_locked": n_locked,
        "n_locked_rot": n_locked_rot, "rot_cert": rot_cert,
        "rot_hata": rot_hata, "sokum_planli": sokum_planli,
        "r11_uygulandi": bool(_r11.get("uygulandi")),
        "r11_kazanc_mm": _r11.get("kazanc_mm"),
        "duration_s": round(time.perf_counter() - t0, 1),
    }


def _print_set_ozeti(name, r):
    """Per-set tek satir ozet — sirali ve paralel yol AYNI formati kullanir."""
    lh = r["legal_height_mm"]
    lh_s = f"{lh:.1f}mm" if lh is not None else f"INVALID({r['invalid_reason']})"
    rot_s = ""
    if r.get("n_locked_rot") is not None:
        rot_s = f"  rot_kilit={r['n_locked_rot']}"
        if r.get("sokum_planli"):
            rot_s += f" SOKUM-PLANLI ({r.get('rot_cert')} cert)"
    print(f"[{name}] legal_height={lh_s}  ham={r['height_mm']}  "
          f"clear={r['min_clearance_mm']}  kilit={r['n_locked']}{rot_s}  "
          f"({r['duration_s']}s)", flush=True)


def _bos_exception_sonucu(hata):
    """Cocuk-surec/istisna durumunda sirali yolun EXCEPTION sekliyle AYNI dict."""
    return {
        "legal_height_mm": None, "invalid_reason": f"EXCEPTION: {hata}",
        "height_mm": None, "n_placed": None, "n_total": None,
        "min_clearance_mm": None, "n_locked": None, "n_locked_rot": None,
        "rot_cert": None, "rot_hata": None, "sokum_planli": False,
        "r11_uygulandi": False, "r11_kazanc_mm": None, "duration_s": None,
    }


def _run_sets_parallel(sets, seed, skip_clearance, n_proc,
                       heldout_final=False, reason=None, _spawn=None):
    """K-57b: her seti AYRI python surecinde kos, sonuclari birlestir.

    Duvar-saati ~ en yavas set (siralida toplamlarin toplami; k51e olcumu:
    sirali ~88dk, en yavas set 35dk). Per-set sonuclar surec-izolasyonu
    sayesinde sirali kosuyla BIT-OZDES (ayni fonksiyonlar + ayni seed; yalniz
    duration_s CPU-cekismesiyle degisebilir — sayilar degismez, k57 parite
    kosusuyla kanitlanir). Cocuklar --json-out modunda kosar: LAST/baseline'a
    DOKUNMAZLAR (dosya yarisi yok); kiyas + baseline karari yalniz ebeveynde.
    Pencere: ayni anda en fazla n_proc cocuk; tamamlanma beklemesi gonderim
    sirasiyla (pencere her tamamlanmada yeniden dolar).

    _spawn test enjeksiyonu: (name, out_path) -> proc (communicate/returncode).
    """
    import subprocess
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="eval_gate_k57_"))

    def _gercek_spawn(name, out_path):
        import os
        cmd = [sys.executable, "-m", "scripts.eval_gate", "--sets", name,
               "--seed", str(seed), "--json-out", str(out_path)]
        if skip_clearance:
            cmd.append("--skip-clearance")
        if heldout_final:
            cmd.append("--heldout-final")
            if reason:
                cmd += ["--reason", reason]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.Popen(
            cmd, cwd=str(_ROOT), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace")

    spawn = _spawn or _gercek_spawn
    results = {}
    bekleyen = list(sets)
    kosan = []  # (name, proc, out_path)
    while bekleyen or kosan:
        while bekleyen and len(kosan) < max(1, int(n_proc)):
            nm = bekleyen.pop(0)
            op = tmpdir / f"{nm}.json"
            print(f"[{nm}] paralel cocuk basladi", flush=True)
            kosan.append((nm, spawn(nm, op), op))
        nm, proc, op = kosan.pop(0)
        out, _ = proc.communicate()
        if out:
            for ln in out.splitlines():
                print(f"  [{nm}] {ln}", flush=True)
        hata = None
        if proc.returncode == 0 and op.exists():
            try:
                doc = json.loads(op.read_text(encoding="utf-8"))
                results[nm] = doc["sets"][nm]
            except Exception as e:
                hata = f"cocuk json okunamadi: {e}"
        else:
            hata = f"cocuk surec exit={proc.returncode}"
        if hata is not None:
            results[nm] = _bos_exception_sonucu(hata)

    # Iyimser paralel + SERI kurtarma (2026-07-17 olcum bulgusu: plan2||plan3
    # cakismasi plan3'u OOM'a dusurdu — 1.19MiB alloc bile basarisiz = RAM
    # tukenmesi). EXCEPTION'li setler (cocuk cokusu VEYA set-ici istisna)
    # digerleri bitince TEK BASINA bir kez yeniden denenir: en kotu durumda o
    # set icin sirali maliyete donulur, parite bozulmaz. Duz INVALID (kilit,
    # clearance...) deterministik OLCUMDUR — yeniden denenMEZ.
    yeniden = [s for s in sets
               if (results[s].get("invalid_reason") or "").startswith("EXCEPTION")]
    for nm in yeniden:
        print(f"[{nm}] EXCEPTION — SERI kurtarma denemesi (tek basina)",
              flush=True)
        op = tmpdir / f"{nm}_retry.json"
        proc = spawn(nm, op)
        out, _ = proc.communicate()
        if out:
            for ln in out.splitlines():
                print(f"  [{nm}|retry] {ln}", flush=True)
        if proc.returncode == 0 and op.exists():
            try:
                doc = json.loads(op.read_text(encoding="utf-8"))
                results[nm] = doc["sets"][nm]
            except Exception:
                pass  # ilk EXCEPTION sonucu kalir (kanit kaybolmaz)
    return results


def main():
    ap = argparse.ArgumentParser(description="STRATEJI Faz-0 eval kapisi")
    ap.add_argument("--sets", default=",".join(DEV_SETS),
                    help=f"virgullu set listesi (default: {','.join(DEV_SETS)})")
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--save-baseline", action="store_true",
                    help="bu kosuyu baseline olarak YAZ (bilincli karar!)")
    ap.add_argument("--heldout-final", action="store_true",
                    help="held-out setleri kosmaya izin (bakis registry'ye OTOMATIK yazilir)")
    ap.add_argument("--reason", default=None,
                    help="held-out bakis sebebi (registry bakislar kaydina gider)")
    ap.add_argument("--skip-clearance", action="store_true",
                    help="clearance olcumunu atla (SONUC INVALID kalir; hizli debug)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--parallel", type=int, default=0,
                    help="K-57b: setleri N ayri surecte paralel kos "
                         "(0=KAPALI, sirali eski yol BIREBIR; oneri: set sayisi)")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="cocuk modu (K-57b ic kullanim): sonuclari bu dosyaya "
                         "yaz; LAST/kiyas/baseline ATLANIR")
    args = ap.parse_args()

    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    bilinmeyen = [s for s in sets if s not in DEV_SETS + HELDOUT_SETS]
    if bilinmeyen:
        print(f"HATA: bilinmeyen set(ler): {bilinmeyen}. "
              f"Gecerli: {DEV_SETS + HELDOUT_SETS}")
        sys.exit(2)
    heldout_istenen = [s for s in sets if s in HELDOUT_SETS]
    if heldout_istenen and not args.heldout_final:
        print(f"RED (ANAYASA A3): {heldout_istenen} HELD-OUT. Final dogrulama "
              f"icin --heldout-final (+--reason) ekle. Held-out ile TUNING YASAK.")
        sys.exit(3)
    if heldout_istenen and args.json_out is None:
        # K-57b: cocuk surecler (json-out modu) bakisi TEKRAR loglamaz —
        # bakis ebeveynde bir kez kayda gecer (A3 tek-kayit).
        _log_heldout_bakis(heldout_istenen, args.reason)
        print(f"[registry] held-out bakisi loglandi: {heldout_istenen} "
              f"(sebep: {args.reason or 'belirtilmedi'})")

    print("=" * 78)
    print(f"EVAL KAPISI (Faz-0) — setler: {sets}  seed={args.seed}  "
          f"clearance_req={CLEARANCE_REQ_MM}mm")
    print("=" * 78, flush=True)

    results = {}
    if args.parallel and args.parallel > 0:
        # K-57b: setler ayri sureclerde — duvar-saati ~ en yavas set.
        results = _run_sets_parallel(
            sets, args.seed, args.skip_clearance, args.parallel,
            heldout_final=args.heldout_final, reason=args.reason)
        for name in sets:
            _print_set_ozeti(name, results[name])
    else:
        for name in sets:
            print(f"[{name}] kosuyor...", flush=True)
            try:
                results[name] = evaluate_set(name, args.seed,
                                             args.skip_clearance)
            except Exception as e:  # bir setin cokusu digerlerini engellemesin
                results[name] = _bos_exception_sonucu(e)
            _print_set_ozeti(name, results[name])

    # K-57b cocuk modu: sonuclari json-out'a yaz ve CIK — LAST/kiyas/baseline
    # yalniz ebeveynde (dosya yarisi + cift-kayit onlenir).
    if args.json_out is not None:
        doc = {
            "schema": 1, "created": datetime.now().isoformat(timespec="seconds"),
            "seed": args.seed, "clearance_req_mm": CLEARANCE_REQ_MM,
            "sets": results,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                                 encoding="utf-8")
        print(f"json-out yazildi: {args.json_out}")
        sys.exit(0)

    # --- kiyas ---------------------------------------------------------------
    base = None
    if args.baseline.exists():
        base_doc = json.loads(args.baseline.read_text(encoding="utf-8"))
        base = {s: v.get("legal_height_mm") for s, v in base_doc["sets"].items()}
    cur = {s: r["legal_height_mm"] for s, r in results.items()}
    overall, per = compare_verdict(
        cur, {s: base.get(s) for s in cur} if base is not None else None)

    print("-" * 78)
    print(f"  {'set':<10} {'baseline':>10} {'simdi':>10} {'delta%':>8}  durum")
    for s in sets:
        b = (base or {}).get(s)
        c = cur[s]
        d, durum = per[s]
        print(f"  {s:<10} {(f'{b:.1f}' if b is not None else 'INV/yok'):>10} "
              f"{(f'{c:.1f}' if c is not None else 'INVALID'):>10} "
              f"{(f'{d:+.2f}' if d is not None else '-'):>8}  {durum}")
    print("-" * 78)
    print(f"  VERDICT: {overall}")
    if overall == "INSAN-KARARI":
        print("  -> trade-off tablosunu Eren'e sun; karar insana ait (B2).")
    print("=" * 78)

    # --- yazim ---------------------------------------------------------------
    doc = {
        "schema": 1, "created": datetime.now().isoformat(timespec="seconds"),
        "seed": args.seed, "clearance_req_mm": CLEARANCE_REQ_MM,
        "sets": results, "verdict": overall,
    }
    LAST.parent.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"yazildi: {LAST}")
    if args.save_baseline:
        invalids = [s for s, v in cur.items() if v is None]
        if invalids:
            print(f"BASELINE YAZILMADI: INVALID set(ler) var: {invalids} — "
                  f"bozuk baseline kilitlenemez.")
            sys.exit(4)
        args.baseline.write_text(
            json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"BASELINE yazildi: {args.baseline}")
    sys.exit(0 if overall in ("PASS", "NOOP", "BASELINE-YOK") else 1)


if __name__ == "__main__":
    main()

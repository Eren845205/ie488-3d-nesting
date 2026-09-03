# -*- coding: utf-8 -*-
"""backfill_v2.py — K-xx olcumlerini + otonom_gecmis kayitlarini telemetri
v2'ye geri-doldur (ML plani Faz A2, 2026-07-13).

TASARIM (plan geregi):
  * Markdown PARSE EDILMEZ — KAYITLAR elle-transkribe edilmistir; her kayit
    kaynak-izi (kosu_id + log + alinti satiri) tasir ve scripts/*.log
    SONUC satirlariyla capraz-teyitlidir (insan gozden gecirebilir).
  * INVALID turetimi append_run_v2'nin kendisine birakilir (A2/Y-7 bedava:
    d4 heightmap 288.0 + clear 1.555 @req2.0 -> legal=None otomatik).
  * Idempotent: backfill_id = sha1(kosu_id|mode|recete|height) — mevcut
    id'ler atlanir; runs_v2.jsonl append-only kalir (Y-9).
  * KAPSAM KURALLARI: yalniz STANDART kosul satirlari (335x335 + no-go
    ((152.5,0.2),(185.5,45)), 2mm kurali). BILINCLI DISARIDA: soft-nogo
    serhli satirlar (k37/k43/k40-soft — FARKLI kisit = farkli problem),
    1mm-devri satirlar (685/646/834/288.5, k21/k22), tek-seferlik mekanizma
    denemeleri (k29 tahliye, k30 eski-guard), k42 (k39b'nin dogrulama
    tekrari). Bu dislamalar bilinctir ve buradan denetlenir.
  * KILIT METRIGI notu: K-34 sonrasi satirlarda n_locked = (b+c) rot-sokum
    (hoca kriteri; kanit: ilgili log 'legal(b+c)=' satiri); 5-yon (b) sayisi
    ve sertifika adedi extra alanlarda saklanir. ax24-devri satirlarda
    n_locked=0 logdaki gibi (+Z metrigi; 0 -> 5-yon'da da 0, guvenli yon).

Kosum: python -m scripts.backfill_v2 [--dry-run] [--out YOL] [--otonom]
SAF ASCII stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.telemetry import V2_DEFAULT_PATH, append_run_v2

PLATE_STD = (335.0, 335.0)
NOGO_STD = ((152.5, 0.2), (185.5, 45.0))

# --------------------------------------------------------------------------
# ELLE-TRANSKRIBE OLCUM KAYITLARI (kaynak: scripts/*.log SONUC satirlari)
# --------------------------------------------------------------------------
def _k(set_, mode, recete, pitch, h, clear, kilit, n, dk, kosu, log, alinti,
       **extra):
    d = dict(set=set_, mode=mode, recete=recete, pitch=pitch, height_mm=h,
             min_clearance_mm=clear, n_locked=kilit, n_placed=n, n_total=n,
             duration_s=(dk * 60.0 if dk is not None else None),
             clearance_req_mm=2.0, plate=PLATE_STD,
             kosu_id=kosu, log=log, alinti=alinti)
    d.update(extra)
    return d


KAYITLAR = [
    # ---- plan3 (109 parca) ----
    _k("plan3", "heightmap", "sq_n24", 0.5, 735.0, 2.355, 0, 109, 44.6,
       "ax24/plan3_sq_n24_s42", "scripts/ax24_kuyruk_335.log",
       "[sq_n24_s42] h=735.0  legal=735.0  clear=2.355  kilit=0  (44.6 dk)",
       seed=42, n_orientations=24),
    _k("plan3", "nfv", "ham@auto2.5", 2.5, 618.1, 2.501, 0, 109, 13.1,
       "K-34/nfv_ham", "scripts/k34_rot_sokum.log",
       "SONUC: h=618.1  clear=2.501  legal(b)=INVALID  legal(b+c)=618.125",
       b_kilit=20, cert=1, n_orientations=24),
    _k("plan3", "nfv", "derin@2.0", 2.0, 598.5, 2.271, 0, 109, 31.5,
       "K-36/p2.0_s42", "scripts/k36_derin_arama.log",
       "[p2.0_s42] SONUC: h=598.5  clear=2.271  legal(b+c)=598.5",
       b_kilit=0, cert=0, seed=42, n_orientations=24),
    _k("plan3", "nfv", "ham@1.75", 1.75, 674.2, 3.737, 0, 109, 62.7,
       "K-38/p1.75", "scripts/k38_pitch175.log",
       "SONUC: h=674.2  clear=3.737  legal(b)=INVALID  legal(b+c)=674.1875",
       b_kilit=23, cert=2, n_orientations=24),
    # ---- plan1 (112 parca; hard-nogo standart kosul — soft-nogo serhli DISARIDA) ----
    _k("plan1", "heightmap", "dik_n24", None, 260.0, 2.000, 0, 112, None,
       "K-35/dik_n24", "scripts/k35_host_rz.log",
       "[dik_n24] SONUC: h=260.0  legal=260.0  clear=2.000  kilit=0",
       n_orientations=24),
    _k("plan1", "heightmap", "tilt_n24", None, 141.0, 2.018, 0, 112, None,
       "K-35/tilt_n24", "scripts/k35_host_rz.log",
       "[tilt_n24] SONUC: h=141.0  legal=141.0  clear=2.018  kilit=0",
       n_orientations=24),
    _k("plan1", "nfv", "ham@auto0.6", 0.6, 333.0, 2.404, 0, 112, 2.6,
       "K-40/nfv_hard", "scripts/k40_plan1_nfv.log",
       "[nfv_hard] SONUC: h=333.0  clear=2.404  legal(b)=INVALID  legal(b+c)=333.0",
       b_kilit=7, cert=1, n_orientations=24),
    # ---- plan2 (226 parca) ----
    _k("plan2", "heightmap", "n24", 0.5, 618.0, 2.000, 0, 226, 106.6,
       "ax24/plan2_n24_gece3", "scripts/ax24_kuyruk_335.log",
       "[plan2_n24] h=618.0  legal=618.0  clear=2.000(req=2, pair=(124, 127))  kilit=0",
       n_orientations=24),
    _k("plan2", "nfv", "ham@2.0", 2.0, 532.0, 2.002, 29, 226, 8.7,
       "K-39b/p2", "scripts/k39b_plan2_nfv_v2.log",
       "[p2] SONUC: h=532.0  clear=2.002  legal(b)=INVALID  legal(b+c)=INVALID(29 kilit)",
       b_kilit=61, cert=8, seed=42, n_orientations=24),
    _k("plan2", "nfv", "guard@2.0", 2.0, 544.5, 2.004, 0, 226, None,
       "K-41/guard", "scripts/k41_plan2_exit_guard.log",
       "SONUC: h=544.5  clear=2.004  legal(b)=544.5  legal(b+c)=544.5",
       b_kilit=0, cert=0, seed=42, n_orientations=24,
       sure_notu="logda solve suresi satiri yok; RESUME 29.6dk"),
    # ---- deneme4 (588 parca) ----
    _k("deneme4", "heightmap+wall_aware", "n24", 0.5, 288.0, 1.555, 0, 588, 21.5,
       "ax24/deneme4_n24", "scripts/ax24_kuyruk_335.log",
       "[deneme4_n24] h=288.0  legal=288.0  clear=1.555  kilit=0  (21.5 dk)  [wall=True]",
       n_orientations=24),
    _k("deneme4", "nfv", "ham@2.0", 2.0, 231.5, 2.018, 0, 588, 32.4,
       "K-46/nfv_ham", "scripts/k46_d4_nfv.log",
       "[nfv_ham] SONUC: h=231.5  clear=2.018(6000 ornek)  legal(b)=INVALID  legal(b+c)=231.5",
       b_kilit=363, cert=39, seed=42, n_orientations=24),
    _k("deneme4", "nfv", "guard@2.0", 2.0, 276.5, 2.019, 0, 588, 32.8,
       "K-46/nfv_guard", "scripts/k46_d4_nfv.log",
       "[nfv_guard] SONUC: h=276.5  clear=2.019(6000 ornek)  legal(b)=276.5  legal(b+c)=276.5",
       b_kilit=0, cert=0, seed=42, n_orientations=24),
    # ---- deneme5 (352 parca) ----
    _k("deneme5", "heightmap", "n24", 1.8, 338.4, 3.800, 0, 352, 5.9,
       "ax24/deneme5_n24", "scripts/ax24_kuyruk_335.log",
       "[deneme5_n24] h=338.4  legal=338.4  clear=3.800  kilit=0  (5.9 dk)",
       n_orientations=24),
    _k("deneme5", "nfv", "ham@2.0", 2.0, 223.5, 2.000, 0, 352, 20.3,
       "K-44/nfv_ham", "scripts/k44_d5_nfv.log",
       "[nfv_ham] SONUC: h=223.5  clear=2.000  legal(b)=223.5  legal(b+c)=223.5",
       b_kilit=0, cert=0, seed=42, n_orientations=24),
    _k("deneme5", "nfv", "guard@2.0", 2.0, 244.0, 2.000, 0, 352, 32.9,
       "K-44/nfv_guard", "scripts/k44_d5_nfv.log",
       "[nfv_guard] SONUC: h=244.0  clear=2.000  legal(b)=244.0  legal(b+c)=244.0",
       b_kilit=0, cert=0, seed=42, n_orientations=24),
    _k("deneme5", "nfv", "ham@1.0", 1.0, 218.0, 2.000, 0, 352, 344.6,
       "K-47a/ham", "scripts/k47a_d5_pitch1.log",
       "[ham] SONUC: h=218.0  clear=2.000  legal(b)=218.0  legal(b+c)=218.0",
       b_kilit=0, cert=0, seed=42, n_orientations=24),
]


def backfill_id(kayit: dict) -> str:
    ham = f"{kayit['kosu_id']}|{kayit['mode']}|{kayit['recete']}|{kayit['height_mm']}"
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def _mevcut_idler(path: Path) -> set:
    if not path.exists():
        return set()
    idler = set()
    for satir in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(satir)
        except json.JSONDecodeError:
            continue
        bid = row.get("backfill_id")
        if bid:
            idler.add(bid)
    return idler


def satirlari_uret(
    kayitlar: list,
    feature_saglayici: Callable[[str], Optional[dict]],
    out: Path,
    *,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """KAYITLAR -> v2 satirlari. Doner: (yeni_satir, atlanan).

    feature_saglayici(set_adi) -> ozellik dict'i (kxx_telemetri.ozellik_cikar
    ciktisi) veya None (yuklenemedi -> satir ATLANIR ve sayilir)."""
    mevcut = _mevcut_idler(out)
    n_yeni = n_atlanan = 0
    for k in kayitlar:
        bid = backfill_id(k)
        if bid in mevcut:
            continue
        oz = feature_saglayici(k["set"])
        if oz is None:
            n_atlanan += 1
            print(f"ATLANDI (ozellik yok): {k['kosu_id']}")
            continue
        n_yeni += 1
        if dry_run:
            legal = (k["height_mm"]
                     if (k["n_placed"] == k["n_total"]
                         and k["min_clearance_mm"] is not None
                         and k["min_clearance_mm"] >= k["clearance_req_mm"]
                         and k["n_locked"] == 0) else None)
            print(f"[dry] {k['set']:<8} {k['mode']:<22} {k['recete']:<12} "
                  f"h={k['height_mm']:<7} legal={legal} ({k['kosu_id']})")
            continue
        extra = {a: k[a] for a in ("b_kilit", "cert", "sure_notu") if a in k}
        append_run_v2(
            out, kaynak="backfill", instance_id=k["set"], mode=k["mode"],
            height_mm=k["height_mm"], n_placed=k["n_placed"],
            n_total=k["n_total"], min_clearance_mm=k["min_clearance_mm"],
            n_locked=k["n_locked"], family_f1=oz.get("family_f1"),
            family_conf=oz.get("family_conf"), source="k_deney",
            pitch_fine=k.get("pitch"), n_orientations=k.get("n_orientations"),
            seed=k.get("seed"), duration_s=k.get("duration_s"),
            clearance_req_mm=k["clearance_req_mm"], recete=k["recete"],
            kosu_id=k["kosu_id"], log=k["log"], alinti=k["alinti"],
            plate=list(k["plate"]), no_go=NOGO_STD, backfill_id=bid,
            feature_vector=oz.get("feature_vector"),
            feature_names=oz.get("feature_names"),
        )
    return n_yeni, n_atlanan


def otonom_satirlari(detay_dir: Path, out: Path, *, dry_run: bool = False
                     ) -> Tuple[int, int]:
    """otonom_gecmis/detay JSON'lari -> v2 satirlari (kanit_seviyesi=dusuk).

    Olculmemis legal bilesenler None gecilir -> append_run_v2 dogal
    invalid_reason turetir (uydurma deger YOK). Feature yeniden-kurulamaz
    (mail instance'lari) -> feature'siz satir; C1 bunlari atlar."""
    mevcut = _mevcut_idler(out)
    n_yeni = n_atlanan = 0
    for f in sorted(Path(detay_dir).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            n_atlanan += 1
            continue
        for batch_id, nr in (d.get("nesting_results") or {}).items():
            h = nr.get("height_mm")
            npar = nr.get("n_parts")
            mode = nr.get("nesting_mode_used") or "heightmap"
            if h is None or npar is None:
                n_atlanan += 1
                continue
            if mode == "wall_aware":
                mode = "heightmap+wall_aware"
            kosu_id = f"{f.name}/{batch_id}"
            bid = hashlib.sha1(f"otonom|{kosu_id}|{h}".encode()).hexdigest()[:16]
            if bid in mevcut:
                continue
            n_yeni += 1
            if dry_run:
                print(f"[dry-otonom] {kosu_id} mode={mode} h={h}")
                continue
            append_run_v2(
                out, kaynak="otonom_gecmis", instance_id=kosu_id, mode=mode,
                height_mm=float(h), n_placed=int(npar), n_total=int(npar),
                min_clearance_mm=nr.get("min_clearance_mm"),
                n_locked=None, source="mail",
                pitch_fine=nr.get("applied_pitch_mm"),
                duration_s=nr.get("elapsed_sec"), clearance_req_mm=2.0,
                recete="uretim", kosu_id=kosu_id,
                log=f"data/otonom_gecmis/detay/{f.name}",
                kanit_seviyesi="dusuk", backfill_id=bid,
                plate=[nr.get("plate_w_mm"), nr.get("plate_d_mm")],
            )
    return n_yeni, n_atlanan


def _gercek_feature_saglayici():
    """Set adi -> ozellik dict'i; instance yukleyicileri + onbellek."""
    from scripts.kxx_telemetri import ozellik_cikar
    onbellek: dict = {}

    def sagla(set_adi: str) -> Optional[dict]:
        if set_adi in onbellek:
            return onbellek[set_adi]
        inst = None
        try:
            if set_adi == "deneme5":
                from scripts.ax24_kuyruk_335 import _load
                inst = _load("deneme5", PLATE_STD)
            else:
                from scripts.eval_gate import _load_instance
                inst = _load_instance(set_adi)
        except Exception as e:
            print(f"UYARI: {set_adi} yuklenemedi ({type(e).__name__}: {e})")
        oz = ozellik_cikar(inst) if inst is not None else None
        onbellek[set_adi] = oz
        return oz

    return sagla


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(_ROOT / V2_DEFAULT_PATH))
    ap.add_argument("--otonom", action="store_true",
                    help="otonom_gecmis/detay kayitlarini da dok")
    args = ap.parse_args()
    out = Path(args.out)
    n, a = satirlari_uret(KAYITLAR, _gercek_feature_saglayici(), out,
                          dry_run=args.dry_run)
    print(f"K-deney: {n} yeni satir, {a} atlanan (toplam kayit {len(KAYITLAR)})")
    if args.otonom:
        no, ao = otonom_satirlari(_ROOT / "data" / "otonom_gecmis" / "detay",
                                  out, dry_run=args.dry_run)
        print(f"otonom_gecmis: {no} yeni satir, {ao} atlanan")
    print("BITTI")


if __name__ == "__main__":
    main()

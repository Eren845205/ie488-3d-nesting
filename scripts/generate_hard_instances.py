"""scripts/generate_hard_instances.py -- Zorlu/cesitli instance uretici.

Amac
----
Mevcut telemetride tabu/multistart/alns HICBIR instance'ta kazanmamis:
bunlar benchmark'ta hic kosulmadi. Bu script bu cozuculerin KAZANMA SANSININ
yuksek oldugu instance aileleri uretir, benchmark ile kosar, ve telemetriye ekler.

Hangi instance'larda kazanirlar?
---------------------------------
- multistart: Cok sayida yerel optimum iceren genis arama uzaylari (yuksek
  n_total_parts, siki konteyner, heterojen boyut dagilimi). Cok-baslangicli
  SA farkli yerel optimumlardan kacabilir; tek-basit-SA'nin kacirdigi global
  optimumu bulur.

- tabu: Orta buyuklukte, tabu listesinin "daha once gidilen noktadan kac"
  yarari sagladigi duzgun manzarali uzaylar. Tekrar-parca ailesi (high_qty_repeat)
  buyuk adet + siki konteyner ile iyi uyum saglar.

- alns: Buyuk ve yapisal problemler. "Worst removal" + "greedy repair" kombinasyonu
  yuksek-hacimli parcalari yeniden konumlandirarak bolgeler yaratir. Heterojen
  tekrar modellerinde (6-8 model x 6-8 adet) iyi sonuc uretir.

Kanit kosusu (varsayilan)
--------------------------
--proof modunda (varsayilan) sadece 4 kucuk instance × tum cozucular kosulur
(~30-60 saniye). Tam kosu icin --full bayragi kullanin.

Telemetri guvenligi
-------------------
- Genel runs.jsonl dosyasina DOKUNULMAZ (varsayilan davranis).
- Sonuclar "hard_instances" etiketiyle ayri gecici CSV/MD dosyasina yazilir.
- Ardindan ONAY ile (--append-telemetry) runs.jsonl'a eklenir.
- VEYA direkt append icin --append-telemetry --force bayraklari kullanilir.

Kullanim ornekleri
------------------
  # Kucuk kanit kosusu -- sonuclari goster, telemetriyi degistirme:
  python scripts/generate_hard_instances.py

  # Sonuclari incele, ardindan telemetriye ekle:
  python scripts/generate_hard_instances.py --append-telemetry

  # Tam set (uzun surer):
  python scripts/generate_hard_instances.py --full --append-telemetry --force

  # Sadece belirli cozuculer:
  python scripts/generate_hard_instances.py --solvers multistart,alns,tabu,dblf

Determinizm: seed=42 varsayilan. Ayni parametre + seed -> ayni instance -> ayni sonuc.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# Proje kokunu sys.path'e ekle
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.benchmark import run_benchmark
from src.nesting3d.instances.format import ContainerSpec

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_DEFAULT_TELEMETRY = _ROOT / "data" / "telemetry" / "runs.jsonl"
_DEFAULT_OUT_DIR = _ROOT / "results"

# Kanit kosusu icin dusuk butce (hiz onceligi)
_PROOF_BUDGET = 120
# Tam kosu icin yuksek butce (kalite onceligi)
_FULL_BUDGET = 400

_PROOF_SEED = 42
_FULL_SEED = 42


def _sq(side: float) -> ContainerSpec:
    """Kare-taban, acik-yukseklik konteyner."""
    return ContainerSpec(width_mm=side, depth_mm=side, height_mm=None)


# ---------------------------------------------------------------------------
# Instance aileleri: tabu/multistart/alns icin tasarlanmis
# ---------------------------------------------------------------------------

def _proof_instances() -> List[Dict[str, Any]]:
    """Kanit kosusu: 4 kucuk instance, her biri farkli aile."""
    return [
        # --- multistart hedefi: yuksek n_parts, siki konteyner, heterojen ---
        {
            "id": "hard_ms_rb_tight",
            "family": "random_boxes",
            "split": "tune",
            "params": {
                "n_parts": 28,
                "min_dim": 15,
                "max_dim": 65,
                "container": _sq(115),
                "seed": 7,
            },
        },
        # --- tabu hedefi: yuksek adet tekrar, siki konteyner ---
        {
            "id": "hard_tabu_hqr_dense",
            "family": "high_qty_repeat",
            "split": "tune",
            "params": {
                "n_models": 7,
                "qty_per_model": 7,
                "dim_min": 18,
                "dim_max": 40,
                "container": _sq(105),
                "seed": 13,
            },
        },
        # --- alns hedefi: buyuk tekrar model seti, heterojen hacim ---
        {
            "id": "hard_alns_flms_wide",
            "family": "few_large_many_small",
            "split": "tune",
            "params": {
                "n_large": 5,
                "n_small": 22,
                "large_min": 45,
                "large_max": 85,
                "small_min": 10,
                "small_max": 28,
                "container": _sq(125),
                "seed": 19,
            },
        },
        # --- multistart/alns: long_rods yuksek adet ---
        {
            "id": "hard_ms_lr_dense",
            "family": "long_rods",
            "split": "tune",
            "params": {
                "n_parts": 14,
                "cross_min": 10,
                "cross_max": 20,
                "length_min": 55,
                "length_max": 110,
                "container": _sq(135),
                "seed": 31,
            },
        },
    ]


def _full_instances() -> List[Dict[str, Any]]:
    """Tam set: 20 instance, 5 aile x 4 seed, yuksek n_parts."""
    insts: List[Dict[str, Any]] = []

    # random_boxes -- yuksek yuk, heterojen boyut
    for n_parts, cont, sd in [
        (25, 115, 7), (28, 120, 11), (30, 125, 17), (32, 118, 23),
    ]:
        insts.append({
            "id": f"hard_rb_n{n_parts}_s{sd}",
            "family": "random_boxes",
            "split": "tune",
            "params": {
                "n_parts": n_parts, "min_dim": 15, "max_dim": 65,
                "container": _sq(cont), "seed": sd,
            },
        })

    # high_qty_repeat -- cok adet, siki konteyner
    for n_models, qty, cont, sd in [
        (6, 7, 105, 3), (7, 7, 110, 13), (7, 8, 108, 19), (8, 6, 112, 29),
    ]:
        insts.append({
            "id": f"hard_hqr_{n_models}x{qty}_s{sd}",
            "family": "high_qty_repeat",
            "split": "tune",
            "params": {
                "n_models": n_models, "qty_per_model": qty,
                "dim_min": 18, "dim_max": 40,
                "container": _sq(cont), "seed": sd,
            },
        })

    # few_large_many_small -- buyuk parcalar + cok kucuk
    for n_large, n_small, cont, sd in [
        (4, 22, 120, 5), (5, 22, 125, 19), (5, 25, 128, 37), (6, 20, 130, 41),
    ]:
        insts.append({
            "id": f"hard_flms_{n_large}L{n_small}S_s{sd}",
            "family": "few_large_many_small",
            "split": "tune",
            "params": {
                "n_large": n_large, "n_small": n_small,
                "large_min": 45, "large_max": 85,
                "small_min": 10, "small_max": 28,
                "container": _sq(cont), "seed": sd,
            },
        })

    # thin_plates -- yuksek adet, siki konteyner
    for n_parts, cont, sd in [
        (22, 78, 3), (24, 80, 11), (25, 82, 23), (26, 78, 37),
    ]:
        insts.append({
            "id": f"hard_tp_n{n_parts}_s{sd}",
            "family": "thin_plates",
            "split": "tune",
            "params": {
                "n_parts": n_parts, "xy_min": 22, "xy_max": 42,
                "thickness_min": 5, "thickness_max": 12,
                "container": _sq(cont), "seed": sd,
            },
        })

    # long_rods -- yuksek adet, heterojen uzunluk
    for n_parts, cont, sd in [
        (14, 135, 7), (16, 140, 17), (14, 138, 29), (16, 142, 43),
    ]:
        insts.append({
            "id": f"hard_lr_n{n_parts}_s{sd}",
            "family": "long_rods",
            "split": "tune",
            "params": {
                "n_parts": n_parts, "cross_min": 10, "cross_max": 20,
                "length_min": 55, "length_max": 115,
                "container": _sq(cont), "seed": sd,
            },
        })

    return insts


# ---------------------------------------------------------------------------
# Winner ozeti
# ---------------------------------------------------------------------------

def _winner_summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """winner_flag=True olan satirlarin cozucu dagilimini dondur."""
    return dict(Counter(r["cozucu"] for r in rows if r.get("winner_flag")))


def _instance_winner_table(rows: List[Dict[str, Any]]) -> str:
    """Instance bazinda kazanan cozucuyu goster (insan-okunabilir)."""
    by_inst: Dict[str, Dict[str, float]] = {}
    for r in rows:
        iid = r["instance_id"]
        if iid not in by_inst:
            by_inst[iid] = {}
        if r.get("winner_flag"):
            by_inst[iid]["winner"] = r["cozucu"]
            by_inst[iid]["height_mm"] = r["height_mm"]

    lines = [
        f"{'Instance':35s}  {'Kazanan':15s}  Height(mm)",
        "-" * 65,
    ]
    for iid, info in sorted(by_inst.items()):
        winner = info.get("winner", "?")
        h = info.get("height_mm", float("nan"))
        lines.append(f"{iid:35s}  {winner:15s}  {h:.2f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# _append_to_telemetry: JSONL append helper
# ---------------------------------------------------------------------------

def _append_to_telemetry(
    source_jsonl: Path,
    target_jsonl: Path,
) -> int:
    """source_jsonl satirlarini target_jsonl'a ekle. Eklenen satir sayisi doner."""
    if not source_jsonl.exists():
        return 0
    lines = [
        line for line in source_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    target_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with target_jsonl.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")
    return len(lines)


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tabu/multistart/alns'in kazanma sansi olan zorlu instance ailesi uret,\n"
            "benchmark ile cos, telemetriyi zenginlestir.\n\n"
            "Varsayilan: kucuk kanit kosusu (4 instance, telemetri degismez).\n"
            "Tam set icin: --full --append-telemetry --force"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        default=False,
        help="Tam set (20 instance, yuksek budget). Varsayilan: kanit kosusu (4 instance).",
    )
    parser.add_argument(
        "--solvers",
        default="multistart,alns,tabu,dblf,sa3d",
        help=(
            "Virgul-ayri cozucu listesi. "
            "Varsayilan: multistart,alns,tabu,dblf,sa3d"
        ),
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=None,
        help=(
            f"Iterasyon butcesi. Varsayilan: "
            f"kanit={_PROOF_BUDGET}, tam={_FULL_BUDGET}"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_PROOF_SEED,
        help=f"Raslantisallik tohumu (varsayilan: {_PROOF_SEED}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT_DIR,
        help=f"Sonuc dizini (varsayilan: {_DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--append-telemetry",
        action="store_true",
        default=False,
        help=(
            "Sonuclari runs.jsonl'a ekle. "
            "Dikkat: --force olmadan onay sorar."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="--append-telemetry ile birlikte: onay sormadan ekle.",
    )
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=_DEFAULT_TELEMETRY,
        help=f"Ana telemetri dosyasi (varsayilan: {_DEFAULT_TELEMETRY}).",
    )
    args = parser.parse_args()

    solver_names = [s.strip() for s in args.solvers.split(",") if s.strip()]
    is_full = args.full
    budget = args.budget or (_FULL_BUDGET if is_full else _PROOF_BUDGET)
    instances = _full_instances() if is_full else _proof_instances()
    label = "hard_full" if is_full else "hard_proof"

    print("=" * 70)
    print("generate_hard_instances.py -- Zorlu Instance Uretici")
    print("=" * 70)
    print(f"  Mod        : {'TAM SET' if is_full else 'KANIT KOSUSU (kucuk)'}")
    print(f"  Instance   : {len(instances)} adet")
    print(f"  Cozucular  : {solver_names}")
    print(f"  Budget     : {budget} iterasyon")
    print(f"  Seed       : {args.seed}")
    print(f"  Cikti      : {args.out_dir}")
    print()

    # Gecici telemetri dosyasi (ana dosyaya dokunma)
    tmp_tel = args.out_dir / f"telemetry_{label}.jsonl"
    tmp_tel.parent.mkdir(parents=True, exist_ok=True)
    # Eski gecici dosyayi temizle (tekrar kosu)
    if tmp_tel.exists():
        tmp_tel.unlink()

    t0 = time.perf_counter()
    rows = run_benchmark(
        instances=instances,
        solver_names=solver_names,
        pitch=15.0,
        budget=budget,
        seed=args.seed,
        out_dir=args.out_dir,
        label=label,
        telemetry_path=tmp_tel,
        adaptive_pitch=True,
        pitch_factor=2.5,
        pitch_floor=0.5,
        max_voxels_per_axis=200,
        is_quick=False,
    )
    elapsed = time.perf_counter() - t0

    print()
    print(f"Tamamlandi: {len(rows)} satir, {elapsed:.1f} saniye")
    print()

    # Kazanan dagilimi
    wins = _winner_summary(rows)
    print("--- Kazanan Dagilimi (winner_flag=True) ---")
    all_solvers_in_run = sorted({r["cozucu"] for r in rows})
    for s in all_solvers_in_run:
        w = wins.get(s, 0)
        total = sum(1 for r in rows if r["cozucu"] == s)
        bar = "#" * w + "." * (total - w)
        status = " <-- KAZANDI" if w > 0 and s in ("tabu", "multistart", "alns") else ""
        print(f"  {s:15s}: {w:2d}/{total} kazanma  [{bar}]{status}")
    print()

    # Instance bazinda tablo
    print("--- Instance Bazinda Kazanan ---")
    print(_instance_winner_table(rows))
    print()

    # Sonuc dosyalari
    print(f"  MD  : {args.out_dir}/benchmark_{label}.md")
    print(f"  CSV : {args.out_dir}/benchmark_{label}.csv")
    print(f"  Gecici telemetri: {tmp_tel}  ({sum(1 for _ in tmp_tel.read_text(encoding='utf-8').splitlines() if _.strip())} satir)")
    print()

    # Telemetriye ekleme
    if args.append_telemetry:
        do_append = True
        if not args.force:
            existing_lines = 0
            if args.telemetry.exists():
                existing_lines = sum(
                    1 for line in args.telemetry.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            new_lines = sum(
                1 for line in tmp_tel.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            confirm = input(
                f"runs.jsonl mevcut: {existing_lines} satir. "
                f"{new_lines} satir eklenecek. Onayliyor musunuz? [e/h]: "
            ).strip().lower()
            do_append = confirm in ("e", "evet", "y", "yes")

        if do_append:
            n_added = _append_to_telemetry(tmp_tel, args.telemetry)
            print(f"Telemetri guncellendi: {n_added} satir {args.telemetry} dosyasina eklendi.")
            print(f"Simdi 'python -m scripts.retrain_selection' ile modeli yeniden egitebilirsiniz.")
        else:
            print("Ekleme iptal edildi. Gecici dosya kaldi: {tmp_tel}")
    else:
        print(
            "Telemetri degistirilmedi (--append-telemetry bayraklari yok).\n"
            f"Eklemek icin:\n"
            f"  python scripts/generate_hard_instances.py --append-telemetry\n"
            f"Veya elle ekleyin:\n"
            f"  cat {tmp_tel} >> {args.telemetry}"
        )

    print("=" * 70)


if __name__ == "__main__":
    main()

"""benchmark.py — Tek komutla cok-instance x cok-cozucu kiyaslama koşucusu.

Kullanim:
    python scripts/benchmark.py --quick           # hizli alt kume, kaba pitch
    python scripts/benchmark.py                   # tam set (gece kosusu)
    python scripts/benchmark.py --label my_run    # ozel etiket

Cikti:
    results/benchmark_<label>.md   — markdown tablosu
    results/benchmark_<label>.csv  — ham veri (ozellik kolonlari dahil)
    data/telemetry/runs.jsonl       — kalici telemetri (append-only)

Tablo kolonlari:
    instance_id, aile, split, cozucu,
    height_mm, density, time_s,
    height_lb_mm (teorik alt sinir),
    density_ratio (R5: lb_mm / height_mm — oran (0,1]; 1.0 = kayipsiz, kucuk = buyuk
                   heightmap kaybi; height_mm elde edilen gercek yukseklik,
                   lb_mm teorik alt sinir yuksekligi),
    <FEATURE_NAMES> (20 ozellik),
    winner_flag (bu instance icin en iyi cozucu mu?)
    is_tied (birden fazla cozucu ayni minimum yuksekligi paylasiyor mu?)

Tek-konfig kurali (PLAN_DEMO1 §5):
    Parametre seti scripts/benchmark_config.py'de dondurulmustur.
    --quick modu pitch'i kabalastirir ve instance alt kumesi alir.

Ciplak-motor notu:
    Mevcut kosuların tamamı elle kisitsiz (ciplak motor) — override mekanizmasi
    (Instance-Tuner) geldiginde ayri ciplak-motor kolonu eklenecek
    (PLAN_DEMO1 §2.5 sartinin bilincli ertelenen kismi).
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Proje kokunu sys.path'e ekle (script dogrudan da calistirabilmeli)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.features import FEATURE_NAMES, extract_features
from src.nesting3d.instances.format import to_voxel_parts, ContainerSpec
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.instances.synthetic import (
    random_boxes,
    few_large_many_small,
    high_qty_repeat,
    thin_plates,
    long_rods,
)
from src.nesting3d.instances.br_loader import load_br_instance
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.solvers.sa_solver import SASolver, MultiStartSA
from src.nesting3d.solvers.ga_solver import GASolver
from src.nesting3d.solvers.tabu_solver import TabuSolver
from src.nesting3d.telemetry import append_run

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_SOLVER_REGISTRY: Dict[str, Any] = {
    "dblf": DBLFSolver,
    "sa3d": SASolver,
    "ga": GASolver,
    "tabu": TabuSolver,
    "multistart": MultiStartSA,  # R4: çok-start SA (median/best/std raporlar)
}

_FAMILY_BUILDERS = {
    "random_boxes": random_boxes,
    "few_large_many_small": few_large_many_small,
    "high_qty_repeat": high_qty_repeat,
    "thin_plates": thin_plates,
    "long_rods": long_rods,
}

# Tablo MD kolonlari (ozellik kolonlari sonraya eklenir)
# _ALL_COLS tek kaynaktan turetilir: ozellik kolonlari + sentinel kolonlar.
_SENTINEL_COLS = ["winner_flag", "is_tied"]
_BASE_COLS = [
    "instance_id", "aile", "split", "cozucu",
    "height_mm", "density", "time_s",
    "height_lb_mm", "density_ratio",
] + _SENTINEL_COLS
_ALL_COLS = (
    _BASE_COLS[: _BASE_COLS.index("winner_flag")]
    + list(FEATURE_NAMES)
    + _SENTINEL_COLS
)


# ---------------------------------------------------------------------------
# Instance uretimi
# ---------------------------------------------------------------------------

def _build_instance(inst_spec: Dict[str, Any]):
    """Instance spec'ten NestingInstance uret."""
    family = inst_spec["family"]
    params = inst_spec.get("params", {})

    if family == "bischoff_ratcliff":
        return load_br_instance(
            class_name=params["class_name"],
            instance_idx=params.get("instance_idx", 0),
        )
    builder = _FAMILY_BUILDERS.get(family)
    if builder is None:
        raise ValueError(f"Bilinmeyen aile: '{family}'")
    return builder(**params)


# ---------------------------------------------------------------------------
# Teorik alt sinir hesabi
# ---------------------------------------------------------------------------

def _compute_lb(instance) -> float:
    """Teorik alt sinir yukseklik (mm).

    Alt sinir = toplam parca hacmi / (konteyner genisligi * konteyner derinligi).
    Bu deger her turlu 3D istifin asagisindan gidemeyecegi yuksekliktir.

    Not: pitch parametresi burada kullanilmaz (gelecekte pitch-aware LB
    gerekirse bu fonksiyon genisletilebilir).
    """
    cont = instance.container
    total_vol = sum(
        (p.width_mm or 0.0) * (p.depth_mm or 0.0) * (p.height_mm or 0.0) * p.qty
        for p in instance.parts
    )
    base_area = cont.width_mm * cont.depth_mm
    lb = total_vol / max(base_area, 1e-12)
    return lb


# ---------------------------------------------------------------------------
# Ana kosucu fonksiyon (programatik API + CLI cagrisinin ortak iskeleti)
# ---------------------------------------------------------------------------

def run_benchmark(
    instances: List[Dict[str, Any]],
    solver_names: List[str],
    pitch: float,
    budget: int,
    seed: int,
    out_dir: Path,
    label: str,
    telemetry_path: Optional[Path] = None,
    n_orientations: int = 4,
    is_quick: bool = False,
    adaptive_pitch: bool = False,
    pitch_factor: float = 2.5,
    pitch_floor: float = 2.0,
    max_voxels_per_axis: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Tum instance'lar x tum cozucular icin benchmark kosu.

    Her (instance, cozucu) cifti icin bir satir uretir.

    Args:
        instances:        Instance spec listesi (id, family, split, instance).
                          "instance" anahtari varsa dogrudan NestingInstance;
                          yoksa family + params'tan uretilir.
        solver_names:     Cozucu isim listesi (benchmark_config.SOLVER_NAMES).
        pitch:            Voxelizasyon adimi (mm).
        budget:           Iterasyon butcesi.
        seed:             Tum kosular icin ana seed.
        out_dir:          Cikti dizini (MD + CSV dosyalari buraya yazilir).
        label:            Dosya adi etiketi (benchmark_<label>.md/.csv).
        telemetry_path:   JSONL telemetri dosya yolu; None ise
                          out_dir/telemetry_runs.jsonl kullanilir.
        n_orientations:   Voxelizasyonda kullanilacak poz sayisi (default=4).
        is_quick:         --quick bayragiyla calistirildiysa True; telemetri
                          satirina "is_quick" alani olarak yazilir (kirlilik onleme).

    Returns:
        List[dict] — her satir bir (instance, cozucu) sonucu.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if telemetry_path is None:
        telemetry_path = out_dir / "telemetry_runs.jsonl"

    # Cozuculeri hazirla
    solvers: Dict[str, Any] = {}
    for name in solver_names:
        cls = _SOLVER_REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"Bilinmeyen cozucu: '{name}'. "
                f"Kayitli: {list(_SOLVER_REGISTRY)}"
            )
        solvers[name] = cls()

    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for inst_spec in instances:
        inst_id = inst_spec["id"]
        family = inst_spec["family"]
        split = inst_spec["split"]

        # NestingInstance: dogrudan verilmisse kullan; lazy factory varsa cagir
        # (ornek: numune STL yuklemesi import'ta degil kosuda); yoksa uret.
        if "instance" in inst_spec:
            nesting_inst = inst_spec["instance"]
        elif "instance_factory" in inst_spec:
            nesting_inst = inst_spec["instance_factory"]()
        else:
            nesting_inst = _build_instance(inst_spec)

        # Ozellik vektoru (deterministik)
        feat = extract_features(nesting_inst)
        feat_dict = feat.to_dict()

        # Teorik alt sinir
        lb_mm = _compute_lb(nesting_inst)

        # Pitch: adaptif modda her instance'a kendi pitch'i (R6); aksi halde
        # gecirilen scalar pitch (geriye uyumlu — testler + --quick yolu).
        # adaptif modda gecirilen `pitch` scalar'i TAVAN (ceil) olarak kullanilir.
        cont = nesting_inst.container
        if adaptive_pitch:
            inst_pitch = suggest_pitch(
                nesting_inst,
                factor=pitch_factor,
                floor=pitch_floor,
                ceil=pitch,
            )
        else:
            inst_pitch = pitch

        # Runtime bütçesi: adaptif pitch çok ince parça (ör. BR birim-ölçek
        # 1 mm) için konteyner-eksen voxel sayısını patlatabilir. "Sessiz
        # kabalaştırma YOK" ilkesi (parça kaybolur) + "çökme YOK": eşiği aşan
        # instance ATLA + LOGLA (drop'u açıkça raporla). Atlananlar HPC/A14
        # veya veri-yeniden-ölçekleme backlog'una düşer.
        cont_axes = [cont.width_mm, cont.depth_mm]
        if cont.height_mm:
            cont_axes.append(cont.height_mm)
        vox_per_axis = max(cont_axes) / max(inst_pitch, 1e-9)
        if max_voxels_per_axis is not None and vox_per_axis > max_voxels_per_axis:
            skipped.append({
                "instance_id": inst_id,
                "aile": family,
                "split": split,
                "pitch_mm": round(inst_pitch, 4),
                "vox_per_axis": round(vox_per_axis, 1),
                "neden": (
                    f"voxel/eksen {vox_per_axis:.0f} > butce {max_voxels_per_axis} "
                    f"(min parca {pitch_floor}mm cozunurlugu konteyner olcegine gore "
                    f"asiri ince — veri yeniden-olceklensin veya HPC)"
                ),
            })
            print(f"[benchmark] ATLANDI: {inst_id} ({family}) — "
                  f"voxel/eksen {vox_per_axis:.0f} > {max_voxels_per_axis}")
            continue

        # Voxelizasyon
        parts = to_voxel_parts(nesting_inst, inst_pitch, n_orientations=n_orientations)

        # Q4: default-arg ile closure gecmis-baglama tuzagini onle
        def make_bin(cont=cont, inst_pitch=inst_pitch) -> Bin3D:  # type: ignore[assignment]
            return Bin3D(
                plate_w_mm=cont.width_mm,
                plate_d_mm=cont.depth_mm,
                pitch=inst_pitch,
            )

        # Her cozucu icin kos
        inst_results: List[Dict[str, Any]] = []

        for solver_name, solver in solvers.items():
            t0 = time.perf_counter()
            result = solver.solve(
                parts,
                make_bin,
                budget=budget,
                seed=seed,
            )
            elapsed = time.perf_counter() - t0

            # Q1: density_ratio = lb_mm / height_mm
            # Aralik (0,1]: 1.0 = kayipsiz (gercek yukseklik alt sinira esit),
            # kucuk deger = buyuk heightmap kaybi (cozucu verimsiz istif yapti).
            density_ratio = round(
                lb_mm / max(result.height_mm, 1e-12), 6
            )

            row: Dict[str, Any] = {
                "instance_id": inst_id,
                "aile": family,
                "split": split,
                "pitch_mm": round(inst_pitch, 4),
                "cozucu": solver_name,
                "height_mm": round(result.height_mm, 4),
                "density": round(result.density, 6),
                "time_s": round(elapsed, 4),
                "height_lb_mm": round(lb_mm, 4),
                "density_ratio": density_ratio,
            }
            # Ozellik kolonlarini ekle
            row.update(feat_dict)
            inst_results.append(row)

        # Q5: winner_flag + is_tied
        # Esitlik karsilastirmasi: 1e-9 tolerans (float yuvarlama guvencesi).
        min_height = min(r["height_mm"] for r in inst_results)
        winners = [r for r in inst_results if abs(r["height_mm"] - min_height) < 1e-9]
        is_tied = len(winners) > 1
        for r in inst_results:
            r["winner_flag"] = abs(r["height_mm"] - min_height) < 1e-9
            # is_tied: True ise birden fazla cozucu ayni minimum yuksekligi
            # paylasir; secim modeli bu durumda ek kriter kullanmali.
            r["is_tied"] = is_tied

        # Telemetriye yaz
        for r in inst_results:
            append_run(
                telemetry_path,
                kaynak="benchmark",
                instance_id=r["instance_id"],
                aile=r["aile"],
                feature_vector=feat.values,
                cozucu=r["cozucu"],
                pitch=inst_pitch,
                budget=budget,
                seed=seed,
                height_mm=r["height_mm"],
                density=r["density"],
                time_s=r["time_s"],
                winner_flag=r["winner_flag"],
                # Q3: is_quick etiketi — kirlilik onleme
                is_quick=is_quick,
            )

        rows.extend(inst_results)

    # Cikti dosyalari yaz
    _write_outputs(rows, out_dir, label, skipped=skipped)
    if skipped:
        print(f"[benchmark] {len(skipped)} instance ATLANDI (voxel butcesi) — "
              f"detay MD'de '## Atlanan Instance'lar' bolumunde.")

    return rows


# ---------------------------------------------------------------------------
# Cikti dosyalari
# ---------------------------------------------------------------------------

def _write_outputs(
    rows: List[Dict[str, Any]],
    out_dir: Path,
    label: str,
    skipped: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """MD ve CSV cikti dosyalarini yaz."""
    md_path = out_dir / f"benchmark_{label}.md"
    csv_path = out_dir / f"benchmark_{label}.csv"

    # CSV — tum kolonlar
    fieldnames = list(rows[0].keys()) if rows else _ALL_COLS
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    csv_path.write_text(csv_buf.getvalue(), encoding="utf-8")

    # Markdown — ana sonuc kolonlari + ortalama satirlari
    md_lines = [
        f"# Benchmark Sonuclari — {label}",
        f"",
        f"Tarih: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
    ]

    # Tune ve holdout tablolari ayri
    for split_name in ("tune", "holdout"):
        split_rows = [r for r in rows if r["split"] == split_name]
        if not split_rows:
            continue
        md_lines.append(f"## {split_name.capitalize()} Seti")
        md_lines.append("")
        md_lines.extend(_build_md_table(split_rows))
        md_lines.append("")
        md_lines.extend(_build_avg_section(split_rows, split_name))
        md_lines.append("")

    # Atlanan instance'lar — "no silent caps": drop'u acikca raporla.
    if skipped:
        md_lines.append("## Atlanan Instance'lar (voxel butcesi)")
        md_lines.append("")
        md_lines.append("| instance_id | aile | split | pitch_mm | vox/eksen | neden |")
        md_lines.append("|---|---|---|---|---|---|")
        for s in skipped:
            md_lines.append(
                f"| {s['instance_id']} | {s['aile']} | {s['split']} | "
                f"{s['pitch_mm']} | {s['vox_per_axis']} | {s['neden']} |"
            )
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")


def _build_md_table(rows: List[Dict[str, Any]]) -> List[str]:
    """Ana kolonlarla markdown tablosu olustur."""
    cols = [
        "instance_id", "aile", "pitch_mm", "cozucu",
        "height_mm", "density", "time_s",
        "height_lb_mm", "density_ratio", "winner_flag",
    ]
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for r in rows:
        vals = []
        for col in cols:
            v = r.get(col, "")
            if isinstance(v, float):
                vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def _build_avg_section(rows: List[Dict[str, Any]], split_name: str) -> List[str]:
    """Cozucu basina ortalama yukseklik + doluluk + sure satirlari."""
    lines = [f"### {split_name.capitalize()} Ortalamalar"]
    lines.append("")
    lines.append("| cozucu | ortalama_height_mm | ortalama_density | ortalama_time_s |")
    lines.append("|---|---|---|---|")

    solvers = sorted({r["cozucu"] for r in rows})
    for solver_name in solvers:
        sr = [r for r in rows if r["cozucu"] == solver_name]
        if not sr:
            continue
        avg_h = sum(r["height_mm"] for r in sr) / len(sr)
        avg_d = sum(r["density"] for r in sr) / len(sr)
        avg_t = sum(r["time_s"] for r in sr) / len(sr)
        lines.append(
            f"| {solver_name} | {avg_h:.4f} | {avg_d:.4f} | {avg_t:.4f} |"
        )
    return lines


# ---------------------------------------------------------------------------
# CLI giris noktasi
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark koşucusu — instance × cozucu kiyaslama tablosu"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Hizli mod: sadece tune setinin ilk 3 instance'ini, "
            "kaba pitch (20 mm), dusuk budget (30 iter) kullanir. "
            "Tam kos icin bu bayrak olmadan calistir (gece kosusu)."
        ),
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Cikti dosyasi etiketi (varsayilan: tarih)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Cikti dizini (varsayilan: results/)",
    )
    parser.add_argument(
        "--solvers",
        default=None,
        help="Virgul-ayri cozucu listesi (varsayilan: benchmark_config.SOLVER_NAMES)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI giris noktasi."""
    args = _parse_args()

    from scripts.benchmark_config import (
        ADAPTIVE_PITCH,
        PITCH_FACTOR,
        PITCH_FLOOR,
        MAX_VOXELS_PER_AXIS,
        PITCH,
        BUDGET,
        SEED,
        SOLVER_NAMES,
        TUNE_INSTANCES,
        HOLDOUT_INSTANCES,
    )

    # Pitch politikasi:
    # --quick: sabit pitch=10 (sadece ilk 3 sağlam instance; hizli smoke).
    # tam set: adaptif (her instance'a kendi pitch'i, R6) — PITCH tavan rolunde.
    # adaptif mod thin_plates/long_rods cokuslerini yapisal olarak cozer.
    pitch = 10.0 if args.quick else PITCH
    adaptive_pitch = ADAPTIVE_PITCH and not args.quick
    budget = 30 if args.quick else BUDGET
    seed = SEED
    solver_names = args.solvers.split(",") if args.solvers else SOLVER_NAMES

    label = args.label or datetime.utcnow().strftime("%Y%m%d_%H%M")
    out_dir = Path(args.out_dir) if args.out_dir else _ROOT / "results"
    tel_path = _ROOT / "data" / "telemetry" / "runs.jsonl"

    # --quick: sadece tune'un ilk 3 instance'i
    if args.quick:
        instances_to_run = TUNE_INSTANCES[:3]
        print(f"[benchmark] --quick modu: {len(instances_to_run)} tune instance, "
              f"pitch={pitch} mm, budget={budget}")
    else:
        instances_to_run = TUNE_INSTANCES + HOLDOUT_INSTANCES
        pitch_desc = (
            f"adaptif (min_dim/{PITCH_FACTOR}, [{PITCH_FLOOR}, {pitch}] mm)"
            if adaptive_pitch else f"{pitch} mm"
        )
        print(f"[benchmark] Tam set: {len(instances_to_run)} instance, "
              f"pitch={pitch_desc}, budget={budget}, cozucu={solver_names}")

    rows = run_benchmark(
        instances=instances_to_run,
        solver_names=solver_names,
        pitch=pitch,
        budget=budget,
        seed=seed,
        out_dir=out_dir,
        label=label,
        telemetry_path=tel_path,
        is_quick=args.quick,
        adaptive_pitch=adaptive_pitch,
        pitch_factor=PITCH_FACTOR,
        pitch_floor=PITCH_FLOOR,
        max_voxels_per_axis=None if args.quick else MAX_VOXELS_PER_AXIS,
    )

    # Ozet basmak
    print(f"\n[benchmark] {len(rows)} satir uretildi.")
    print(f"[benchmark] MD  : {out_dir}/benchmark_{label}.md")
    print(f"[benchmark] CSV : {out_dir}/benchmark_{label}.csv")
    print(f"[benchmark] Telemetri: {tel_path} ({_count_lines(tel_path)} satir toplam)")

    # Ornek tablo (ilk 5 satir)
    _print_summary(rows[:5])


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    cols = ["instance_id", "cozucu", "height_mm", "density", "time_s", "winner_flag"]
    header = " | ".join(f"{c:20}" for c in cols)
    print("\n--- Ilk Satirlar ---")
    print(header)
    print("-" * len(header))
    for r in rows:
        line = " | ".join(
            f"{str(r.get(c, ''))[:20]:20}" for c in cols
        )
        print(line)


if __name__ == "__main__":
    main()

"""models.py — STL loading + scaling for the 3D nesting pipeline (PLAN_3D.md §3).

A "model" here is a (name, mesh, qty) triple.  The default set mirrors the
hoca directive (2026-06-09 note): chair x10, bracket x5, ring x15.  Any STL
dropped into data/models/ can be used instead via load_model().
"""

from pathlib import Path
from typing import List, Tuple

import trimesh

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"

# (file stem, target longest edge in mm) — PLAN_3D.md §2.2/§2.3
MODEL_SIZES = [
    ("chair", 70.0),
    ("bracket", 50.0),
    ("ring", 40.0),
]

# Scenario = quantity profile.  "default" is the hoca directive (x10/x5/x15);
# "stress" scales it 1.4x — the instance where SA demonstrably beats the
# greedy baseline (calibration run 2026-06-09), mirroring the 2D small/stress
# scenario split.  "numune" = hocanın yolladığı 8 gerçek parça (2026-06-10),
# Numuneler/ klasöründen GERÇEK mm boyutlarıyla (ölçeklenmeden) yüklenir.
NUMUNE_DIR = Path(__file__).resolve().parent.parent.parent / "Numuneler"

NUMUNE_QUANTITIES = {
    "n1": 4, "n2": 16, "n3": 3, "n4": 15, "n5": 1, "n6": 3, "n7": 3, "n8": 3,
}

SCENARIOS = {
    "default": {"chair": 10, "bracket": 5, "ring": 15},
    "stress": {"chair": 14, "bracket": 7, "ring": 21},
    "numune": NUMUNE_QUANTITIES,
}

DEFAULT_SET = [
    (name, size, SCENARIOS["default"][name]) for name, size in MODEL_SIZES
]


def load_model(stl_path: Path | str, target_max_dim_mm: float) -> trimesh.Trimesh:
    """Load an STL, scale it uniformly so its longest edge is the target size,
    and move its bounding-box min corner to the origin."""
    mesh = trimesh.load(str(stl_path), force="mesh")
    if mesh.is_empty or len(mesh.faces) == 0:
        raise ValueError(f"empty or unreadable mesh: {stl_path}")

    scale = target_max_dim_mm / float(mesh.extents.max())
    mesh.apply_scale(scale)
    mesh.apply_translation(-mesh.bounds[0])
    return mesh


def _decimate_display(
    mesh: trimesh.Trimesh, target_faces: int = 4000, max_drift: float = 0.05
) -> trimesh.Trimesh:
    """Görsel/STL export için hafif kopya: kademeli quadric decimation.

    Hacim drifti max_drift'i aşan adım GERİ alınır — delikli numune
    plakalarında (n3/n6/n7/n8) agresif decimation %28'e varan hacim kaybı
    yaratabiliyor (kalibrasyon 2026-06-10).  fast_simplification yoksa
    orijinal mesh döner (sadece render yavaşlar, sonuç değişmez).
    """
    try:
        import fast_simplification
    except ImportError:
        return mesh

    best = mesh
    while len(best.faces) > target_faces:
        # tek hamlede hedefe inmek delikli plakalarda drifti patlatıyor;
        # adım başına en çok %60 küçült, her adımda ORİJİNALE karşı doğrula
        reduction = min(0.6, 1.0 - target_faces / len(best.faces))
        v, f = fast_simplification.simplify(
            best.vertices, best.faces, target_reduction=reduction, agg=7
        )
        cand = trimesh.Trimesh(vertices=v, faces=f, process=False)
        no_progress = len(cand.faces) > 0.95 * len(best.faces)
        if no_progress or abs(cand.volume - mesh.volume) > max_drift * abs(mesh.volume):
            break
        best = cand
    return best


def numune_model_set(
    models_dir: Path | str = NUMUNE_DIR,
) -> List[tuple]:
    """Hocanın gerçek numuneleri: [(name, mesh, qty, display_mesh), ...].

    Mesh'ler GERÇEK boyutlarıyla kullanılır — load_model'deki ölçekleme
    burada YOK.  Packing orijinal (watertight) mesh'ten voxelize edilir;
    4. eleman display_mesh görsel + STL export içindir.
    """
    models_dir = Path(models_dir)
    out = []
    for name, qty in NUMUNE_QUANTITIES.items():
        path = models_dir / f"{name[1:]}.stl"
        if not path.exists():
            raise FileNotFoundError(f"{path} yok — Numuneler/ klasörünü kontrol et.")
        mesh = trimesh.load(str(path), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            raise ValueError(f"empty or unreadable mesh: {path}")
        mesh.apply_translation(-mesh.bounds[0])
        out.append((name, mesh, qty, _decimate_display(mesh)))
    return out


def model_set(
    scenario: str = "default",
    models_dir: Path | str = MODELS_DIR,
) -> List[Tuple[str, trimesh.Trimesh, int]]:
    """Return a scenario's model set: [(name, scaled mesh, qty), ...].

    Raises FileNotFoundError with a pointer to the generator script when the
    STL files have not been produced yet.
    """
    if scenario == "numune":
        return numune_model_set()
    quantities = SCENARIOS[scenario]
    models_dir = Path(models_dir)
    out = []
    for name, target_mm in MODEL_SIZES:
        path = models_dir / f"{name}.stl"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} yok — önce 'python scripts/generate_models.py' çalıştır."
            )
        out.append((name, load_model(path, target_mm), quantities[name]))
    return out


def default_model_set(
    models_dir: Path | str = MODELS_DIR,
) -> List[Tuple[str, trimesh.Trimesh, int]]:
    """The hoca-directive set (chair x10, bracket x5, ring x15)."""
    return model_set("default", models_dir)

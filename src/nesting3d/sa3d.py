"""sa3d.py — Simulated Annealing layer over the DBLF decoder (PLAN_3D.md §2.7).

Direct port of the 2D src/metaheuristic.py skeleton; differences only where
3D requires them:
  - Solution  = ordered list of (part, orientation_idx) — orientation joined
    the decision variable (2D had only the order; rotation was enumerated
    inside the decoder).
  - Decoder   = dblf.place_in_order with the solution's FIXED orientation per
    part (single-orientation decode keeps SA iterations cheap).
  - Energy    = max_height_mm + 0.1 * rms_height_mm.  Primary objective is
    the bin height; the RMS term breaks the plateau ties a discrete voxel
    heightmap produces — it strictly prefers flat, spread-out poses over tall
    ones of equal volume, giving SA a gradient toward compact layouts.
  - Start     = the full DBLF baseline solution (order AND chosen
    orientations), so SA can never end worse than the baseline
    (best-so-far is retained, same guarantee as 2D).

Determinism: all randomness flows through one seeded random.Random — same
(parts, bin, seed, schedule) always gives the same result.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Union

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import dblf
from src.nesting3d.voxelize import VoxelPart

Solution = List[Tuple[VoxelPart, int]]

# §1.4 (PLAN_DEMO1): decode is defined in solvers/base.py as the canonical
# shared implementation; sa3d re-exports it so existing callers are unchanged.
from src.nesting3d.solvers.base import decode  # noqa: E402 (import after type aliases)

# Adaptif t0 (R2). "auto" sentinel + probe parametreleri (modül seviyesinde →
# testler monkeypatch edebilir).
_T0_AUTO = "auto"
_AUTO_T0_PROBES: int = 50          # t0 kalibrasyonu için rastgele komşu sayısı
_AUTO_T0_P0: float = 0.5           # t=t0'da hedef erken-kabul olasılığı


def _energy(bin3d: Bin3D) -> float:
    """max height (primary, mm) + RMS compactness gradient (see Bin3D.rms_height_mm)."""
    return bin3d.max_height_mm() + 0.1 * bin3d.rms_height_mm()


def _neighbour(solution: Solution, rng: random.Random) -> Solution:
    """One move away: order move (as in 2D) or an orientation flip."""
    n = len(solution)
    new = list(solution)
    if n < 2:
        return new

    move = rng.random()
    if move < 0.25:  # swap
        i, j = rng.randrange(n), rng.randrange(n)
        new[i], new[j] = new[j], new[i]
    elif move < 0.40:  # insert
        i = rng.randrange(n)
        elem = new.pop(i)
        new.insert(rng.randrange(n), elem)
    elif move < 0.50:  # reverse segment (2-opt style)
        i, j = sorted((rng.randrange(n), rng.randrange(n)))
        new[i:j + 1] = reversed(new[i:j + 1])
    else:  # orientation flip
        i = rng.randrange(n)
        part, oi = new[i]
        n_or = len(part.orientations)
        if n_or > 1:
            choices = [k for k in range(n_or) if k != oi]
            new[i] = (part, rng.choice(choices))
    return new


def _calibrate_t0(
    solution: Solution,
    bin_factory: Callable[[], Bin3D],
    rng: random.Random,
    n_probes: int = _AUTO_T0_PROBES,
    p0: float = _AUTO_T0_P0,
) -> float:
    """t0'ı rastgele komşuların enerji-delta dağılımından kestir (R2).

    n_probes rastgele komşu çek, pozitif (yokuş-yukarı) deltaları topla, dön:
        t0 = medyan(pozitif_deltalar) / ln(1/p0)
    böylece medyan yokuş hamlesi başlangıçta p0 olasılıkla kabul edilir.
    Pozitif delta yoksa (tüm problar lokal minimumda) fallback = 3.0 (elle
    kalibre default). Problar rng'yi tüketir → seed verildiğinde deterministik.
    """
    _, cur_bin = decode(solution, bin_factory)
    cur_energy = _energy(cur_bin)
    positive_deltas: List[float] = []
    for _ in range(n_probes):
        candidate = _neighbour(solution, rng)
        _, cand_bin = decode(candidate, bin_factory)
        delta = _energy(cand_bin) - cur_energy
        if delta > 0:
            positive_deltas.append(delta)
    if not positive_deltas:
        return 3.0
    positive_deltas.sort()
    median_delta = positive_deltas[len(positive_deltas) // 2]
    return median_delta / max(-math.log(p0), 1e-9)


@dataclass
class SA3DResult:
    """Outcome of a 3D Simulated Annealing run."""

    placements: List[Placement3D]
    bin3d: Bin3D
    best_height_mm: float
    baseline_height_mm: float           # height of the DBLF starting solution
    best_density: float
    baseline_density: float
    history: List[float] = field(default_factory=list)  # best-so-far height/iter
    iterations: int = 0
    accepted: int = 0


def simulated_annealing_3d(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    *,
    seed: int = 42,
    iterations: int = 600,
    t0: Union[float, str] = 3.0,
    t_min: float = 0.05,
    order_key: Optional[Callable[[VoxelPart], tuple]] = None,
) -> SA3DResult:
    """Minimize bin height by searching (order, orientation) space with SA.

    t0 (sayısal, default 3.0): elle kalibre (2026-06-09; 8 çok sıcaktı). Erken
    yokuş hamlelerini bir voxel katman altında kabul eder; geometrik soğuma son
    adımda t_min'e ulaşır. t0=3.0'ı AÇIKÇA vermek default ile BİREBİR aynı sonuç
    verir (seed'li random.Random garantisi) — numune 181.5 mm rekoru bu yola bağlı.

    t0="auto" (R2): ana döngü ÖNCESİ ilk _AUTO_T0_PROBES rastgele-komşu enerji
    deltasından türetilir (t0 = medyan pozitif delta / ln(1/_AUTO_T0_P0)).
    Problar aynı rng'den çekilir → seed verildiğinde tam deterministik. Sayısal
    t0 davranışı DEĞİŞMEZ (sıcak döngüde yeni dal yok). Best-so-far korunur.
    """
    rng = random.Random(seed)

    # Start from the full DBLF baseline (order + orientation choices).
    # order_key (örn. dblf.plates_first_key) başlangıç sırasını değiştirir;
    # best-so-far korunduğundan SA bu baseline'ın altına asla düşmez.
    base_placements, base_bin = dblf(parts, bin_factory, order_key=order_key)
    by_id = {p.id: p for p in parts}
    current: Solution = [
        (by_id[pl.part_id], pl.orientation_idx) for pl in base_placements
    ]
    baseline_height = base_bin.max_height_mm()
    baseline_density = base_bin.packing_density()

    cur_bin = base_bin
    cur_energy = _energy(cur_bin)

    best = list(current)
    best_bin = cur_bin
    best_energy = cur_energy

    # t0'ı çöz: "auto" ise kalibre et (R2), aksi halde sayısalı aynen kullan.
    # Problar ana döngüden ÖNCE rng'yi tüketir → seed verildiğinde deterministik.
    if t0 == _T0_AUTO:
        t0 = _calibrate_t0(current, bin_factory, rng)
    # Buradan sonra t0 her zaman float.

    cooling = (t_min / t0) ** (1.0 / (iterations - 1)) if iterations > 1 else 1.0
    temperature = t0
    history: List[float] = [best_bin.max_height_mm()]
    accepted = 0

    for _ in range(iterations):
        candidate = _neighbour(current, rng)
        _, cand_bin = decode(candidate, bin_factory)
        cand_energy = _energy(cand_bin)

        delta = cand_energy - cur_energy
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            current, cur_bin, cur_energy = candidate, cand_bin, cand_energy
            accepted += 1
            if cur_energy < best_energy:
                best, best_bin, best_energy = list(current), cur_bin, cur_energy

        temperature *= cooling
        history.append(best_bin.max_height_mm())

    best_placements, best_bin = decode(best, bin_factory)
    return SA3DResult(
        placements=best_placements,
        bin3d=best_bin,
        best_height_mm=best_bin.max_height_mm(),
        baseline_height_mm=baseline_height,
        best_density=best_bin.packing_density(),
        baseline_density=baseline_density,
        history=history,
        iterations=iterations,
        accepted=accepted,
    )

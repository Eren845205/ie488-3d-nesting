"""nesting3d/tuner.py — Instance-Tuner deterministik çekirdeği (APP_YOL_HARITASI §6 Ajan 2).

Genel motor (portfolio) bir örneği çözdükten SONRA, o örneğe özel sabit bir
KONFİG MENÜSÜNÜ deneyip en iyisini seçer.

Arayüz
------
    menu  = build_menu()                           # deterministik konfig menüsü
    tr    = tune(parts, bin_factory,               # → TuneResult
                 budget=200, seed=42)

Güvenlik garantisi (Monoton Kabul)
-----------------------------------
Çıktı height_mm, genel portföy sonucundan (baseline_height_mm) asla KÖTÜ
olamaz.  En iyi = min(baseline, tüm deney sonuçları).  Dolayısıyla tuner,
portföy adımının üzerine ek iyileştirme fırsatı sunar; asla gerileme yaratmaz.

Pluggable menü
--------------
`build_menu()` şimdi deterministik tam-menüyü döndürür.  İleride LLM önerici
aynı arayüze takılır: önerici de aynı imzayı taşıyan bir dict döndürür.
Bkz. `build_menu` docstring.

Motor KODUNU değiştirmez; yalnız solver konfig seçimi yapar.
Pitch / n_orientations değiştirmez (parts ZATEN voxelize edilmiş gelir).

Determinizm
-----------
Aynı (parts, budget, seed) → birebir aynı TuneResult.
- Portfolio adımı: her solver aynı (budget, seed) alır.
- Deney adımı: her konfig sabit parametre + aynı seed ile koşar.
- Konfig listesi sıralı-sabit (dict insertion order, Python 3.7+).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.solvers.ga_solver import GASolver
from src.nesting3d.solvers.portfolio import run_portfolio
from src.nesting3d.solvers.sa_solver import MultiStartSA, SASolver
from src.nesting3d.solvers.tabu_solver import TabuSolver
from src.nesting3d.voxelize import VoxelPart

# ---------------------------------------------------------------------------
# TuneResult
# ---------------------------------------------------------------------------


@dataclass
class TuneResult:
    """Instance-Tuner çıktısı.

    Fields
    ------
    result               : En iyi SolveResult (monoton kabul garantisi ile).
    winning_config_name  : En iyi sonucu veren konfig adı (build_menu() key).
    baseline_height_mm   : Portfolio genel koşusunun en iyi height_mm değeri.
    improvement_mm       : baseline_height_mm - result.height_mm (>= 0).
    all_results          : Menüdeki her konfig için (name, SolveResult) çifti.
    """

    result: SolveResult
    winning_config_name: str
    baseline_height_mm: float
    improvement_mm: float
    all_results: List[tuple] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Konfig menüsü
# ---------------------------------------------------------------------------

_MenuEntry = Dict[str, Any]
_Menu = Dict[str, _MenuEntry]


def build_menu() -> _Menu:
    """Deterministik Instance-Tuner konfig menüsü döndür.

    Her giriş:
        {
            "solver": <Solver örneği>,
            "params": <solve() çağrısında override edilecek dict (boşsa {})>
        }

    "params" içindeki anahtarlar solve(..., **params) olarak geçirilir.
    Şu an desteklenen override'lar: budget, seed (order_key ileride).

    Pluggable tasarım notu
    ----------------------
    Bu fonksiyon şimdi deterministik tam-menüyü döndürür.  İleride LLM
    önerici aynı arayüze takılır: `build_menu(instance_features=None)` imzası
    genişletilir; LLM varyantı aynı dict formatını üretir; çağıran `tune()`
    bundan habersiz çalışır.

    Konfig listesi (voxelize gerektirmeyen, sadece çözücü konfig seçimi):
    1.  baseline        — tam portföy sonucu (dblf + sa + ga + tabu)
    2.  sa_auto         — SA, t0="auto" (adaptif sıcaklık kalibrasyonu)
    3.  sa_3starts      — MultiStartSA, n_starts=3
    4.  sa_5starts      — MultiStartSA, n_starts=5
    5.  dblf_only       — Sadece DBLF (constructive baseline, hızlı)
    6.  ga_only         — Sadece GA (evrimsel arama)
    7.  tabu_only       — Sadece Tabu Search
    """
    return {
        "baseline": {
            "solver": None,  # özel: run_portfolio tüm portföyü çalıştırır
            "params": {},
        },
        "sa_auto": {
            "solver": SASolver(t0="auto"),
            "params": {},
        },
        "sa_3starts": {
            "solver": MultiStartSA(seed_base=1, n_starts=3, t0="auto"),
            "params": {},
        },
        "sa_5starts": {
            "solver": MultiStartSA(seed_base=2, n_starts=5, t0="auto"),
            "params": {},
        },
        "dblf_only": {
            "solver": DBLFSolver(),
            "params": {},
        },
        "ga_only": {
            "solver": GASolver(),
            "params": {},
        },
        "tabu_only": {
            "solver": TabuSolver(),
            "params": {},
        },
    }


# ---------------------------------------------------------------------------
# Yardımcı: tek solver'ı koştur
# ---------------------------------------------------------------------------

def _run_config(
    name: str,
    cfg: _MenuEntry,
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    budget: int,
    seed: int,
) -> SolveResult:
    """Tek bir menü konfigini koştur, SolveResult döndür.

    "baseline" konfig özel durum: tüm portföy (dblf+sa+ga+tabu) koşturulur.
    """
    if name == "baseline":
        pr = run_portfolio(
            parts,
            bin_factory,
            [DBLFSolver(), SASolver(), GASolver(), TabuSolver()],
            budget=budget,
            seed=seed,
        )
        return pr.winner

    solver = cfg["solver"]
    extra: Dict[str, Any] = dict(cfg.get("params", {}))
    # seed ve budget her zaman geçirilir; cfg.params override edebilir
    solve_budget = extra.pop("budget", budget)
    solve_seed = extra.pop("seed", seed)
    return solver.solve(
        parts,
        bin_factory,
        budget=solve_budget,
        seed=solve_seed,
        **extra,
    )


# ---------------------------------------------------------------------------
# Ana arayüz
# ---------------------------------------------------------------------------


def tune(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    *,
    budget: int = 200,
    seed: int = 42,
    menu: _Menu | None = None,
) -> TuneResult:
    """Instance-Tuner: portföy koşur, menüdeki tüm konfigleri dener, en iyiyi seçer.

    Parametreler
    ------------
    parts       : Voxelize edilmiş VoxelPart listesi (pitch sabit, değiştirilmez).
    bin_factory : () -> Bin3D fabrika fonksiyonu.
    budget      : Her konfig için iterasyon sayısı.
    seed        : Tüm konfigler için ortak seed (determinizm garantisi).
    menu        : Opsiyonel özel menü; None ise build_menu() kullanılır.

    Dönüş
    ------
    TuneResult: monoton kabul garantili en iyi sonuç + kazanan konfig adı.

    Monoton kabul
    -------------
    1. "baseline" konfig portföy (dblf+sa+ga+tabu) koşturur → baseline_height.
    2. Menüdeki diğer konfigler denenip sonuçları kıyaslanır.
    3. En iyi = min(tüm konfig sonuçları) (baseline dahil).
    Dolayısıyla çıktı height_mm <= baseline_height_mm garantilidir.
    """
    active_menu = menu if menu is not None else build_menu()

    all_results: List[tuple] = []

    for name, cfg in active_menu.items():
        result = _run_config(name, cfg, parts, bin_factory, budget, seed)
        all_results.append((name, result))

    # baseline_height: "baseline" konfigin sonucu (portföy en iyisi)
    baseline_result = next(
        (r for n, r in all_results if n == "baseline"), None
    )
    if baseline_result is None:
        # Eğer menüde baseline yoksa tüm sonuçların en iyisi baseline kabul edilir
        baseline_result = min((r for _, r in all_results), key=lambda r: r.height_mm)
    baseline_height = baseline_result.height_mm

    # En iyi sonuç: tüm konfigler arasında min(height_mm); eşitlikte ilk gelene öncelik
    best_name, best_result = min(
        all_results,
        key=lambda pair: (pair[1].height_mm, all_results.index(pair)),
    )

    improvement = baseline_height - best_result.height_mm

    return TuneResult(
        result=best_result,
        winning_config_name=best_name,
        baseline_height_mm=baseline_height,
        improvement_mm=improvement,
        all_results=all_results,
    )

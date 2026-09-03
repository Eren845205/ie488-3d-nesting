"""Tests for run3d.py CLI changes (1.6) — --algo portfolio + --solvers flags.

Acceptance criteria (PLAN_DEMO1 §1.6):
  - --algo portfolio is a valid choice (no argparse error)
  - --solvers dblf,sa is a valid flag (no argparse error)
  - Old CLI calls (--algo dblf, --algo sa, no --algo) produce unchanged behaviour
  - _parse_args is backward-compatible: missing --solvers defaults to "dblf,sa"
"""

import pytest

from src.nesting3d.run3d import _parse_args


# ---------------------------------------------------------------------------
# Backward-compatibility: old algo choices still work
# ---------------------------------------------------------------------------


def test_default_algo_is_sa():
    args = _parse_args([])
    assert args.algo == "sa"


def test_algo_dblf_accepted():
    args = _parse_args(["--algo", "dblf"])
    assert args.algo == "dblf"


def test_algo_sa_accepted():
    args = _parse_args(["--algo", "sa"])
    assert args.algo == "sa"


# ---------------------------------------------------------------------------
# New --algo portfolio
# ---------------------------------------------------------------------------


def test_algo_portfolio_accepted():
    """--algo portfolio must not raise."""
    args = _parse_args(["--algo", "portfolio"])
    assert args.algo == "portfolio"


def test_algo_portfolio_default_solvers():
    """When --algo portfolio and no --solvers, the four-solver default is used.

    The default must include all four Demo-1 portfolio solvers: dblf, sa, ga,
    tabu.  test_default_portfolio_solvers_include_ga_and_tabu (below) also
    covers ga and tabu; both tests are kept for explicit coverage of each name.
    """
    args = _parse_args(["--algo", "portfolio"])
    assert hasattr(args, "solvers")
    assert "dblf" in args.solvers
    assert "sa" in args.solvers
    assert "ga" in args.solvers
    assert "tabu" in args.solvers


# ---------------------------------------------------------------------------
# --solvers flag
# ---------------------------------------------------------------------------


def test_solvers_flag_accepted():
    args = _parse_args(["--algo", "portfolio", "--solvers", "dblf,sa"])
    assert args.solvers == "dblf,sa"


def test_solvers_flag_dblf_only():
    args = _parse_args(["--algo", "portfolio", "--solvers", "dblf"])
    assert "dblf" in args.solvers


def test_solvers_flag_ignored_for_non_portfolio():
    """--solvers with --algo sa should not error (flag is always accepted)."""
    args = _parse_args(["--algo", "sa", "--solvers", "sa"])
    assert args.algo == "sa"


def test_invalid_algo_raises():
    """Completely unknown algo must raise SystemExit."""
    with pytest.raises(SystemExit):
        _parse_args(["--algo", "nonexistent_algo"])


def test_unknown_solver_name_raises():
    """--solvers with an unknown name must raise SystemExit with the known list."""
    from src.nesting3d.run3d import run_scenario
    import argparse

    # _parse_args only validates algo/scenario/etc. — unknown solver detection
    # happens inside run_scenario. We simulate that path via a minimal args stub.
    class _Args:
        algo = "portfolio"
        solvers = "nonexistent"
        scenario = "default"
        plate = None
        pitch = None
        margin = None
        voxel_method = None
        rotations = 4
        orient = "flat"
        max_z = 600.0
        seed = 42
        iters = 1
        export_stl = False
        check_clearance = False
        start = "volume"
        out = __import__("pathlib").Path("/tmp/nesting_test_out")

    with pytest.raises(SystemExit, match="nonexistent"):
        run_scenario("default", _Args())


# ---------------------------------------------------------------------------
# Seed + iters forwarding unchanged
# ---------------------------------------------------------------------------


def test_seed_and_iters_still_work():
    args = _parse_args(["--seed", "7", "--iters", "100"])
    assert args.seed == 7
    assert args.iters == 100


def test_portfolio_with_seed_and_iters():
    args = _parse_args(["--algo", "portfolio", "--seed", "99", "--iters", "50"])
    assert args.algo == "portfolio"
    assert args.seed == 99
    assert args.iters == 50


# ---------------------------------------------------------------------------
# §5.3 — ga and tabu accepted in --solvers (acceptance tests)
# ---------------------------------------------------------------------------


def test_solvers_flag_ga_accepted():
    """--solvers ga must parse without error."""
    args = _parse_args(["--algo", "portfolio", "--solvers", "ga"])
    assert "ga" in args.solvers


def test_solvers_flag_tabu_accepted():
    """--solvers tabu must parse without error."""
    args = _parse_args(["--algo", "portfolio", "--solvers", "tabu"])
    assert "tabu" in args.solvers


def test_solvers_flag_all_four_accepted():
    """--solvers dblf,sa,ga,tabu must parse without error."""
    args = _parse_args(["--algo", "portfolio", "--solvers", "dblf,sa,ga,tabu"])
    assert args.solvers == "dblf,sa,ga,tabu"


def test_default_portfolio_solvers_include_ga_and_tabu():
    """Default --solvers must include ga and tabu (§5.3 four-solver portfolio)."""
    args = _parse_args(["--algo", "portfolio"])
    assert "ga" in args.solvers
    assert "tabu" in args.solvers


def test_ga_accepted_in_run_scenario():
    """--solvers ga,tabu must resolve to known solvers in run_scenario.

    Uses the 'stress' scenario with default plate/pitch so parts fit cleanly.
    Budget is kept tiny (4 iterations) so the test runs fast.
    """
    from src.nesting3d.run3d import run_scenario

    class _Args:
        algo = "portfolio"
        solvers = "ga,tabu"
        scenario = "stress"
        plate = None   # use scenario default
        pitch = None
        margin = None
        voxel_method = None
        rotations = 4
        orient = "flat"
        max_z = 600.0
        seed = 42
        iters = 4   # tiny budget — just test the solver name routing
        export_stl = False
        check_clearance = False
        start = "volume"
        out = __import__("pathlib").Path(__import__("tempfile").mkdtemp())

    # Should not raise SystemExit (unknown solver would raise SystemExit)
    rows = run_scenario("stress", _Args())
    solver_names = {r["algo"].replace("portfolio/", "").rstrip("*") for r in rows}
    assert "ga" in solver_names
    assert "tabu" in solver_names

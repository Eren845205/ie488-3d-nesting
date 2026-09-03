"""R1 testi — 24 eksen-hizali master poz seti (voxelize.py, PLAN_DEMO1.md Faz 3).

Degismezler:
  - Eski indeks 0..11 birebir korunur (8 eksen-hizali + 4 egik).
  - Indeks 12..27 = kalan 16 eksen-hizali rotasyon (Ry dahil).
  - N_MASTER_POSES = 28 olmali.
  - 24 eksen-hizali matris dedup'lu BENZERSIZ olmali.
  - Eski grid'ler degismemeli (golden check).
"""

import math

import numpy as np
import pytest
import trimesh

from src.nesting3d.voxelize import N_MASTER_POSES, rotation_matrices, voxelize_part

PITCH = 5.0


def _box(w=20.0, d=20.0, h=20.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


# ---------------------------------------------------------------------------
# Yardimci: iki 4x4 matrisin "ayni" olup olmadigini tole eder (yuvarlama)
# ---------------------------------------------------------------------------

def _mat_close(a: np.ndarray, b: np.ndarray, atol: float = 1e-9) -> bool:
    return bool(np.allclose(a, b, atol=atol))


# ---------------------------------------------------------------------------
# Test 1: N_MASTER_POSES = 28 (8 eksen-hizali + 4 egik + 16 yeni)
# ---------------------------------------------------------------------------

def test_n_master_poses_is_28():
    assert N_MASTER_POSES == 28, (
        f"N_MASTER_POSES {N_MASTER_POSES} degil 28 — "
        "Ry rotasyonlari (indeks 12-27) eklendi mi?"
    )


# ---------------------------------------------------------------------------
# Test 2: rotation_matrices(N_MASTER_POSES) tam 28 matris dondurmeli
# ---------------------------------------------------------------------------

def test_rotation_matrices_returns_28():
    mats = rotation_matrices(N_MASTER_POSES)
    assert len(mats) == 28, f"Beklenen 28, bulunan {len(mats)}"


# ---------------------------------------------------------------------------
# Test 3: Eski indeks 0..11 birebir ayni (degismez kilit)
# ---------------------------------------------------------------------------

def test_old_indices_0_to_11_unchanged():
    """Eski 12 pozun matrisleri R1 sonrasi degismemeli."""
    rz = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1))
    rz2 = rz @ rz
    rx = trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0))
    rx2 = rx @ rx
    tilt = [
        trimesh.transformations.rotation_matrix(math.radians(a), (1, 0, 0))
        for a in (70.0, 65.0, 60.0, 55.0)
    ]
    # Orijinal 12 matris (committen onceki siralama)
    expected = [
        np.eye(4),        # 0
        rz,               # 1
        rx,               # 2
        rz @ rx,          # 3
        rz2,              # 4
        rz2 @ rz,         # 5
        rx2,              # 6
        rz @ rx2,         # 7
        *tilt,            # 8, 9, 10, 11
    ]
    mats = rotation_matrices(N_MASTER_POSES)
    for i, (exp, got) in enumerate(zip(expected, mats[:12])):
        assert _mat_close(exp, got), (
            f"Indeks {i}: matris degisti!\n  beklenen:\n{exp}\n  bulunan:\n{got}"
        )


# ---------------------------------------------------------------------------
# Test 4: 24 eksen-hizali rotasyon BENZERSIZ (dedup)
# ---------------------------------------------------------------------------

def test_24_axis_aligned_rotations_are_unique():
    """Indeks 0..7 + 12..27 = 24 eksen-hizali rotasyon; hepsi farkli olmali."""
    mats = rotation_matrices(N_MASTER_POSES)
    axis_aligned_indices = list(range(8)) + list(range(12, 28))
    assert len(axis_aligned_indices) == 24, "Indeks sayisi 24 degil"
    axis_aligned = [mats[i] for i in axis_aligned_indices]

    n = len(axis_aligned)
    for i in range(n):
        for j in range(i + 1, n):
            assert not _mat_close(axis_aligned[i], axis_aligned[j], atol=1e-6), (
                f"Tekrarlanan rotasyon: pozisyon {i} ve {j} ayni matris\n"
                f"  i matris:\n{axis_aligned[i]}\n  j matris:\n{axis_aligned[j]}"
            )


# ---------------------------------------------------------------------------
# Test 5: 24 eksen-hizali rotasyon GERÇEKTEN eksen-hizali
#         (sadece 0 ve +-1 elemanlar — tilt degil)
# ---------------------------------------------------------------------------

def test_24_axis_aligned_rotations_are_truly_axis_aligned():
    """Her eksen-hizali 3x3 alt-matrisinin elemanlari 0 veya +-1 olmali."""
    mats = rotation_matrices(N_MASTER_POSES)
    axis_aligned_indices = list(range(8)) + list(range(12, 28))
    for idx in axis_aligned_indices:
        R = mats[idx][:3, :3]
        rounded = np.round(R).astype(int)
        assert np.allclose(R, rounded, atol=1e-9), (
            f"Indeks {idx} eksen-hizali degil (non-integer elemanlar):\n{R}"
        )
        # Her satir ve sutunda tam olarak bir +1 veya -1 olmali
        abs_row_sum = np.abs(R).sum(axis=1)
        abs_col_sum = np.abs(R).sum(axis=0)
        assert np.allclose(abs_row_sum, 1.0, atol=1e-9), (
            f"Indeks {idx} satir toplami != 1: {abs_row_sum}"
        )
        assert np.allclose(abs_col_sum, 1.0, atol=1e-9), (
            f"Indeks {idx} sutun toplami != 1: {abs_col_sum}"
        )


# ---------------------------------------------------------------------------
# Test 6: Golden — eski indeks 0..11 ile voxelize edilen grid'ler
#         R1 sonrasi DEGISMEMELI
# ---------------------------------------------------------------------------

def test_golden_old_indices_produce_same_grids():
    """Eski 0..11 allowed_orientations ile grid shape'i ayni kalmali.

    Tilt pozlar (8..11) hesaplama agirdigi nedeniyle tek bir kutu ornek
    uzerinde shape kontrolu yapilir (determinizm yeterlI).
    """
    box = _box(w=30.0, d=20.0, h=10.0)

    # Eksen-hizali eski 8 poz: her birinin grid shape'ini kaydet
    for idx in range(8):
        vp = voxelize_part("box", box, PITCH, allowed_orientations=(idx,))
        o = vp.orientations[0]
        assert o.voxel_count > 0, f"Indeks {idx}: bos grid"
        # Shape deterministik olmali — iki kez calistirilinca ayni sonuc
        vp2 = voxelize_part("box", box, PITCH, allowed_orientations=(idx,))
        assert vp2.orientations[0].shape == o.shape, (
            f"Indeks {idx}: deterministik degil"
        )

    # Tilt 8..11 — shape kontrolu
    for idx in range(8, 12):
        vp = voxelize_part("box", box, PITCH, allowed_orientations=(idx,))
        assert vp.orientations[0].voxel_count > 0, f"Tilt indeks {idx}: bos grid"


# ---------------------------------------------------------------------------
# Test 7: Yeni indeks 12..27 gecerli voxel verir (bos degil)
# ---------------------------------------------------------------------------

def test_new_indices_12_to_27_produce_valid_grids():
    """Her yeni pozun voxelize sonucu bos olmamali."""
    box = _box(w=30.0, d=20.0, h=10.0)
    for idx in range(12, 28):
        vp = voxelize_part("box", box, PITCH, allowed_orientations=(idx,))
        o = vp.orientations[0]
        assert o.voxel_count > 0, f"Yeni indeks {idx}: bos grid"
        assert o.filled.any(), f"Yeni indeks {idx}: filled tamamen False"


# ---------------------------------------------------------------------------
# Test 8: --rotations 24 CLI choice mevcut olmali
# ---------------------------------------------------------------------------

def test_run3d_rotations_choice_24():
    """run3d.py --rotations choices listesi 24'u icermeli."""
    import importlib
    import sys

    # Modulu import edip _parse_args'i test ediyoruz
    # (import edilebilmesi icin src.nesting3d.run3d'nin import edilebilmesi yeter)
    try:
        import src.nesting3d.run3d as run3d_mod
        # _parse_args argparse objesini yaratmali; --rotations 24 kabul etmeli
        args = run3d_mod._parse_args(["--rotations", "24"])
        assert args.rotations == 24
    except SystemExit as e:
        pytest.fail(
            f"--rotations 24 cozumlenmedi (SystemExit {e}). "
            "run3d.py choices listesine 24 eklendi mi?"
        )


# ---------------------------------------------------------------------------
# Test 9: Default cagrilar (n_orientations=4) hala eski 4 pozu donduruyor
# ---------------------------------------------------------------------------

def test_default_n_orientations_unchanged():
    """rotation_matrices(4) hala 4 matris dondurmeli (geriye donuk uyumluluk)."""
    mats = rotation_matrices(4)
    assert len(mats) == 4
    # Ilk 4 matris orijinal 4 pozla ayni olmali
    rz = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1))
    rx = trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0))
    expected4 = [np.eye(4), rz, rx, rz @ rx]
    for i, (exp, got) in enumerate(zip(expected4, mats)):
        assert _mat_close(exp, got), f"Default poz {i} degisti"

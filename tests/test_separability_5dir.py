# -*- coding: utf-8 -*-
"""5-yon sirali sokum metrigi (A2 guncellemesi 2026-07-09, Eren onayi).

Hoca kriteri (b): duz bir dogrultuda cekme yeterli (yana kaydirma dahil).
check_separability_5dir: +Z-tek'te kilitli gorunen ama yandan cikabilen
parca KILIT SAYILMAZ; 5 yonde de cikamayan sayilir.
"""
import numpy as np
import trimesh

from src.nesting3d.accessibility import (check_placements,
                                         check_separability_5dir)
from src.nesting3d.bin3d import Placement3D
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0


def _part(name, w=10.0, d=10.0, h=10.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return voxelize_part(name, b, PITCH, n_orientations=1, method="slice")


def _pl(pid, x, y, z):
    return Placement3D(pid, pid, x, y, z, 0)


def test_serbest_yigin_iki_metrikte_de_temiz():
    # yan yana iki kutu: +Z'de de 5-yonde de 0 kilit
    parts = {p.id: p for p in (_part("a"), _part("b"))}
    pls = [_pl("a", 0, 0, 0), _pl("b", 5, 0, 0)]
    assert check_placements(pls, parts).n_locked == 0
    assert check_separability_5dir(pls, parts).n_locked == 0


# --- kenet fixture'lari: SIRALI sokumde kilit ancak KARSILIKLI kenetle olusur
# (kutu yiginlari her zaman ustten sirayla cozulur — ilk test kurgusu bu
# mekanigi iskaladi). Sahte grid'li parcalar kullanilir (metrik topolojiye
# bakar, baglantililiga bakmaz).

class _FakeOrient:
    def __init__(self, g):
        self.grid = np.asarray(g, dtype=bool)


class _FakePart:
    def __init__(self, g):
        self.orientations = [_FakeOrient(g)]


def _xz_capraz(desen_a=True):
    """2x2x2 grid, y-DEGISMEZ xz-caprazi: A=(x0,z0)+(x1,z1) / B=tamamlayici."""
    g = np.zeros((2, 2, 2), dtype=bool)
    if desen_a:
        g[0, :, 0] = True
        g[1, :, 1] = True
    else:
        g[1, :, 0] = True
        g[0, :, 1] = True
    return g


def test_karsilikli_z_kenedi_yandan_cikar():
    # xz-caprazi cift: +Z'de KARSILIKLI kenet (A, B'nin ustunde VE B, A'nin
    # ustunde) ama desen y-degismez -> +-Y kaymasiyla ayrilir.
    # Eski metrik 2 kilit sayardi; hoca (b) kriteriyle 0 (yana kaydirma).
    parts = {"A": _FakePart(_xz_capraz(True)), "B": _FakePart(_xz_capraz(False))}
    pls = [_pl("A", 0, 0, 0), _pl("B", 0, 0, 0)]
    eski = check_placements(pls, parts)
    yeni = check_separability_5dir(pls, parts)
    assert eski.n_locked == 2          # +Z-tek: karsilikli kenet cozulmez
    assert yeni.n_locked == 0          # +-Y kaymasi kurtarir
    assert set(yeni.removable_order) == {"A", "B"}


def _tam_kenet(desen_a=True):
    """2x2x2 satranc-kenet: satirlar arasi desen degisir -> +-X, +-Y ve +Z'nin
    BESI de karsilikli blokeli (gercek 'cozulmez' kenet)."""
    g = np.zeros((2, 2, 2), dtype=bool)
    if desen_a:
        g[0, 0, 0] = g[1, 0, 1] = True   # y0: (x0,z0)+(x1,z1)
        g[1, 1, 0] = g[0, 1, 1] = True   # y1: ters desen
    else:
        g[1, 0, 0] = g[0, 0, 1] = True
        g[0, 1, 0] = g[1, 1, 1] = True
    return g


def test_tam_kenet_5yonde_de_kilit():
    parts = {"A": _FakePart(_tam_kenet(True)), "B": _FakePart(_tam_kenet(False))}
    pls = [_pl("A", 0, 0, 0), _pl("B", 0, 0, 0)]
    r = check_separability_5dir(pls, parts)
    assert r.n_locked == 2
    kilitli = {pid for grup in r.locked_groups for pid in grup}
    assert kilitli == {"A", "B"}

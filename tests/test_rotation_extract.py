# -*- coding: utf-8 -*-
"""R10 dondurme-sokum sertifikasi (hoca kriteri (c)) testleri.

Kurgu: check_separability_rot yalniz peel TAKILDIGINDA rotasyon dener;
sertifika (eksen, aci, yon, lift) raporlanir. Konservatiflik: sertifika
sound olmali (yanlis-serbest yok) — muhurlu kafes rotasyonla da kilitli
kalmali; slot-kafesindeki cubuk ancak 90 derece cevrilerek cikmali.
"""
import numpy as np

from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.bin3d import Placement3D
from src.nesting3d.rotation_extract import check_separability_rot


class _FakeOrient:
    def __init__(self, g):
        self.grid = np.asarray(g, dtype=bool)


class _FakePart:
    def __init__(self, g):
        self.orientations = [_FakeOrient(g)]


def _pl(pid, x, y, z):
    return Placement3D(pid, pid, x, y, z, 0)


def _slot_kafesi():
    """Ust tavaninda dar SLOT olan kafes + icinde X-yonlu cubuk.

    Cubuk (8x2x2) kafes bosluguna X boyunca yatirilmis; slot (x 6..10)
    yalniz 4 voxel genis -> cubuk duz +Z'de tavana takilir, yanlara
    duvarlara takilir (5-yon KILIT). Z etrafinda 90 derece cevrilirse
    slotun altina hizalanir ve +Z'den cikar (rotasyon sertifikasi).
    Kafes de cubuk icerideyken kilitli (tabani cubugun altinda).
    """
    kafes = np.zeros((16, 16, 7), dtype=bool)
    kafes[1:15, 1:15, 0:7] = True          # dis kutu
    kafes[3:13, 3:13, 1:5] = False         # ic bosluk (10x10x4)
    kafes[6:10, 1:15, 5:7] = False         # tavan slotu (x 6..10, tum y)
    cubuk = np.ones((8, 2, 2), dtype=bool)  # X-yonlu cubuk
    parts = {"cubuk": _FakePart(cubuk), "kafes": _FakePart(kafes)}
    pls = [_pl("cubuk", 4, 7, 1), _pl("kafes", 0, 0, 0)]
    return pls, parts


def test_slot_kafesi_5dir_kilitli_rotasyonla_cozulur():
    pls, parts = _slot_kafesi()
    # (b) metrigi: 5 duz yonde KILIT (cubuk+kafes karsilikli)
    assert check_separability_5dir(pls, parts).n_locked == 2
    # (c) metrigi: cubuk Z-90 ile slottan cikar, kafes pesinden serbest
    r = check_separability_rot(pls, parts)
    assert r.n_locked == 0
    assert set(r.removable_order) == {"cubuk", "kafes"}
    assert list(r.certificates) == ["cubuk"]
    c = r.certificates["cubuk"]
    # 75 derecede cubugun x-izdusumu tam slot genisligine iner (8cos75+2sin75
    # = 4.0) -> 75-90 bandi fiziksel olarak dogru sertifika; kesin 90 sarti
    # bicak-sirti olurdu. Oz: BUYUK Z donusu + ustten (+Z) cikis.
    assert c.eksen == "Z" and abs(c.aci_deg) >= 75.0 and c.yon == "+Z"


def test_muhurlu_kafes_rotasyonla_da_kilitli():
    """Slotsuz (muhurlu) kafes: hicbir donus cikis yaratamaz — sound."""
    kafes = np.zeros((12, 12, 6), dtype=bool)
    kafes[1:11, 1:11, 0:6] = True
    kafes[3:9, 3:9, 1:4] = False           # ic bosluk, tavan kapali
    kutu = np.ones((2, 2, 2), dtype=bool)
    parts = {"kutu": _FakePart(kutu), "kafes": _FakePart(kafes)}
    pls = [_pl("kutu", 5, 5, 1), _pl("kafes", 0, 0, 0)]
    assert check_separability_5dir(pls, parts).n_locked == 2
    r = check_separability_rot(pls, parts)
    assert r.n_locked == 2
    assert r.certificates == {}
    assert r.locked_groups and set(r.locked_groups[0]) == {"kutu", "kafes"}


def test_serbest_sahne_5dir_ile_ozdes_ve_sertifikasiz():
    """Kilitsiz sahnede rot asamasi hic devreye girmez (bit-davranis)."""
    a = np.ones((3, 3, 3), dtype=bool)
    parts = {"a": _FakePart(a), "b": _FakePart(a)}
    pls = [_pl("a", 0, 0, 0), _pl("b", 10, 0, 0)]
    r5 = check_separability_5dir(pls, parts)
    rr = check_separability_rot(pls, parts)
    assert r5.n_locked == 0 and rr.n_locked == 0
    assert rr.certificates == {}
    assert set(rr.removable_order) == set(r5.removable_order)


def test_buyuk_parca_muafiyeti_konservatif():
    """max_grid_vox'u asan kilitli parca rotasyon DENEMEZ, kilitli kalir
    (konservatif taraf) ve raporda isaretlenir."""
    pls, parts = _slot_kafesi()
    r = check_separability_rot(pls, parts, max_grid_vox=4)
    # cubuk (8 voxel) da kafes (16) de muaf -> kimse rotasyonla acilamaz
    assert r.n_locked == 2
    assert r.certificates == {}
    assert "cubuk" in r.skipped_large

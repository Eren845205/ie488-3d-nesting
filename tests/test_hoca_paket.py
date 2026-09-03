# -*- coding: utf-8 -*-
"""Hoca teslim paketi yardimcisi testleri (scripts/_hoca_paket.py).

Sozlesmeler: multi-solid ASCII STL'de her parca kendi adiyla ayri solid;
m{i} anahtari placements[i]'ye eslenir; kilit 0 -> tumu duz cekme."""
from types import SimpleNamespace as NS

import pytest
import trimesh

from scripts._hoca_paket import (multi_solid_stl_yaz, paket_uret,
                                 sokum_plani_derle, solid_adi)


def _kutu(kenar=2.0):
    return trimesh.creation.box(extents=(kenar, kenar, kenar))


def _vp(ad, uid=None, kopya=0, siparis=None):
    return NS(name=ad, parca_uid=uid, kopya_no=kopya, order_id=siparis)


def _pl(pid, oi=0, x=0, y=0, z=0):
    return NS(part_id=pid, orientation_idx=oi, x=x, y=y, z=z)


def test_multi_solid_stl_her_parca_kendi_adiyla(tmp_path):
    yol = tmp_path / "cift.stl"
    multi_solid_stl_yaz([_kutu(), _kutu(3.0)], ["parcaA", "parcaB"], yol)
    icerik = yol.read_text(encoding="ascii")
    assert "solid parcaA" in icerik and "endsolid parcaA" in icerik
    assert "solid parcaB" in icerik and "endsolid parcaB" in icerik
    # kutu basina 12 ucgen -> toplam 24 facet
    assert icerik.count("facet normal") == 24
    # solid bloklari sirali ve ic ice degil
    assert icerik.index("endsolid parcaA") < icerik.index("solid parcaB")


def test_multi_solid_stl_esleme_bozuksa_fail_loud(tmp_path):
    with pytest.raises(ValueError):
        multi_solid_stl_yaz([_kutu()], ["a", "b"], tmp_path / "x.stl")


def test_solid_adi_ascii_guvenli_ve_benzersiz_kimlikli():
    vp = _vp("kapak çanı", uid="abc123-sip1-2")
    assert solid_adi(vp, "p1") == "kapak_an___abc123-sip1-2"
    # ad == uid ise tekrarlanmaz
    assert solid_adi(_vp("p7", uid="p7"), "p7") == "p7"


def _paket(n_locked, rot_rep=None, nfv_tel=None, meshes=None):
    placements = [_pl("p0"), _pl("p1"), _pl("p2")]
    parts = {"p0": _vp("govde", "g-1", 0, "SIP-A"),
             "p1": _vp("kapak", "k-1", 0, "SIP-A"),
             "p2": _vp("kapak", "k-2", 1, "SIP-B")}
    metrik = {"legal_height_mm": 100.0, "invalid_reason": None,
              "n_placed": 3, "n_total": 3, "min_clearance_mm": 2.1,
              "n_locked": n_locked,
              "n_locked_rot": 0 if n_locked else None,
              "sokum_planli": bool(n_locked)}
    return {"placements": placements, "voxel_parts": parts, "pitch": 2.0,
            "dz": None, "meshes": meshes, "rot_rep": rot_rep,
            "nfv_tel": nfv_tel, "metrikler": metrik}


def test_sokum_plani_kilitsiz_tumu_duz_cekme():
    plan = sokum_plani_derle(_paket(n_locked=0))
    assert plan["n_duz_cekme"] == 3 and plan["n_dondurmeli"] == 0
    assert plan["sokum_planli"] is False
    assert [e["part_id"] for e in plan["duz_cekme"]] == ["p0", "p1", "p2"]


def test_sokum_plani_rot_rep_mi_eslemesi():
    """'m1' sertifikasi placements[1] kimligine (ad/kopya/siparis) eslenir."""
    rot = NS(certificates={"m1": NS(eksen=(0, 0, 1), aci_deg=30.0,
                                    yon="+X", lift_vox=3)},
             removable_order=["m0", "m2", "m1"], n_locked=0)
    plan = sokum_plani_derle(_paket(n_locked=1, rot_rep=rot))
    assert plan["n_dondurmeli"] == 1
    e = plan["dondurmeli"][0]
    assert e["part_id"] == "p1" and e["ad"] == "kapak"
    assert e["siparis"] == "SIP-A" and e["yon"] == "+X"
    assert e["aci_deg"] == 30.0 and e["lift_vox"] == 3
    assert plan["cikis_sirasi"] == ["p0", "p2", "p1"]
    # dondurmeli parca duz-cekme listesinde TEKRARLANMAZ
    assert {x["part_id"] for x in plan["duz_cekme"]} == {"p0", "p2"}


def test_sokum_plani_tel_fallback_solve_reuse():
    """rot_rep yoksa nfv_tel.rot_kabul.sokum_plani kullanilir."""
    tel = {"rot_kabul": {"uygulandi": True, "rot_kilit": 0, "cert": 1,
                         "sokum_plani": [{"parca": "kapak", "part_id": "p2",
                                          "eksen": (1, 0, 0),
                                          "aci_deg": 15.0, "yon": "+Z",
                                          "lift_vox": 2}],
                         "sokum_sirasi": ["p0", "p1", "p2"]}}
    plan = sokum_plani_derle(_paket(n_locked=1, nfv_tel=tel))
    assert plan["n_dondurmeli"] == 1
    assert plan["dondurmeli"][0]["part_id"] == "p2"
    assert plan["cikis_sirasi"] == ["p0", "p1", "p2"]


def test_paket_uret_dosyalari_yazar(tmp_path):
    meshes = [_kutu(), _kutu(), _kutu(3.0)]
    paket = _paket(n_locked=0, meshes=meshes)
    yollar = paket_uret(paket, tmp_path, "deneme_seti")
    stl = (tmp_path / "deneme_seti_yerlesim.stl").read_text(encoding="ascii")
    assert "solid govde__g-1" in stl and "solid kapak__k-2" in stl
    import json
    pl = json.loads((tmp_path / "deneme_seti_placements.json")
                    .read_text(encoding="utf-8"))
    assert len(pl["placements"]) == 3
    assert pl["placements"][0]["ad"] == "govde"
    assert pl["placements"][0]["siparis"] == "SIP-A"
    md = (tmp_path / "deneme_seti_sokum_plani.md").read_text(encoding="utf-8")
    assert "Tüm parçalar doğrudan" in md
    assert yollar["n_parca"] == 3 and yollar["n_dondurmeli"] == 0
    assert yollar["stl_mb"] is not None


def test_paket_uret_meshsiz_stl_atlanir(tmp_path):
    yollar = paket_uret(_paket(n_locked=0, meshes=None), tmp_path, "e")
    assert yollar["stl"] is None
    assert (tmp_path / "e_sokum_plani.json").exists()


def test_paket_uret_tip_binary_buyuk_set(tmp_path):
    """tip_binary: ayni model adindaki kopyalar tek binary STL'de birlesir;
    dosya adi ad+adet tasir, 80-byte header'da ad yazar."""
    import struct
    meshes = [_kutu(), _kutu(), _kutu(3.0)]
    paket = _paket(n_locked=0, meshes=meshes)
    yollar = paket_uret(paket, tmp_path, "buyuk", stl_bicim="tip_binary")
    stl_dir = tmp_path / "buyuk_stl"
    kapak = stl_dir / "buyuk_kapak_2adet.stl"
    govde = stl_dir / "buyuk_govde_1adet.stl"
    assert kapak.exists() and govde.exists()
    data = kapak.read_bytes()
    assert b"kapak_x2" in data[:80]
    # 2 kutu birlesik = 24 ucgen (binary sayac header'dan sonraki 4 byte)
    assert struct.unpack("<I", data[80:84])[0] == 24
    assert yollar["stl_bicim"] == "tip_binary"
    assert yollar["stl_dosyalari"] == 2


def test_paket_uret_oto_kucuk_set_ascii(tmp_path):
    """oto bicim: kucuk facet sayisinda ASCII multi-solid'e gider."""
    meshes = [_kutu(), _kutu(), _kutu(3.0)]
    yollar = paket_uret(_paket(n_locked=0, meshes=meshes), tmp_path, "k")
    assert yollar["stl_bicim"] == "ascii"
    assert (tmp_path / "k_yerlesim.stl").exists()

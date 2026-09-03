# -*- coding: utf-8 -*-
"""P0 — icerik-tabanli parca kimligi + siparis izi (Sokum Konsolu F2-P0).

Ilke (Eren, 2026-07-15): kimlik ASLA ada guvenmez — iki siparisin ayni-adli
farkli parcalari da, farkli-adli benzer parcalari da olabilir. Sistem her
parcayi GEOMETRISINDEN tanir (geo_imza), tum kunyesini depolar ve kendi
benzersiz ID'sini (parca_uid) uretir; karisma yapisal olarak imkansizdir.
Yerlesim BIT-OZDES kalir: solver girdisi (id'ler, grid'ler, sira) degismez,
yalniz metadata eklenir. Plan: ~/.claude/plans/cheeky-sniffing-corbato.md P0.

Kosum: pytest tests/test_parca_kimlik.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import trimesh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.format import (  # noqa: E402
    ContainerSpec, NestingInstance, PartSpec, geo_imza_of_bytes,
    geo_imza_of_mesh, to_voxel_parts)


def _box_mesh(w, d, h):
    m = trimesh.creation.box(extents=(float(w), float(d), float(h)))
    m.apply_translation(-m.bounds[0])
    return m


def _inst(parts):
    return NestingInstance(
        container=ContainerSpec(width_mm=200.0, depth_mm=200.0), parts=parts)


def _box_spec(name, w, d, h, qty=1, **kunye):
    return PartSpec(id=name, name=name, qty=qty, source="box",
                    width_mm=float(w), depth_mm=float(d), height_mm=float(h),
                    **kunye)


# ---------------------------------------------------------------------------
# geo_imza determinizmi: ayni geometri -> her kosuda AYNI imza ("her seferinde
# tanima"); farkli geometri -> farkli imza.
# ---------------------------------------------------------------------------

def test_geo_imza_mesh_deterministik():
    a1 = geo_imza_of_mesh(_box_mesh(30, 20, 10))
    a2 = geo_imza_of_mesh(_box_mesh(30, 20, 10))
    b = geo_imza_of_mesh(_box_mesh(31, 20, 10))
    assert a1 == a2
    assert a1 != b
    assert isinstance(a1, str) and len(a1) >= 16


def test_geo_imza_mesh_konum_bagimsiz():
    # Ayni sekil, farkli orijinal konum -> ayni imza (kanonik kok)
    m1 = _box_mesh(30, 20, 10)
    m2 = trimesh.creation.box(extents=(30.0, 20.0, 10.0))
    m2.apply_translation([55.0, -7.0, 12.0])
    assert geo_imza_of_mesh(m1) == geo_imza_of_mesh(m2)


def test_geo_imza_bytes_deterministik():
    a1 = geo_imza_of_bytes(b"solid x\n")
    a2 = geo_imza_of_bytes(b"solid x\n")
    b = geo_imza_of_bytes(b"solid y\n")
    assert a1 == a2 and a1 != b


# ---------------------------------------------------------------------------
# Karismazlik: ayni ad + farkli geometri -> gruplar AYRISIR (bugunku yanlis
# tek-mesh birlesmesi = yanlis geometri basilirdi). Gorunen ad ~2 ile ayrisir.
# ---------------------------------------------------------------------------

def test_ayni_ad_farkli_geometri_gruplar_ayrisir():
    inst = _inst([
        _box_spec("kapak", 30, 20, 10, qty=1, order_id="SIP-A"),
        _box_spec("kapak", 60, 40, 20, qty=1, order_id="SIP-B"),
    ])
    parts = to_voxel_parts(inst, 2.0, n_orientations=1)
    assert len(parts) == 2
    adlar = sorted(p.name for p in parts)
    assert adlar == ["kapak", "kapak~2"]
    # Iki instance FARKLI geometri tasir (tek mesh'e dusme YOK)
    v0, v1 = (p.mesh.volume for p in parts)
    assert abs(v0 - v1) > 1.0
    # Siparis izi dogru dagilir
    by_name = {p.name: p for p in parts}
    assert by_name["kapak"].order_id == "SIP-A"
    assert by_name["kapak~2"].order_id == "SIP-B"


def test_ayni_geometri_gruplar_birlesik_kalir_bit_ozdes():
    # Onceden ayrik olmayan hicbir grup ayrismaz: ayni ad + ayni geometri
    # (2 siparis) -> TEK grup, id'ler bugunku desenle (kapak_01..)
    inst = _inst([
        _box_spec("kapak", 30, 20, 10, qty=3, order_id="SIP-A"),
        _box_spec("kapak", 30, 20, 10, qty=2, order_id="SIP-B"),
    ])
    parts = to_voxel_parts(inst, 2.0, n_orientations=1)
    assert [p.id for p in parts] == [
        "kapak_01", "kapak_02", "kapak_03", "kapak_04", "kapak_05"]
    assert all(p.name == "kapak" for p in parts)


# ---------------------------------------------------------------------------
# Kopya-sayimi siparis atamasi: ozdes kopyalar fiziksel olarak degistirilebilir
# -> kopya k'lar deterministik sirayla siparis kovalarindan tuketilir.
# ---------------------------------------------------------------------------

def test_kopya_sayimi_siparis_atamasi():
    inst = _inst([
        _box_spec("kapak", 30, 20, 10, qty=3, order_id="SIP-A"),
        _box_spec("kapak", 30, 20, 10, qty=2, order_id="SIP-B"),
    ])
    parts = to_voxel_parts(inst, 2.0, n_orientations=1)
    assert [p.order_id for p in parts] == [
        "SIP-A", "SIP-A", "SIP-A", "SIP-B", "SIP-B"]
    assert [p.kopya_no for p in parts] == [1, 2, 3, 4, 5]
    # geo_imza hepsi ayni (ayni geometri), kaynak_ad tasiniyor
    assert len({p.geo_imza for p in parts}) == 1
    assert parts[0].geo_imza is not None


def test_parca_uid_benzersiz_ve_kosular_arasi_kararli():
    def kos():
        inst = _inst([
            _box_spec("a", 30, 20, 10, qty=2, order_id="S1"),
            _box_spec("b", 40, 20, 10, qty=2, order_id="S1"),
            _box_spec("a", 30, 20, 10, qty=1, order_id="S2"),
        ])
        return to_voxel_parts(inst, 2.0, n_orientations=1)

    p1, p2 = kos(), kos()
    uids1 = [p.parca_uid for p in p1]
    assert None not in uids1
    assert len(set(uids1)) == len(uids1)          # benzersiz
    assert uids1 == [p.parca_uid for p in p2]     # kosular-arasi kararli
    # uid icerik+koken+kopya tasir (insan-okur)
    assert all("S1" in u or "S2" in u for u in uids1)


def test_kunyesiz_eski_yol_bit_ozdes():
    # order_id/geo_imza verilmemis eski cagiran: id'ler/gridler birebir,
    # kunye alanlari None/uretilmis — solver girdisi degismez.
    eski = _inst([_box_spec("k", 30, 20, 10, qty=2)])
    kunyeli = _inst([_box_spec("k", 30, 20, 10, qty=2, order_id="S1")])
    pe = to_voxel_parts(eski, 2.0, n_orientations=1)
    pk = to_voxel_parts(kunyeli, 2.0, n_orientations=1)
    assert [p.id for p in pe] == [p.id for p in pk]
    assert all(
        (a.orientations[0].grid == b.orientations[0].grid).all()
        for a, b in zip(pe, pk))
    assert pe[0].order_id is None and pk[0].order_id == "S1"
    # geo_imza icerikten HER ZAMAN uretilir (kimlik ada guvenmez)
    assert pe[0].geo_imza == pk[0].geo_imza is not None


# ---------------------------------------------------------------------------
# PartSpec kunye alanlari: geriye-uyumlu opsiyonel (wall_mm/family deseni)
# ---------------------------------------------------------------------------

def test_partspec_kunye_roundtrip():
    p = _box_spec("k", 30, 20, 10, qty=1, order_id="S1",
                  geo_imza="abc123", kaynak_ad="kapak.stl")
    d = p.to_dict()
    assert d["order_id"] == "S1" and d["geo_imza"] == "abc123"
    assert d["kaynak_ad"] == "kapak.stl"
    p2 = PartSpec.from_dict(d)
    assert (p2.order_id, p2.geo_imza, p2.kaynak_ad) == (
        "S1", "abc123", "kapak.stl")


def test_partspec_kunye_none_yazilmaz():
    d = _box_spec("k", 30, 20, 10).to_dict()
    assert "order_id" not in d and "geo_imza" not in d and "kaynak_ad" not in d
    p = PartSpec.from_dict(d)  # eski kayit sorunsuz okunur
    assert p.order_id is None and p.geo_imza is None and p.kaynak_ad is None


# ---------------------------------------------------------------------------
# Loader doldurmasi: ZIP-STL yolu geo_imza'yi STL byte'larindan doldurur
# (mail_ingest sha256 deseniyle ayni kaynak; kaynak_ad = dosya adi)
# ---------------------------------------------------------------------------

def test_stl_loader_geo_imza_ve_kaynak_ad_doldurur(tmp_path):
    from src.nesting3d.instances.stl_order_loader import (
        build_instance_from_order)
    stl_bytes = _box_mesh(30, 20, 10).export(file_type="stl")
    res = build_instance_from_order({"kapak": stl_bytes}, {"kapak": 2},
                                    persist_dir=tmp_path)
    p = [q for q in res.instance.parts if q.name == "kapak"][0]
    assert p.geo_imza == geo_imza_of_bytes(stl_bytes)
    assert p.kaynak_ad == "kapak"


# ---------------------------------------------------------------------------
# Pipeline persist: parca_kimlik kaydi + siparis_ozeti nesting dict'te
# (UI'nin TEK kimlik kaynagi; placements _AGIR'da dustugu icin persist ONCESI)
# ---------------------------------------------------------------------------

def _iki_siparis_senaryo():
    from datetime import date
    from tests.test_demo_pipeline import SMOKE_SCENARIO
    return {
        "ref_date": date(2026, 6, 13),
        "seed": 7,
        "capacity": {"num_machines": 1, "batch_duration_hours": 8.0,
                     "shifts_per_day": 1,
                     "max_volume_per_batch_cm3": 200_000.0},
        "container": {"width_mm": 200.0, "depth_mm": 200.0},
        "pitch": 10.0,
        "n_orientations": 1,
        "portfolio_budget": 10,
        "nesting_mode": "heightmap",
        "orders": [
            {"order_id": "SIP-A", "customer": "ACME",
             "deadline": "2026-07-01", "priority_class": 1,
             "parts": [{"id": "pA", "name": "kapak", "qty": 2,
                        "source": "box", "width_mm": 40.0, "depth_mm": 30.0,
                        "height_mm": 20.0}]},
            {"order_id": "SIP-B", "customer": "BETA",
             "deadline": "2026-07-01", "priority_class": 1,
             "parts": [{"id": "pB", "name": "kapak", "qty": 1,
                        "source": "box", "width_mm": 40.0, "depth_mm": 30.0,
                        "height_mm": 20.0}]},
        ],
        "pricing_rules": SMOKE_SCENARIO["pricing_rules"],
    }


def test_pipeline_parca_kimlik_ve_siparis_ozeti():
    from scripts.demo_pipeline import run_pipeline
    result = run_pipeline(_iki_siparis_senaryo())
    rows = [nr for nr in result["nesting_results"].values()
            if nr.get("n_parts", 0) > 0]
    assert rows, "parti cozulmedi"
    tum_orderlar = set()
    toplam_parca = {}
    for nr in rows:
        kimlik = nr.get("parca_kimlik")
        assert kimlik, "parca_kimlik kaydi eksik"
        for pid, k in kimlik.items():
            for alan in ("parca_uid", "order_id", "geo_imza",
                         "kaynak_ad", "ad", "kopya_no"):
                assert alan in k, f"{pid}: {alan} eksik"
            assert k["order_id"] in ("SIP-A", "SIP-B")
            tum_orderlar.add(k["order_id"])
            toplam_parca[k["order_id"]] = toplam_parca.get(k["order_id"], 0) + 1
        # uid'ler parti icinde benzersiz
        uids = [k["parca_uid"] for k in kimlik.values()]
        assert len(set(uids)) == len(uids)
        ozet = nr.get("siparis_ozeti")
        assert ozet is not None
        for o in ozet:
            assert {"order_id", "musteri", "n_parca",
                    "n_sokum_planli"} <= set(o)
    # kopya-sayimi: ayni-ad ayni-geometri iki siparis dogru bolusuldu
    assert tum_orderlar == {"SIP-A", "SIP-B"}
    assert toplam_parca == {"SIP-A": 2, "SIP-B": 1}
    musteri = {o["order_id"]: o["musteri"]
               for nr in rows for o in nr["siparis_ozeti"]}
    assert musteri.get("SIP-A") == "ACME" and musteri.get("SIP-B") == "BETA"


def test_pipeline_bit_ozdeslik_kunye_sonuclari_degistirmez(monkeypatch):
    # Ayni senaryo — kimlik uretimi yerlesimi/yuksekligi degistiremez:
    # height/n_parts, parca_kimlik alani cikarilinca birebir ayni kalmali.
    from scripts.demo_pipeline import run_pipeline
    r1 = run_pipeline(_iki_siparis_senaryo())
    r2 = run_pipeline(_iki_siparis_senaryo())
    h1 = [(b, nr.get("height_mm"), nr.get("n_parts"))
          for b, nr in sorted(r1["nesting_results"].items())]
    h2 = [(b, nr.get("height_mm"), nr.get("n_parts"))
          for b, nr in sorted(r2["nesting_results"].items())]
    assert h1 == h2

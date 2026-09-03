"""dz export kablosu — R11/rot-kabul mesh-duzeyi dusme musteri STL/GLB'sine yansir.

Ships-dark serhinin kapanisi (K-50 kablosu R11 kazancini telemetriye yaziyordu
ama musteriye giden dosya voxel yerlesiminde kaliyordu). Kabul kriterleri:

  1. placed_meshes(dz=...): parca i, dz[i] kadar asagi iner (yalniz dz>0;
     apply_dz semantigiyle ayni); dz=None BIT-OZDES eski davranis; uzunluk
     uyusmazligi ValueError (fail-loud — sessiz hizasizlik illegal STL uretir).
  2. build_result_scene: normal VE instanced (merge_by_type=True) yollarin
     ikisi de dz'yi uygular (instanced yol dugum matrisinde tasir).
  3. export_scene(dz=...): STL dosyasinin olculen max-z'si dz kadar iner.
  4. Pipeline: r11 uygulanirsa nesting_results[bid]["r11_dz"] yazilir ve
     placements ile ayni uzunluktadir.
  5. App kalicilastirma: r11_dz'li kayit GLB'ye dz uygulanarak yazilir; STL
     indirme rotasi tam-detay GLB'den turedigi icin ayni dusmeyi tasir;
     detay JSON r11_dz'yi denetim izi olarak korur.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Placement3D
from src.nesting3d.export_stl import (build_result_scene, export_scene,
                                      placed_meshes)
from src.nesting3d.voxelize import voxelize_part


def _vox_box(pid, w=20.0, d=20.0, h=10.0, pitch=2.0):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2, d / 2, h / 2])
    return voxelize_part(pid, m, pitch, n_orientations=1, margin=0,
                         z_dilate=0, rot_matrices=[np.eye(4)], method="slice")


def _sahne(pitch=2.0):
    """Iki kutu: biri tabanda, digeri z=10 hucre (20mm) yukarida."""
    parts = {"a": _vox_box("a"), "b": _vox_box("b")}
    pls = [Placement3D("a", "a", 0, 0, 0, 0),
           Placement3D("b", "b", 0, 0, 10, 0)]
    return pls, parts, pitch


# ---------- placed_meshes ----------

def test_placed_meshes_dz_indirir():
    pls, parts, pitch = _sahne()
    base = placed_meshes(pls, parts, pitch)
    kayik = placed_meshes(pls, parts, pitch, dz=[0.0, 5.0])
    assert np.allclose(kayik[0].bounds, base[0].bounds)          # dz=0 -> ayni
    assert np.isclose(base[1].bounds[1][2] - kayik[1].bounds[1][2], 5.0)
    assert np.isclose(base[1].bounds[0][2] - kayik[1].bounds[0][2], 5.0)


def test_placed_meshes_dz_none_bit_ozdes():
    pls, parts, pitch = _sahne()
    a = placed_meshes(pls, parts, pitch)
    b = placed_meshes(pls, parts, pitch, dz=None)
    for ma, mb in zip(a, b):
        assert np.allclose(ma.vertices, mb.vertices)


def test_placed_meshes_dz_negatif_uygulanmaz():
    # apply_dz sozlesmesi: yalniz d>0 asagi ceker; negatif deger YUKARI itmez
    pls, parts, pitch = _sahne()
    base = placed_meshes(pls, parts, pitch)
    kayik = placed_meshes(pls, parts, pitch, dz=[-3.0, 0.0])
    assert np.allclose(kayik[0].bounds, base[0].bounds)


def test_placed_meshes_dz_uzunluk_uyusmazligi_hata():
    pls, parts, pitch = _sahne()
    with pytest.raises(ValueError):
        placed_meshes(pls, parts, pitch, dz=[1.0])


# ---------- build_result_scene ----------

def test_scene_dz_normal_yol():
    pls, parts, pitch = _sahne()
    s0 = build_result_scene(pls, parts, pitch=pitch)
    s1 = build_result_scene(pls, parts, pitch=pitch, dz=[0.0, 5.0])
    assert np.isclose(s0.bounds[1][2] - s1.bounds[1][2], 5.0)


def test_scene_dz_instanced_yol():
    pls, parts, pitch = _sahne()
    s0 = build_result_scene(pls, parts, pitch=pitch, merge_by_type=True)
    s1 = build_result_scene(pls, parts, pitch=pitch, merge_by_type=True,
                            dz=[0.0, 5.0])
    assert np.isclose(s0.bounds[1][2] - s1.bounds[1][2], 5.0)


def test_scene_dz_uzunluk_uyusmazligi_hata():
    pls, parts, pitch = _sahne()
    with pytest.raises(ValueError):
        build_result_scene(pls, parts, pitch=pitch, merge_by_type=True,
                           dz=[1.0, 2.0, 3.0])


# ---------- export_scene (STL) ----------

def test_export_scene_dz_stl(tmp_path):
    pls, parts, pitch = _sahne()
    p0 = export_scene(pls, parts, pitch, tmp_path / "duz.stl")
    p1 = export_scene(pls, parts, pitch, tmp_path / "kayik.stl", dz=[0.0, 5.0])
    m0 = trimesh.load(p0)
    m1 = trimesh.load(p1)
    assert np.isclose(m0.bounds[1][2] - m1.bounds[1][2], 5.0)


# ---------- pipeline kablosu ----------

def test_pipeline_r11_dz_kablosu(monkeypatch):
    import src.nesting3d.continuous_settle as cs
    from tests.test_demo_pipeline import SMOKE_SCENARIO
    from scripts.demo_pipeline import run_pipeline

    def fake_r11(meshes, **kw):
        return {"dz": [0.25] * len(meshes), "height_mm": 1.0,
                "height_before_mm": 1.25, "kazanc_mm": 0.25,
                "min_clearance_mm": 2.5, "kilit_pre": 0, "kilit_post": 0,
                "rafine_tur": 1}

    monkeypatch.setattr(cs, "uretim_r11", fake_r11)
    result = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv"})
    bulundu = False
    for nr in result["nesting_results"].values():
        if nr.get("r11_dz"):
            bulundu = True
            assert len(nr["r11_dz"]) == len(nr["placements"])
            assert all(float(d) == 0.25 for d in nr["r11_dz"])
    assert bulundu, "hicbir partide r11_dz yok — kablo kopuk"


# ---------- app kalicilastirma + STL rotasi ----------

@pytest.fixture
def app_with_llm():
    from tests.test_gecmis_detay_tam import _make_provider_with_teklif
    from src.webapp.app import create_app
    return create_app(testing=True,
                      llm_provider_override=_make_provider_with_teklif())


def test_detay_glb_ve_stl_dz_uygulanir(app_with_llm):
    pls, parts, pitch = _sahne()
    beklenen = placed_meshes(pls, parts, pitch, dz=[0.0, 5.0])
    beklenen_zmax = max(float(m.bounds[1][2]) for m in beklenen)

    fn = app_with_llm.config["GECMIS_KAYDET_FN"]
    nr = {"height_mm": 30.0, "density": 0.5, "n_parts": 2, "pitch_mm": pitch,
          "placements": pls, "voxel_parts": parts, "r11_dz": [0.0, 5.0]}
    kayit = fn({"ranked_orders": [], "batches": [],
                "nesting_results": {"B001": nr},
                "pricing_results": {}, "elapsed_sec": 0.0},
               mod="auto", kaynak="manuel")[0]

    store = app_with_llm.config["OTONOM_GECMIS"]

    # 1) Kalici GLB dz'li
    glb_p = store.glb_path(kayit["id"], "B001")
    assert glb_p is not None
    scene = trimesh.load(io.BytesIO(glb_p.read_bytes()), file_type="glb")
    assert np.isclose(float(scene.bounds[1][2]), beklenen_zmax, atol=1e-3)

    # 2) STL indirme GLB'den turedigi icin ayni dusmeyi tasir
    client = app_with_llm.test_client()
    resp = client.get(f"/gecmis/{kayit['id']}/stl/B001")
    assert resp.status_code == 200
    stl = trimesh.load(io.BytesIO(resp.data), file_type="stl")
    assert np.isclose(float(stl.bounds[1][2]), beklenen_zmax, atol=1e-3)

    # 3) Detay JSON denetim izi olarak r11_dz'yi korur
    detay = store.detay_get(kayit["id"])
    assert detay["nesting_results"]["B001"]["r11_dz"] == [0.0, 5.0]

"""Rot-kabul katmani — kilit reddi yerine rot-sokum sorgusu (hoca 2026-07-14).

Hoca kriteri: gercek red sebebi yalniz yapisma + CIKARILAMAYAN ic-ice;
"zor cikan ama cikabilen" ihmal edilebilir. Kabul kriterleri:

  1. uretim_r11(rot_kabul=False, default) BIT-OZDES: kilit artisi -> None.
  2. uretim_r11(rot_kabul=True): kilit artisi + rot kilit=0 -> sokum-planli
     KABUL (dict'te sokum_planli/rot_kilit/rot_cert); rot kilit>0 -> None;
     rot denetimi exception -> None (tek-tarafli sozlesme bozulmaz).
  3. Kilit artmadiysa rot denetimi HIC cagrilmaz (maliyet: K-42 dersi).
  4. solve_nfv_kalite(rot_kabul=...): False -> tel'de anahtar yok + eski akis;
     True + ham kilitli + rot kilit=0 -> guard ATLANIR (vergi odenmez), ham
     sokum-planli secilir; rot kilit>0 / hata / kilit-bilinmiyor -> guard eski
     gibi kosulur; "auto" -> parca tavani ustunde atlanir (iz birakir).
  5. check_separability_rot erode_clearance_vox'u int kabul eder (K-52 dersi:
     ciplak 2, _ensure_eroded unpack'inde TypeError'du -> normalize edilir).
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pytest
import trimesh

from src.nesting3d.continuous_settle import kilit_rot_meshes, uretim_r11
from src.nesting3d.nfv_solve import (
    R11_AUTO_PARCA_TAVANI, ROT_KABUL_AUTO_PARCA_TAVANI, solve_nfv_kalite)
from src.nesting3d.rotation_extract import (RotSeparabilityReport,
                                            check_separability_rot)


def _box(w, d, h, at=(0.0, 0.0, 0.0)):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2 + at[0], d / 2 + at[1], h / 2 + at[2]])
    return m


def _kule():
    """Kazancli sahne (test_r11_uretim ile ayni): 3.5mm bosluklar dusebilir."""
    return [_box(20, 20, 8, at=(0, 0, 0)),
            _box(20, 20, 8, at=(0, 0, 11.5)),
            _box(20, 20, 8, at=(0, 0, 23.0))]


def _kilit_artar():
    """Sayac-tabanli sahte kilit: pre=0 (ilk cagri), post=1 (ikinci) -> artis."""
    sayac = {"n": 0}

    def f(meshes):
        sayac["n"] += 1
        return 0 if sayac["n"] == 1 else 1

    return f


def _boom(*a, **k):
    raise AssertionError("bu yol cagrilmamaliydi")


# ---------- uretim_r11 katmani ----------

def test_r11_kilit_artisi_rot_kapali_none():
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, _kilit_fn=_kilit_artar(),
                   _rot_fn=_boom)  # rot_kabul default False -> rot sorulmaz
    assert r is None


def test_r11_rot_kabul_go_sokum_planli():
    cert = NS(eksen="Z", aci_deg=15.0, yon="+X", lift_vox=1)
    rot = NS(n_locked=0, certificates={"m1": cert})
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=lambda ms: rot)
    assert r is not None
    assert r["sokum_planli"] is True
    assert r["rot_kilit"] == 0
    assert r["rot_cert"] == 1
    assert r["kilit_pre"] == 0 and r["kilit_post"] == 1
    assert r["kazanc_mm"] > 0.5
    assert r["min_clearance_mm"] >= 2.0
    # K-52 musteri-yuzu: sokum talimati KAYBOLMAZ (mesh_idx m1 -> 1)
    assert r["sokum_plani"] == [{"mesh_idx": 1, "eksen": "Z",
                                 "aci_deg": 15.0, "yon": "+X",
                                 "lift_vox": 1}]


def test_r11_rot_kilitli_none():
    rot = NS(n_locked=2, certificates={})
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=lambda ms: rot)
    assert r is None


def test_r11_rot_hata_none():
    def patlar(ms):
        raise RuntimeError("rot denetimi kurulamadi")

    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=patlar)
    assert r is None


def test_r11_kilit_artmadiysa_rot_cagrilmaz():
    # gercek kilit fonksiyonu (kule 0->0) + _boom: rot yoluna hic girilmemeli
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True, _rot_fn=_boom)
    assert r is not None  # normal kabul
    assert "sokum_planli" not in r


# ---------- solve_nfv_kalite katmani ----------

def _ham(h=100.0, n=4):
    return NS(height_mm=h, n_placed=n,
              placements=[NS(part_id=f"k_{i:02d}", name="k")
                          for i in range(n)],
              fine_voxel_parts={}, fine_pitch=2.0)


def test_kalite_rot_kabul_go_guard_atlanir():
    ham = _ham()

    def solve(inst, **kw):
        assert "exit_guard" not in kw, "guard kosulmamaliydi"
        return ham

    cert = NS(eksen="Y", aci_deg=-30.0, yon="+Z", lift_vox=0)
    res, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=lambda r: NS(n_locked=0, certificates={"m2": cert}))
    assert res is ham
    assert tel["secilen"] == "ham"
    assert tel["guard_kosuldu"] is False
    assert tel["ham_n_locked"] == 3
    rk = tel["rot_kabul"]
    assert rk["uygulandi"] is True and rk["rot_kilit"] == 0 and rk["cert"] == 1
    # HD-1: plan hem gorunen adi hem INSTANCE kimligini (part_id) tasir
    assert rk["sokum_plani"] == [{"parca": "k", "part_id": "k_02",
                                  "eksen": "Y", "aci_deg": -30.0,
                                  "yon": "+Z", "lift_vox": 0}]


def test_kalite_rot_kilitli_guard_kosulur():
    ham, guard = _ham(100.0), _ham(110.0)

    def solve(inst, **kw):
        return guard if kw.get("exit_guard") else ham

    res, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=lambda r: NS(n_locked=1, certificates={}))
    assert tel["guard_kosuldu"] is True
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"] == "rot_kilitli"
    assert tel["rot_kabul"]["rot_kilit"] == 1
    assert res is ham  # ikisi de kilitli -> alcak olan


def test_kalite_rot_auto_parca_tavani():
    """rot_kabul tavani KENDI sabiti (600) — R11 tavanindan (150) AYRI.

    d4 routing karari (Eren 2026-07-15): rot denetimi 588p @1.0 = 1.4dk
    (K-52; K-42'nin 'saatler'i eski parametre setiydi) — asil sigorta
    rot_butce_s. Tavan ustunde eski RED davranisi."""
    ham = _ham(n=ROT_KABUL_AUTO_PARCA_TAVANI + 1)

    def solve(inst, **kw):
        return ham

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul="auto", _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3), _check_rot=_boom)
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"] == "parca_tavani"
    assert tel["guard_kosuldu"] is True


def test_kalite_rot_auto_588_parca_kosar():
    """d4 senaryosu (588p): hem R11 hem ROT auto tavani KAPSAMINDA (K-58:
    R11 tavani 150->600, K-55 hiz kanitiyla rot tavaniyla hizalandi) ->
    rot denetimi KOSAR, sokum-planli kabul mumkun."""
    assert 588 <= R11_AUTO_PARCA_TAVANI <= ROT_KABUL_AUTO_PARCA_TAVANI
    ham = _ham(n=588)

    def solve(inst, **kw):
        return ham

    res, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul="auto", _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=lambda r: NS(n_locked=0, certificates={}))
    assert res is ham
    assert tel["rot_kabul"]["uygulandi"] is True
    assert tel["guard_kosuldu"] is False


def test_kalite_rot_false_bit_ozdes():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        _solve=solve, _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=_boom)  # rot_kabul default False
    assert "rot_kabul" not in tel
    assert tel["guard_kosuldu"] is True


def test_kalite_rot_hata_guard_kosulur():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    def patlar(r):
        raise RuntimeError("rot kurulamadi")

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3), _check_rot=patlar)
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"].startswith("hata:")
    assert tel["guard_kosuldu"] is True


def test_kalite_kilit_bilinmiyorsa_rot_denenmez():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    def kilit_patlar(p, v):
        raise RuntimeError("denetim kurulamadi")

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve, _check_5dir=kilit_patlar,
        _check_rot=_boom)
    assert "rot_kabul" not in tel  # kilit sayisi bilinmiyor -> rot sorulmaz
    assert tel["guard_kosuldu"] is True


# ---------- kutuphane katmani ----------

def _vox(grid):
    return NS(orientations=[NS(grid=np.asarray(grid, dtype=bool))])


def test_check_rot_int_erode_normalize():
    # kapali kafes (7^3, 3^3 ic bosluk) + iceride 3^3 kup: ikisi de 5-yon
    # kilitli -> rot asamasi (_ensure_eroded unpack yolu) KESIN kosulur.
    kafes = np.ones((7, 7, 7), bool)
    kafes[2:5, 2:5, 2:5] = False
    kup = np.ones((3, 3, 3), bool)
    parts = {"kafes": _vox(kafes), "kup": _vox(kup)}
    pls = [NS(part_id="kafes", orientation_idx=0, x=0, y=0, z=0),
           NS(part_id="kup", orientation_idx=0, x=2, y=2, z=2)]
    rapor = check_separability_rot(pls, parts, max_grid_vox=50,
                                   sure_butcesi_s=30.0,
                                   erode_clearance_vox=1)  # K-52 dersi: int
    assert isinstance(rapor, RotSeparabilityReport)
    assert rapor.n_parts == 2
    # rot asamasinin (dolayisiyla _ensure_eroded unpack yolunun) gercekten
    # kosuldugunun kaniti: sertifika veya fail-telemetri uretilmis olmali.
    # (normalize oncesi bu cagri TypeError atardi.)
    assert rapor.certificates or rapor.fail_telemetri


def test_kilit_rot_meshes_serbest_sahne_deterministik():
    sahne = [_box(20, 20, 10, at=(0, 0, 0)), _box(20, 20, 10, at=(30, 0, 0))]
    r1 = kilit_rot_meshes(sahne)
    r2 = kilit_rot_meshes(sahne)
    assert r1.n_locked == r2.n_locked == 0
    assert r1.n_parts == 2


# ---------- pipeline kablosu (K-52 GO sonrasi, Eren onayi 2026-07-15) ----------

def test_pipeline_rot_kabul_auto_kablosu(monkeypatch):
    """Uretim pipeline'i solve_nfv_kalite'ye rot_kabul="auto" gecirmeli."""
    import src.nesting3d.nfv_solve as nfv
    from scripts.demo_pipeline import run_pipeline
    from tests.test_demo_pipeline import SMOKE_SCENARIO

    yakalanan = {}
    orijinal = nfv.solve_nfv_kalite

    def sarmal(*a, **kw):
        yakalanan.update(kw)
        return orijinal(*a, **kw)

    monkeypatch.setattr(nfv, "solve_nfv_kalite", sarmal)
    run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv"})
    assert yakalanan.get("rot_kabul") == "auto"
    assert yakalanan.get("r11") == "auto"  # mevcut kablo bozulmadi


def test_pipeline_sokum_plani_kablosu(monkeypatch):
    """r11-rot yolundan gelen mesh_idx'li plan pipeline'da parca adina eslenir
    ve nesting_results'a yazilir (detay JSON'da kalicilasir — Faz-2 UI kaynagi)."""
    import src.nesting3d.continuous_settle as cs
    from scripts.demo_pipeline import run_pipeline
    from tests.test_demo_pipeline import SMOKE_SCENARIO

    def fake_r11(meshes, **kw):
        return {"dz": [0.1] * len(meshes), "height_mm": 1.0,
                "height_before_mm": 1.1, "kazanc_mm": 0.1,
                "min_clearance_mm": 2.5, "kilit_pre": 0, "kilit_post": 1,
                "rafine_tur": 1, "sokum_planli": True, "rot_kilit": 0,
                "rot_cert": 1,
                "sokum_plani": [{"mesh_idx": 0, "eksen": "Z", "aci_deg": 15.0,
                                 "yon": "+X", "lift_vox": 0}]}

    monkeypatch.setattr(cs, "uretim_r11", fake_r11)
    result = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv"})
    planli = [nr for nr in result["nesting_results"].values()
              if nr.get("sokum_plani")]
    assert planli, "sokum_plani hicbir partiye yazilmadi — kablo kopuk"
    e = planli[0]["sokum_plani"][0]
    assert e.get("parca"), "mesh_idx parca adina eslenmedi"
    assert e["eksen"] == "Z" and e["yon"] == "+X" and e["aci_deg"] == 15.0


def _r11_passthrough_kur(monkeypatch):
    """HD-0: uretim_r11 + placed_meshes kaydediciyle degistirilir."""
    import src.nesting3d.continuous_settle as cs
    import src.nesting3d.export_stl as es
    yakalanan = {}

    def fake_uretim_r11(meshes, **kw):
        yakalanan.update(kw)
        return None  # kapilar gecilemedi say — sonuc aynen korunur

    monkeypatch.setattr(cs, "uretim_r11", fake_uretim_r11)
    monkeypatch.setattr(es, "placed_meshes", lambda p, v, px, dz=None: [])
    return yakalanan


def test_hd0_r11_rot_kabul_passthrough(monkeypatch):
    """HD-0 (plan 2026-07-15): rot-kabul R11 kapisina da akmali — K-52'nin
    kanitladigi yol (R11'in yarattigi kilidin rot'la aklanmasi)."""
    yakalanan = _r11_passthrough_kur(monkeypatch)
    ham = _ham()

    def solve(inst, **kw):
        return ham

    solve_nfv_kalite(None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
                     r11=True, rot_kabul=True, rot_butce_s=777.0,
                     _solve=solve, _check_5dir=lambda p, v: NS(n_locked=0))
    assert yakalanan.get("rot_kabul") is True
    assert yakalanan.get("rot_butce_s") == 777.0


def test_hd0_rot_kabul_auto_tavani_r11_icinde(monkeypatch):
    """r11=True buyuk seti zorlarken rot_kabul='auto' tavani asilirsa
    R11-rot KAPALI gecmeli (auto semantigi uretim_r11'e tasinmaz, cozulur).
    Tavan = ROT_KABUL_AUTO_PARCA_TAVANI (rot tavani; R11 tavanindan ayri)."""
    yakalanan = _r11_passthrough_kur(monkeypatch)
    ham = _ham(n=ROT_KABUL_AUTO_PARCA_TAVANI + 1)

    def solve(inst, **kw):
        return ham

    solve_nfv_kalite(None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
                     r11=True, rot_kabul="auto",
                     _solve=solve, _check_5dir=lambda p, v: NS(n_locked=0))
    assert yakalanan.get("rot_kabul") is False


def test_hd0_rot_kabul_auto_rot_tavani_altinda_acik(monkeypatch):
    """r11=True + rot_kabul='auto' + n rot-tavani icinde (sinir dahil) ->
    R11-rot ACIK gecer. (K-58 oncesi bu test R11-ustu/rot-alti penceresini
    kullaniyordu; tavanlar 600'de hizalaninca pencere kapandi — sinir degeri
    ayni 'auto acik' semantigini tasir.)"""
    yakalanan = _r11_passthrough_kur(monkeypatch)
    ham = _ham(n=ROT_KABUL_AUTO_PARCA_TAVANI)  # 600: tavan dahil -> acik

    def solve(inst, **kw):
        return ham

    solve_nfv_kalite(None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
                     r11=True, rot_kabul="auto",
                     _solve=solve, _check_5dir=lambda p, v: NS(n_locked=0))
    assert yakalanan.get("rot_kabul") is True


def test_k58_r11_auto_588_parca_denenir(monkeypatch):
    """K-58 (2026-07-19): R11 auto tavani 150 -> 600 — d4 senaryosu (588p)
    r11='auto'da artik ATLANMAZ. Gerekce: K-55 hizlandirmasi (588p
    settle+rafine 393dk -> 43.5dk ~9x, h/clear BIREBIR) 'R11 pahali' (K-50:
    588p=375dk) gerekcesini kaldirdi; tavan rot tavaniyla hizalandi."""
    yakalanan = _r11_passthrough_kur(monkeypatch)
    ham = _ham(n=588)

    def solve(inst, **kw):
        return ham

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        r11="auto", rot_kabul="auto",
        _solve=solve, _check_5dir=lambda p, v: NS(n_locked=0))
    assert tel["r11"]["neden"] == "kapilar"    # tavana TAKILMADI, denendi
    assert yakalanan.get("rot_kabul") is True  # 588 <= rot tavani (600)


def test_gecmis_detay_sokum_plani_render():
    """Detay sayfasi sokum planini operator talimati olarak gosterir."""
    from tests.test_gecmis_detay_tam import _make_provider_with_teklif
    from src.webapp.app import create_app

    app = create_app(testing=True,
                     llm_provider_override=_make_provider_with_teklif())
    fn = app.config["GECMIS_KAYDET_FN"]
    nr = {"height_mm": 42.0, "density": 0.5, "n_parts": 3, "pitch_mm": 2.0,
          "sokum_plani": [{"parca": "kanat_sol", "eksen": "Z",
                           "aci_deg": 15.0, "yon": "+X", "lift_vox": 1}]}
    kayit = fn({"ranked_orders": [], "batches": [],
                "nesting_results": {"B001": nr},
                "pricing_results": {}, "elapsed_sec": 0.0},
               mod="auto", kaynak="manuel")[0]
    html = app.test_client().get(f"/gecmis/{kayit['id']}").data.decode("utf-8")
    assert "Sokum Plani" in html
    assert "kanat_sol" in html
    assert "Z ekseninde 15" in html
    assert "+X yonunden cek" in html

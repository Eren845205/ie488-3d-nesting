# -*- coding: utf-8 -*-
"""eval_gate saf fonksiyon testleri (legal_of + compare_verdict â€” ANAYASA A2/B2).

Solve KOSMAZ â€” yalniz metrik/verdict mantigi. Kosum: pytest tests/test_eval_gate.py
"""
from scripts.eval_gate import legal_of, compare_verdict


# ---------------------------------------------------------------------------
# legal_of â€” A2: yerlesen==N ve clearance>=1 ve 0 kilit, aksi INVALID(sebep)
# ---------------------------------------------------------------------------

def test_legal_of_gecerli():
    lh, reason = legal_of(264.0, 588, 588, 2.023, 0)  # A2: req=2.0 (Sprint-3)
    assert lh == 264.0 and reason is None


def test_legal_of_clearance_ihlali():
    lh, reason = legal_of(282.0, 588, 588, 0.084, 0)
    assert lh is None and "clearance" in reason


def test_legal_of_kilit():
    lh, reason = legal_of(262.5, 588, 588, 1.1, 554)
    assert lh is None and "554 kilit" in reason


def test_legal_of_eksik_yerlesim():
    lh, reason = legal_of(193.0, 193, 588, 1.5, 0)
    assert lh is None and "193/588" in reason


def test_legal_of_coklu_sebep_hepsi_raporlanir():
    lh, reason = legal_of(100.0, 500, 588, 0.5, 3)
    assert lh is None
    assert "500/588" in reason and "clearance" in reason and "3 kilit" in reason


def test_legal_of_clearance_olculemedi_invalid():
    # kanitsizlik gecer not degildir (live-runtime kurali)
    lh, reason = legal_of(264.0, 588, 588, None, 0)
    assert lh is None and "olculemedi" in reason


# ---------------------------------------------------------------------------
# A2 rot-sokum katmani (Eren karari 2026-07-15; hoca kabulu 2026-07-14):
# 5-yon kilit>0 tek basina RED degil — rot-sokum denetimi kilitleri yeniden
# yargilar; rot kilit=0 -> SOKUM-PLANLI legal. Default None = eski davranis.
# ---------------------------------------------------------------------------

def test_legal_of_rot_sokum_kabul():
    lh, reason = legal_of(220.7, 588, 588, 2.016, 12, n_locked_rot=0)
    assert lh == 220.7 and reason is None


def test_legal_of_rot_sokum_hala_kilitli():
    lh, reason = legal_of(220.7, 588, 588, 2.016, 12, n_locked_rot=3)
    assert lh is None
    assert "12 kilit" in reason and "rot-sokum 3" in reason


def test_legal_of_rot_olculmedi_eski_davranis_bit_ozdes():
    lh, reason = legal_of(262.5, 588, 588, 2.1, 554, n_locked_rot=None)
    assert lh is None and reason == "554 kilit"


def test_legal_of_rot_kilitsizde_etkisiz():
    lh, reason = legal_of(264.0, 588, 588, 2.023, 0, n_locked_rot=0)
    assert lh == 264.0 and reason is None


def test_legal_of_rot_diger_ihlalleri_aklamaz():
    # rot kabulu YALNIZ kilit kosulunu aklar; clearance ihlali INVALID kalir
    lh, reason = legal_of(220.7, 588, 588, 1.5, 12, n_locked_rot=0)
    assert lh is None and "clearance" in reason and "kilit" not in reason


# ---------------------------------------------------------------------------
# evaluate_set rot katmani kablosu (lazy + konservatif + enjeksiyon)
# ---------------------------------------------------------------------------

def _fake_eval_ortam(monkeypatch, n_locked, min_mm=2.1, nfv_tel=None):
    """evaluate_set'in solve/olcum bagimliliklarini stub'lar; cagri sayaclari doner."""
    from types import SimpleNamespace as NS
    import scripts.eval_gate as eg

    class _R:
        placements = ["pl"]
        fine_voxel_parts = {"k": "vp"}
        fine_pitch = 1.0
        height_mm = 220.7
        n_placed = 588

    sayac = {"rot": 0, "placed_kw": {}}
    monkeypatch.setattr(eg, "_load_instance",
                        lambda name: NS(parts=[NS(qty=588)]))
    monkeypatch.setattr(eg, "_run_champion",
                        lambda name, inst, seed, budget=None,
                        n_orientations=None: (_R(), nfv_tel))

    def _placed(*a, **k):
        sayac["placed_kw"] = k
        return ["mesh"]

    monkeypatch.setattr(eg, "placed_meshes", _placed)
    monkeypatch.setattr(eg, "min_clearance",
                        lambda *a, **k: NS(min_mm=min_mm))
    monkeypatch.setattr(eg, "check_placements",
                        lambda *a, **k: NS(n_locked=n_locked))
    return eg, sayac


def test_evaluate_set_rot_kabul_sokum_planli(monkeypatch):
    from types import SimpleNamespace as NS
    eg, sayac = _fake_eval_ortam(monkeypatch, n_locked=12)

    def rot_fn(meshes):
        sayac["rot"] += 1
        return NS(n_locked=0, certificates=[1, 2, 3, 4, 5])

    r = eg.evaluate_set("t", 42, _rot_fn=rot_fn)
    assert sayac["rot"] == 1
    assert r["legal_height_mm"] == 220.7 and r["invalid_reason"] is None
    assert r["n_locked"] == 12 and r["n_locked_rot"] == 0
    assert r["rot_cert"] == 5 and r["sokum_planli"] is True


def test_evaluate_set_rot_hala_kilitli_invalid(monkeypatch):
    from types import SimpleNamespace as NS
    eg, _ = _fake_eval_ortam(monkeypatch, n_locked=12)
    r = eg.evaluate_set(
        "t", 42, _rot_fn=lambda m: NS(n_locked=3, certificates=[1]))
    assert r["legal_height_mm"] is None
    assert "12 kilit" in r["invalid_reason"]
    assert "rot-sokum 3" in r["invalid_reason"]
    assert r["sokum_planli"] is False


def test_evaluate_set_kilitsizde_rot_hic_kosmaz(monkeypatch):
    # K-42 maliyet dersi: kilit yoksa rot denetimi HIC kosulmaz
    eg, sayac = _fake_eval_ortam(monkeypatch, n_locked=0)

    def rot_fn(meshes):
        sayac["rot"] += 1
        raise AssertionError("kosulmamaliydi")

    r = eg.evaluate_set("t", 42, _rot_fn=rot_fn)
    assert sayac["rot"] == 0
    assert r["legal_height_mm"] == 220.7
    assert r["n_locked_rot"] is None and r["sokum_planli"] is False


def test_evaluate_set_rot_hatasi_konservatif_eski_red(monkeypatch):
    # rot denetimi cokerse kabul tarafina sizamaz: eski RED + hata kaydi
    def rot_fn(meshes):
        raise RuntimeError("VRAM bitti")

    eg, _ = _fake_eval_ortam(monkeypatch, n_locked=12)
    r = eg.evaluate_set("t", 42, _rot_fn=rot_fn)
    assert r["legal_height_mm"] is None
    assert r["invalid_reason"] == "12 kilit"
    assert "VRAM bitti" in r["rot_hata"]


def test_evaluate_set_skip_clearance_rot_kosmaz(monkeypatch):
    # meshes uretilmedi -> rot denetimi atlanir (sonuc zaten INVALID)
    eg, sayac = _fake_eval_ortam(monkeypatch, n_locked=12)

    def rot_fn(meshes):
        sayac["rot"] += 1
        raise AssertionError("kosulmamaliydi")

    r = eg.evaluate_set("t", 42, skip_clearance=True, _rot_fn=rot_fn)
    assert sayac["rot"] == 0
    assert r["legal_height_mm"] is None


def test_evaluate_set_r11_dz_kaymis_sahne(monkeypatch):
    """r11 uygulandiysa kapi dz-KAYMIS sahneyi olcer (uretim paritesi:
    musteri STL'i dz'li — 7add014): yukseklik r11-sonrasi, meshes dz'li,
    kilit K-50 metrigiyle (kilit_5yon_meshes) dz'li meshlerde."""
    tel = {"r11": {"uygulandi": True, "dz": [1.0, 2.5],
                   "height_mm": 200.0, "kazanc_mm": 20.7}}
    eg, sayac = _fake_eval_ortam(monkeypatch, n_locked=99, nfv_tel=tel)
    kilit5 = {"n": 0}

    def kilit5_fn(meshes):
        kilit5["cagri"] = True
        return kilit5["n"]

    r = eg.evaluate_set("t", 42, _kilit5_fn=kilit5_fn)
    assert sayac["placed_kw"].get("dz") == [1.0, 2.5]
    assert kilit5.get("cagri") is True
    assert r["legal_height_mm"] == 200.0     # r11-sonrasi gercek yukseklik
    assert r["n_locked"] == 0                # dz'li sahnede olculdu (99 degil)
    assert r["r11_uygulandi"] is True and r["r11_kazanc_mm"] == 20.7


def test_evaluate_set_r11_yoksa_eski_yol_bit_ozdes(monkeypatch):
    """r11 uygulanmadiysa (tel yok/None): dz gecilmez, kilit check_placements."""
    eg, sayac = _fake_eval_ortam(monkeypatch, n_locked=0, nfv_tel=None)
    r = eg.evaluate_set("t", 42)
    assert sayac["placed_kw"].get("dz") is None
    assert r["legal_height_mm"] == 220.7
    assert r["r11_uygulandi"] is False


# ---------------------------------------------------------------------------
# compare_verdict â€” B2 esikleri: >%2 kotu veya INVALID=FAIL; +-%0.5 gurultu;
# kotulesme yoksa ve >=1 iyilesme varsa PASS; arasi INSAN-KARARI.
# ---------------------------------------------------------------------------

def test_verdict_pass_iyilesme():
    overall, per = compare_verdict({"a": 250.0, "b": 500.0},
                                   {"a": 264.0, "b": 500.0})
    assert overall == "PASS"
    assert per["a"][1] == "iyilesme"


def test_verdict_noop_gurultu_bandi():
    overall, _ = compare_verdict({"a": 264.5}, {"a": 264.0})  # +0.19% < 0.5
    assert overall == "NOOP"


def test_verdict_fail_buyuk_kotulesme():
    overall, _ = compare_verdict({"a": 270.0}, {"a": 264.0})  # +2.27% > 2
    assert overall == "FAIL"


def test_verdict_fail_invalid_set():
    overall, per = compare_verdict({"a": None, "b": 490.0},
                                   {"a": 264.0, "b": 500.0})
    assert overall == "FAIL"          # INVALID her seyi FAIL yapar (iyilesmeye ragmen)
    assert "INVALID" in per["a"][1]


def test_verdict_insan_karari_tradeoff():
    # bir sette gurultu-ustu ama <%2 kotulesme + digerinde iyilesme -> insan karari
    overall, _ = compare_verdict({"a": 266.0, "b": 480.0},
                                 {"a": 264.0, "b": 500.0})  # a: +0.76%
    assert overall == "INSAN-KARARI"


def test_verdict_baseline_invalid_simdi_gecerli_iyilesmedir():
    overall, per = compare_verdict({"a": 264.0}, {"a": None})
    assert overall == "PASS" and "iyilesme" in per["a"][1]


def test_verdict_baseline_yok():
    overall, _ = compare_verdict({"a": 264.0}, None)
    assert overall == "BASELINE-YOK"


def test_verdict_sinir_tam_fail_esiginde_fail_degil():
    # tam +%2.0 -> FAIL degil (esik "asilirsa"); INSAN-KARARI bandi
    overall, _ = compare_verdict({"a": 102.0}, {"a": 100.0})
    assert overall == "INSAN-KARARI"


# ---------------------------------------------------------------------------
# Sprint-3 v2 sozlesmesi: sampiyon-yolu paritesi (NFV dali + no-go + 2mm)
# ---------------------------------------------------------------------------

def _mini_inst():
    from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
    return NestingInstance(
        container=ContainerSpec(width_mm=335.0, depth_mm=335.0),
        parts=[PartSpec(id="k", name="k", qty=2, source="box",
                        width_mm=30.0, depth_mm=30.0, height_mm=20.0)])


def test_clearance_req_iki_mm():
    from scripts.eval_gate import CLEARANCE_REQ_MM, legal_of
    assert CLEARANCE_REQ_MM == 2.0
    lh, reason = legal_of(100.0, 5, 5, 1.5, 0)
    assert lh is None and "clearance 1.500<2.0" in reason


def test_run_champion_nfv_dali_uretim_paritesi(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}
    routing_kw = {}

    def sahte_kalite(inst, **kw):
        yakalanan.update(kw)
        return "NFV_SONUC", {"secilen": "ham"}

    class _Dec:
        mode = "nfv"
        wall_aware = False

    def sahte_predict(inst, **k):
        routing_kw.update(k)
        return _Dec()

    import src.nesting3d.nfv_solve as nfv_mod
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sahte_kalite)
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", sahte_predict)
    r, tel = eg._run_champion("t", _mini_inst(), 42)
    assert r == "NFV_SONUC"
    assert tel == {"secilen": "ham"}  # telemetri kapiya akar (r11 dz olcumu)
    assert yakalanan["clearance_mm"] == 2.0
    assert yakalanan["quality"] == "fast"          # uretim DEFAULT'u
    assert yakalanan["no_go_bounds"] == eg.NOGO_STD
    # Uretim paritesi (2026-07-15): pipeline r11="auto" + rot_kabul="auto"
    # kosuyor ve dz-export (7add014) r11 kazancini musteri STL'ine yansitiyor
    # — kapi da AYNI default'larla olcer (eski r11=False donemi dz'nin
    # height'a yansimadigi doneme aitti).
    assert yakalanan["r11"] == "auto"
    assert yakalanan["rot_kabul"] == "auto"
    # d4 routing karari (Eren 2026-07-15): uretim rot-sokum dunyasinda —
    # routing kararina rot_sokum=True gecer (thin_shell -> NFV+rot).
    assert routing_kw["rot_sokum"] is True
    assert routing_kw["family_routing"] is True


def test_run_champion_heightmap_dali_nogo_tasir(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_c2f(inst, **kw):
        yakalanan.update(kw)
        return "HM_SONUC"

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    monkeypatch.setattr(eg, "solve_coarse_to_fine", sahte_c2f)
    r, tel = eg._run_champion("t", _mini_inst(), 42)
    assert r == "HM_SONUC"
    assert tel is None  # heightmap dalinda nfv telemetrisi yok
    assert yakalanan["no_go_bounds"] == eg.NOGO_STD
    assert yakalanan["clearance_mm"] == 2.0

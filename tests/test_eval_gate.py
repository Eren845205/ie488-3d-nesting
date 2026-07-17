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
    # plan1 dersi (K-40): tilt-zorunlu fizibilite kapisi no-go'yu bilir
    assert routing_kw["no_go_bounds"] == eg.NOGO_STD


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


# ---------------------------------------------------------------------------
# K-53c: n_orientations="ax24" poz seti (quality=max cevirisi)
# ---------------------------------------------------------------------------

def test_poz_seti_cevir_none_ve_int_birebir():
    from scripts.eval_gate import _poz_seti_cevir
    assert _poz_seti_cevir(None) == ("fast", None)
    assert _poz_seti_cevir(12) == ("fast", 12)


def test_poz_seti_cevir_ax24_max():
    from scripts.eval_gate import _poz_seti_cevir
    assert _poz_seti_cevir("ax24") == ("max", None)
    assert _poz_seti_cevir("AX24") == ("max", None)  # buyuk/kucuk duyarsiz


def test_poz_seti_cevir_bilinmeyen_reddedilir():
    import pytest
    from scripts.eval_gate import _poz_seti_cevir
    with pytest.raises(ValueError, match="bilinmeyen poz seti"):
        _poz_seti_cevir("egik24")


def test_run_champion_ax24_nfv_dalinda_max(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_kalite(inst, **kw):
        yakalanan.update(kw)
        return "NFV_SONUC", None

    class _Dec:
        mode = "nfv"
        wall_aware = False

    import src.nesting3d.nfv_solve as nfv_mod
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sahte_kalite)
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    r, _ = eg._run_champion("t", _mini_inst(), 42, n_orientations="ax24")
    assert r == "NFV_SONUC"
    assert yakalanan["quality"] == "max"          # AX24 = max poz seti
    assert yakalanan["n_orientations"] is None    # ilk-N override DEVRE DISI


def test_run_champion_ax24_heightmap_dalinda_reddedilir(monkeypatch):
    import pytest
    import scripts.eval_gate as eg

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    with pytest.raises(ValueError, match="yalniz NFV dalinda"):
        eg._run_champion("t", _mini_inst(), 42, n_orientations="ax24")


def test_run_champion_aile_onerisi_max_kullanilir(monkeypatch):
    """K-53c: acik override yokken dec.nfv_quality='max' kapida da gecerli."""
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_kalite(inst, **kw):
        yakalanan.update(kw)
        return "NFV_SONUC", None

    class _Dec:
        mode = "nfv"
        wall_aware = False
        nfv_quality = "max"

    import src.nesting3d.nfv_solve as nfv_mod
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sahte_kalite)
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    eg._run_champion("t", _mini_inst(), 42)
    assert yakalanan["quality"] == "max"


def test_run_champion_int_override_aile_onerisini_ezer(monkeypatch):
    """Acik n_orientations=12 verilirse aile onerisi ('max') EZILIR (fast+12)."""
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_kalite(inst, **kw):
        yakalanan.update(kw)
        return "NFV_SONUC", None

    class _Dec:
        mode = "nfv"
        wall_aware = False
        nfv_quality = "max"

    import src.nesting3d.nfv_solve as nfv_mod
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sahte_kalite)
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    eg._run_champion("t", _mini_inst(), 42, n_orientations=12)
    assert yakalanan["quality"] == "fast"
    assert yakalanan["n_orientations"] == 12


# ---------------------------------------------------------------------------
# K-57b: set-paralel orkestrasyon (--parallel) + cocuk modu (--json-out)
# Duvar-saati ~ en yavas set; per-set sonuclar surec-izolasyonuyla bit-ozdes.
# ---------------------------------------------------------------------------

def _tam_sonuc(name, h=100.0):
    return {
        "legal_height_mm": h, "invalid_reason": None, "height_mm": h,
        "n_placed": 5, "n_total": 5, "min_clearance_mm": 2.1, "n_locked": 0,
        "n_locked_rot": None, "rot_cert": None, "rot_hata": None,
        "sokum_planli": False, "r11_uygulandi": False, "r11_kazanc_mm": None,
        "duration_s": 1.0,
    }


class _FakeProc:
    def __init__(self, returncode=0, out="cocuk cikti\n"):
        self.returncode = returncode
        self._out = out

    def communicate(self):
        return (self._out, None)


def test_k57_parallel_sonuclari_birlestirir(tmp_path):
    import json as _json
    import scripts.eval_gate as eg

    def fake_spawn(name, out_path):
        doc = {"schema": 1, "sets": {name: _tam_sonuc(name, h=float(len(name)))}}
        out_path.write_text(_json.dumps(doc), encoding="utf-8")
        return _FakeProc()

    res = eg._run_sets_parallel(["plan1", "plan2"], 42, False, 2,
                                _spawn=fake_spawn)
    assert set(res) == {"plan1", "plan2"}
    assert res["plan1"]["legal_height_mm"] == 5.0
    assert res["plan2"]["legal_height_mm"] == 5.0


def test_k57_parallel_cocuk_hatasi_digerlerini_engellemez(tmp_path):
    import json as _json
    import scripts.eval_gate as eg

    def fake_spawn(name, out_path):
        if name == "plan1":
            return _FakeProc(returncode=1)  # json yazmadan oldu
        doc = {"schema": 1, "sets": {name: _tam_sonuc(name)}}
        out_path.write_text(_json.dumps(doc), encoding="utf-8")
        return _FakeProc()

    res = eg._run_sets_parallel(["plan1", "plan2"], 42, False, 2,
                                _spawn=fake_spawn)
    assert res["plan1"]["legal_height_mm"] is None
    assert res["plan1"]["invalid_reason"].startswith("EXCEPTION")
    assert res["plan2"]["legal_height_mm"] == 100.0


def test_k57_json_out_cocuk_modu_last_ve_baseline_yazmaz(tmp_path, monkeypatch):
    import json as _json
    import pytest
    import scripts.eval_gate as eg

    out = tmp_path / "cocuk.json"
    fake_last = tmp_path / "last.json"
    monkeypatch.setattr(eg, "LAST", fake_last)
    monkeypatch.setattr(eg, "evaluate_set",
                        lambda name, seed, skip, **kw: _tam_sonuc(name))
    monkeypatch.setattr("sys.argv",
                        ["eval_gate", "--sets", "plan1", "--json-out", str(out)])
    with pytest.raises(SystemExit) as e:
        eg.main()
    assert e.value.code == 0
    doc = _json.loads(out.read_text(encoding="utf-8"))
    assert doc["sets"]["plan1"]["legal_height_mm"] == 100.0
    assert not fake_last.exists()  # cocuk LAST'a DOKUNMAZ (yaris onlenir)


def test_k57_parallel_flagsiz_sekans_bit_ozdes(tmp_path, monkeypatch):
    import pytest
    import scripts.eval_gate as eg

    cagri = []
    monkeypatch.setattr(eg, "LAST", tmp_path / "last.json")
    monkeypatch.setattr(eg, "evaluate_set",
                        lambda name, seed, skip, **kw: (cagri.append(name),
                                                        _tam_sonuc(name))[1])
    monkeypatch.setattr(eg, "_run_sets_parallel",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("parallel yol cagrilmamali")))
    monkeypatch.setattr("sys.argv",
                        ["eval_gate", "--sets", "plan1,plan2",
                         "--baseline", str(tmp_path / "yok.json")])
    with pytest.raises(SystemExit) as e:
        eg.main()
    assert e.value.code == 0
    assert cagri == ["plan1", "plan2"]  # sirali in-process yol AYNEN


def test_k57_parallel_ana_akis_kiyas_ve_last(tmp_path, monkeypatch):
    import json as _json
    import pytest
    import scripts.eval_gate as eg

    fake_last = tmp_path / "last.json"
    monkeypatch.setattr(eg, "LAST", fake_last)
    monkeypatch.setattr(eg, "evaluate_set",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("parallel modda in-process evaluate yok")))
    monkeypatch.setattr(
        eg, "_run_sets_parallel",
        lambda sets, seed, skip, n, **kw: {s: _tam_sonuc(s) for s in sets})
    monkeypatch.setattr("sys.argv",
                        ["eval_gate", "--sets", "plan1,plan2", "--parallel", "2",
                         "--baseline", str(tmp_path / "yok.json")])
    with pytest.raises(SystemExit) as e:
        eg.main()
    assert e.value.code == 0  # BASELINE-YOK
    doc = _json.loads(fake_last.read_text(encoding="utf-8"))
    assert set(doc["sets"]) == {"plan1", "plan2"}


def test_k57_exception_seti_seri_yeniden_denenir(tmp_path):
    """OOM/cocuk-cokusu iyimser-paralel kosuyu oldurmesin: EXCEPTION'li set
    digerleri bitince TEK BASINA bir kez yeniden denenir (2026-07-17 olcum
    kosusu bulgusu: plan2||plan3 cakismasi plan3'u OOM'a dusurdu)."""
    import json as _json
    import scripts.eval_gate as eg

    cagri = {"plan1": 0}

    def fake_spawn(name, out_path):
        cagri[name] = cagri.get(name, 0) + 1
        if name == "plan1" and cagri[name] == 1:
            doc = {"sets": {name: dict(_tam_sonuc(name),
                                       legal_height_mm=None,
                                       invalid_reason="EXCEPTION: OOM")}}
        elif name == "plan1":  # kurtarma denemesi
            doc = {"sets": {name: _tam_sonuc(name, h=77.0)}}
        else:
            doc = {"sets": {name: _tam_sonuc(name)}}
        out_path.write_text(_json.dumps(doc), encoding="utf-8")
        return _FakeProc()

    res = eg._run_sets_parallel(["plan1", "plan2"], 42, False, 2,
                                _spawn=fake_spawn)
    assert cagri["plan1"] == 2                       # bir kez yeniden denendi
    assert res["plan1"]["legal_height_mm"] == 77.0   # kurtarildi
    assert res["plan2"]["legal_height_mm"] == 100.0


def test_k57_normal_invalid_yeniden_denenmez(tmp_path):
    """EXCEPTION degil duz INVALID (or. kilit) -> yeniden deneme YOK
    (deterministik olcum sonucu; tekrar ayni cikar, CPU israfi)."""
    import json as _json
    import scripts.eval_gate as eg

    cagri = {}

    def fake_spawn(name, out_path):
        cagri[name] = cagri.get(name, 0) + 1
        doc = {"sets": {name: dict(_tam_sonuc(name),
                                   legal_height_mm=None,
                                   invalid_reason="219 kilit")}}
        out_path.write_text(_json.dumps(doc), encoding="utf-8")
        return _FakeProc()

    res = eg._run_sets_parallel(["plan1"], 42, False, 1, _spawn=fake_spawn)
    assert cagri["plan1"] == 1
    assert res["plan1"]["invalid_reason"] == "219 kilit"

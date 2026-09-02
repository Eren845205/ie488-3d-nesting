# -*- coding: utf-8 -*-
"""KARAR-G (Eren onayi 2026-09-01: "bundan sonra her sey max'la yapilacak"):
uretim default kalitesi MAX. Tek kaynak: demo_pipeline.NFV_QUALITY_DEFAULT.
Kafes zinciri BILEREK kapsam disi (kaniti fast-recete; ayri olcum).
Kirmizi: bugun default'lar "fast" dagitik sabitler."""
from __future__ import annotations

import inspect


def test_tek_kaynak_sabit_max():
    from scripts import demo_pipeline as dp
    assert getattr(dp, "NFV_QUALITY_DEFAULT", None) == "max", (
        "NFV_QUALITY_DEFAULT sabiti yok veya max degil (KARAR-G)")


def test_process_batch_fallbackler_sabite_bagli():
    from scripts import demo_pipeline as dp
    src = inspect.getsource(dp._process_batch)
    assert 'quality=(nfv_quality or NFV_QUALITY_DEFAULT)' in src
    assert 'getattr(_dec, "nfv_quality", NFV_QUALITY_DEFAULT)' in src
    assert '(nfv_quality or "fast")' not in src, "eski fast fallback kalmis"


def test_webapp_manuel_form_default_max():
    import inspect as _i
    import src.webapp.app as app
    src = _i.getsource(app)
    assert '"max" if request.form.get("nfv_quality") == "max" else "fast"' \
        not in src, "manuel form hala fast-default (KARAR-G)"
    assert '"max" if _body.get("nfv_quality") == "max" else "fast"' \
        not in src, "otonom route hala fast-default (KARAR-G)"


def test_eval_gate_fallback_max():
    import inspect as _i
    from scripts import eval_gate as eg
    src = _i.getsource(eg._run_champion)
    assert 'getattr(dec, "nfv_quality", "fast")' not in src, (
        "eval_gate kural-fallback hala fast (KARAR-G; baseline'lar MAX ile "
        "yenilenecek)")


def test_karar_g_kural_onerisi_davranissal_max():
    """DAVRANIS testi (kaynak-metin degil): kural katmani cavity-aday
    instance icin nfv + quality=MAX onermeli (plan2 kapisi 521-fast kaniti
    — getattr-fallback olu noktaydi)."""
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.instances.format import (
        ContainerSpec, NestingInstance, PartSpec)
    inst = NestingInstance(
        container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
        parts=[PartSpec(id=f"k{i}", name=f"k{i}", qty=3, source="box",
                        width_mm=20.0, depth_mm=20.0, height_mm=120.0)
               for i in range(4)])
    dec = predict_nfv_benefit(inst)
    assert dec.mode == "nfv"
    assert dec.nfv_quality == "max", (
        f"kural onerisi {dec.nfv_quality} — KARAR-G'ye gore max olmali")

def test_kanopi_zinciri_fast_sabit():
    """KANOPI-FAST (Eren onayi 2026-09-01): zincir ic mini-solve'lari fast
    recetede sabit — MAX-zincir olculmedi ve 13-17GB patlatti (v8 kampanya).
    Ana solve MAX kalir (KARAR-G bozulmaz)."""
    from pathlib import Path as _P
    src = _P("scripts/demo_pipeline.py").read_text(encoding="utf-8")
    i = src.index("kanopi_zinciri_uretim(")
    blok = src[i:i + 1600]
    assert 'quality="fast"' in blok, (
        "kanopi zinciri fast'e sabit degil (KANOPI-FAST fix'i kayip)")
    assert "quality=(nfv_quality or NFV_QUALITY_DEFAULT)" not in blok, (
        "zincire hala default akiyor (MAX-zincir bellek riski)")

def test_kafes_zinciri_scenario_aktarimi():
    """KAFES-AKTARIM FIX (2026-09-01): scenario'daki kafes_zinciri anahtari
    payload'a tasinmali — m4 karsi-olgusal saflik buna dayanir."""
    from pathlib import Path as _P
    src = _P("scripts/demo_pipeline.py").read_text(encoding="utf-8")
    assert '"kafes_zinciri": scenario.get("kafes_zinciri", True)' in src, (
        "payload kurulumunda kafes_zinciri aktarimi yok (saflik kirilir)")

def test_m4_kollari_zincirsiz_saflik():
    """m4 kollari karsi-olgusal SAFLIK: kafes VE kanopi zinciri kapali
    (eval-parite; 2026-09-01 bellek teshisi)."""
    from pathlib import Path as _P
    src = _P("scripts/m4_portfoy_kosu.py").read_text(encoding="utf-8")
    i = src.index("def scenario_kur")
    blok = src[i:i + 2500]
    assert '"kafes_zinciri": False' in blok
    assert '"kanopi_zincir": False' in blok, (
        "m4 scenario kanopi'yi kapatmiyor (bellek + saflik)")

def _mini_satir(instance_id, max_hata=False, karantina=None):
    arms = {
        "heightmap": {"height_mm": 800.0},
        "nfv_fast": {"height_mm": 600.0},
        "nfv_max": ({"hata": "BEKCI: kol iptal"} if max_hata
                    else {"height_mm": 500.0}),
    }
    inv = {"heightmap": None, "nfv_fast": None,
           "nfv_max": ("kosu hatasi: BEKCI" if max_hata else None)}
    s = {"instance_id": instance_id, "scale": "gercek", "arms": arms,
         "invalid_reasons": inv, "n_total": 10}
    if karantina:
        s["karantina"] = karantina
    return s


def test_eksik_ana_kol_egitime_giremez():
    """Eren 2026-09-02: MAX olculemedigi satirdan fast-winner OGRENILEMEZ —
    kopru savunmasi bayraksiz satiri da dislar."""
    from src.nesting3d.selection.m4_koprusu import m4_training_rows
    res = lambda s: ([1.0], ["f"])
    ist = {}
    rows = m4_training_rows(
        [_mini_satir("x_bozuk", max_hata=True),
         _mini_satir("y_temiz", max_hata=False)],
        res, istatistik=ist)
    ids = [r.instance_id for r in rows]
    assert not any("x_bozuk" in i for i in ids), "eksik-kollu satir egitime girdi!"
    assert any("y_temiz" in i for i in ids), "temiz satir yanlislikla dislandi"
    assert ist.get("m4_n_eksik_ana_kol") == 1
    assert [r.winner for r in rows] == ["nfv_max"], "temiz satirda winner MAX olmali"


def test_uretici_otokarantina_kaynakta():
    from pathlib import Path as _P
    src = _P("scripts/asama2_devset_etiket.py").read_text(encoding="utf-8")
    assert "eksik-ana-kol otokarantinasi" in src, (
        "uretici otokarantinasi kayip (Eren 2026-09-02 kurali)")

def test_r11_bellek_diyeti_kaynakta():
    """R11-BELLEK DIYETI (2026-09-02): _surface_samples ornekleme sonrasi
    trimesh cache'ini birakir — p3-max 15,6GB patlamasinin ilaci."""
    from pathlib import Path as _P
    src = _P("src/nesting3d/clearance.py").read_text(encoding="utf-8")
    i = src.index("def _surface_samples")
    assert "mesh._cache.clear()" in src[i:i + 900], (
        "R11 bellek diyeti kayip (clearance._surface_samples)")

def test_bagging_roundtrip_mode_model_io(tmp_path):
    """E-genisletme (2026-09-02): MiniBagging fit -> save -> load -> proba
    birebir oy dagilimi; cift-kilit karar() calisir."""
    from src.nesting3d.selection.bagging import MiniBaggingSelector
    from src.nesting3d.selection.dataset import TrainingRow
    from src.nesting3d.selection.mode_model_io import (
        load_mode_model, save_mode_model)
    rows = []
    for i in range(12):
        w = "nfv_max" if i % 2 else "heightmap"
        rows.append(TrainingRow(
            instance_id="t%d" % i, is_easy=False, winner=w,
            dblf_height=None, best_height=100.0,
            feature_vector=[float(i % 2), float(i)],
            feature_names=["a", "b"], aile="fam_x"))
    mb = MiniBaggingSelector(n_trees=5, max_depth=2)
    mb.fit(rows)
    yol = tmp_path / "mm.json"
    save_mode_model(yol, mb, skorlar=[0.1, 0.2, 0.3],
                    armlar=["heightmap", "nfv_max"], allowlist=["fam_x"],
                    meta={"surum": "test", "alpha": 0.1})
    lm = load_mode_model(yol)
    assert lm is not None and lm.agaclar, "bagging artefakti yuklenemedi"
    for feats in ([0.0, 3.0], [1.0, 7.0]):
        assert lm.proba(feats) == mb.predict_proba(feats), "round-trip farkli!"
    assert lm.karar([1.0, 7.0], "yabanci_aile") is None, "allowlist delindi"


def test_eski_lojistik_artefakt_geriye_uyum():
    """Arsivdeki ESKI lojistik artefakt (v2) okunabilir kalmali; uretim
    artefakti ise TIPINDEN BAGIMSIZ (lojistik/bagging/agac) yuklenip
    olasilik dagilimi vermeli (E-genisletme 2026-09-02 sonrasi uretim
    artefakti agac-listeli olabilir -> `mu` alani yoktur)."""
    from src.nesting3d.selection.mode_model_io import load_mode_model
    from pathlib import Path as _P
    for yol in (_P("data/selection_archive/mode_model.v2.json"),
                _P("data/mode_model.json")):
        if not yol.exists():
            continue
        lm = load_mode_model(yol)
        assert lm is not None, f"{yol} yuklenemedi (geriye-uyum kirildi)"
        n_feat = len(lm.mu) if not lm.agaclar else 32
        p = lm.proba([0.0] * n_feat)
        assert abs(sum(p.values()) - 1.0) < 1e-9
    v2 = _P("data/selection_archive/mode_model.v2.json")
    if v2.exists():
        assert not load_mode_model(v2).agaclar, "v2 arsivi lojistik olmali"

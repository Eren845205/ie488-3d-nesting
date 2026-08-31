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

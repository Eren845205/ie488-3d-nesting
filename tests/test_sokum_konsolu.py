# -*- coding: utf-8 -*-
"""Sokum Konsolu P2-P6 render testleri (gecmis_detay + sonuc paritesi).

JS davranisi (renk/tikla-tani/rehber) tarayici dogrulamasiyla; burada
template sozlesmesi test edilir: (1) kimlikli kayitta konsol verisi +
ozet kartlari + sira rozetleri render olur, (2) ESKI kayitlarda (yeni
alanlar yok) tum yeni bolumler GIZLI kalir (P6 geriye-uyum), (3) iki
sayfa ortak viewer3d.js modulunu kullanir (P2 tek kaynak).

Kosum: pytest tests/test_sokum_konsolu.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_gecmis_detay_tam import _make_provider_with_teklif  # noqa: E402


@pytest.fixture
def app_llm():
    from src.webapp.app import create_app
    return create_app(testing=True,
                      llm_provider_override=_make_provider_with_teklif())


def _nr_konsollu():
    return {
        "height_mm": 42.0, "density": 0.5, "n_parts": 3, "pitch_mm": 2.0,
        "parca_kimlik": {
            "kapak_01": {"parca_uid": "ab12cd34-SIP-A-1", "order_id": "SIP-A",
                         "geo_imza": "ab12cd34ef", "kaynak_ad": "kapak.stl",
                         "ad": "kapak", "kopya_no": 1},
            "kapak_02": {"parca_uid": "ab12cd34-SIP-A-2", "order_id": "SIP-A",
                         "geo_imza": "ab12cd34ef", "kaynak_ad": "kapak.stl",
                         "ad": "kapak", "kopya_no": 2},
            "kapak_03": {"parca_uid": "ab12cd34-SIP-B-3", "order_id": "SIP-B",
                         "geo_imza": "ab12cd34ef", "kaynak_ad": "kapak.stl",
                         "ad": "kapak", "kopya_no": 3},
        },
        "siparis_ozeti": [
            {"order_id": "SIP-A", "musteri": "ACME", "n_parca": 2,
             "n_sokum_planli": 1},
            {"order_id": "SIP-B", "musteri": "BETA", "n_parca": 1,
             "n_sokum_planli": 0},
        ],
        "sokum_sirasi": ["kapak_03", "kapak_01", "kapak_02"],
        "sokum_plani": [{"parca": "kapak", "part_id": "kapak_02",
                         "eksen": "Y", "aci_deg": -30.0, "yon": "+Z",
                         "lift_vox": 0}],
    }


def _gecmis_html(app, nr):
    fn = app.config["GECMIS_KAYDET_FN"]
    kayit = fn({"ranked_orders": [], "batches": [],
                "nesting_results": {"B001": nr},
                "pricing_results": {}, "elapsed_sec": 0.0},
               mod="auto", kaynak="manuel")[0]
    return app.test_client().get(f"/gecmis/{kayit['id']}").data.decode("utf-8")


class TestGecmisDetayKonsol:
    def test_kimlikli_kayit_konsol_render(self, app_llm):
        html = _gecmis_html(app_llm, _nr_konsollu())
        # P2: ortak modul import edilir
        assert "viewer3d.js" in html
        assert "sokum_konsol.js" in html
        # P3: siparis ozet kartlari (musteri + sayilar)
        assert "sk-ozet" in html
        assert "ACME" in html and "BETA" in html
        assert "söküm-planlı" in html
        # P6: sokum plani sira rozeti (kapak_02 siranin 3.su)
        assert "sira 3/3" in html
        assert "kapak_02" in html

    def test_eski_kayit_konsol_gizli(self, app_llm):
        eski_nr = {"height_mm": 42.0, "density": 0.5, "n_parts": 3,
                   "pitch_mm": 2.0}
        html = _gecmis_html(app_llm, eski_nr)
        assert "sk-ozet" not in html
        assert 'id="sk-data-' not in html   # JS'teki string literal sayilmaz
        assert "Sokum Plani" not in html


class TestSonucKonsol:
    def _sonuc_html(self, app, nr):
        app.config["LAST_RESULT"] = {
            "ranked_orders": [], "warnings": [],
            "batches": [NS(batch_id="B001", customer="ACME",
                           oversized=False, orders=[],
                           total_volume_cm3=0.0)],
            "nesting_results": {"B001": nr},
            "pricing_results": {"B001": {"total_price": 1.0,
                                         "breakdown": []}},
            "elapsed_sec": 0.0, "used_demo": True,
        }
        return app.test_client().get("/sonuc").data.decode("utf-8")

    def test_sonuc_konsol_paritesi(self, app_llm):
        html = self._sonuc_html(app_llm, _nr_konsollu())
        # P2/P6: ayni modul + konsol verisi + tam ekran
        assert "viewer3d.js" in html
        assert "sokum_konsol.js" in html
        assert 'id="sk-data-B001"' in html
        assert "parca_uid" in html            # veri JSON'u gomulu
        assert "gd-fs-btn" in html            # tam ekran (bedava kazanim)
        # P3: ozet kartlari
        assert "sk-ozet" in html and "ACME" in html
        # P6: Sokum Plani bolumu sonuc.html'de de var
        assert "Sokum Plani" in html
        assert "sira 3/3" in html

    def test_sonuc_eski_alansiz_gizli(self, app_llm):
        html = self._sonuc_html(app_llm, {"height_mm": 42.0, "density": 0.5,
                                          "n_parts": 3, "pitch_mm": 2.0})
        assert 'id="sk-data-' not in html   # JS'teki string literal sayilmaz
        assert "sk-ozet" not in html
        assert "Sokum Plani" not in html

"""test_rehberli_sokum.py — Rehberli Sokum (cevrimdisi HTML) TDD.

Kapsam:
  (a) build_rehberli_sokum_html paketleyici: veri + GLB gomulu, yer
      tutucular kalmiyor.
  (b) sablon dosyasinda 5 yon icin hazir Turkce talimat metinleri var.
  (c) webapp route: gecerli kayit -> 200 + text/html; veri/GLB eksik -> 404.
  (d) sokum_veri_hazirla: nesting sonucundan veri sozlesmesi + eksik
      "yon" alaninda cokmeden varsayilana dusme.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.rehberli_sokum import build_rehberli_sokum_html


_TEMPLATE_PATH = (
    _ROOT / "src" / "webapp" / "static" / "rehberli_sokum_template.html"
)


def _ornek_veri():
    return {
        "meta": {
            "etiket": "plan7_488p4", "yukseklik_mm": 488.4, "n_parca": 2,
            "clearance_mm": 2.0, "n_duz": 1, "n_dondurmeli": 1,
            "uretim_notu": "nesting motoru, 2026-07-26",
        },
        "siparisler": [{"id": "SIP-1", "musteri": "Test Musteri"}],
        "adimlar": [
            {
                "sira": 1, "part_id": "174100686-a_08", "ad": "174100686-a",
                "kopya": 8, "siparis": None, "yontem": "duz", "yon": "+Z",
                "dondurme": None, "node": "174100686-a_08",
            },
            {
                "sira": 2, "part_id": "174100684-a_18", "ad": "174100684-a",
                "kopya": 18, "siparis": None, "yontem": "dondurmeli",
                "yon": "+X",
                "dondurme": {"eksen": "Z", "aci_deg": 1.0, "lift_mm": 0.0},
                "node": "174100684-a_18",
            },
        ],
        "kilitli": [],
    }


class TestPaketleyici:
    def test_veri_ve_glb_gomulu_yer_tutucu_kalmiyor(self):
        veri = _ornek_veri()
        glb_bytes = b"sahte-glb-icerik-0123456789"
        html = build_rehberli_sokum_html(veri, glb_bytes)

        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        # Yer tutucular tamamen degistirilmis olmali
        for placeholder in (
            "__VERI_JSON__", "__GLB_BASE64__", "__THREE_JS_B64__",
            "__GLTFLOADER_JS_B64__", "__ORBITCONTROLS_JS_B64__",
        ):
            assert placeholder not in html

        # Veri alanlari JSON olarak gomulu
        assert "174100686-a_08" in html
        assert "plan7_488p4" in html

        # GLB base64'u gomulu (dogrudan bytes'i base64'e cevirip ara)
        b64 = base64.b64encode(glb_bytes).decode("ascii")
        assert b64 in html

    def test_three_js_kaynagi_gomulu(self):
        veri = _ornek_veri()
        html = build_rehberli_sokum_html(veri, b"x")
        # 2026-07-26 duman testi dersi: data:-URI import-map file://'da BOS
        # SAYFA verdi -> blob-URL dinamik import zinciri. Yer tutucular dolu,
        # blob mekanizmasi + gorunur hata kaplamasi gomulu olmali.
        assert "__THREE_JS_B64__" not in html          # yer tutucu dolduruldu
        assert "URL.createObjectURL" in html            # blob zinciri
        assert "__rehberBaslat" in html                 # yukleme -> uygulama
        assert "hata-kaplama" in html                   # sessiz bos sayfa yasak
        assert "importmap" not in html                  # eski mekanizma kalkti

    def test_bos_adimlar_cokmuyor(self):
        veri = {"meta": {}, "siparisler": [], "adimlar": [], "kilitli": []}
        html = build_rehberli_sokum_html(veri, b"")
        assert "<!DOCTYPE html>" in html

    def test_script_kapatma_enjeksiyonu_kaciriliyor(self):
        """Veri icinde '</script' gecerse HTML parcalanmamali (kacirilmis olmali)."""
        veri = _ornek_veri()
        veri["meta"]["uretim_notu"] = "zararli</script><script>alert(1)</script>"
        html = build_rehberli_sokum_html(veri, b"x")
        assert "<script>alert(1)</script>" not in html
        assert "<\\/script" in html


class TestSablonYonMetinleri:
    """(b) 5 yon icin hazir Turkce talimat metinleri sablon dosyasinda var."""

    def test_sablon_dosyasi_var(self):
        assert _TEMPLATE_PATH.exists()

    @pytest.mark.parametrize("yon", ["+X", "-X", "+Y", "-Y", "+Z"])
    def test_yon_anahtari_sozlukte_var(self, yon):
        metin = _TEMPLATE_PATH.read_text(encoding="utf-8")
        assert f"'{yon}':" in metin

    def test_duz_z_metni_yukari_cek(self):
        metin = _TEMPLATE_PATH.read_text(encoding="utf-8")
        assert "Dogrudan yukari cekin" in metin

    def test_yatay_yon_metni_kenara_kaydir(self):
        metin = _TEMPLATE_PATH.read_text(encoding="utf-8")
        assert "kenara kaydirin" in metin

    def test_dondurmeli_dinamik_sablon_var(self):
        metin = _TEMPLATE_PATH.read_text(encoding="utf-8")
        assert "ekseni etrafinda" in metin


class TestSokumVeriHazirla:
    def test_duz_ve_dondurmeli_karisik(self):
        from src.runtime.sokum_veri import sokum_veri_hazirla

        kayit = {"id": "abc123", "musteri": "Test Co.", "zaman": "2026-07-26T10:00:00"}
        nr = {
            "height_mm": 300.5,
            "n_parts": 2,
            "parca_kimlik": {
                "p1": {"ad": "braket", "kopya_no": 3, "order_id": "SIP-1"},
                "p2": {"ad": "kapak", "kopya_no": 1, "order_id": "SIP-1"},
            },
            "sokum_sirasi": ["p1", "p2"],
            "sokum_plani": [
                {"part_id": "p2", "parca": "kapak", "eksen": "Z",
                 "aci_deg": 2.0, "yon": "+X", "lift_vox": 1.0},
            ],
            "siparis_ozeti": [{"order_id": "SIP-1", "musteri": "Test Co.", "n_parca": 2}],
        }
        veri = sokum_veri_hazirla(kayit, nr)
        assert veri["meta"]["n_duz"] == 1
        assert veri["meta"]["n_dondurmeli"] == 1
        assert len(veri["adimlar"]) == 2
        duz = veri["adimlar"][0]
        assert duz["yontem"] == "duz"
        assert duz["yon"] == "+Z"  # varsayilan (yon alani gelmedi)
        dondurmeli = veri["adimlar"][1]
        assert dondurmeli["yontem"] == "dondurmeli"
        assert dondurmeli["dondurme"]["eksen"] == "Z"

    def test_sokum_sirasi_dict_girdisinde_yon_okunur(self):
        """sokum_sirasi ogesi dict ise ({'part_id':..,'yon':..}) yon alinir."""
        from src.runtime.sokum_veri import sokum_veri_hazirla

        kayit = {"id": "abc", "musteri": "X", "zaman": "2026-07-26"}
        nr = {
            "height_mm": 100.0, "n_parts": 1,
            "parca_kimlik": {"p1": {"ad": "parca", "kopya_no": 1, "order_id": None}},
            "sokum_sirasi": [{"part_id": "p1", "yon": "+X"}],
        }
        veri = sokum_veri_hazirla(kayit, nr)
        assert veri["adimlar"][0]["yon"] == "+X"

    def test_sokum_sirasi_yon_alani_yoksa_z_varsayilan_cokmez(self):
        from src.runtime.sokum_veri import sokum_veri_hazirla

        kayit = {"id": "abc", "musteri": "X", "zaman": "2026-07-26"}
        nr = {
            "height_mm": 100.0, "n_parts": 1,
            "parca_kimlik": {"p1": {"ad": "parca", "kopya_no": 1, "order_id": None}},
            "sokum_sirasi": ["p1"],  # duz string, yon alani yok
        }
        veri = sokum_veri_hazirla(kayit, nr)
        assert veri["adimlar"][0]["yon"] == "+Z"


# ---------------------------------------------------------------------------
# (c) Webapp route
# ---------------------------------------------------------------------------

@pytest.fixture
def client_no_llm():
    from src.webapp.app import create_app
    app = create_app(testing=True, llm_enabled=False)
    return app, app.test_client()


def _sahte_glb_bytes():
    trimesh = pytest.importorskip("trimesh")
    box = trimesh.creation.box(extents=(10, 10, 10))
    scene = trimesh.Scene()
    scene.add_geometry(box, node_name="p1_01")
    return scene.export(file_type="glb")


class TestRehberliSokumRoute:
    def _kayit_ekle(self, app, *, sokum_var=True, glb_var=True):
        store = app.config["OTONOM_GECMIS"]
        kayit = store.kaydet({"musteri": "Test Co.", "durum": "bitti"})
        kayit_id = kayit["id"]
        nr = {
            "height_mm": 120.0, "n_parts": 1,
            "parca_kimlik": {"p1": {"ad": "braket", "kopya_no": 1, "order_id": None}},
            "siparis_ozeti": [],
        }
        if sokum_var:
            nr["sokum_sirasi"] = ["p1"]
        detay = {"nesting_results": {"b1": nr}, "pricing_results": {}}
        store.detay_kaydet(kayit_id, detay)
        if glb_var:
            store.glb_kaydet(kayit_id, "b1", _sahte_glb_bytes())
        return kayit_id

    def test_gecerli_kayit_200_html(self, client_no_llm):
        app, client = client_no_llm
        kayit_id = self._kayit_ekle(app)
        resp = client.get(f"/gecmis/{kayit_id}/rehberli-sokum")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        html = resp.data.decode("utf-8")
        assert "<!DOCTYPE html>" in html
        assert "braket" in html

    def test_bilinmeyen_kayit_404(self, client_no_llm):
        _, client = client_no_llm
        resp = client.get("/gecmis/0123456789ab/rehberli-sokum")
        assert resp.status_code == 404

    def test_sokum_sirasi_yoksa_404(self, client_no_llm):
        app, client = client_no_llm
        kayit_id = self._kayit_ekle(app, sokum_var=False)
        resp = client.get(f"/gecmis/{kayit_id}/rehberli-sokum")
        assert resp.status_code == 404

    def test_glb_yoksa_404(self, client_no_llm):
        app, client = client_no_llm
        kayit_id = self._kayit_ekle(app, glb_var=False)
        resp = client.get(f"/gecmis/{kayit_id}/rehberli-sokum")
        assert resp.status_code == 404

    def test_gecersiz_id_formati_404(self, client_no_llm):
        _, client = client_no_llm
        resp = client.get("/gecmis/../../etc/rehberli-sokum")
        assert resp.status_code == 404

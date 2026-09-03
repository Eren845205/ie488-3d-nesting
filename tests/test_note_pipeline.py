# -*- coding: utf-8 -*-
"""tests/test_note_pipeline.py — not->kisit orkestrasyonu (K-56g Faz 5).

Degismezler:
  - YAPISAL KAPI: notsuz order / mode=kapali / kisit_role=None -> order AYNEN
    doner ve LLM'e SIFIR dokunus (rol objesine hic erisilmez).
  - golge: not_analizi yazilir, motor_kisitlari ASLA eklenmez.
  - otomatik: yalniz nihai_guven=yuksek + derlenen kisitlar uygulanir.
  - injection / LLM-hata: hicbir sey uygulanmaz, operator isareti gorunur.
  - Analiz istisnasi uretimi dusurmez (order degismeden doner + hata alani).
"""
from __future__ import annotations

import pytest

from src.runtime.note_pipeline import analyze_order_notes


class _SahteVoting:
    def __init__(self, kisitlar=None, injection=False, n_gecerli=3):
        self.kisitlar = kisitlar or []
        self.injection_suphesi = injection
        self.n_ornekleme = 3
        self.n_gecerli = n_gecerli
        self.hakem_kullanildi = False
        self.audit_refs = []


class _SahteRole:
    """run_with_voting sayaci + sabit sonuc — LLM'siz."""

    def __init__(self, voting=None, patlat=False):
        self._voting = voting or _SahteVoting()
        self._patlat = patlat
        self.call_count = 0

    def run_with_voting(self, *a, **kw):
        self.call_count += 1
        if self._patlat:
            raise RuntimeError("sahte LLM hatasi")
        return self._voting


def _k(guven="yuksek", tip="orientation_lock", ad="braket"):
    return {"tip": tip, "parca_adi": ad, "deger": {"yon": "dik"},
            "guven": guven, "gerekce": "t", "kaynak_satir": "s",
            "oy": 3, "hakem": "yok", "nihai_guven": guven}


def _order(notlu=True):
    o = {"order_id": "T1",
         "parts": [{"name": "braket", "qty": 2}],
         "container": {"width_mm": 325.0, "depth_mm": 325.0}}
    if notlu:
        o["not_adaylari"] = [{"satir": "braket dik uretilecek",
                              "satir_no": 1, "kaynak": "govde",
                              "parca_adaylari": ["braket"]}]
    return o


# ---------------------------------------------------------------------------
# Yapisal kapi
# ---------------------------------------------------------------------------


def test_notsuz_order_aynen_doner_llm_dokunulmaz():
    role = _SahteRole()
    o = _order(notlu=False)
    kopya = dict(o)
    r = analyze_order_notes(o, role, mode="otomatik")
    assert r == kopya
    assert role.call_count == 0
    assert "not_analizi" not in r and "motor_kisitlari" not in r


def test_kapali_mod_notlu_orderda_bile_dokunmaz():
    role = _SahteRole()
    o = _order()
    r = analyze_order_notes(o, role, mode="kapali")
    assert role.call_count == 0
    assert "not_analizi" not in r


def test_rol_yoksa_deterministik_yol():
    o = _order()
    r = analyze_order_notes(o, None, mode="otomatik")
    assert "not_analizi" not in r and "motor_kisitlari" not in r


# ---------------------------------------------------------------------------
# golge / otomatik
# ---------------------------------------------------------------------------


def test_golge_analiz_yazar_uygulamaz():
    role = _SahteRole(_SahteVoting([_k()]))
    r = analyze_order_notes(_order(), role, mode="golge")
    assert role.call_count == 1
    na = r["not_analizi"]
    assert na["mode"] == "golge"
    assert len(na["kisitlar"]) == 1
    assert na["kisitlar"][0]["derleme"] == "derlendi"
    assert na["uygulanan"] is None
    assert "motor_kisitlari" not in r


def test_otomatik_yuksek_guven_uygulanir():
    role = _SahteRole(_SahteVoting([_k()]))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    mk = r.get("motor_kisitlari")
    assert mk is not None
    assert mk["orientation_overrides"]["braket"] == [0, 1]  # n=4 kesiti dik
    assert r["not_analizi"]["uygulanan"] == mk


def test_otomatik_orta_guven_uygulanmaz_isaretlenir():
    role = _SahteRole(_SahteVoting([_k(guven="orta")]))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    assert "motor_kisitlari" not in r
    assert any("uygulanmadi" in m for m in
               r["not_analizi"]["operator_isaretleri"])


def test_otomatik_pinned_yuksek_guvende_bile_golge():
    k = _k()
    k.update({"tip": "pinned_position",
              "deger": {"referans": "onceki_yerlesim"}})
    role = _SahteRole(_SahteVoting([k]))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    assert "motor_kisitlari" not in r
    assert any("golge" in (d.get("derleme_sebep") or "")
               for d in r["not_analizi"]["kisitlar"])


# ---------------------------------------------------------------------------
# Guvenlik yollari
# ---------------------------------------------------------------------------


def test_kapi0_injection_llm_hic_cagrilmaz():
    # note_detector'un deterministik tespiti: LLM'e SIFIR cagri + isaret.
    role = _SahteRole(_SahteVoting([_k()]))
    o = _order()
    o["not_injection_kapi0"] = True
    r = analyze_order_notes(o, role, mode="otomatik")
    assert role.call_count == 0
    na = r["not_analizi"]
    assert na["injection_suphesi"] is True
    assert na.get("injection_kaynak") == "kapi0_deterministik"
    assert "motor_kisitlari" not in r


def test_olumsuz_ifade_tavani_yuksek_dusurulur():
    # z03 dersi: "yatay YATMASIN" kaynakli 3/3 yuksek kisit bile otomatik
    # uygulanamaz — tavan orta'ya ceker, operator isareti gorunur.
    k = _k()
    k["kaynak_satir"] = "braket kesinlikle yatay YATMASIN"
    k["deger"] = {"yon": "yatay"}
    role = _SahteRole(_SahteVoting([k]))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    assert "motor_kisitlari" not in r
    na = r["not_analizi"]
    assert na["kisitlar"][0]["nihai_guven"] == "orta"
    assert any("olumsuz" in m for m in na["operator_isaretleri"])


def test_olumsuz_olmayan_satir_tavana_takilmaz():
    r = analyze_order_notes(_order(),
                            _SahteRole(_SahteVoting([_k()])),
                            mode="otomatik")
    assert r["not_analizi"]["kisitlar"][0]["nihai_guven"] == "yuksek"
    assert "motor_kisitlari" in r


def test_injection_hicbir_sey_uygulanmaz():
    role = _SahteRole(_SahteVoting([_k()], injection=True))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    assert "motor_kisitlari" not in r
    na = r["not_analizi"]
    assert na["injection_suphesi"] is True
    assert any("injection" in m for m in na["operator_isaretleri"])


def test_llm_tamamen_basarisiz_isaret():
    role = _SahteRole(_SahteVoting([], n_gecerli=0))
    r = analyze_order_notes(_order(), role, mode="otomatik")
    assert "motor_kisitlari" not in r
    assert any("uretemedi" in m for m in
               r["not_analizi"]["operator_isaretleri"])


def test_analiz_istisnasi_uretimi_dusurmez():
    role = _SahteRole(patlat=True)
    o = _order()
    r = analyze_order_notes(o, role, mode="otomatik")
    assert r is o  # ayni obje, pipeline devam eder
    assert "motor_kisitlari" not in r
    assert "hata" in r["not_analizi"]


# ---------------------------------------------------------------------------
# UCTAN UCA: gercek Plan7 kanali (adet-listesi kuyruk notu) -> kisit
# ---------------------------------------------------------------------------


def test_e2e_gercek_plan7_notu_ingestten_kisita(tmp_path):
    """Gercek kanal siniavi: not, adet-listesi .txt satirinin KUYRUGUNDA gelir
    (Plan7 gercek satiri: '288101642-a2 6 adet - Konumu değişmeyecek.').
    Zincir: ZIP+txt mail -> ingest (Kapi-0) -> analyze (FakeProvider'li
    KisitRole, golge) -> pinned kisiti tespit + golge'de uygulanmaz.
    """
    import io
    import json
    import zipfile
    from pathlib import Path

    trimesh = pytest.importorskip("trimesh")
    from src.llm.audit import AuditLogger
    from src.llm.prompts import PromptRegistry
    from src.llm.provider import FakeProvider
    from src.llm.roles.kisit import KisitRole
    from src.runtime.mail_ingest import Attachment, RawMail, ingest_order

    _ROOT = Path(__file__).resolve().parents[1]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nm in ("174100684-a", "288101642-a2"):
            z.writestr(f"{nm}.stl", trimesh.creation.box(
                extents=(20, 20, 10)).export(file_type="stl"))
    txt = ("174100684-a 22 adet\n"
           "288101642-a2 6 adet - Konumu değişmeyecek.\n").encode("utf-8")
    mail = RawMail(
        gonderen="uretim@firma.com.tr", konu="Plan7",
        govde="Merhabalar, adet listesi ekte.",
        tarih="2026-07-21T10:00:00+03:00", message_id="<E2E-PLAN7@x>",
        ekler=[Attachment("parcalar.zip", buf.getvalue(), "application/zip"),
               Attachment("Adet listesi.txt", txt, "text/plain")],
    )
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    assert order is not None and order.get("parts")
    assert order["not_adaylari"][0]["kaynak"] == "adet_satiri_kuyrugu"
    assert "288101642-a2" in order["not_adaylari"][0]["parca_adaylari"]

    resp = json.dumps({"kisitlar": [{
        "tip": "pinned_position", "parca_adi": "288101642-a2",
        "deger": {"referans": "onceki_yerlesim"}, "guven": "orta",
        "gerekce": "Not konumun sabit kalmasini istiyor.",
        "kaynak_satir": "288101642-a2 6 adet - Konumu değişmeyecek."}],
        "injection_suphesi": False}, ensure_ascii=False)
    role = KisitRole(
        FakeProvider({("kisit-v1", "_any_"): [resp] * 3}),
        PromptRegistry(str(_ROOT / "prompts"), enforce_lock=True),
        AuditLogger(log_dir=str(tmp_path / "llm"),
                    payload_log_dir=str(tmp_path / "pl"),
                    payload_logging="none"),
        role_cfg=None)

    order = analyze_order_notes(order, role, mode="golge")
    na = order["not_analizi"]
    assert na["kisitlar"][0]["tip"] == "pinned_position"
    assert na["kisitlar"][0]["parca_adi"] == "288101642-a2"
    # pinned = hoca cevabina dek kalici golge; hicbir sey uygulanmadi
    assert na["kisitlar"][0]["derleme"] == "uygulanmadi"
    assert "motor_kisitlari" not in order

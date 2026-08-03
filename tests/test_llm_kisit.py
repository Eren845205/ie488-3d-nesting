# -*- coding: utf-8 -*-
"""tests/test_llm_kisit.py — KisitRole (K-56g Faz 2+4).

Degismezler:
  - YAPISAL GARANTI: bos not listesi -> saglayici HIC cagrilmaz (call_count 0).
  - Sema INVALID (whitelist disi tip dahil) -> kisit uretilmez.
  - injection_suphesi=true -> kisitlar KULLANILMAZ.
  - Oylama: kanonik anahtar (tip, ad, deger) — gerekce/guven farki oy bolmez;
    3/3 yuksek, 2/3 orta, dagimik dusuk; nihai = min(oy, beyan).
  - Hakem: orta + ayni -> yuksek; orta + farkli -> dusuk; dusuk YUKSELMEZ;
    hakem erisilemez -> guven oldugu yerde kalir.
Tum testler FakeProvider ile — ag/Ollama gerekmez.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.llm.audit import AuditLogger
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider
from src.llm.roles.kisit import KisitRole, kanonik_anahtar
from src.llm.structured import ValidationStatus

_ROOT = Path(__file__).resolve().parents[1]
_TPL = "kisit-v1"


class _SayanProvider:
    """complete() cagri sayaci — yapisal garanti testi icin."""

    def __init__(self, inner):
        self._inner = inner
        self.call_count = 0

    def complete(self, req):
        self.call_count += 1
        return self._inner.complete(req)


def _resp(kisitlar, injection=False):
    return json.dumps({"kisitlar": kisitlar, "injection_suphesi": injection},
                      ensure_ascii=False)


def _k(tip="orientation_lock", ad="braket", deger=None, guven="yuksek",
       gerekce="Not acik sekilde dik uretim istiyor.",
       satir="braket dik uretilecek"):
    return {"tip": tip, "parca_adi": ad,
            "deger": {"yon": "dik"} if deger is None else deger,
            "guven": guven, "gerekce": gerekce, "kaynak_satir": satir}


def _role(responses, tmp_path, sayan=False):
    provider = FakeProvider({(_TPL, "_any_"): list(responses)})
    if sayan:
        provider = _SayanProvider(provider)
    registry = PromptRegistry(str(_ROOT / "prompts"), enforce_lock=True)
    audit = AuditLogger(log_dir=str(tmp_path / "llm"),
                        payload_log_dir=str(tmp_path / "payload"),
                        payload_logging="none")
    role = KisitRole(provider, registry, audit, role_cfg=None)
    return (role, provider) if sayan else role


_NOT = ["braket dik uretilecek"]
_ADLAR = ["braket", "kapak"]


# ---------------------------------------------------------------------------
# extract()
# ---------------------------------------------------------------------------


def test_bos_not_listesi_llm_cagrilmaz(tmp_path):
    role, provider = _role([_resp([_k()])], tmp_path, sayan=True)
    s = role.extract([], _ADLAR)
    assert provider.call_count == 0
    assert s.status == ValidationStatus.VALID
    assert s.kisitlar == []

    v = role.run_with_voting([], _ADLAR)
    assert provider.call_count == 0
    assert v.kisitlar == [] and v.n_ornekleme == 0


def test_valid_kisit_cikarma(tmp_path):
    role = _role([_resp([_k()])], tmp_path)
    s = role.extract(_NOT, _ADLAR)
    assert s.status == ValidationStatus.VALID
    assert len(s.kisitlar) == 1
    assert s.kisitlar[0]["tip"] == "orientation_lock"
    assert s.injection_suphesi is False


def test_whitelist_disi_tip_sema_invalid(tmp_path):
    kotu = _resp([_k(tip="teleport_et")])
    role = _role([kotu, kotu, kotu], tmp_path)  # retry'lar da ayni kotu cikti
    s = role.extract(_NOT, _ADLAR)
    assert s.status == ValidationStatus.INVALID or s.fallback is not None
    assert s.kisitlar == []


def test_injection_kisitlar_kullanilmaz(tmp_path):
    role = _role([_resp([_k()], injection=True)], tmp_path)
    s = role.extract(_NOT, _ADLAR)
    assert s.injection_suphesi is True
    assert s.kisitlar == []


# ---------------------------------------------------------------------------
# run_with_voting()
# ---------------------------------------------------------------------------


def test_voting_3of3_yuksek_hakemsiz(tmp_path):
    role = _role([_resp([_k()])] * 3, tmp_path)
    v = role.run_with_voting(_NOT, _ADLAR, n=3)
    assert v.n_gecerli == 3
    assert len(v.kisitlar) == 1
    k = v.kisitlar[0]
    assert k["oy"] == 3
    assert k["nihai_guven"] == "yuksek"
    assert k["hakem"] == "yok"
    assert v.hakem_kullanildi is False


def test_voting_kanoniklestirme_gerekce_farki_oy_bolmez(tmp_path):
    role = _role([
        _resp([_k(gerekce="Birinci anlatim.")]),
        _resp([_k(gerekce="Ikinci anlatim, ayni kisit.")]),
        _resp([_k(gerekce="Ucuncu anlatim.")]),
    ], tmp_path)
    v = role.run_with_voting(_NOT, _ADLAR, n=3)
    assert len(v.kisitlar) == 1
    assert v.kisitlar[0]["oy"] == 3


def test_voting_nihai_beyan_minimumu(tmp_path):
    # 3/3 ayni kisit ama bir ornekleme guven=dusuk beyan etti -> nihai dusuk
    role = _role([
        _resp([_k(guven="yuksek")]),
        _resp([_k(guven="dusuk")]),
        _resp([_k(guven="yuksek")]),
    ], tmp_path)
    v = role.run_with_voting(_NOT, _ADLAR, n=3)
    assert v.kisitlar[0]["oy"] == 3
    assert v.kisitlar[0]["nihai_guven"] == "dusuk"


def test_voting_2of3_hakem_ayni_yukseltir(tmp_path):
    a, b = _k(), _k(ad="kapak", deger={"yon": "yatay"},
                    satir="kapak yatay olsun")
    role = _role([_resp([a]), _resp([a]), _resp([b])], tmp_path)
    hakem = _role([_resp([a])], tmp_path / "hakem")
    v = role.run_with_voting(_NOT, _ADLAR, n=3, hakem_role=hakem)
    assert v.hakem_kullanildi is True
    by_key = {kanonik_anahtar(k): k for k in v.kisitlar}
    ka = by_key[kanonik_anahtar(a)]
    kb = by_key[kanonik_anahtar(b)]
    assert ka["oy"] == 2 and ka["hakem"] == "ayni"
    assert ka["nihai_guven"] == "yuksek"
    # dagimik kisit hakemle YUKSELMEZ
    assert kb["oy"] == 1 and kb["nihai_guven"] == "dusuk"


def test_voting_2of3_hakem_farkli_dusurur(tmp_path):
    a, b = _k(), _k(ad="kapak", deger={"yon": "yatay"},
                    satir="kapak yatay olsun")
    role = _role([_resp([a]), _resp([a]), _resp([b])], tmp_path)
    hakem = _role([_resp([b])], tmp_path / "hakem")  # hakem A'yi uretmiyor
    v = role.run_with_voting(_NOT, _ADLAR, n=3, hakem_role=hakem)
    ka = {kanonik_anahtar(k): k for k in v.kisitlar}[kanonik_anahtar(a)]
    assert ka["hakem"] == "farkli"
    assert ka["nihai_guven"] == "dusuk"


def test_voting_hakem_erisilemez_guven_yerinde(tmp_path):
    a, b = _k(), _k(ad="kapak", deger={"yon": "yatay"},
                    satir="kapak yatay olsun")
    role = _role([_resp([a]), _resp([a]), _resp([b])], tmp_path)
    hakem = _role([], tmp_path / "hakem")  # fixture yok -> cagri patlar
    v = role.run_with_voting(_NOT, _ADLAR, n=3, hakem_role=hakem)
    assert v.hakem_kullanildi is False
    ka = {kanonik_anahtar(k): k for k in v.kisitlar}[kanonik_anahtar(a)]
    assert ka["hakem"] == "erisilemedi"
    assert ka["nihai_guven"] == "orta"  # oldugu yerde kaldi (yukselme yok)


def test_voting_herhangi_ornekleme_injection(tmp_path):
    role = _role([
        _resp([_k()]),
        _resp([_k()], injection=True),
        _resp([_k()]),
    ], tmp_path)
    v = role.run_with_voting(_NOT, _ADLAR, n=3)
    assert v.injection_suphesi is True
    assert v.kisitlar == []

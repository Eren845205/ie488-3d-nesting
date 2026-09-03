"""Kisit rolu — siparis-notu satirlari -> yapisal nesting kisitlari (K-56g).

Girdi  : {"not_satirlari": [str, ...], "parca_adlari": [str, ...]}
Cikti  : kisit-v1 semasi:
  kisitlar          : [{tip, parca_adi, deger, guven, gerekce, kaynak_satir}]
  injection_suphesi : bool

Tasarim sinirlari (K-56g plan):
  * LLM yalniz WHITELIST enum tip + SEMBOLIK deger uretir ({"yon": "dik"});
    poz indeksi / koordinat / motor parametresi ASLA — sayisal ceviri
    deterministik constraint_compiler'in isi.
  * Bu rol KENDI BASINA hicbir kisiti uygulamaz; cikti daima dogrulama +
    karar-politikasi katmanindan (note_pipeline) gecer.
  * injection_suphesi=true -> kisitlar KULLANILMAZ (parser deseni).

Oylama (Faz 4 — self-consistency + hakem eskalasyonu):
  * run_with_voting: ayni girdi N=3 bagimsiz orneklemeyle (temperature=0.7)
    ayristirilir; oy birimi TEK KISIT'tir — kanonik anahtar
    (tip, normalize(parca_adi), deger-json). guven/gerekce/kaynak_satir
    kanonik anahtara GIRMEZ.
  * Oy sinifi (n=3): 3/3 -> yuksek, 2/3 -> orta, 1/3 -> dusuk.
  * Nihai guven = min(oy sinifi, orneklemelerin beyan ettigi en dusuk guven).
  * HAKEM (Eren karari 2026-07-22 — bastan dahil): nihai guven yuksek DEGILSE
    hakem rolu (qwen2.5:7b, temp 0.0) ayni girdiyi BAGIMSIZ ayristirir.
    Politika: oy=orta + hakem AYNI kisiti uretti -> yuksek'e yukselt;
    hakem farkli/uretmedi -> dusuk. oy=dusuk hakemle YUKSELMEZ (operator
    isareti kalir). Hakem erisilemez/hata -> eskalasyon atlanir, guven
    oldugu yerde kalir (fail-safe: asla yukseltme yonunde varsayim yok).
  * Herhangi bir orneklemede injection_suphesi -> tum sonuc kullanilmaz.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.prompts import PromptRegistry
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import HumanFallback, ValidationStatus

logger = logging.getLogger(__name__)

# Whitelist: motorun gercekten tasiyabildigi kisit tipleri + belirsiz etiketi.
# Sema enum'uyla AYNI liste (cifte kilit: sema INVALID'ler, bu sabit ise
# semayi atlatan yollara karsi son savunma).
GECERLI_TIPLER = ("orientation_lock", "pinned_position",
                  "pinned_orientation", "belirsiz")

_VOTING_TEMPERATURE = 0.7
_GUVEN_SIRA = {"dusuk": 0, "orta": 1, "yuksek": 2}


def _kanonik_ad(ad: Any) -> str:
    """Oylama kanonik anahtari icin ad normalizasyonu (rol-ici tutarlilik).

    Alt cizgi KORUNUR (2026-08-18 gercek musteri verisi dersi): "kapak" ve
    "kapak_" iki AYRI parcadir; alt cizgiyi bosluga katlamak iki parcanin
    oylarini AYNI anahtarda birlestirip birinin kisitini sessizce dusuruyordu
    (dedup son-kazanan). quantity_text_parser._ham_name ile ayni ilke.
    """
    s = str(ad or "").casefold()
    return re.sub(r"\s+", " ", s).strip()


def kanonik_anahtar(kisit: Dict[str, Any]) -> Tuple[str, str, str]:
    """Tek kisitin oy-birligi anahtari: (tip, ad, deger). guven/gerekce/
    kaynak_satir bilerek DISARIDA (ayni kisitin farkli anlatimi ayni oydur)."""
    return (
        str(kisit.get("tip") or ""),
        _kanonik_ad(kisit.get("parca_adi")),
        json.dumps(kisit.get("deger"), sort_keys=True, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# Sonuc tipleri
# ---------------------------------------------------------------------------


@dataclass
class KisitSonucu:
    """Tek-atis extract() sonucu."""

    role_result: RoleResult
    kisitlar: List[Dict[str, Any]] = field(default_factory=list)
    injection_suphesi: bool = False

    @property
    def status(self) -> ValidationStatus:
        return self.role_result.status

    @property
    def fallback(self) -> Optional[HumanFallback]:
        return self.role_result.fallback

    @property
    def audit_ref(self) -> str:
        return self.role_result.audit_ref


@dataclass
class KisitOylamaSonucu:
    """run_with_voting() sonucu.

    kisitlar ogeleri sema alanlarina ek uc karar alani tasir:
      oy          : kac orneklemede gorundu (int)
      hakem       : "ayni" | "farkli" | "yok" | "erisilemedi"
      nihai_guven : "yuksek" | "orta" | "dusuk" (karar politikasi girdisi)
    """

    kisitlar: List[Dict[str, Any]] = field(default_factory=list)
    injection_suphesi: bool = False
    n_ornekleme: int = 0
    n_gecerli: int = 0
    hakem_kullanildi: bool = False
    audit_refs: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KisitRole
# ---------------------------------------------------------------------------


class KisitRole:
    """Siparis-notu satirlari -> yapisal kisit JSON'u.

    Parametreler
    ------------
    provider  : LLMProvider ornegi
    registry  : PromptRegistry ornegi
    audit     : AuditLogger ornegi
    role_cfg  : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "kisit"

    def __init__(
        self,
        provider: Any,
        registry: PromptRegistry,
        audit: AuditLogger,
        role_cfg: Optional[RoleConfig] = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._audit = audit
        self._role_cfg = role_cfg
        self._base_role = LLMRole(
            role_name=self.ROLE_NAME,
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=role_cfg,
        )

    # ------------------------------------------------------------------
    def extract(
        self,
        not_satirlari: List[str],
        parca_adlari: List[str],
        *,
        temperature: Optional[float] = None,
    ) -> KisitSonucu:
        """Not satirlarini tek atista ayristir.

        Bos not listesi -> LLM'e HIC gidilmez (Kapi-0'in rol-ici yedegi;
        asil yapisal kapi note_pipeline'dadir).
        """
        if not not_satirlari:
            dummy = RoleResult(
                status=ValidationStatus.VALID, data={"kisitlar": [],
                                                     "injection_suphesi": False},
                fallback=None, audit_ref="", attempt_count=0)
            return KisitSonucu(role_result=dummy)

        role = self._base_role
        if temperature is not None and self._role_cfg is not None:
            role = LLMRole(
                role_name=self.ROLE_NAME,
                provider=self._provider,
                registry=self._registry,
                audit=self._audit,
                role_cfg=dataclasses.replace(
                    self._role_cfg, temperature=temperature),
            )

        role_result = role.run({
            "not_satirlari": list(not_satirlari),
            "parca_adlari": list(parca_adlari),
        })

        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            logger.warning(
                "KisitRole: LLM gecerli kisit JSON'u uretemedi. audit_ref=%s",
                role_result.audit_ref)
            return KisitSonucu(role_result=role_result)

        data = role_result.data or {}
        injection = bool(data.get("injection_suphesi", False))
        ham = list(data.get("kisitlar") or [])
        # Cifte kilit: sema enum'unu atlatan tip son savunmada duser.
        kisitlar = [k for k in ham
                    if isinstance(k, dict) and k.get("tip") in GECERLI_TIPLER]
        if len(kisitlar) != len(ham):
            logger.warning(
                "KisitRole: whitelist disi %d kisit dusuruldu. audit_ref=%s",
                len(ham) - len(kisitlar), role_result.audit_ref)

        if injection:
            # Parser deseni: injection suphesinde cikti KULLANILMAZ.
            logger.warning(
                "KisitRole: injection_suphesi=true — kisitlar kullanilmayacak. "
                "audit_ref=%s", role_result.audit_ref)
            return KisitSonucu(role_result=role_result, kisitlar=[],
                               injection_suphesi=True)

        return KisitSonucu(role_result=role_result, kisitlar=kisitlar)

    # ------------------------------------------------------------------
    def run_with_voting(
        self,
        not_satirlari: List[str],
        parca_adlari: List[str],
        *,
        n: int = 3,
        hakem_role: Optional["KisitRole"] = None,
    ) -> KisitOylamaSonucu:
        """N bagimsiz ornekleme + cogunluk oyu + (gerekirse) hakem eskalasyonu.

        Oy sinifi (n=3): 3/3 yuksek, 2/3 orta, 1/3 dusuk. Nihai guven =
        min(oy sinifi, beyan edilen en dusuk guven). Hakem politikasi modul
        docstring'inde; hakem ancak YUKSELTMEYI orta->yuksek yonunde yapar,
        dusuk hakemle yukselmez.
        """
        if not not_satirlari:
            return KisitOylamaSonucu()

        oylar: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        injection = False
        n_gecerli = 0
        audit_refs: List[str] = []

        for _i in range(n):
            s = self.extract(not_satirlari, parca_adlari,
                             temperature=_VOTING_TEMPERATURE)
            if s.audit_ref:
                audit_refs.append(s.audit_ref)
            if s.injection_suphesi:
                injection = True
            if s.status == ValidationStatus.INVALID or s.fallback:
                continue
            n_gecerli += 1
            gorulen: set = set()
            for k in s.kisitlar:
                key = kanonik_anahtar(k)
                if key in gorulen:
                    continue  # ayni ornekleme ayni kisiti iki kez oylayamaz
                gorulen.add(key)
                kayit = oylar.setdefault(key, {"kisit": k, "oy": 0,
                                               "beyan_min": "yuksek"})
                kayit["oy"] += 1
                beyan = str(k.get("guven") or "dusuk")
                if _GUVEN_SIRA.get(beyan, 0) < _GUVEN_SIRA[kayit["beyan_min"]]:
                    kayit["beyan_min"] = beyan

        if injection:
            # Herhangi bir ornekleme supheliyse tum sonuc kullanilmaz.
            return KisitOylamaSonucu(
                kisitlar=[], injection_suphesi=True, n_ornekleme=n,
                n_gecerli=n_gecerli, audit_refs=audit_refs)

        # Oy siniflari (n_gecerli uzerinden — INVALID ornekleme oy havuzunu
        # kucultur, cogunluk esigi gecerli ornekleme sayisina gore kurulur).
        tam = max(1, n_gecerli)
        cogunluk = tam // 2 + 1

        def _oy_sinifi(oy: int) -> str:
            if oy >= tam:
                return "yuksek"
            if oy >= cogunluk:
                return "orta"
            return "dusuk"

        # Hakem eskalasyonu: yuksek olmayan kisit varsa TEK hakem ayristirmasi
        # (kisit basina degil — bir parse tum notlari kapsar).
        hakem_keys: Optional[set] = None
        hakem_kullanildi = False
        gerek_hakem = any(
            min(_GUVEN_SIRA[_oy_sinifi(v["oy"])],
                _GUVEN_SIRA[v["beyan_min"]]) < _GUVEN_SIRA["yuksek"]
            for v in oylar.values())
        if hakem_role is not None and gerek_hakem:
            try:
                hs = hakem_role.extract(not_satirlari, parca_adlari)
                if hs.audit_ref:
                    audit_refs.append(hs.audit_ref)
                if hs.injection_suphesi:
                    return KisitOylamaSonucu(
                        kisitlar=[], injection_suphesi=True, n_ornekleme=n,
                        n_gecerli=n_gecerli, audit_refs=audit_refs)
                if hs.status != ValidationStatus.INVALID and not hs.fallback:
                    hakem_keys = {kanonik_anahtar(k) for k in hs.kisitlar}
                    hakem_kullanildi = True
            except Exception:
                logger.warning(
                    "KisitRole: hakem eskalasyonu basarisiz — atlandi "
                    "(guven oldugu yerde kaldi).", exc_info=True)

        sonuc: List[Dict[str, Any]] = []
        for key, v in oylar.items():
            oy_sinif = _oy_sinifi(v["oy"])
            nihai = min(_GUVEN_SIRA[oy_sinif], _GUVEN_SIRA[v["beyan_min"]])
            hakem_durum = "yok"
            if hakem_keys is not None:
                hakem_durum = "ayni" if key in hakem_keys else "farkli"
                if nihai == _GUVEN_SIRA["orta"]:
                    # orta + hakem ayni -> yuksek; hakem farkli -> dusuk
                    nihai = (_GUVEN_SIRA["yuksek"] if hakem_durum == "ayni"
                             else _GUVEN_SIRA["dusuk"])
                # dusuk hakemle YUKSELMEZ (politika: operator isareti kalir)
            elif hakem_role is not None and gerek_hakem:
                hakem_durum = "erisilemedi"
            k = dict(v["kisit"])
            k["oy"] = v["oy"]
            k["hakem"] = hakem_durum
            k["nihai_guven"] = [g for g, s in _GUVEN_SIRA.items()
                                if s == nihai][0]
            sonuc.append(k)

        # Deterministik sira (raporlama + testler): once en yuksek oy.
        sonuc.sort(key=lambda k: (-int(k["oy"]), kanonik_anahtar(k)))

        return KisitOylamaSonucu(
            kisitlar=sonuc, injection_suphesi=False, n_ornekleme=n,
            n_gecerli=n_gecerli, hakem_kullanildi=hakem_kullanildi,
            audit_refs=audit_refs)

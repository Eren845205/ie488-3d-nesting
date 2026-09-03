"""not_onay.py — Siparis notu icin operator-onay kapisi (2026-08-16, Eren istegi).

Akis: mail'den TAM siparis (adetleri belli) cikti ve siparis notu tespit
edildiyse, pipeline'a sokulmadan ONCE bekleyen-onay deposuna park edilir.
Operator /kisit-onay'dan (veya sag-alt baloncuktan) onay verince siparis
OTOMATIK kosulur. Anahtar "not_onay_iste" (configs/app_ayarlar.json,
varsayilan ACIK) kapatilirsa kapi devre disi kalir ve kisit hattinin
"otomatik" modu devreye girer (yalniz yuksek guvenli istekler uygulanir).

Hem webapp (otonom buton) hem mail_poller (Auto Mode) ayni kapiyi kullanir.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
AYAR_PATH = _ROOT / "configs" / "app_ayarlar.json"

# Bekleyen depoda not-onay parkini isaretleyen review_reason degeri.
NOT_ONAY_REASON = "not_onayi"


def ayarlari_oku() -> Dict[str, Any]:
    """configs/app_ayarlar.json icerigi (yoksa/bozuksa bos dict)."""
    try:
        return json.loads(AYAR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ayar_yaz(anahtar: str, deger: Any) -> None:
    """Tek anahtari kalici yaz (dosya yoksa olusturur)."""
    ayar = ayarlari_oku()
    ayar[anahtar] = deger
    AYAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    AYAR_PATH.write_text(
        json.dumps(ayar, ensure_ascii=False, indent=2), encoding="utf-8")


def not_onay_iste() -> bool:
    """Notlu siparis operator onayina dussun mu? Varsayilan ACIK."""
    return bool(ayarlari_oku().get("not_onay_iste", True))


def efektif_kisit_modu(kisit_modu: str) -> str:
    """Onay kapisi KAPALIYSA golge yerine otomatik mod kullanilir.

    kapali -> kapali (kisit hatti tumden kapali; anahtar bunu ezmez).
    golge  -> operator onayi acikken golge (oneriler uretilir, uygulanmaz);
              onay kapisi kapatildiysa "otomatik" (yalniz yuksek guven).
    """
    if kisit_modu == "golge" and not not_onay_iste():
        return "otomatik"
    return kisit_modu


def not_onay_gerekli(order: Dict[str, Any]) -> bool:
    """Bu TAM siparis onaya park edilmeli mi?"""
    return bool(order.get("not_adaylari")) and not_onay_iste()


def notlu_siparisi_beklet(
    pending_store: Any,
    order: Dict[str, Any],
    mail: Any,
    *,
    mail_idem_key: Optional[str] = None,
) -> Optional[str]:
    """Notlu TAM siparisi bekleyen-onay deposuna park et.

    Adetler order["parts"]'tan (kaynak STL adi stem'iyle) meta'ya
    `not_onay_quantities` olarak yazilir; onay sonrasi kosu bu adetlerle
    adet-gir makinesini kullanir. Golge analiz calistiysa oneriler de
    (`kisit_onerileri`) meta'ya tasinir ki baloncuk tek tikla onay sunsun.

    Basarili park -> order_id; store yok / STL okunamadi -> None
    (cagiran siparisi NORMAL akista birakmalidir — siparis kaybolmaz).
    """
    if pending_store is None:
        return None
    parts = order.get("parts") or []
    if not parts:
        return None

    stl_map: Dict[str, bytes] = {}
    quantities: Dict[str, int] = {}
    try:
        for p in parts:
            ad = p.get("kaynak_ad") or p.get("name") or ""
            yol = p.get("stl_path")
            if not ad or not yol:
                return None
            stl_map[ad] = Path(yol).read_bytes()
            quantities[Path(ad).stem] = int(p.get("qty") or 0)
    except OSError as exc:
        logger.warning("not_onay: STL okunamadi, park iptal (%s): %s",
                       order.get("order_id"), exc)
        return None
    if not any(q > 0 for q in quantities.values()):
        return None

    try:
        park_id = pending_store.add(
            order_id=order.get("order_id", ""),
            customer=order.get("customer", ""),
            sender=getattr(mail, "gonderen", ""),
            deadline=order.get("deadline", ""),
            priority_class=order.get("priority_class", 2),
            konu=getattr(mail, "konu", ""),
            stl_map=stl_map,
            container=order.get("container"),
            review_reason=NOT_ONAY_REASON,
            not_adaylari=order.get("not_adaylari"),
            govde_metni=order.get("govde_metni"),
        )
    except Exception as exc:  # park edilemedi -> normal akis
        logger.warning("not_onay: bekleyen siparis kaydedilemedi (%s): %s",
                       order.get("order_id"), exc)
        return None

    ekstra: Dict[str, Any] = {"not_onay_quantities": quantities,
                              "kaynak_tip": "mail"}
    if mail_idem_key:
        # "Gecmisten sil -> yeniden islensin" zinciri: onay-sonrasi kosunun
        # gecmis kaydi bu anahtari _idem_keys olarak tasir (2026-08-18 fix).
        ekstra["mail_idem_key"] = mail_idem_key
    na = order.get("not_analizi") or {}
    if na.get("kisitlar"):
        ekstra["kisit_onerileri"] = na["kisitlar"]
    try:
        pending_store.update_meta(park_id, **ekstra)
    except Exception:
        logger.warning("not_onay: meta guncellenemedi (%s)", park_id,
                       exc_info=True)
    logger.info("not_onay: siparis onaya parklandi id=%s (%d not, %d STL)",
                park_id, len(order.get("not_adaylari") or []), len(stl_map))
    return park_id

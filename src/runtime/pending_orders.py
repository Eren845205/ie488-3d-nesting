"""src/runtime/pending_orders.py — Eksik-bilgi (adet yok) siparis deposu.

ZIP ekinde GECERLI STL var ama mail govdesinde ADET yoksa siparis otomatik
ISLENMEZ (karar: operatore sor/beklet). Bu store STL byte'larini + siparis
meta'sini diske yazar; operator /adet-gir ekranindan adetleri girince siparis
yeniden kurulup pipeline'a sokulur.

Dizin duzeni
------------
  <root>/<order_id>/
      meta.json     -> {order_id, customer, sender, deadline, priority_class,
                        konu, stl_names, container, created_tag}
      <ad>.stl      -> bekleyen her STL dosyasi (adi guvenli basename)

Saf dosya-tabanli (sqlite gerekmez) — tek-operator/tek-sunucu demo icin yeterli.
Postgres/coklu-operator gerekirse arayuz korunup arka uc degistirilebilir.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_META = "meta.json"


def _safe_id(order_id: str) -> str:
    """order_id'yi guvenli klasor adina cevir (path-traversal engelle)."""
    base = os.path.basename(str(order_id)).strip()
    # Yalniz alfasayisal + tire/altcizgi/nokta birak
    cleaned = "".join(c for c in base if c.isalnum() or c in "-_.")
    return cleaned or "order"


class PendingOrderStore:
    """Eksik-bilgi siparislerinin dosya-tabanli deposu."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------------
    def add(
        self,
        *,
        order_id: str,
        customer: str,
        sender: str,
        deadline: str,
        priority_class: int,
        konu: str,
        stl_map: Dict[str, bytes],
        container: Optional[Dict[str, Any]] = None,
        review_reason: str = "",
        share_links: Optional[List[str]] = None,
        adet_listesi: Optional[Dict[str, int]] = None,
        not_adaylari: Optional[List[Dict[str, Any]]] = None,
        govde_metni: Optional[str] = None,
    ) -> str:
        """Bekleyen siparisi (STL'ler + meta) diske yaz. order_id (guvenli) doner.

        Ayni order_id ile tekrar cagrilirsa USTUNE yazar (idempotent — ayni mail
        iki kez islenirse cogalmaz).

        review_reason/share_links/adet_listesi: dosya-paylasim-linkli siparisler
        icin (STL'ler mail ekinde degil linkte — operator indirir). Additive;
        eski cagiranlar vermeyebilir (geriye uyum, default bos).

        not_adaylari/govde_metni (K-56g): siparis-notu tespiti (note_detector)
        ciktisi + ham govde — /kisit-onay operator yuzeyini besler. Additive;
        YALNIZ doluysa meta.json'a yazilir (notsuz meta bit-ozdes eski sekil).
        """
        sid = _safe_id(order_id)
        d = self.root / sid
        # Temiz baslangic (idempotency): varsa eski klasoru sil
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)

        stl_names: List[str] = []
        for name, data in stl_map.items():
            safe = os.path.basename(str(name)) or "part"
            (d / f"{safe}.stl").write_bytes(data)
            stl_names.append(safe)
        stl_names.sort()

        meta = {
            "order_id": sid,
            "customer": customer,
            "sender": sender,
            "deadline": deadline,
            "priority_class": int(priority_class),
            "konu": konu,
            "stl_names": stl_names,
            "container": container,
            "review_reason": review_reason or "",
            "share_links": list(share_links or []),
            "adet_listesi": dict(adet_listesi or {}),
        }
        # K-56g: not alanlari YALNIZ doluysa yazilir (notsuz meta bit-ozdes).
        if not_adaylari:
            meta["not_adaylari"] = list(not_adaylari)
            meta["govde_metni"] = (govde_metni or "")[:20480]
        (d / _META).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "PendingOrderStore: bekleyen siparis kaydedildi id=%s (%d STL)",
            sid, len(stl_names),
        )
        return sid

    # ------------------------------------------------------------------
    def update_meta(self, order_id: str, **fields: Any) -> bool:
        """meta.json'a alan ekle/guncelle (K-56g /kisit-onay onay kalicisi).

        Var olmayan kayit icin False doner; STL'lere dokunmaz. Degeri None
        verilen alan meta'dan SILINIR (onay geri alma).
        """
        sid = _safe_id(order_id)
        mp = self.root / sid / _META
        if not mp.exists():
            return False
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("PendingOrderStore: meta okunamadi id=%s — %s",
                           sid, exc)
            return False
        for k, v in fields.items():
            if v is None:
                meta.pop(k, None)
            else:
                meta[k] = v
        mp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    # ------------------------------------------------------------------
    def get(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Tek bekleyen siparisin meta'sini don (yoksa None)."""
        sid = _safe_id(order_id)
        mp = self.root / sid / _META
        if not mp.exists():
            return None
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("PendingOrderStore: meta okunamadi id=%s — %s", sid, exc)
            return None

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        """Tum bekleyen siparislerin meta listesini don (order_id'ye gore sirali)."""
        if not self.root.exists():
            return []
        out: List[Dict[str, Any]] = []
        for child in sorted(self.root.iterdir()):
            if child.is_dir() and (child / _META).exists():
                m = self.get(child.name)
                if m is not None:
                    out.append(m)
        return out

    # ------------------------------------------------------------------
    def count(self) -> int:
        """Bekleyen siparis sayisi (nav rozeti icin)."""
        return len(self.list())

    # ------------------------------------------------------------------
    def load_stl_map(self, order_id: str) -> Dict[str, bytes]:
        """Bekleyen siparisin STL byte'larini {ad: bytes} olarak don (yoksa bos)."""
        sid = _safe_id(order_id)
        d = self.root / sid
        if not d.exists():
            return {}
        out: Dict[str, bytes] = {}
        for f in sorted(d.glob("*.stl")):
            out[f.stem] = f.read_bytes()
        return out

    # ------------------------------------------------------------------
    def remove(self, order_id: str) -> None:
        """Bekleyen siparisi (klasoru) sil. Yoksa sessizce gec."""
        sid = _safe_id(order_id)
        d = self.root / sid
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            logger.info("PendingOrderStore: bekleyen siparis silindi id=%s", sid)

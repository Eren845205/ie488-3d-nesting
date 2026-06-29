"""runtime/otonom_gecmis.py — Kalici otonom is gecmisi deposu (Faz 2).

Tamamlanan her otonom isi (senkron + asenkron) ozet olarak diske yazilir;
/gecmis sayfasi buradan okur. Boylece operatorler daha once islenen nesting
isleri ("gecmis") gorebilir — ana ekran kalabaliklasmaz.

Bicim: JSONL (her satir bir kayit) — append-only, dayanikli (bozuk satir
atlanir), uygulama yeniden baslasa da kalir. Tek-dosya + kilit; otonom isleri
seyrek oldugundan (operator-tetikli) bu yeterli.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


def _default_id() -> str:
    import secrets
    return secrets.token_hex(6)


def _default_now_iso() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


class OtonomGecmisStore:
    """Kalici, kilitli is-gecmisi deposu (JSONL)."""

    def __init__(
        self,
        root: Union[str, Path],
        *,
        id_factory: Callable[[], str] = _default_id,
        now_iso: Callable[[], str] = _default_now_iso,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / "gecmis.jsonl"
        self._id_factory = id_factory
        self._now_iso = now_iso
        self._lock = threading.Lock()

    def kaydet(
        self,
        ozet: Dict[str, Any],
        *,
        dedup_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bir is ozetini gecmise ekle; id + zaman eklenmis kaydi dondur.

        dedup_key verilmisse: ayni _dedup_key degerli kayit zaten varsa
        YAZMA — mevcut kaydi dondur (idempotent). Yoksa kayda _dedup_key
        ekleyip yaz.
        dedup_key=None ise: mevcut davranis (her cagri yeni kayit).
        Kontrol-sonra-yaz tek self._lock icinde atomik yapilir.
        """
        if dedup_key is not None:
            with self._lock:
                for k in self._oku_kilitsiz():
                    if k.get("_dedup_key") == dedup_key:
                        return k
                kayit = dict(ozet)
                kayit["id"] = self._id_factory()
                kayit["zaman"] = self._now_iso()
                kayit["_dedup_key"] = dedup_key
                line = json.dumps(kayit, ensure_ascii=False, default=str)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            return kayit

        kayit = dict(ozet)
        kayit["id"] = self._id_factory()
        kayit["zaman"] = self._now_iso()
        line = json.dumps(kayit, ensure_ascii=False, default=str)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return kayit

    def liste(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Kayitlar — EN YENI ustte. Bozuk satirlar atlanir (dayaniklilik)."""
        kayitlar = self._oku_hepsi()
        kayitlar.reverse()  # en yeni ustte
        kayitlar = kayitlar[:limit] if limit and limit > 0 else kayitlar
        return [self._strip_internal(k) for k in kayitlar]

    def get(self, kayit_id: str) -> Optional[Dict[str, Any]]:
        """id ile tek kayit; bulunamazsa None."""
        for k in self._oku_hepsi():
            if k.get("id") == kayit_id:
                return self._strip_internal(k)
        return None

    # -- ic --------------------------------------------------------------

    @staticmethod
    def _strip_internal(kayit: Dict[str, Any]) -> Dict[str, Any]:
        """`_`-onekli ic alanlari (_dedup_key vb.) public donuslerden ayikla.

        Dedup kontrolu kaydet() icinde _oku_kilitsiz uzerinden yapilir;
        bu ayiklama YALNIZ disa acik liste()/get() icindir -> dedup bozulmaz.
        """
        return {k: v for k, v in kayit.items() if not k.startswith("_")}

    def _oku_kilitsiz(self) -> List[Dict[str, Any]]:
        """Dosyadan lock almadan oku — yalnizca self._lock icinde cagrilmali."""
        if not self._path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # bozuk satir — atla (dayaniklilik)
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def _oku_hepsi(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._oku_kilitsiz()

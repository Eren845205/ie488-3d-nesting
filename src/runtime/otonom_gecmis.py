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
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

# GLB dosya adinda batch_id icin izinli karakterler; gerisi "_"e cevrilir
# (path traversal / ayirici enjeksiyonu imkansizlasir).
_SAFE_BATCH_RE = re.compile(r"[^A-Za-z0-9_-]")


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
        self._detay_dir = self._root / "detay"
        self._glb_dir = self._root / "glb"
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

    def sil(self, kayit_id: str) -> Optional[Dict[str, Any]]:
        """Bir kaydi kalici olarak siler; dosyayi (kayit disinda) yeniden yazar.

        Bulunamazsa None dondurur (dosya degismez). Bulunursa TAM kaydi
        (ic `_`-onekli alanlar DAHIL — orn. `_dedup_key`, `_idem_keys`)
        dondurur ki cagiran (route) idempotency anahtarlarini da
        acabilsin (yeniden-islenebilirlik). Kaydin silinmesi kendiliginden
        dedup_key'i acar: kaydet() dedup kontrolu mevcut satirlari taradigi
        icin silinen kayit artik eslesmez -> ayni dedup_key ile yeni kayit
        yazilabilir. Atomik: tek self._lock icinde oku+yaz; dosya yazimi
        gecici dosyaya yapilip os.replace() ile degistirilir — crash orta
        yerde olsa bile ya eski (butun) icerik ya da yeni (butun) icerik
        gorulur, kismi/kesik dosya (ve ilgisiz kayit kaybi) olmaz.
        """
        with self._lock:
            kayitlar = self._oku_kilitsiz()
            bulunan: Optional[Dict[str, Any]] = None
            kalanlar: List[Dict[str, Any]] = []
            for k in kayitlar:
                if bulunan is None and k.get("id") == kayit_id:
                    bulunan = k
                    continue
                kalanlar.append(k)
            if bulunan is None:
                return None
            lines = [
                json.dumps(k, ensure_ascii=False, default=str) for k in kalanlar
            ]
            content = "\n".join(lines)
            if content:
                content += "\n"
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._path)
            self._artifact_temizle(kayit_id)
            return bulunan

    # -- detay / GLB kalicilastirma ---------------------------------------

    def detay_kaydet(self, kayit_id: str, detay: Dict[str, Any]) -> Path:
        """Bir kaydin TAM detayini (JSON-guvenli dict) diske yaz.

        Ozet kaydindan AYRI dosyada tutulur (detay/<id>.json) ki
        gecmis.jsonl kucuk kalsin (liste() her cagride tum dosyayi okur).
        Atomik yazim: tmp + os.replace — yarim dosya kalmaz.
        """
        self._detay_dir.mkdir(parents=True, exist_ok=True)
        hedef = self._detay_dir / f"{kayit_id}.json"
        tmp = hedef.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(detay, fh, ensure_ascii=False, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, hedef)
        return hedef

    def detay_get(self, kayit_id: str) -> Optional[Dict[str, Any]]:
        """Kaydin tam detayi; yoksa/bozuksa None (eski kayitlar kirilmaz)."""
        hedef = self._detay_dir / f"{kayit_id}.json"
        if not hedef.exists():
            return None
        try:
            obj = json.loads(hedef.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None

    def glb_kaydet(self, kayit_id: str, batch_id: str, glb_bytes: bytes) -> Path:
        """Bir partinin GLB onizlemesini kalici dosyaya yaz (atomik)."""
        self._glb_dir.mkdir(parents=True, exist_ok=True)
        hedef = self._glb_yol(kayit_id, batch_id)
        tmp = hedef.with_suffix(".glb.tmp")
        tmp.write_bytes(glb_bytes)
        os.replace(tmp, hedef)
        return hedef

    def glb_path(self, kayit_id: str, batch_id: str) -> Optional[Path]:
        """Kalici GLB dosya yolu; yoksa None. Containment garantili."""
        hedef = self._glb_yol(kayit_id, batch_id)
        return hedef if hedef.exists() else None

    def _glb_yol(self, kayit_id: str, batch_id: str) -> Path:
        safe_batch = _SAFE_BATCH_RE.sub("_", str(batch_id))[:64] or "batch"
        hedef = (self._glb_dir / f"{kayit_id}_{safe_batch}.glb").resolve()
        kok = self._glb_dir.resolve()
        if not str(hedef).startswith(str(kok) + os.sep):
            raise ValueError("GLB yolu store koku disina cikamaz")
        return hedef

    def _artifact_temizle(self, kayit_id: str) -> None:
        """Silinen kaydin detay JSON + GLB dosyalarini kaldir.

        Hatalar yutulur — artifact temizligi kayit silmeyi asla bloklamaz
        (en kotu durumda yetim dosya kalir, kayit tutarliligi bozulmaz).
        """
        try:
            hedef = self._detay_dir / f"{kayit_id}.json"
            if hedef.exists():
                hedef.unlink()
        except OSError:
            pass
        try:
            if self._glb_dir.exists():
                for p in self._glb_dir.glob(f"{kayit_id}_*.glb"):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    # -- ic --------------------------------------------------------------

    @staticmethod
    def _strip_internal(kayit: Dict[str, Any]) -> Dict[str, Any]:
        """`_`-onekli ic alanlari (_dedup_key vb.) public donuslerden ayikla.

        Dedup kontrolu kaydet() icinde _oku_kilitsiz uzerinden yapilir;
        bu ayiklama YALNIZ disa acik liste()/get() icindir -> dedup bozulmaz.

        Ayiklamadan SONRA turetilmis `yeniden_islenebilir` bayragi eklenir:
        kayit idempotency anahtarlari (_idem_keys) tasiyorsa True. Eski/edge
        kayitlarda bu alan olmayabilir -> False (yanlis "yeniden islenebilir"
        vaadi verilmez).
        """
        temiz = {k: v for k, v in kayit.items() if not k.startswith("_")}
        temiz["yeniden_islenebilir"] = bool(kayit.get("_idem_keys"))
        return temiz

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

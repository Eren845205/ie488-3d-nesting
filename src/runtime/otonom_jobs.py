"""runtime/otonom_jobs.py — Asenkron /otonom is deposu (kilitli, tek-is).

Otonom pipeline (mail-cek -> parse -> nesting -> fiyat -> teklif) uzun surer
(gercek NFV CPU'da dakikalarca). Senkron HTTP istegi tarayicida timeout olur ve
sunucu bloke olur. Bu depo, isi arka-plan thread'ine alir; tarayici durumu
GET /otonom/durum/<job_id> ile yoklayarak ilerlemeyi CANLI gosterir.

Tasarim:
  - Tek-is politikasi: ayni anda EN FAZLA 1 aktif (calisiyor) is. Ikinci
    try_start aktif is varken None doner (operator + agir kaynak icin dogru).
  - Thread guvenligi: tum durum tek RLock altinda. add_stage (on_stage callback)
    HICBIR kosulda atmaz — job'i dusurmemeli.
  - Durum: 'calisiyor' -> 'bitti' (status==200) | 'hata' (status!=200 ya da fail).

Bellek: tamamlanan isler son _MAX_KEEP kadar saklanir (polling bitmis isi de
gorebilsin); kalici GECMIS ayri depodadir (otonom_gecmis, Faz 2).
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

_MAX_KEEP = 20  # bellekte tutulacak en fazla (aktif + tamamlanmis) is


def _default_id_factory() -> str:
    import secrets
    return secrets.token_hex(8)


def _default_now() -> float:
    import time
    return time.time()


class OtonomJobStore:
    """Kilitli, tek-is asenkron is deposu."""

    def __init__(
        self,
        *,
        id_factory: Callable[[], str] = _default_id_factory,
        now: Callable[[], float] = _default_now,
        max_keep: int = _MAX_KEEP,
    ) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []  # ekleme sirasi (eski silme icin)
        self._id_factory = id_factory
        self._now = now
        self._max_keep = max_keep

    # -- yasam dongusu ----------------------------------------------------

    def try_start(self, *, meta: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Aktif is yoksa yeni job baslat (job_id don); varsa None.

        Atomiktir: eszamanli cagrilarda tam 1'i job_id alir (tek-is).
        """
        with self._lock:
            if self._active_id_locked() is not None:
                return None
            jid = self._id_factory()
            t = self._now()
            self._jobs[jid] = {
                "job_id": jid,
                "durum": "calisiyor",
                "asamalar": [],
                "sonuc": None,
                "status": None,
                "hata": None,
                "started_at": t,
                "updated_at": t,
                "meta": dict(meta or {}),
            }
            self._order.append(jid)
            self._evict_locked()
            return jid

    def add_stage(self, job_id: str, asama: Dict[str, Any]) -> None:
        """Bir asama ekle (on_stage callback). Bilinmeyen job'da SESSIZ gecer."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["durum"] != "calisiyor":
                return
            job["asamalar"].append(asama)
            job["updated_at"] = self._now()

    def finish(self, job_id: str, *, sonuc: Dict[str, Any], status: int) -> None:
        """Isi tamamla. status==200 -> 'bitti', degilse -> 'hata'."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["sonuc"] = sonuc
            job["status"] = status
            job["durum"] = "bitti" if status == 200 else "hata"
            job["updated_at"] = self._now()
            # asamalar nihai sonuctan da tazelensin (tam liste)
            if isinstance(sonuc, dict) and isinstance(sonuc.get("asamalar"), list):
                job["asamalar"] = sonuc["asamalar"]

    def fail(self, job_id: str, *, hata: str) -> None:
        """Beklenmeyen istisna — isi 'hata' yap."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["durum"] = "hata"
            job["hata"] = hata
            job["status"] = 500
            job["updated_at"] = self._now()

    # -- okuma ------------------------------------------------------------

    def snapshot(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job durumunun KOPYASI; bilinmeyen job -> None."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            snap = dict(job)
            snap["asamalar"] = list(job["asamalar"])
            snap["meta"] = dict(job["meta"])
            return snap

    def active_job_id(self) -> Optional[str]:
        with self._lock:
            return self._active_id_locked()

    # -- ic yardimcilar (lock altinda cagrilir) ---------------------------

    def _active_id_locked(self) -> Optional[str]:
        for jid in reversed(self._order):
            job = self._jobs.get(jid)
            if job is not None and job["durum"] == "calisiyor":
                return jid
        return None

    def _evict_locked(self) -> None:
        """En eski TAMAMLANMIS isleri sil (aktif olani asla silme)."""
        while len(self._order) > self._max_keep:
            for i, jid in enumerate(self._order):
                job = self._jobs.get(jid)
                if job is None or job["durum"] != "calisiyor":
                    self._order.pop(i)
                    self._jobs.pop(jid, None)
                    break
            else:
                break  # hepsi aktif (olmaz ama guvenli) — dur

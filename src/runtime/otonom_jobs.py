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

Restart durustlugu (2026-07-25): bellek-ici is takibi restart'ta kaybolur —
yarim kalan is sessizce yok olurdu. `marker_dir` verilirse OtonomJobStore is
baslarken/biterken kucuk bir "calisiyor_<job_id>.json" isareti yazar/siler;
uygulama baslangicinda `scan_orphaned_markers()` sahipsiz isaretleri tarayip
(restart sirasinda yarim kalmis is) cagirana bildirir — RECOVERY YOK, yalniz
durust raporlama (bkz. src/webapp/app.py create_app).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

_MAX_KEEP = 20  # bellekte tutulacak en fazla (aktif + tamamlanmis) is
_MARKER_PREFIX = "calisiyor_"
_MARKER_SUFFIX = ".json"


def _default_id_factory() -> str:
    import secrets
    return secrets.token_hex(8)


def _default_now() -> float:
    import time
    return time.time()


def _marker_path(marker_dir: Union[str, Path], job_id: str) -> Path:
    return Path(marker_dir) / f"{_MARKER_PREFIX}{job_id}{_MARKER_SUFFIX}"


def _write_marker(
    marker_dir: Union[str, Path], job_id: str, *, started_at: float,
    meta: Dict[str, Any],
) -> None:
    """Calisiyor isaretini atomik yaz (tmp + os.replace). Hata YUTULUR —

    isaret yazma basarisiz olsa bile is akisini BLOKLAMAZ (en kotu durumda
    restart-durustlugu kaniti eksik kalir, is'in kendisi etkilenmez).
    """
    try:
        d = Path(marker_dir)
        d.mkdir(parents=True, exist_ok=True)
        hedef = _marker_path(d, job_id)
        tmp = hedef.with_suffix(hedef.suffix + ".tmp")
        payload = {"job_id": job_id, "started_at": started_at, "meta": meta}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, hedef)
    except OSError:
        pass


def _remove_marker(marker_dir: Union[str, Path], job_id: str) -> None:
    """Calisiyor isaretini sil — bulunamazsa/hata olursa sessizce gecer."""
    try:
        _marker_path(marker_dir, job_id).unlink(missing_ok=True)
    except OSError:
        pass


def scan_orphaned_markers(marker_dir: Union[str, Path]) -> List[Dict[str, Any]]:
    """Sahipsiz "calisiyor_*.json" isaretlerini tara + SIL; icerigi dondur.

    Onceki calistirmadan (crash/restart) kalan yarim isleri temsil eder.
    RECOVERY YAPMAZ — yalniz bulundugu bilgiyi (job_id, started_at, meta)
    cagirana dondurur ki durust bir "kesildi" kaydi dusulebilsin. Bozuk/
    okunamayan isaret dosyalari atlanir (dayaniklilik) ama yine de silinir
    (yetim dosya birikmesin).
    """
    d = Path(marker_dir)
    if not d.exists():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(d.glob(f"{_MARKER_PREFIX}*{_MARKER_SUFFIX}")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            out.append(data)
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    return out


class OtonomJobStore:
    """Kilitli, tek-is asenkron is deposu."""

    def __init__(
        self,
        *,
        id_factory: Callable[[], str] = _default_id_factory,
        now: Callable[[], float] = _default_now,
        max_keep: int = _MAX_KEEP,
        marker_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []  # ekleme sirasi (eski silme icin)
        self._id_factory = id_factory
        self._now = now
        self._max_keep = max_keep
        # marker_dir=None -> mevcut davranis BIREBIR (isaret yazilmaz/okunmaz).
        self._marker_dir = marker_dir

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
            if self._marker_dir is not None:
                _write_marker(self._marker_dir, jid, started_at=t, meta=dict(meta or {}))
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
            if self._marker_dir is not None:
                _remove_marker(self._marker_dir, job_id)

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
            if self._marker_dir is not None:
                _remove_marker(self._marker_dir, job_id)

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

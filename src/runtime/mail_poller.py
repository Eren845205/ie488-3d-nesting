"""runtime/mail_poller.py — Gelen kutusunu periyodik tarayip pipeline'i kosturan
arka plan poll modu (otomatik tetik).

Tek-tik /otonom butonundan AYRI: kullanici hicbir sey yapmadan, yeni mail
geldikce otomatik islenir. Idempotency mevcut mail kaynaklarinda (ImapMailbox
SqliteIdempotencyStore + _seen_uids) saglanir — ayni mail iki kez islenmez.

Tasarim:
  - process_inbox_once(...) : SAF, Flask'siz, test edilebilir tek-tur isleyici.
      mail cek -> ingest_order (zip-stl/excel/csv/llm) -> run_pipeline -> sonuc.
  - MailPoller            : process_inbox_once'i daemon thread'de periyodik kosar;
      sonucu bir callback (result_sink) ile disari verir (orn. app LAST_RESULT).

Thread guvenligi: durum (PollState) tek thread'de yazilir; okuma atomiktir
(dict get). Pipeline saf fonksiyon (run_pipeline) — paylasilan mutable durum yok.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tek-tur isleyici (saf, Flask'siz)
# ---------------------------------------------------------------------------

def process_inbox_once(
    mail_source: Any,
    parser_role: Any,
    *,
    base_scenario: Dict[str, Any],
    persist_root: Optional[str] = None,
    deadline_fallback: str = "",
) -> Optional[Dict[str, Any]]:
    """Gelen kutusunu BIR kez isle: cek -> parse -> pipeline.

    Args:
        mail_source:   MailSource (fetch_new()).
        parser_role:   LLM parser (serbest-metin maili icin; ek-tabanli yollar
                       kullanmaz). None olabilir (yalniz zip/excel/csv islenir).
        base_scenario: run_pipeline icin temel senaryo (RICH_SCENARIO gibi);
                       'orders' bu fonksiyonda doldurulur.
        persist_root:  ZIP-STL yolu icin STL'lerin yazilacagi kok dizin.
        deadline_fallback: Termini bos gelen siparislere atanacak ISO tarih
                       (run_pipeline bos deadline'da hata verir). Bos ise
                       base_scenario['ref_date'] + 30 gun kullanilir.

    Returns:
        run_pipeline ciktisi (dict) — yeni siparis islendiyse.
        None — yeni mail yok veya hicbir siparis cikmadi.
    """
    from scripts.demo_pipeline import run_pipeline
    from src.runtime.mail_ingest import ingest_order

    mails = mail_source.fetch_new()
    if not mails:
        return None

    fallback = deadline_fallback or _default_deadline(base_scenario)

    orders: List[Dict[str, Any]] = []
    for mail in mails:
        try:
            order = ingest_order(mail, parser_role, persist_root=persist_root)
        except Exception as exc:
            logger.warning("mail_poller: ingest hatasi (%s): %s", mail.gonderen, exc)
            continue
        if not order:
            continue
        if not order.get("deadline"):
            order["deadline"] = fallback
        orders.append(order)

    if not orders:
        return None

    scenario = {**base_scenario, "orders": orders}
    # ZIP-STL siparisi kendi konteynerini tasir (gercek plaka) — varsa uygula.
    stl_container = next((o["container"] for o in orders if o.get("container")), None)
    if stl_container:
        scenario = {**scenario, "container": stl_container}

    return run_pipeline(scenario)


def _default_deadline(base_scenario: Dict[str, Any]) -> str:
    """base_scenario['ref_date'] + 30 gun ISO tarih (deadline fallback)."""
    import datetime
    ref = base_scenario.get("ref_date")
    if isinstance(ref, datetime.date):
        return (ref + datetime.timedelta(days=30)).isoformat()
    return "2099-12-31"  # ref yoksa uzak-gelecek (pipeline'i bloklamaz)


# ---------------------------------------------------------------------------
# Poll durumu + arka plan thread
# ---------------------------------------------------------------------------

@dataclass
class PollState:
    """Poller'in gozlemlenebilir durumu (UI icin)."""

    enabled: bool = False
    interval_s: int = 120
    last_poll_ts: Optional[float] = None       # son tur (epoch); None=hic kosmadi
    last_processed: int = 0                     # son turda islenen siparis sayisi
    total_processed: int = 0                    # kumulatif
    last_error: Optional[str] = None
    runs: int = 0                               # toplam tur sayisi

    def snapshot(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_s": self.interval_s,
            "last_poll_ts": self.last_poll_ts,
            "last_processed": self.last_processed,
            "total_processed": self.total_processed,
            "last_error": self.last_error,
            "runs": self.runs,
        }


class MailPoller:
    """process_inbox_once'i daemon thread'de periyodik kosar.

    on_result(pipeline_result) callback'i her basarili (siparis ureten) turda
    cagrilir — app bunu LAST_RESULT'a yazabilir. now() enjekte edilebilir
    (test determinizmi; Date.now yasagi yok ama enjeksiyon test kolayligi).
    """

    def __init__(
        self,
        *,
        make_source: Callable[[], Any],     # her tur taze MailSource uretir
        parser_role: Any,
        base_scenario: Dict[str, Any],
        persist_root: Optional[str],
        interval_s: int = 120,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._make_source = make_source
        self._parser_role = parser_role
        self._base_scenario = base_scenario
        self._persist_root = persist_root
        self._on_result = on_result
        self._now = now
        self.state = PollState(interval_s=interval_s)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    def poll_once(self) -> Optional[Dict[str, Any]]:
        """Tek tur: kaynak uret + isle + durum guncelle + callback. Atmaz."""
        self.state.runs += 1
        if self._now is not None:
            self.state.last_poll_ts = self._now()
        try:
            source = self._make_source()
            result = process_inbox_once(
                source,
                self._parser_role,
                base_scenario=self._base_scenario,
                persist_root=self._persist_root,
            )
            self.state.last_error = None
            if result is not None:
                n = len(result.get("ranked_orders", [])) or len(
                    result.get("nesting_results", {})
                )
                self.state.last_processed = n
                self.state.total_processed += n
                if self._on_result is not None:
                    try:
                        self._on_result(result)
                    except Exception as exc:
                        logger.warning("mail_poller: on_result hatasi: %s", exc)
            else:
                self.state.last_processed = 0
            return result
        except Exception as exc:
            self.state.last_error = str(exc)
            logger.warning("mail_poller: poll_once hatasi: %s", exc)
            return None

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        # Event.wait(interval): stop set edilince hemen cikar; aksi halde bekler.
        while not self._stop.wait(self.state.interval_s):
            self.poll_once()

    def start(self) -> None:
        """Daemon thread baslat (zaten calisiyorsa no-op)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.state.enabled = True
        self._thread = threading.Thread(
            target=self._loop, name="mail-poller", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Thread'i durdur (bir sonraki wait'te cikar)."""
        self._stop.set()
        self.state.enabled = False

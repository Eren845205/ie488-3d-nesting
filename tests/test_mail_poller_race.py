"""tests/test_mail_poller_race.py -- FIX 3 (inflight-lock yarisi) + FIX 4
(PollState alanlari lock altinda) TDD.

FIX 3: restart() eski thread'i JOIN etmeden yeni thread baslatir (UI kilitlenmesin).
Eski thread uzun pipeline icindeyken yeni thread 'ilk-tarama-hemen' ile ayni
maili PARALEL fetch edebilir -> ayni UID iki thread'de. Cozum: poll_once icinde
non-reentrant inflight-lock (acquire blocking=False); tutuluysa taramayi ATLA.

FIX 4: last_error / last_processed lock DISINDA yaziliyordu; restart-race'te eski
thread yeni sonucun ustune yazip yaniltici durum gosterebilir. Tum PollState
yazimlari self._lock altinda olmali.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.demo_pipeline import RICH_SCENARIO
from src.runtime.mail_poller import MailPoller, PollState


class _EmptySource:
    def fetch_new(self):
        return []


# ---------------------------------------------------------------------------
# FIX 3 -- inflight-lock: ayni anda yalniz BIR tarama
# ---------------------------------------------------------------------------

def test_poll_once_inflight_lock_prevents_concurrent_scan(tmp_path):
    """Iki thread ayni anda poll_once cagirirsa fetch/process AYNI ANDA
    yalnizca BIR kez yurumeli (inflight-lock). Restart-race modeli.

    RED (fix'siz): ikinci tarama da fetch'e girer -> max eszamanlilik 2.
    GREEN (fix'li): ikinci tarama inflight-lock tutuldugu icin ATLANIR -> max 1.
    """
    counters = {"cur": 0, "max": 0}
    clock = threading.Lock()
    entered = threading.Event()

    class _SlowSource:
        def fetch_new(self):
            with clock:
                counters["cur"] += 1
                counters["max"] = max(counters["max"], counters["cur"])
            entered.set()
            time.sleep(0.5)  # A tarama icinde 'uzun pipeline' simulasyonu
            with clock:
                counters["cur"] -= 1
            return []

    poller = MailPoller(
        make_source=lambda: _SlowSource(), parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
    )

    t1 = threading.Thread(target=poller.poll_once, name="scan-A")
    t1.start()
    assert entered.wait(2.0), "A taramasi fetch'e girmeli"

    # B: A hala fetch icinde (0.5s uyku) iken cagrilir -> inflight-lock tutulu
    r2 = poller.poll_once()
    assert r2 is None, "B taramasi inflight-lock tutuldugu icin atlanmali"
    assert counters["max"] == 1, (
        f"ayni anda yalniz BIR tarama olmali (max={counters['max']})"
    )

    t1.join(5.0)
    assert not t1.is_alive()


def test_inflight_lock_serbestse_normal_calisir(tmp_path):
    """Regresyon: kilit serbestken poll_once normal calisir (ardisik cagrilar)."""
    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
    )
    assert poller.poll_once() is None
    assert poller.poll_once() is None  # kilit her turda serbest birakilmali
    assert poller.state.runs == 2


def test_inflight_lock_enjekte_edilebilir(tmp_path):
    """app manuel /otonom ile ORTAK kilit enjekte edebilmeli (poller ile paylasim)."""
    shared = threading.Lock()
    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        inflight_lock=shared,
    )
    assert poller._inflight_lock is shared

    # Kilit disaridan tutulursa poll_once taramayi atlar (manuel akis surer)
    shared.acquire()
    try:
        assert poller.poll_once() is None
    finally:
        shared.release()


# ---------------------------------------------------------------------------
# FIX 4 -- tum PollState yazimlari _lock altinda
# ---------------------------------------------------------------------------

def test_pollstate_writes_happen_under_lock(tmp_path):
    """last_error / last_processed dahil tum sayac/durum yazimlari _lock altinda.

    RED (fix'siz): last_error=None ve last_processed=0 lock DISINDA yazilir -> ihlal.
    GREEN (fix'li): tum yazimlar 'with self._lock' icinde.
    """
    class _TrackLock:
        def __init__(self):
            self._l = threading.Lock()
            self.held = False

        def acquire(self, blocking=True):
            ok = self._l.acquire(blocking)
            if ok:
                self.held = True
            return ok

        def release(self):
            self.held = False
            self._l.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *a):
            self.release()

    tracked = ("last_error", "last_processed", "total_processed", "runs", "last_poll_ts")
    violations = []

    class _ProbeState(PollState):
        def __setattr__(self, k, v):
            lr = self.__dict__.get("_lockref")
            if lr is not None and k in tracked and not lr.held:
                violations.append(k)
            object.__setattr__(self, k, v)

    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        now=lambda: 1.0,
    )
    tl = _TrackLock()
    poller._lock = tl
    ps = _ProbeState(interval_s=120)
    object.__setattr__(ps, "_lockref", tl)
    poller.state = ps

    # Bos-sonuc turu: last_error=None + last_processed=0 yollari calisir
    poller.poll_once()
    assert not violations, f"PollState alan(lar)i lock disinda yazildi: {violations}"

    # Hata turu: last_error=str(exc) yolu calisir
    def _boom():
        raise RuntimeError("patla")

    poller._make_source = _boom
    poller.poll_once()
    assert not violations, f"hata yolunda lock disinda yazim: {violations}"

"""test_webapp_normalize_deadline.py -- _normalize_deadline yardimci fonksiyon testleri.

Kapsam:
  - ISO tarih formatlari
  - Turkce tarih formatlari (19 Haziran 2026)
  - Bos/gecersiz -> fallback
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.webapp.app import _normalize_deadline


class TestNormalizeDeadlineISO:

    def test_iso_format_passthrough(self):
        assert _normalize_deadline("2026-06-19") == "2026-06-19"

    def test_iso_format_with_time_trimmed(self):
        result = _normalize_deadline("2026-06-19T14:00:00+03:00")
        assert result == "2026-06-19"

    def test_iso_format_future(self):
        assert _normalize_deadline("2027-01-01") == "2027-01-01"


class TestNormalizeDeadlineTurkce:

    def test_turkce_haziran(self):
        assert _normalize_deadline("19 Haziran 2026") == "2026-06-19"

    def test_turkce_temmuz(self):
        assert _normalize_deadline("14 Temmuz 2026") == "2026-07-14"

    def test_turkce_ocak(self):
        assert _normalize_deadline("1 Ocak 2027") == "2027-01-01"

    def test_turkce_aralik(self):
        assert _normalize_deadline("31 Aralik 2026") == "2026-12-31"

    def test_turkce_eylul(self):
        assert _normalize_deadline("15 Eylul 2026") == "2026-09-15"

    def test_turkce_case_insensitive(self):
        assert _normalize_deadline("21 haziran 2026") == "2026-06-21"

    def test_turkce_with_comma(self):
        # "21 Haziran, 2026" -> parsingte virgul temizlenir
        result = _normalize_deadline("21 Haziran, 2026")
        assert result == "2026-06-21"


class TestNormalizeDeadlineFallback:

    def test_empty_string_returns_future_date(self):
        result = _normalize_deadline("")
        d = date.fromisoformat(result)
        assert d >= date.today(), f"Fallback gecmiste: {result}"

    def test_none_like_empty(self):
        result = _normalize_deadline("", mail_tarih="2026-06-14T08:15:00+03:00")
        assert result == "2026-07-14"

    def test_unknown_format_fallback(self):
        result = _normalize_deadline("next month")
        d = date.fromisoformat(result)
        assert d >= date.today()

    def test_mail_tarih_used_for_fallback(self):
        result = _normalize_deadline("", mail_tarih="2026-06-13T14:30:00+03:00")
        # mail tarihi + 30 gun
        expected = (date(2026, 6, 13) + timedelta(days=30)).isoformat()
        assert result == expected

    def test_returns_string(self):
        result = _normalize_deadline("")
        assert isinstance(result, str)
        assert len(result) == 10  # YYYY-MM-DD

    def test_result_is_valid_iso(self):
        result = _normalize_deadline("gecersiz tarih")
        date.fromisoformat(result)  # Should not raise

"""test_not_onay_idem.py — park meta'sina mail idempotency anahtari tasima.

"Gecmisten sil -> yeniden islensin" zincirinin park-yolu ayagi (2026-08-18):
notlu_siparisi_beklet(mail_idem_key=...) anahtari pending meta'ya yazmali ki
onay-sonrasi kosunun gecmis kaydi _idem_keys tasisin.

Kosus: pytest tests/test_not_onay_idem.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.not_onay import notlu_siparisi_beklet


class SahtePendingStore:
    def __init__(self):
        self.meta = {}

    def add(self, **kw):
        self.meta["kayit"] = dict(kw)
        return "PARK-1"

    def update_meta(self, park_id, **kw):
        self.meta.setdefault(park_id, {}).update(kw)


def _ornek_order(tmp_path):
    stl = tmp_path / "kapak.stl"
    stl.write_bytes(b"solid k\nendsolid k")
    return {
        "order_id": "ZIP-TEST",
        "customer": "T",
        "parts": [{"name": "kapak", "qty": 3, "stl_path": str(stl)}],
        "not_adaylari": [{"satir": "dik uretilecek"}],
    }


class SahteMail:
    gonderen = "t@t"
    konu = "test"


def test_mail_idem_key_meta_ya_yazilir(tmp_path):
    store = SahtePendingStore()
    pid = notlu_siparisi_beklet(store, _ornek_order(tmp_path), SahteMail(),
                                mail_idem_key="HASH-XYZ")
    assert pid == "PARK-1"
    assert store.meta["PARK-1"]["mail_idem_key"] == "HASH-XYZ"


def test_anahtar_yoksa_meta_alani_yok(tmp_path):
    store = SahtePendingStore()
    pid = notlu_siparisi_beklet(store, _ornek_order(tmp_path), SahteMail())
    assert pid == "PARK-1"
    assert "mail_idem_key" not in store.meta.get("PARK-1", {})

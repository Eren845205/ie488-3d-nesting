"""tests/test_pending_orders.py — PendingOrderStore (eksik-bilgi siparis deposu)."""

from src.runtime.pending_orders import PendingOrderStore, _safe_id


def _store(tmp_path):
    return PendingOrderStore(tmp_path / "pending")


def test_add_then_list_and_get(tmp_path):
    s = _store(tmp_path)
    s.add(
        order_id="ZIP-ABC123", customer="FORD", sender="x@ford.com.tr",
        deadline="2026-07-01", priority_class=1, konu="Plan1",
        stl_map={"braket": b"AAA", "kapak": b"BBB"},
    )
    lst = s.list()
    assert len(lst) == 1
    meta = lst[0]
    assert meta["order_id"] == "ZIP-ABC123"
    assert meta["customer"] == "FORD"
    assert meta["priority_class"] == 1
    assert meta["stl_names"] == ["braket", "kapak"]  # sirali
    # get aynisini verir
    assert s.get("ZIP-ABC123")["sender"] == "x@ford.com.tr"


def test_load_stl_map_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.add(
        order_id="O1", customer="C", sender="s", deadline="", priority_class=2,
        konu="", stl_map={"a": b"hello", "b": b"world"},
    )
    m = s.load_stl_map("O1")
    assert m == {"a": b"hello", "b": b"world"}


def test_remove(tmp_path):
    s = _store(tmp_path)
    s.add(order_id="O1", customer="C", sender="s", deadline="", priority_class=2,
          konu="", stl_map={"a": b"x"})
    assert s.count() == 1
    s.remove("O1")
    assert s.count() == 0
    assert s.get("O1") is None
    s.remove("O1")  # ikinci sil -> sessiz gecer (hata atmaz)


def test_add_idempotent_overwrites(tmp_path):
    s = _store(tmp_path)
    s.add(order_id="O1", customer="C", sender="s", deadline="", priority_class=2,
          konu="", stl_map={"a": b"1", "b": b"2"})
    # ayni id, farkli icerik -> ustune yazar, cogalmaz
    s.add(order_id="O1", customer="C2", sender="s", deadline="", priority_class=2,
          konu="", stl_map={"a": b"99"})
    assert s.count() == 1
    assert s.get("O1")["customer"] == "C2"
    assert s.load_stl_map("O1") == {"a": b"99"}  # eski 'b' kalmadi


def test_get_missing_returns_none(tmp_path):
    s = _store(tmp_path)
    assert s.get("yok") is None
    assert s.list() == []
    assert s.load_stl_map("yok") == {}


def test_safe_id_blocks_traversal():
    assert _safe_id("../../etc/passwd") == "passwd"
    assert _safe_id("ZIP-AB_12.x") == "ZIP-AB_12.x"
    assert _safe_id("") == "order"
    assert _safe_id("a/b/c") == "c"

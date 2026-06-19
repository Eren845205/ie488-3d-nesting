"""tests/test_ingest_zip_stl.py — ingest_order ZIP-STL yolu testleri.

Gercek senaryo: mail ekinde .zip (STL'ler) + govdede '<ad> <adet> adet'.
"""

import io
import zipfile

import pytest

trimesh = pytest.importorskip("trimesh")

from src.runtime.mail_ingest import Attachment, RawMail, ingest_order


def _zip_bytes(names_extents):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nm, ext in names_extents:
            mesh = trimesh.creation.box(extents=ext)
            z.writestr(f"{nm}.stl", mesh.export(file_type="stl"))
    return buf.getvalue()


def _mail(govde, zip_bytes, mid="<ZIP-TEST-1@x>"):
    return RawMail(
        gonderen="uretim@firma.com.tr",
        konu="Plan1 siparis",
        govde=govde,
        tarih="2026-06-19T10:00:00+03:00",
        message_id=mid,
        ekler=[Attachment("parcalar.zip", zip_bytes, "application/zip")],
    )


def test_zip_stl_temel_eslestirme(tmp_path):
    zb = _zip_bytes([("braket", (40, 30, 15)), ("kapak", (60, 40, 10))])
    mail = _mail("braket 2 adet\nkapak 3 adet", zb)
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    assert order is not None
    assert order["parse_source"] == "attachment_zip_stl"
    pmap = {p["name"]: p for p in order["parts"]}
    assert pmap["braket"]["qty"] == 2
    assert pmap["kapak"]["qty"] == 3
    assert all(p["source"] == "stl" for p in order["parts"])
    # stl_path kalici (persist_dir) — dosya hala var
    import os
    assert all(os.path.exists(p["stl_path"]) for p in order["parts"])


def test_zip_stl_container_var(tmp_path):
    zb = _zip_bytes([("a", (10, 10, 10))])
    order = ingest_order(_mail("a 1 adet", zb), parser_role=None, persist_root=str(tmp_path))
    assert "container" in order
    assert order["container"]["width_mm"] == 335.0


def test_zip_stl_eslesmeyen_atlanir(tmp_path):
    # zip'te 'c' var ama govdede yok; govdede 'd' var ama zip'te yok
    zb = _zip_bytes([("a", (10, 10, 10)), ("c", (12, 12, 12))])
    mail = _mail("a 5 adet\nd 9 adet", zb)
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    names = {p["name"] for p in order["parts"]}
    assert names == {"a"}                       # sadece eslesni
    assert "c" in order["skipped_no_qty"]       # STL var adet yok
    assert "d" in order["skipped_no_stl"]       # adet var STL yok


def test_zip_stl_govdede_adet_yoksa_none(tmp_path):
    zb = _zip_bytes([("a", (10, 10, 10))])
    mail = _mail("Merhabalar, adet bilgisi yok.", zb)
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    assert order is None  # hicbir parca eslesmedi


def test_zip_oncelik_excelden_yuksek(tmp_path):
    # Hem zip hem (sozde) bir baska ek varsa zip yolu secilir (parser cagrilmaz)
    zb = _zip_bytes([("a", (10, 10, 10))])
    mail = _mail("a 4 adet", zb)
    # parser_role=None — eger LLM yoluna duserse AttributeError olurdu
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    assert order["parse_source"] == "attachment_zip_stl"


def test_bozuk_zip_none(tmp_path):
    mail = _mail("a 2 adet", b"not a real zip")
    order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
    assert order is None


def test_determinizm(tmp_path):
    zb = _zip_bytes([("braket", (40, 30, 15))])
    m1 = _mail("braket 2 adet", zb)
    m2 = _mail("braket 2 adet", zb)
    o1 = ingest_order(m1, parser_role=None, persist_root=str(tmp_path / "a"))
    o2 = ingest_order(m2, parser_role=None, persist_root=str(tmp_path / "b"))
    assert o1["order_id"] == o2["order_id"]
    assert [(p["name"], p["qty"]) for p in o1["parts"]] == \
           [(p["name"], p["qty"]) for p in o2["parts"]]

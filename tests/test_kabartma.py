# -*- coding: utf-8 -*-
"""test_kabartma.py — parca ustu kabartma okuma (KANAL-3 MVP) testleri.

VL cagrisi CI'da KOSULMAZ (enjeksiyonla sahte okuyucu — A9: imza gercekle
ayni). Geometrik kapi gercek a2 STL'i + sentetik negatifle test edilir.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from src.runtime.kabartma import (
    _durus_cumlesi,
    kabartma_goruntusu,
    kabartma_not_adaylari,
)

_ROOT = Path(__file__).resolve().parent.parent
A2 = _ROOT / "data" / "demo_assets" / "288101642-a2.stl"


def test_geometrik_kapi_a2_yakalar():
    """Gercek a2: alt yuzeye 0.4mm gomulu yazi katmani -> goruntu + 'alt'."""
    if not A2.exists():
        pytest.skip("a2 demo varligi yok")
    g = kabartma_goruntusu(trimesh.load(A2, force="mesh"))
    assert g is not None
    im, yuz = g
    assert yuz == "alt"
    assert im.size[0] > 100  # bos degil


def test_geometrik_kapi_duz_kutuda_none():
    """Kabartmasiz kutu: kapi None doner (VL maliyeti odenmez)."""
    kutu = trimesh.creation.box(extents=(60.0, 40.0, 10.0))
    assert kabartma_goruntusu(kutu) is None


def test_not_adaylari_vl_mock_durus_kalibi():
    if not A2.exists():
        pytest.skip("a2 demo varligi yok")
    adaylar = kabartma_not_adaylari(
        {"288101642-a2": A2.read_bytes()},
        _oku=lambda im: "XY-1\nP3-ALTM-26-001")
    assert len(adaylar) == 1
    a = adaylar[0]
    assert a["kaynak"] == "parca_label"
    assert a["parca_adaylari"] == ["288101642-a2.stl"]
    assert "XY duzleminde" in a["satir"] and "yatay" in a["satir"]
    assert "kabartma" in a["satir"]


def test_not_adaylari_kabartmasizda_vl_cagrilmaz():
    def patlar(im):
        raise AssertionError("kabartmasiz parcada VL cagrilmamali")

    kutu = trimesh.creation.box(extents=(60.0, 40.0, 10.0))
    adaylar = kabartma_not_adaylari(
        {"kutu": kutu.export(file_type="stl")}, _oku=patlar)
    assert adaylar == []


def test_not_adaylari_vl_kapaliyken_bos():
    """VL okuyamazsa (None) aday uretilmez — hat sessizce devam eder."""
    if not A2.exists():
        pytest.skip("a2 demo varligi yok")
    adaylar = kabartma_not_adaylari(
        {"288101642-a2": A2.read_bytes()}, _oku=lambda im: None)
    assert adaylar == []


def test_kabartma_acik_config(tmp_path):
    from src.runtime.kabartma import kabartma_acik
    cfg = tmp_path / "configs"
    cfg.mkdir()
    p = cfg / "llm.local.json"
    p.write_text('{"kabartma_okuma": true}', encoding="utf-8")
    assert kabartma_acik(tmp_path) is True
    p.write_text('{"kabartma_okuma": false}', encoding="utf-8")
    assert kabartma_acik(tmp_path) is False
    p.write_text('{}', encoding="utf-8")
    assert kabartma_acik(tmp_path) is False  # eksik alan = kapali
    p.unlink()
    assert kabartma_acik(tmp_path) is False  # dosya yok = kapali


# ------------------------------------------- mail-ingest kablosu ----------

def _zip_mail(govde="braket 2 adet"):
    """Kucuk kutu STL'li ZIP tasiyan sahte mail."""
    import io as _io
    import zipfile

    from src.runtime.mail_ingest import Attachment, RawMail

    buf = _io.BytesIO()
    kutu = trimesh.creation.box(extents=(60.0, 40.0, 10.0))
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("braket.stl", kutu.export(file_type="stl"))
    return RawMail(gonderen="musteri@ornek.com", konu="siparis",
                   govde=govde, tarih="2026-08-15",
                   message_id="<kabartma-test@ornek.com>",
                   ekler=[Attachment(dosya_adi="parcalar.zip",
                                     icerik=buf.getvalue(),
                                     mime="application/zip")])


def test_ingest_kablo_flag_kapaliyken_tarama_yok(tmp_path, monkeypatch):
    import src.runtime.kabartma as kb
    from src.runtime.mail_ingest import ingest_order

    monkeypatch.setattr(kb, "kabartma_acik", lambda root=None: False)

    def patlar(*a, **k):
        raise AssertionError("flag kapaliyken tarama cagrilmamali")

    monkeypatch.setattr(kb, "kabartma_not_adaylari", patlar)
    order = ingest_order(_zip_mail(), None, persist_root=str(tmp_path))
    assert order is not None
    assert "not_adaylari" not in order  # notsuz + taramasiz = bit-ozdes


def test_ingest_kablo_flag_acikken_aday_eklenir(tmp_path, monkeypatch):
    import src.runtime.kabartma as kb
    from src.runtime.mail_ingest import ingest_order

    monkeypatch.setattr(kb, "kabartma_acik", lambda root=None: True)
    monkeypatch.setattr(
        kb, "kabartma_not_adaylari",
        lambda stl_map, **kw: [{"satir": "braket parcasi XY duzleminde "
                                         "(yatay) uretilecek — parca ustu "
                                         "kabartma etiketi: 'XY-1'",
                                "satir_no": None, "kaynak": "parca_label",
                                "parca_adaylari": ["braket.stl"]}])
    order = ingest_order(_zip_mail(), None, persist_root=str(tmp_path))
    assert order is not None
    adaylar = order.get("not_adaylari") or []
    assert any(a.get("kaynak") == "parca_label" for a in adaylar)


def test_durus_cumlesi_kaliplari():
    assert "XY duzleminde (yatay)" in _durus_cumlesi("XY-1", "a2")
    assert "XZ duzleminde" in _durus_cumlesi("etiket: XZ", "a2")
    assert _durus_cumlesi("P3-ALTM-26-001", "a2") is None  # kalip yok
    assert _durus_cumlesi("XX", "a2") is None  # ayni eksen = kalip degil


def test_vl_echo_filtresi():
    """2026-08-16 plan1 bulgusu: VL prompt-echo/halusinasyon satirlari elenir,
    gercek etiketler gecer."""
    from src.runtime.kabartma import _vl_satir_supheli
    # prompt echo (model talimati geri basti; typo'lu varyant dahil)
    assert _vl_satir_supheli('"SADECE GORDUGUN YAZILARI AYNEN LISTELLE"')
    assert _vl_satir_supheli("SADECE gordugun yazilari aynen listele")
    # prompt kelimelerinden uydurma (ek almis kok dahil)
    assert _vl_satir_supheli("1. Muhendislik")
    assert _vl_satir_supheli("Kazinmis yazilar")
    # canli 2. tur bulgusu: TURKCE AKSANLI + parafraz varyantlar
    assert _vl_satir_supheli(
        "SADECE GÖRÜNGÜN YAZILARI AYNEN LİSTELEMEK İÇİN GÖRÜNGÜNİ "
        "KULLANIMIYORUM.")
    assert _vl_satir_supheli(
        "İşte listelenen yazılardan başka bir açıklama yapmadan, bu "
        "yazılara dair bilgi vermek için aşağıdaki bilgileri "
        "kullanabilirsiniz:")
    # gercek etiketler GECER
    assert not _vl_satir_supheli("XY-1")
    assert not _vl_satir_supheli("P3-ALTM-26-001")
    assert not _vl_satir_supheli("Konumu degismeyecek")


def test_vl_echo_filtresi_not_adaylarinda(tmp_path):
    """Echo-only VL ciktisi not adayi URETMEZ; gercek etiket uretir."""
    import trimesh

    from src.runtime.kabartma import kabartma_not_adaylari

    kutu = trimesh.creation.box(extents=(20.0, 20.0, 5.0))
    stl_map = {"p1.stl": kutu.export(file_type="stl")}

    def _g(mesh):
        return object(), "ust"

    # echo-only cikti -> aday yok
    adaylar = kabartma_not_adaylari(
        stl_map, _goruntu=_g,
        _oku=lambda im: "SADECE GORDUGUN YAZILARI AYNEN LISTELLE")
    assert adaylar == []
    # gercek etiket -> aday var, echo satiri temizden dislanmis
    adaylar = kabartma_not_adaylari(
        stl_map, _goruntu=_g,
        _oku=lambda im: "XY-1\nSADECE GORDUGUN YAZILARI AYNEN LISTELLE")
    assert len(adaylar) == 1
    assert "XY-1" in adaylar[0]["satir"]
    assert "SADECE" not in adaylar[0]["ham_metin"]
    # VL loop artefakti: ayni satir >=3 kez -> elenir
    adaylar = kabartma_not_adaylari(
        stl_map, _goruntu=_g,
        _oku=lambda im: "XY-1\n" + "Muhendislik projesi\n" * 10)
    assert len(adaylar) == 1
    assert "projesi" not in adaylar[0]["ham_metin"]
    # asiri-liste artefakti: >4 farkli satir -> tumu supheli, aday yok
    adaylar = kabartma_not_adaylari(
        stl_map, _goruntu=_g,
        _oku=lambda im: "Gorsel tasarim\nYazilim tasarim\nMimarlik tasarim\n"
                        "Isletim sistemleri\nDonanim tasarim")
    assert adaylar == []
    # gercek cift-satirli etiket (a2 kaniti) GECER
    adaylar = kabartma_not_adaylari(
        stl_map, _goruntu=_g, _oku=lambda im: "XY-1\nP3-ALTM-26-001")
    assert len(adaylar) == 1

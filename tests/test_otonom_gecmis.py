"""test_otonom_gecmis.py — Kalici is gecmisi deposu (Faz 2) TDD.

Tamamlanan her otonom isi ozet olarak diske yazilir (JSONL); /gecmis sayfasi
buradan okur. Uygulama yeniden baslasa da kalir.
"""
from __future__ import annotations

import threading

import pytest

from src.runtime.otonom_gecmis import OtonomGecmisStore


@pytest.fixture
def store(tmp_path):
    seq = iter(range(1, 10_000))
    clock = iter(range(1, 10_000))
    return OtonomGecmisStore(
        tmp_path / "gecmis",
        id_factory=lambda: f"g{next(seq)}",
        now_iso=lambda: f"2026-06-27T00:00:{next(clock):02d}",
    )


def _ozet(**kw):
    base = {
        "durum": "bitti", "mod": "auto", "musteri": "HOTMAIL",
        "siparis_sayisi": 2, "parti_sayisi": 1, "min_yukseklik_mm": 667.5,
        "toplam_fiyat": 200.0, "sure_sn": 9.4,
    }
    base.update(kw)
    return base


class TestKaydetListe:
    def test_kaydet_id_ve_zaman_ekler(self, store):
        kayit = store.kaydet(_ozet())
        assert kayit["id"] == "g1"
        assert kayit["zaman"].startswith("2026-06-27")
        assert kayit["musteri"] == "HOTMAIL"

    def test_liste_en_yeni_ustte(self, store):
        store.kaydet(_ozet(musteri="A"))
        store.kaydet(_ozet(musteri="B"))
        store.kaydet(_ozet(musteri="C"))
        musteriler = [k["musteri"] for k in store.liste()]
        assert musteriler == ["C", "B", "A"]

    def test_liste_limit(self, store):
        for i in range(5):
            store.kaydet(_ozet(musteri=f"M{i}"))
        assert len(store.liste(limit=2)) == 2

    def test_bos_liste(self, store):
        assert store.liste() == []


class TestGet:
    def test_get_id_ile_bulur(self, store):
        store.kaydet(_ozet(musteri="X"))
        k2 = store.kaydet(_ozet(musteri="Y"))
        assert store.get(k2["id"])["musteri"] == "Y"

    def test_get_bilinmeyen_none(self, store):
        assert store.get("yok") is None


class TestKalicilik:
    def test_yeni_store_ayni_kok_okur(self, tmp_path):
        kok = tmp_path / "g"
        s1 = OtonomGecmisStore(kok, id_factory=lambda: "g1",
                               now_iso=lambda: "2026-06-27T00:00:01")
        s1.kaydet(_ozet(musteri="KALICI"))
        # Yeni instance ayni dizinden okumali (uygulama yeniden basladi)
        s2 = OtonomGecmisStore(kok)
        assert any(k["musteri"] == "KALICI" for k in s2.liste())

    def test_bozuk_satir_atlanir(self, tmp_path):
        kok = tmp_path / "g"
        s1 = OtonomGecmisStore(kok, id_factory=lambda: "g1",
                               now_iso=lambda: "2026-06-27T00:00:01")
        s1.kaydet(_ozet(musteri="SAGLAM"))
        # Dosyaya bozuk satir ekle
        (kok / "gecmis.jsonl").open("a", encoding="utf-8").write("{bozuk json\n")
        s2 = OtonomGecmisStore(kok)
        liste = s2.liste()
        assert any(k["musteri"] == "SAGLAM" for k in liste)  # bozuk atlandi, saglam okundu


class TestThreadGuvenligi:
    def test_eszamanli_kaydet_kayip_yok(self, tmp_path):
        store = OtonomGecmisStore(tmp_path / "g")

        def worker():
            for _ in range(25):
                store.kaydet(_ozet())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(store.liste(limit=1000)) == 100

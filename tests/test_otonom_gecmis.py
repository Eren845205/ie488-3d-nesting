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


class TestSil:
    """Gecmisten sil -> yeniden islenebilir (idempotency baglantisi UI/route'ta)."""

    def test_sil_kaydi_kaldirir(self, store):
        k1 = store.kaydet(_ozet(musteri="A"))
        store.kaydet(_ozet(musteri="B"))
        silinen = store.sil(k1["id"])
        assert silinen is not None
        assert silinen["musteri"] == "A"
        assert store.get(k1["id"]) is None
        assert [k["musteri"] for k in store.liste()] == ["B"]

    def test_sil_bilinmeyen_id_none_ve_degismez(self, store):
        store.kaydet(_ozet(musteri="A"))
        sonuc = store.sil("yokboyle")
        assert sonuc is None
        assert len(store.liste()) == 1

    def test_sil_ic_alanlari_geri_dondurur(self, store):
        """sil() _dedup_key/_idem_keys gibi ic alanlari da (route icin) dondurmeli."""
        kayit = store.kaydet(
            _ozet(musteri="A", _idem_keys=["k1", "k2"]),
            dedup_key="dedup-1",
        )
        silinen = store.sil(kayit["id"])
        assert silinen["_dedup_key"] == "dedup-1"
        assert silinen["_idem_keys"] == ["k1", "k2"]
        # Public liste()/get() bu alanlari ASLA sizdirmaz
        assert "_dedup_key" not in store.liste()

    def test_sil_sonrasi_ayni_dedup_key_yeni_kayit_yazilabilir(self, store):
        """Silme dedup bariyerini acar: silinen kaydin dedup_key'i artik
        kaydet()'in ic taramasinda eslesmez -> ayni anahtarla yeni kayit yazilir
        (mail yeniden islenince gecmis kaydinin kendisi de tekrar olusabilsin)."""
        k1 = store.kaydet(_ozet(musteri="A"), dedup_key="D1")
        # Silmeden ONCE ayni dedup_key -> engellenir (mevcut davranis, degismedi)
        k1b = store.kaydet(_ozet(musteri="A-tekrar"), dedup_key="D1")
        assert k1b["id"] == k1["id"]
        assert len(store.liste()) == 1

        store.sil(k1["id"])
        assert store.liste() == []

        k2 = store.kaydet(_ozet(musteri="A-yeniden"), dedup_key="D1")
        assert k2["id"] != k1["id"]
        assert len(store.liste()) == 1
        assert store.liste()[0]["musteri"] == "A-yeniden"

    def test_sil_atomik_yazim_tmp_dosya_kalmaz_ve_icerik_butun(self, tmp_path):
        """sil() gecici .tmp dosyaya yazip os.replace() ile degistirmeli:
        islem sonrasi .tmp dosyasi kalmamali (temizlendi/yeniden adlandirildi)
        ve kalan kayitlarin TAMAMI (ilgisiz kayit kaybi olmadan) okunabilmeli."""
        kok = tmp_path / "g"
        seq = iter(range(1, 100))
        s1 = OtonomGecmisStore(kok, id_factory=lambda: f"g{next(seq)}",
                               now_iso=lambda: "2026-06-27T00:00:01")
        k1 = s1.kaydet(_ozet(musteri="A"))
        s1.kaydet(_ozet(musteri="B"))
        s1.kaydet(_ozet(musteri="C"))
        s1.sil(k1["id"])

        tmp_dosya = kok / "gecmis.jsonl.tmp"
        assert not tmp_dosya.exists()  # gecici dosya kalici sistemde kalmamali
        gercek_dosya = kok / "gecmis.jsonl"
        assert gercek_dosya.exists()
        musteriler = [k["musteri"] for k in s1.liste()]
        assert sorted(musteriler) == ["B", "C"]  # ilgisiz kayitlar kaybolmadi

    def test_sil_kalicilik_diskten_dogru_okunur(self, tmp_path):
        """sil() sonrasi YENI store instance'i (uygulama yeniden basladi) dogru okur."""
        kok = tmp_path / "g"
        seq = iter(range(1, 100))
        s1 = OtonomGecmisStore(kok, id_factory=lambda: f"g{next(seq)}",
                               now_iso=lambda: "2026-06-27T00:00:01")
        k1 = s1.kaydet(_ozet(musteri="A"))
        s1.kaydet(_ozet(musteri="B"))
        s1.sil(k1["id"])

        s2 = OtonomGecmisStore(kok)
        musteriler = [k["musteri"] for k in s2.liste()]
        assert musteriler == ["B"]


class TestYenidenIslenebilirBayragi:
    """liste()/get() turetilmis `yeniden_islenebilir` bayragi (_idem_keys tabanli)."""

    def test_idem_keys_varsa_true(self, store):
        store.kaydet(_ozet(musteri="A", _idem_keys=["k1"]))
        assert store.liste()[0]["yeniden_islenebilir"] is True

    def test_idem_keys_yoksa_false(self, store):
        store.kaydet(_ozet(musteri="A"))
        assert store.liste()[0]["yeniden_islenebilir"] is False

    def test_idem_keys_bos_liste_false(self, store):
        store.kaydet(_ozet(musteri="A", _idem_keys=[]))
        assert store.liste()[0]["yeniden_islenebilir"] is False

    def test_get_ayni_bayragi_verir(self, store):
        k = store.kaydet(_ozet(musteri="A", _idem_keys=["k1"]))
        assert store.get(k["id"])["yeniden_islenebilir"] is True


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

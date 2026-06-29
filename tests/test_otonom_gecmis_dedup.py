"""test_otonom_gecmis_dedup.py — Downstream dedup: ayni mail/order tekrar yazilmaz.

Kapsam (6 test):
  1. Ayni dedup_key ile iki kez kaydet -> liste() tek kayit dondurur;
     ikinci cagri ilk kaydi dondurur (id ayni).
  2. Farkli dedup_key -> iki kayit.
  3. dedup_key=None iki kez (ayni icerik) -> iki kayit (geriye uyum).
  4. _dedup_key alani diske yaziliyor (yeni store ornegi ayni dosyadan
     okuyunca dedup hala calisir = kalici).
  5. _dedup_key ic alani liste()/get() ile disari sizmiyor (M2 gizlilik).
  6. Atomik: eslezamanli ayni dedup_key -> tek kayit (race condition yok).
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
        tmp_path / "gecmis_dedup",
        id_factory=lambda: f"g{next(seq)}",
        now_iso=lambda: f"2026-06-28T00:00:{next(clock):02d}",
    )


def _ozet(**kw):
    base = {
        "durum": "bitti",
        "kaynak": "otomatik",
        "mod": "auto",
        "musteri": "TEST",
    }
    base.update(kw)
    return base


class TestDedupKey:
    def test_ayni_dedup_key_tek_kayit(self, store):
        """Ayni dedup_key ile iki kaydet -> liste tek kayit, id ayni."""
        k1 = store.kaydet(_ozet(musteri="A"), dedup_key="ORD-001")
        k2 = store.kaydet(_ozet(musteri="A"), dedup_key="ORD-001")
        assert k1["id"] == k2["id"], "Ikinci cagri ilk kaydi dondurmeli"
        assert len(store.liste(limit=100)) == 1

    def test_farkli_dedup_key_iki_kayit(self, store):
        """Farkli dedup_key -> iki kayit."""
        store.kaydet(_ozet(), dedup_key="ORD-001")
        store.kaydet(_ozet(), dedup_key="ORD-002")
        assert len(store.liste(limit=100)) == 2

    def test_dedup_key_none_geriye_uyum(self, store):
        """dedup_key=None iki kez ayni icerik -> iki kayit (geriye uyum)."""
        store.kaydet(_ozet(musteri="X"))
        store.kaydet(_ozet(musteri="X"))
        assert len(store.liste(limit=100)) == 2

    def test_dedup_key_kalici_yeni_store(self, tmp_path):
        """_dedup_key alani diske yazilir; yeni store ornegi okuyunca dedup calisir."""
        kok = tmp_path / "kalici_dedup"
        s1 = OtonomGecmisStore(
            kok,
            id_factory=lambda: "g-sabit",
            now_iso=lambda: "2026-06-28T00:00:01",
        )
        k1 = s1.kaydet(_ozet(musteri="K"), dedup_key="PERM-KEY")
        assert k1.get("_dedup_key") == "PERM-KEY"

        # Yeni instance ayni kokten okur — dedup hala calisir
        s2 = OtonomGecmisStore(kok)
        k2 = s2.kaydet(_ozet(musteri="K"), dedup_key="PERM-KEY")
        assert k2["id"] == k1["id"], "Kalici dedup: yeni store ayni kaydi bulup dondurmeli"
        assert len(s2.liste(limit=100)) == 1

    def test_dedup_key_public_donuslerden_ayiklanir(self, store):
        """_dedup_key ic alani liste()/get() ile disari sizmamali (M2)."""
        k = store.kaydet(_ozet(), dedup_key="ORD-XYZ")
        # kaydet donusu ic alani tasiyabilir (cagiran-ici kullanim)
        assert k.get("_dedup_key") == "ORD-XYZ"
        # ama public liste()/get() ayiklamali
        liste = store.liste(limit=100)
        assert all("_dedup_key" not in r for r in liste)
        tek = store.get(k["id"])
        assert tek is not None and "_dedup_key" not in tek

    def test_eslezamanli_ayni_dedup_key_tek_kayit(self, tmp_path):
        """Race condition: eslezamanli ayni dedup_key -> kesinlikle tek kayit."""
        store = OtonomGecmisStore(tmp_path / "race")
        sonuclar = []

        def worker():
            k = store.kaydet(_ozet(), dedup_key="RACE-KEY")
            sonuclar.append(k["id"])

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Tum donuslerin id'si ayni olmali
        assert len(set(sonuclar)) == 1, f"Birden fazla id uretildi: {set(sonuclar)}"
        assert len(store.liste(limit=100)) == 1

"""test_otonom_jobs.py — OtonomJobStore (asenkron iş deposu) TDD.

Kilitli, tek-iş job deposu: job_id -> durum/asamalar/sonuc/hata/zaman.
Asenkron /otonom rotalarının arka-plan iş yasam dongusunu yonetir.
"""
from __future__ import annotations

import threading

import pytest

from src.runtime.otonom_jobs import OtonomJobStore


@pytest.fixture
def store():
    # Deterministik zaman + sayac-tabanli job_id (test izolasyonu)
    seq = iter(range(1, 10_000))
    clock = iter(range(1, 10_000))
    return OtonomJobStore(
        id_factory=lambda: f"job{next(seq)}",
        now=lambda: float(next(clock)),
    )


class TestTekIsPolitikasi:
    def test_try_start_aktif_is_yokken_job_id_doner(self, store):
        jid = store.try_start(meta={"mode": "auto"})
        assert jid is not None
        assert store.snapshot(jid)["durum"] == "calisiyor"

    def test_ikinci_try_start_aktif_is_varken_none_doner(self, store):
        jid1 = store.try_start(meta={})
        jid2 = store.try_start(meta={})
        assert jid1 is not None
        assert jid2 is None, "Tek-is politikasi: aktif is varken yeni baslamamali"

    def test_bittikten_sonra_try_start_yeniden_calisir(self, store):
        jid1 = store.try_start(meta={})
        store.finish(jid1, sonuc={"ok": True}, status=200)
        jid2 = store.try_start(meta={})
        assert jid2 is not None and jid2 != jid1

    def test_hata_sonrasi_try_start_yeniden_calisir(self, store):
        jid1 = store.try_start(meta={})
        store.fail(jid1, hata="patladi")
        jid2 = store.try_start(meta={})
        assert jid2 is not None and jid2 != jid1

    def test_active_job_id(self, store):
        assert store.active_job_id() is None
        jid = store.try_start(meta={})
        assert store.active_job_id() == jid
        store.finish(jid, sonuc={}, status=200)
        assert store.active_job_id() is None


class TestAsamaIlerleme:
    def test_add_stage_asamalara_ekler(self, store):
        jid = store.try_start(meta={})
        store.add_stage(jid, {"ad": "Mail-Cek", "durum": "tamam"})
        store.add_stage(jid, {"ad": "Parse", "durum": "tamam"})
        snap = store.snapshot(jid)
        assert [a["ad"] for a in snap["asamalar"]] == ["Mail-Cek", "Parse"]

    def test_add_stage_bilinmeyen_job_sessiz_gecer(self, store):
        # on_stage callback'i hicbir kosulda atmamali (job dusmesin)
        store.add_stage("yok", {"ad": "X", "durum": "tamam"})  # patlamamali

    def test_snapshot_updated_at_ilerler(self, store):
        jid = store.try_start(meta={})
        t0 = store.snapshot(jid)["updated_at"]
        store.add_stage(jid, {"ad": "Parse", "durum": "tamam"})
        t1 = store.snapshot(jid)["updated_at"]
        assert t1 > t0


class TestSonucVeHata:
    def test_finish_durum_bitti_ve_sonuc(self, store):
        jid = store.try_start(meta={})
        store.finish(jid, sonuc={"toplam_fiyat": 200.0}, status=200)
        snap = store.snapshot(jid)
        assert snap["durum"] == "bitti"
        assert snap["sonuc"]["toplam_fiyat"] == 200.0
        assert snap["status"] == 200

    def test_finish_hata_statusu_durum_hata_yapar(self, store):
        # _run_otonom_pipeline (body,status) doner; status!=200 -> is hatali bitti
        jid = store.try_start(meta={})
        store.finish(jid, sonuc={"hata": "parse yok"}, status=500)
        snap = store.snapshot(jid)
        assert snap["durum"] == "hata"
        assert snap["status"] == 500

    def test_fail_durum_hata(self, store):
        jid = store.try_start(meta={})
        store.fail(jid, hata="beklenmeyen istisna")
        snap = store.snapshot(jid)
        assert snap["durum"] == "hata"
        assert "beklenmeyen" in snap["hata"]

    def test_snapshot_bilinmeyen_job_none(self, store):
        assert store.snapshot("yok") is None

    def test_meta_snapshotta_korunur(self, store):
        jid = store.try_start(meta={"mode": "auto", "quality": "fast"})
        assert store.snapshot(jid)["meta"]["mode"] == "auto"


class TestThreadGuvenligi:
    def test_eszamanli_add_stage_kayip_yok(self):
        store = OtonomJobStore()
        jid = store.try_start(meta={})

        def worker():
            for _ in range(50):
                store.add_stage(jid, {"ad": "X", "durum": "tamam"})

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(store.snapshot(jid)["asamalar"]) == 200

    def test_eszamanli_try_start_tek_kazanan(self):
        # 8 thread ayni anda try_start; tam 1'i job_id almali (tek-is)
        store = OtonomJobStore()
        sonuclar = []
        lock = threading.Lock()

        def worker():
            jid = store.try_start(meta={})
            with lock:
                sonuclar.append(jid)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        kazananlar = [j for j in sonuclar if j is not None]
        assert len(kazananlar) == 1, f"Tek-is: tam 1 kazanan beklenir, {len(kazananlar)} oldu"

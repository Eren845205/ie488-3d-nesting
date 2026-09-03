"""webapp/kosu_ilerleme.py — koşu ilerleme + hata bildirimi deposu (P6, 2026-08-18).

Hoca/lab istekleri (HOCA_CEVAPLARI 2026-08-18 İ1+İ2): koşu sırasında
"%X tamamlandı" göstergesi + koşu patlarsa görünür bildirim.

Tasarım sınırları:
  * run_pipeline içine sokulmuş gerçek bir ilerleme kancası YOK (motor
    cerrahisi gerektirir); yüzde TAHMİNİDİR: geçen süre / beklenen süre.
    Beklenen süre son başarılı koşulardan EWMA ile öğrenilir (parça
    sayısına ölçekli); hiç geçmiş yoksa muhafazakâr sabit kullanılır.
    UI bu değeri "tahmini" etiketiyle gösterir — yüzde 97'de doyar,
    yalnız gerçek bitiş 100 yapar (yalan "tamamlandı" yok).
  * Depo süreç-içi ve kilitli; kalıcılık yalnız EWMA parametresi için
    (configs/app_ayarlar.json — not_onay.ayar_yaz altyapısı).
  * Hata kayıtları sınırlı tutulur (son N); operatör baloncuğu kapatana
    dek görünür kalması UI tarafının işidir (localStorage).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

# Beklenen süre modeli: sure ~= taban + parca_basi * n_parca (EWMA'li).
_TABAN_S = 30.0
_PARCA_BASI_S = 0.15
_EWMA_ALFA = 0.4
_YUZDE_TAVAN = 97
_HATA_LIMIT = 20
_BITEN_TTL_S = 30.0  # biten kosu %100 olarak bu kadar daha gorunur


class KosuIlerleme:
    """Süreç-içi koşu ilerleme/hata deposu (thread-güvenli)."""

    def __init__(self, now=time.time, ayar_oku=None, ayar_yaz=None):
        self._now = now
        self._kilit = threading.Lock()
        self._kosular: Dict[str, Dict[str, Any]] = {}
        self._hatalar: List[Dict[str, Any]] = []
        # EWMA kalıcılığı opsiyonel (test: None → yalnız bellek-içi).
        self._ayar_oku = ayar_oku
        self._ayar_yaz = ayar_yaz
        self._parca_basi = self._kalici_parca_basi()

    # ------------------------------------------------------------------ iç
    def _kalici_parca_basi(self) -> float:
        if self._ayar_oku is None:
            return _PARCA_BASI_S
        try:
            v = float((self._ayar_oku() or {}).get(
                "kosu_parca_basi_s", _PARCA_BASI_S))
            return v if 0.001 <= v <= 60.0 else _PARCA_BASI_S
        except Exception:
            return _PARCA_BASI_S

    def _tahmin_s(self, n_parca: int) -> float:
        return _TABAN_S + self._parca_basi * max(1, int(n_parca))

    # ------------------------------------------------------------ yaşam döngüsü
    def baslat(self, order_id: str, n_parca: int, kaynak: str = "manuel") -> None:
        with self._kilit:
            self._kosular[order_id] = {
                "order_id": order_id,
                "n_parca": int(n_parca),
                "kaynak": kaynak,
                "asama": "siparis kuruluyor",
                "baslangic": self._now(),
                "tahmini_s": self._tahmin_s(n_parca),
                "durum": "kosuyor",
                "bitis": None,
                "hata_kodu": None,
            }

    def asama(self, order_id: str, metin: str) -> None:
        with self._kilit:
            k = self._kosular.get(order_id)
            if k is not None and k["durum"] == "kosuyor":
                k["asama"] = str(metin)

    def bitti(self, order_id: str) -> None:
        with self._kilit:
            k = self._kosular.get(order_id)
            if k is None:
                return
            k["durum"] = "bitti"
            k["bitis"] = self._now()
            k["asama"] = "tamamlandi"
            gercek = k["bitis"] - k["baslangic"]
            # EWMA guncelle (parca-basi katsayisi; taban sabit kalir)
            if k["n_parca"] > 0 and gercek > _TABAN_S:
                yeni = (gercek - _TABAN_S) / k["n_parca"]
                self._parca_basi = ((1 - _EWMA_ALFA) * self._parca_basi
                                    + _EWMA_ALFA * yeni)
                if self._ayar_yaz is not None:
                    try:
                        self._ayar_yaz("kosu_parca_basi_s",
                                       round(self._parca_basi, 4))
                    except Exception:
                        pass

    def hata(self, order_id: str, kod: str) -> None:
        with self._kilit:
            k = self._kosular.pop(order_id, None)
            kayit = {
                "order_id": order_id,
                "kod": str(kod),
                "ts": self._now(),
                "kaynak": (k or {}).get("kaynak", "?"),
            }
            self._hatalar.append(kayit)
            del self._hatalar[:-_HATA_LIMIT]

    # ------------------------------------------------------------------ okuma
    def _yuzde(self, k: Dict[str, Any]) -> int:
        if k["durum"] == "bitti":
            return 100
        gecen = self._now() - k["baslangic"]
        return int(min(_YUZDE_TAVAN,
                       max(1, 100.0 * gecen / max(1.0, k["tahmini_s"]))))

    def aktifler(self) -> List[Dict[str, Any]]:
        """Süren koşular + kısa süre önce bitenler (%100 gösterimi)."""
        simdi = self._now()
        out: List[Dict[str, Any]] = []
        with self._kilit:
            silinecek = []
            for oid, k in self._kosular.items():
                if k["durum"] == "bitti" and simdi - (k["bitis"] or 0) > _BITEN_TTL_S:
                    silinecek.append(oid)
                    continue
                out.append({
                    "order_id": oid,
                    "kaynak": k["kaynak"],
                    "asama": k["asama"],
                    "durum": k["durum"],
                    "yuzde": self._yuzde(k),
                    "gecen_s": int(simdi - k["baslangic"]),
                    "tahmini_s": int(k["tahmini_s"]),
                    "n_parca": k["n_parca"],
                })
            for oid in silinecek:
                self._kosular.pop(oid, None)
        return out

    def son_hatalar(self) -> List[Dict[str, Any]]:
        with self._kilit:
            return list(self._hatalar)

"""runtime/mail_poller.py — Gelen kutusunu periyodik tarayip pipeline'i kosturan
arka plan poll modu (otomatik tetik).

Tek-tik /otonom butonundan AYRI: kullanici hicbir sey yapmadan, yeni mail
geldikce otomatik islenir. Idempotency mevcut mail kaynaklarinda (ImapMailbox
SqliteIdempotencyStore + _seen_uids) saglanir — ayni mail iki kez islenmez.

Tasarim:
  - process_inbox_once(...) : SAF, Flask'siz, test edilebilir tek-tur isleyici.
      mail cek -> ingest_order (zip-stl/excel/csv/llm) -> run_pipeline -> sonuc.
  - MailPoller            : process_inbox_once'i daemon thread'de periyodik kosar;
      sonucu bir callback (result_sink) ile disari verir (orn. app LAST_RESULT).

Thread guvenligi: durum (PollState) tek thread'de yazilir; okuma atomiktir
(dict get). Pipeline saf fonksiyon (run_pipeline) — paylasilan mutable durum yok.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tek-tur isleyici (saf, Flask'siz)
# ---------------------------------------------------------------------------

def _attachment_first(mails: List[Any]) -> List[Any]:
    """Ek-li (ZIP/Excel) mailleri basa al -- kesin siparis spam-LLM kuyrugunda beklemesin.

    P2: ZIP/Excel ekli mailler ingest_order'da LLM'siz deterministik yola gider;
    serbest-metin mailler (sinyal varsa) yavas LLM'e gider. Ingest LOOP'unda ek-li
    olanlari ONCE islemek, gercek siparisi spam-LLM gecikmesinden ayirir. Sirala
    KARARLI (stable): her grup icinde giris sirasi korunur.
    """
    from src.runtime.mail_ingest import (
        _find_attachment, _ZIP_EXTENSIONS, _STRUCTURED_EXTENSIONS,
    )

    def _has_att(m: Any) -> bool:
        return bool(
            _find_attachment(m, _ZIP_EXTENSIONS)
            or _find_attachment(m, _STRUCTURED_EXTENSIONS)
        )

    # sorted KARARLI -> key=0 (ekli) once, key=1 (metin) sonra; grup-ici sira korunur.
    return sorted(mails, key=lambda m: 0 if _has_att(m) else 1)


def process_inbox_once(
    mail_source: Any,
    parser_role: Any,
    *,
    base_scenario: Dict[str, Any],
    persist_root: Optional[str] = None,
    deadline_fallback: str = "",
    pending_store: Any = None,
    on_stage: Optional[Any] = None,
    on_result: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Gelen kutusunu BIR kez isle: cek -> parse -> pipeline.

    Args:
        mail_source:   MailSource (fetch_new()).
        parser_role:   LLM parser (serbest-metin maili icin; ek-tabanli yollar
                       kullanmaz). None olabilir (yalniz zip/excel/csv islenir).
        base_scenario: run_pipeline icin temel senaryo (RICH_SCENARIO gibi);
                       'orders' bu fonksiyonda doldurulur.
        persist_root:  ZIP-STL yolu icin STL'lerin yazilacagi kok dizin.
        deadline_fallback: Termini bos gelen siparislere atanacak ISO tarih
                       (run_pipeline bos deadline'da hata verir). Bos ise
                       base_scenario['ref_date'] + 30 gun kullanilir.
        pending_store: PendingOrderStore (opsiyonel). Verilirse "ZIP var ama adet
                       yok" siparisleri burada operator incelemesine kaydedilir;
                       None ise yalniz atlanir (geriye uyum).
        on_stage:      Opsiyonel callback(str) — uzun asamalarin BASINDA insan-okur
                       durum metniyle cagrilir (orn. pipeline'a girerken
                       "2 siparis pipeline'da (588 parca)"). UI canli gorunurlugu
                       icin; hatasi yutulur, akisi etkilemez.
        on_result:     Opsiyonel callback(result) — pipeline sonucu ile,
                       mark_processed'dan ONCE cagrilir (R1 #4 siralama fix'i:
                       gecmis/gozlemci kaydi yazilamazsa mail islendi SAYILMAZ,
                       "gorunmez is" olusamaz). Callback istisna atarsa mail
                       kalici isaretlenmez ve sonraki turda yeniden denenir.

    Returns:
        run_pipeline ciktisi (dict) — yeni siparis islendiyse.
        None — yeni mail yok veya hicbir siparis cikmadi.
    """
    from scripts.demo_pipeline import run_pipeline
    from src.runtime.mail_ingest import ingest_order

    # mark_processed: at-least-once -- kayit yalniz kesin sonuc sonrasi.
    # MailSource ABC concrete no-op tasir, ama testler/dis kaynaklar MailSource'tan
    # TUREMEYEN duck-typed olabilir (orn. _OnceSource) -> getattr guard sart.
    _mark = getattr(mail_source, "mark_processed", None)

    mails = mail_source.fetch_new()
    if not mails:
        return None

    fallback = deadline_fallback or _default_deadline(base_scenario)

    orders: List[Dict[str, Any]] = []
    order_mails: List[Any] = []  # order üreten mailler — pipeline basarisinda register edilir

    for mail in _attachment_first(mails):
        try:
            order = ingest_order(mail, parser_role, persist_root=persist_root)
        except Exception as exc:
            logger.warning("mail_poller: ingest hatasi (%s): %s", mail.gonderen, exc)
            continue  # gecici hata -> mark_processed ETME (sonraki tur tekrar dener)

        if not order:
            # Spam / sinyal yok / parse fail -> kesin sonuc -> register (LLM tekrar yakma)
            if _mark is not None:
                _mark(mail)
            continue

        # Eksik-bilgi siparisi (ZIP var, adet yok) pipeline'a SOKULMAZ —
        # operator incelemesi gerekir; bos parca run_pipeline'i bozardi.
        # pending_store verildiyse operatorun /adet-gir'den islemesi icin kaydet.
        if order.get("needs_review"):
            if pending_store is not None:
                try:
                    pending_store.add(
                        order_id=order.get("order_id", ""),
                        customer=order.get("customer", ""),
                        sender=mail.gonderen,
                        deadline=order.get("deadline", "") or fallback,
                        priority_class=order.get("priority_class", 2),
                        konu=mail.konu,
                        stl_map=order.get("_stl_map", {}),
                        container=order.get("container"),
                    )
                except Exception as exc:
                    logger.warning(
                        "mail_poller: bekleyen siparis kaydedilemedi (%s): %s",
                        mail.gonderen, exc,
                    )
            logger.info(
                "mail_poller: eksik-bilgi siparisi atlandi (%s) — sebep=%s",
                mail.gonderen, order.get("review_reason"),
            )
            # Kesin: pending'e alindi -> register (tekrar zip ayristirmaya girme)
            if _mark is not None:
                _mark(mail)
            continue

        if not order.get("deadline"):
            order["deadline"] = fallback
        orders.append(order)
        order_mails.append(mail)

    if not orders:
        return None

    # Canli gorunurluk: pipeline UZUN surebilir (buyuk nesting) — operatore
    # "is alindi, yerlestirme kosuyor" sinyalini SIMDI ver, bitince sayac artar.
    if on_stage is not None:
        try:
            _n_parca = sum(
                int(p.get("qty", 0) or 0) for o in orders for p in o.get("parts", [])
            )
            on_stage(
                f"{len(orders)} sipariş işlenmeye alındı — nesting koşuyor"
                f" ({_n_parca} parça)"
            )
        except Exception:
            pass  # gorunurluk akisi asla bozmaz

    scenario = {**base_scenario, "orders": orders}
    # Plaka: bir siparis GERCEK plaka tasiyorsa (env PLATE_*) onu uygula.
    # Aksi halde base_scenario'nun demo container'ini BIRAK (None) ki run_pipeline
    # gercek parcalardan parti-bazli otomatik plaka turetsin — demo plakasi
    # gercek STL siparisine dayatilmaz (cekirdek politika her yoldan gecerli).
    stl_container = next((o["container"] for o in orders if o.get("container")), None)
    scenario = {**scenario, "container": stl_container}  # None -> pipeline otomatik

    try:
        result = run_pipeline(scenario)
    except Exception as exc:
        logger.warning(
            "mail_poller: pipeline hatasi (gecici -- sonraki tur tekrar dener) -- %s", exc
        )
        return None  # kesin degil -> mark_processed ETME

    # "Gecmisten sil -> yeniden islenebilir": order ureten maillerin idempotency
    # anahtarlarini sonuca ekle (varsa) -> on_result/_gecmis_kaydet bunlari
    # gecmis kaydina yazar; kayit silinince route bu anahtarlari da acar.
    # mail_source.idem_key_for yoksa (FakeMailbox/eski kaynak) sessizce atlanir.
    _idem_key_for = getattr(mail_source, "idem_key_for", None)
    if _idem_key_for is not None:
        try:
            _idem_keys = []
            _idem_map = {}  # order_id -> mail anahtari (siparis-bazli gecmis kaydi)
            for _o, _m in zip(orders, order_mails):
                _k = _idem_key_for(_m)
                if not _k:
                    continue
                _idem_keys.append(_k)
                _oid = _o.get("order_id")
                if _oid:
                    _idem_map[str(_oid)] = _k
            if _idem_keys:
                result["_idem_keys"] = _idem_keys
                if _idem_map:
                    result["_idem_key_map"] = _idem_map
        except Exception as exc:
            logger.warning("mail_poller: idem_key_for basarisiz -- %s", exc)

    # SIRALAMA (R1 #4): gecmis/gozlemci kaydi mark'tan ONCE. Ters sira
    # "gorunmez is" uretir: mail kalici isaretlenir ama gecmis yazimi (disk
    # dolu vb.) sessizce duserse operator isin yapildigini asla goremez ve
    # mail bir daha cekilmez. Kayit yazilamazsa mark atlanir -> yeniden dene.
    if on_result is not None:
        try:
            on_result(result)
        except Exception as exc:
            logger.error(
                "mail_poller: on_result/gecmis kaydi basarisiz (%s) — "
                "mail(ler) ISLENDI SAYILMADI, sonraki tur yeniden denenecek.", exc,
            )
            return result

    # "KESIN SONUC" TANIMI (2026-07-03 canli dersi + R1 #3): run_pipeline'in
    # donmesi yetmez — nesting adimi hatasini YUTUP note alanina yazar
    # (height=0). Kalici isaretleme TAM basari ister:
    #   * hicbir parti uretmedi  -> gecmiste durum="hata"  -> mark YOK
    #   * bazilari uretti (kismi)-> gecmiste durum="kismi" -> mark YOK
    #     (eksik partilerin siparisleri sessizce kaybolmasin; sonraki tur
    #     tum mail yeniden denenir — at-least-once, is idempotent)
    #   * tumu uretti            -> mark (mail bir daha islenmez)
    if not nesting_fully_succeeded(result):
        if nesting_produced_output(result):
            logger.warning(
                "mail_poller: KISMI basari — bazi partiler nesting uretemedi; "
                "mail(ler) islendi SAYILMADI, sonraki tur yeniden denenecek."
            )
        else:
            logger.warning(
                "mail_poller: pipeline dondu ama hicbir parti gecerli nesting "
                "uretmedi (tum yukseklikler 0/bos) — mail(ler) ISLENDI "
                "SAYILMADI, sonraki tur yeniden denenecek."
            )
        return result

    # TAM basari -> order-ureten mailleri kalici olarak kaydet
    if _mark is not None:
        for m in order_mails:
            _mark(m)

    return result


def nesting_fully_succeeded(result: Optional[Dict[str, Any]]) -> bool:
    """TUM partiler gecerli yukseklik uretti mi? (mark_processed esigi)

    R1 denetim bulgusu (kismi-basari yutmasi): 3 partiden 1'i basarili diye
    mail "tam islendi" sayilirsa, kalan 2 partinin siparisleri hicbir yerde
    gorunmeden kaybolur (eksik teslimat). Bu yuzden kalici isaretleme (mail
    bir daha islenmesin karari) TAM basari ister; kismi basari gecmise
    durum="kismi" olarak dusur ve mail sonraki turda yeniden denenir.
    """
    if not result:
        return False
    nesting = result.get("nesting_results") or {}
    if not nesting:
        return False
    return all(
        float((nr or {}).get("height_mm") or 0.0) > 0.0
        for nr in nesting.values()
    )


def nesting_produced_output(result: Optional[Dict[str, Any]]) -> bool:
    """Pipeline sonucu GECERLI nesting iceriyor mu? (kesin-sonuc tanimi)

    Gecerli = nesting_results'ta en az bir parti pozitif yukseklik uretmis.
    run_pipeline nesting hatalarini yutup {height_mm: 0, note: "..."} dondurur;
    bu yuzden "istisna atmadi" != "sonuc uretti". Poller (mark_processed) ve
    gecmis kaydi (durum=bitti/hata + dedup) AYNI tanimi paylasir — ikisi
    ayrissa ya kayip mail ya gorunmez kayit dogar.
    """
    if not result:
        return False
    nesting = result.get("nesting_results") or {}
    return any(
        float((nr or {}).get("height_mm") or 0.0) > 0.0
        for nr in nesting.values()
    )


def _default_deadline(base_scenario: Dict[str, Any]) -> str:
    """base_scenario['ref_date'] + 30 gun ISO tarih (deadline fallback)."""
    import datetime
    ref = base_scenario.get("ref_date")
    if isinstance(ref, datetime.date):
        return (ref + datetime.timedelta(days=30)).isoformat()
    return "2099-12-31"  # ref yoksa uzak-gelecek (pipeline'i bloklamaz)


# ---------------------------------------------------------------------------
# Poll durumu + arka plan thread
# ---------------------------------------------------------------------------

@dataclass
class PollState:
    """Poller'in gozlemlenebilir durumu (UI icin)."""

    enabled: bool = False
    interval_s: int = 120
    last_poll_ts: Optional[float] = None       # son tur (epoch); None=hic kosmadi
    last_processed: int = 0                     # son turda islenen siparis sayisi
    total_processed: int = 0                    # kumulatif
    last_error: Optional[str] = None
    runs: int = 0                               # toplam tur sayisi
    # Canli gorunurluk: tur su an kosuyorsa True + insan-okur asama metni.
    # "1 tarama 0 is" belirsizligini cozer — uzun nesting kosusunda operator
    # isin ALINDIGINI gorur ("2 siparis pipeline'da..."), bitince sayac artar.
    inflight: bool = False
    inflight_detail: str = ""

    def snapshot(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_s": self.interval_s,
            "last_poll_ts": self.last_poll_ts,
            "last_processed": self.last_processed,
            "total_processed": self.total_processed,
            "last_error": self.last_error,
            "runs": self.runs,
            "inflight": self.inflight,
            "inflight_detail": self.inflight_detail,
        }


class MailPoller:
    """process_inbox_once'i daemon thread'de periyodik kosar.

    on_result(pipeline_result) callback'i her basarili (siparis ureten) turda
    cagrilir — app bunu LAST_RESULT'a yazabilir. now() enjekte edilebilir
    (test determinizmi; Date.now yasagi yok ama enjeksiyon test kolayligi).
    """

    def __init__(
        self,
        *,
        make_source: Callable[[], Any],     # her tur taze MailSource uretir
        parser_role: Any,
        base_scenario: Dict[str, Any],
        persist_root: Optional[str],
        interval_s: int = 120,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        now: Optional[Callable[[], float]] = None,
        pending_store: Any = None,
        inflight_lock: Optional[threading.Lock] = None,
    ) -> None:
        self._make_source = make_source
        self._parser_role = parser_role
        self._base_scenario = base_scenario
        self._persist_root = persist_root
        self._on_result = on_result
        self._now = now
        self._pending_store = pending_store
        self.state = PollState(interval_s=interval_s)
        # _stop: AKTIF thread'in stop sinyali. Her start() TAZE bir Event yaratir
        # -> eski thread eski (set edilmis) event'iyle olur, yenisi temiz event'le
        # kosar. Boylece restart'ta join/clear gerekmez ve "ghost thread" olusmaz.
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # _lock: start/stop/restart state-machine + tum PollState yazimlari
        # (runs/total_processed/last_error/last_processed/last_poll_ts) atomikligi.
        # restart kisa tutulur (eski thread'i BEKLEMEZ; uzun pipeline bloke
        # etmesin), bu yuzden re-entrant degil; Lock yeterli.
        self._lock = threading.Lock()
        # _inflight_lock (FIX 3): ayni anda YALNIZ bir tarama (fetch->pipeline->
        # mark) yurusun. restart() eski thread'i JOIN etmeden yeni thread
        # baslattigindan (UI kilitlenmesin), eski tur uzun NFV pipeline icindeyken
        # yeni thread 'ilk-tarama-hemen' ile ayni maili PARALEL fetch edebilirdi
        # (kayit yalniz pipeline sonunda -> ayni UID iki thread'de). Non-reentrant
        # + acquire(blocking=False): kilit tutuluysa tarama ATLANIR (bloklamaz ->
        # UI donmaz, join yok -> deadlock yok). app manuel /otonom ile ORTAK kilit
        # enjekte eder (sync + async job + poller ayni mailbox'a paralel girmez).
        self._inflight_lock = inflight_lock or threading.Lock()

    # ------------------------------------------------------------------
    def poll_once(self) -> Optional[Dict[str, Any]]:
        """Tek tur: kaynak uret + isle + durum guncelle + callback. Atmaz."""
        with self._lock:
            self.state.runs += 1
            if self._now is not None:
                self.state.last_poll_ts = self._now()
        # FIX 3: inflight-lock. Onceki tarama (restart oncesi eski thread) hala
        # fetch/pipeline icindeyse yeni tarama ayni maili PARALEL cekmesin.
        # Non-blocking: kilit tutuluysa bu turu ATLA (bloklama/join yok -> UI
        # donmaz, deadlock yok). Eski tur bitince kilit serbest kalir.
        if not self._inflight_lock.acquire(blocking=False):
            logger.info(
                "mail_poller: onceki tarama surerken yeni tarama atlandi (inflight-lock)"
            )
            return None
        try:
            with self._lock:
                self.state.inflight = True
                self.state.inflight_detail = "kutu taranıyor"

            def _stage(msg: str) -> None:
                with self._lock:
                    self.state.inflight_detail = str(msg)

            source = self._make_source()
            # on_result process_inbox_once ICINDE, mark_processed'dan ONCE
            # cagrilir (R1 #4 siralamasi) — burada ikinci kez CAGRILMAZ.
            result = process_inbox_once(
                source,
                self._parser_role,
                base_scenario=self._base_scenario,
                persist_root=self._persist_root,
                pending_store=self._pending_store,
                on_stage=_stage,
                on_result=self._on_result,
            )
            with self._lock:
                self.state.last_error = None
            if result is not None:
                n = len(result.get("ranked_orders", [])) or len(
                    result.get("nesting_results", {})
                )
                with self._lock:
                    self.state.last_processed = n
                    self.state.total_processed += n
            else:
                with self._lock:
                    self.state.last_processed = 0
            return result
        except Exception as exc:
            with self._lock:
                self.state.last_error = str(exc)
            logger.warning("mail_poller: poll_once hatasi: %s", exc)
            return None
        finally:
            with self._lock:
                self.state.inflight = False
                self.state.inflight_detail = ""
            self._inflight_lock.release()

    # ------------------------------------------------------------------
    def _loop(self, stop_ev: threading.Event) -> None:
        # Her thread KENDI stop event'ini alir (self._stop degil) -> restart
        # yeni thread baslatip bu thread'i clear etse bile bu dongu eski
        # event'i dinler ve duzgun olur (ghost thread yok).
        # ILK tarama HEMEN (interval beklemeden) — kullanici 'actim ama hic
        # taramadi' gormesin. stop bu thread baslar baslamaz set edildiyse atla.
        if not stop_ev.is_set():
            self.poll_once()
        # Sonraki turlar: Event.wait(interval) — stop set edilince hemen cikar.
        while not stop_ev.wait(self.state.interval_s):
            self.poll_once()

    def _start_locked(self) -> None:
        """start() govdesi — cagiran self._lock TUTMALI. Taze event + thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop = threading.Event()          # TAZE event (clear yerine yeni)
        self.state.enabled = True
        self._thread = threading.Thread(
            target=self._loop, args=(self._stop,), name="mail-poller", daemon=True
        )
        self._thread.start()

    def start(self) -> None:
        """Daemon thread baslat (zaten calisiyorsa no-op)."""
        with self._lock:
            self._start_locked()

    def restart(self) -> None:
        """Calisan poller'i durdurup yeni interval ile yeniden baslat.

        Eski thread'e stop sinyali verilir ama BEKLENMEZ (NFV pipeline dakikalar
        surebilir; join etmek UI'i kilitlerdi). Eski thread KENDI eski event'iyle
        bir sonraki wait'te (veya pipeline bitince) temiz olur; yeni thread taze
        event + guncel interval ile baslar. _loop ilk-tarama-hemen sayesinde
        restart aninda yeni bir tur kosar.
        """
        with self._lock:
            self._stop.set()                    # eski thread'e dur sinyali
            self._thread = None                 # referansi birak (eski kendi olur)
            self._start_locked()                # taze event + yeni thread

    def stop(self) -> None:
        """Thread'i durdur (bir sonraki wait'te cikar)."""
        with self._lock:
            self._stop.set()
            self.state.enabled = False

    def is_running(self) -> bool:
        """Poller thread'i su an aktif mi? (route'lar private attr'a uzanmasin.)"""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

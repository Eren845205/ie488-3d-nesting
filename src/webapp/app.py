"""app.py — Konteyner Nesting Sistemi Flask web uygulamasi.

Kullanim:
    python -m src.webapp.app          # Sunucu baslat (127.0.0.1:8765)

Rotalar:
    GET  /       Ana sayfa (senaryo ozeti + Pipeline Calistir dugmesi)
    POST /run    Demo pipeline kosturur, /sonuc'a yonlendirir
    GET  /sonuc  Son kosun sonuclari
    POST /ozet   LLM yonetici ozeti olustur (LLM aktif ise)
    POST /sor    LLM asistan sorusu (LLM aktif ise)

LLM zarif dusus:
    configs/llm.local.json yoksa veya Ollama kapaliysa, LLM bolumlerini
    gizle — uygulama COKMEZ.

Durum yonetimi:
    _last_result ve _conversation_turns app.config uzerinde tutulur;
    bu sayede her create_app() cagrisinda sifirlanir (test izolasyonu).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Flask, Response, jsonify, redirect, render_template,
    request, session, url_for,
)

# Rate limiting — optional dep; no-op if flask-limiter not installed
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _LIMITER_AVAILABLE = True
except ImportError:
    _LIMITER_AVAILABLE = False
    Limiter = None  # type: ignore

# Proje kokunu sys.path'e ekle (dogrudan calistirma icin)
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

MAX_SORU_LEN = 2000  # /sor soru uzunluk siniri (DoS korumasi)

# ---------------------------------------------------------------------------
# SSRF allowlist — Ollama base_url yalnizca localhost'a izin verilir
# ---------------------------------------------------------------------------
import re as _re

_ALLOWED_BASE_URL_PATTERN = _re.compile(
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/.*)?$"
)


def _validate_ollama_base_url(url: str) -> bool:
    """base_url'in localhost/127.0.0.1 ile sinirli oldugunu dogrular (SSRF korumasi)."""
    return bool(_ALLOWED_BASE_URL_PATTERN.match(url))


# ---------------------------------------------------------------------------
# Paylasilan seri-hale-getirici yardimci (Bulgu 6: /otonom tutarli projeksiyon)
# ---------------------------------------------------------------------------

def _nesting_result_projection(nr: dict) -> dict:
    """Nesting sonuc dict'inden guvenli scalar alanlar cikarir.

    /otonom ve /run yanit yollari bu ortak helper'i kullanir;
    buyuk/seri-edilemeyen nesneler disarda kalir.
    """
    return {
        "height_mm": nr.get("height_mm", 0.0),
        "density": nr.get("density", 0.0),
        "n_parts": nr.get("n_parts", 0),
    }


def _load_llm_components(
    provider_override: Any = None,
    enabled: bool = True,
) -> Optional[Dict[str, Any]]:
    """LLM bilesenleri yukle; hata veya eksik konfig varsa None dondur.

    Parametreler
    ------------
    provider_override : test injection icin sahte saglayici (None = gercek)
    enabled           : False ise yuklemeden None dondur (LLM devre disi)
    """
    if not enabled:
        return None

    try:
        from src.llm.config import LLMConfig
        from src.llm.audit import AuditLogger
        from src.llm.prompts import PromptRegistry
        from src.llm.roles.report import ReportRole
        from src.llm.roles.assistant import AssistantRole, Conversation
        from src.llm.roles.parser import ParserRole

        cfg_path = _ROOT / "configs" / "llm.local.json"
        if not cfg_path.exists():
            logger.info("LLM: configs/llm.local.json bulunamadi — LLM devre disi.")
            return None

        cfg = LLMConfig.from_file(str(cfg_path))
        cfg.validate()

        audit = AuditLogger(
            log_dir=str(_ROOT / cfg.audit.log_dir),
            payload_log_dir=str(_ROOT / cfg.audit.payload_log_dir),
            payload_logging=cfg.audit.payload_logging_default,
        )

        registry = PromptRegistry(
            prompts_dir=str(_ROOT / "prompts"),
            enforce_lock=True,
        )

        if provider_override is not None:
            provider = provider_override

            def _provider_for(role_name: str):  # noqa: E306
                return provider_override
        else:
            # Gercek Ollama saglayicisi — model bazli provider cache
            from src.llm.providers.openai_compat import OpenAICompatProvider

            prov_cfg = cfg.provider_for_role("report")
            _base_url = prov_cfg.base_url or "http://localhost:11434"
            # SSRF allowlist: yalnizca localhost / 127.0.0.1 kabul edilir (Bulgu 4)
            if not _validate_ollama_base_url(_base_url):
                logger.error(
                    "Ollama base_url SSRF allowlist'i disinda: %r — LLM devre disi.",
                    _base_url,
                )
                return None

            _prov_cache: Dict[str, Any] = {}

            def _provider_for(role_name: str):  # noqa: E306
                rc = cfg.roles.get(role_name)
                model = rc.model if rc is not None else cfg.role("report").model
                if model not in _prov_cache:
                    _prov_cache[model] = OpenAICompatProvider(
                        base_url=_base_url,
                        model=model,
                        timeout_s=prov_cfg.timeout_s,
                    )
                return _prov_cache[model]

            # Geriye donuk uyum: 'provider' degiskeni ilk provider'a bakar
            provider = _provider_for("report")

        from src.llm.roles.explainer import ExplainerRole
        from src.llm.roles.watcher import WatcherRole
        from src.llm.roles.teklif import TeklifRole

        report_role = ReportRole(
            provider=_provider_for("report"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("report"),
        )

        assistant_role = AssistantRole(
            provider=_provider_for("assistant"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("assistant"),
            conversation=Conversation(),
        )

        parser_role = ParserRole(
            provider=_provider_for("parser"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("parser"),
        )

        explainer_role = ExplainerRole(
            provider=_provider_for("explainer"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("explainer"),
        )

        watcher_role = WatcherRole(
            provider=_provider_for("watcher"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("watcher"),
        )

        teklif_role = TeklifRole(
            provider=_provider_for("teklif"),
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("teklif"),
        )

        return {
            "report_role": report_role,
            "assistant_role": assistant_role,
            "parser_role": parser_role,
            "explainer_role": explainer_role,
            "watcher_role": watcher_role,
            "teklif_role": teklif_role,
            "llm_active": True,
            # /health probe icin provider referansi (canli Ollama saglik kontrolu)
            "health_provider": provider,
        }

    except Exception as exc:
        logger.warning("LLM bilesenleri yuklenemedi (%s) — LLM devre disi.", exc)
        return None


def _build_grounded_context(pipeline_result: Dict[str, Any]) -> Any:
    """Pipeline sonucundan GroundedContext olustur."""
    from src.llm.grounding import GroundedContext, SourceDoc

    nesting = pipeline_result.get("nesting_results", {})
    pricing = pipeline_result.get("pricing_results", {})
    warnings = pipeline_result.get("warnings", [])

    kaynaklar = []

    for batch_id, nr in nesting.items():
        height = nr.get("height_mm", 0.0)
        density = nr.get("density", 0.0)
        n_parts = nr.get("n_parts", 0)
        icerik = (
            f"Yukseklik: {height} mm\n"
            f"Doluluk: {density:.1%}\n"
            f"Yerlestirilen parca: {n_parts}"
        )
        kaynaklar.append(SourceDoc(
            id=f"yerlesim#{batch_id}",
            tip="yerlesim",
            icerik=icerik,
            uretici="nesting3d.dblf",
        ))

    for batch_id, pr in pricing.items():
        total = pr.get("total_price", 0.0)
        breakdown = pr.get("breakdown", [])
        breakdown_text = "\n".join(f"- {line}" for line in breakdown)
        icerik = f"Nihai fiyat: {total:.2f} USD\n{breakdown_text}"
        kaynaklar.append(SourceDoc(
            id=f"fiyat#{batch_id}",
            tip="fiyat",
            icerik=icerik,
            uretici="pricing.engine",
        ))

    if warnings:
        warn_lines = []
        for w in warnings:
            if isinstance(w, dict):
                oid = w.get("order_id", "?")
                delay = w.get("delay_days", "?")
            else:
                oid = getattr(w, "order_id", "?")
                delay = getattr(w, "delay_days", "?")
            warn_lines.append(f"- {oid}: {delay} gun gecikme")
        icerik = "Uyarilar:\n" + "\n".join(warn_lines)
        kaynaklar.append(SourceDoc(
            id="termin#cizelge",
            tip="termin",
            icerik=icerik,
            uretici="scheduling.report",
        ))

    return GroundedContext(
        is_id="demo-pipeline",
        kaynaklar=kaynaklar,
    )


_TURKCE_AYLAR = {
    "ocak": "01", "subat": "02", "mart": "03", "nisan": "04",
    "mayis": "05", "haziran": "06", "temmuz": "07", "agustos": "08",
    "eylul": "09", "ekim": "10", "kasim": "11", "aralik": "12",
}


def _resolve_mail_source_config(root) -> Dict[str, Any]:
    """Mail kaynak konfigini coz: oncelik mail.local.json > .env MAIL_* > fake.

    - configs/mail.local.json varsa (UI'dan kaydedilmis) O kullanilir.
    - Yoksa .env'deki MAIL_PROVIDER/MAIL_USER/MAIL_PASSWORD/MAIL_FOLDER.
    - O da yoksa demo FakeMailbox.
    """
    p = root / "configs" / "mail.local.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("mail.local.json okunamadi (%s) — .env/demo'ya dusuluyor", exc)
    prov = os.environ.get("MAIL_PROVIDER", "").strip()
    if prov:
        return {
            "provider": prov,
            "user": os.environ.get("MAIL_USER", "").strip(),
            "password": os.environ.get("MAIL_PASSWORD", "").strip(),
            "folder": os.environ.get("MAIL_FOLDER", "INBOX").strip() or "INBOX",
        }
    return {"source": "fake"}


def _normalize_deadline(deadline_str: str, mail_tarih: str = "") -> str:
    """Termin dizesini ISO 8601 (YYYY-MM-DD) formatina donusturur.

    Desteklenen formatlar:
      - ISO 8601: "2026-06-19" -> dogrudan don
      - Turkce tam tarih: "19 Haziran 2026" -> "2026-06-19"
      - Bos/tanimsiz: mail tarihinden +30 gun fallback
    Hicbir durumda atmaz; en kotu fallback bugunden +30 gun.
    """
    from datetime import date, timedelta

    s = (deadline_str or "").strip()

    # ISO formatini dene
    if s:
        try:
            date.fromisoformat(s[:10])
            return s[:10]
        except ValueError:
            logger.debug("_normalize_deadline: ISO parse basarisiz: %r", s[:10])

    # Turkce "GG Ay YYYY" formatini dene
    if s:
        parts = s.replace(",", "").split()
        if len(parts) == 3:
            gun, ay_str, yil = parts[0], parts[1].lower(), parts[2]
            ay = _TURKCE_AYLAR.get(ay_str, "")
            if ay and gun.isdigit() and yil.isdigit():
                try:
                    candidate = f"{yil}-{ay}-{int(gun):02d}"
                    date.fromisoformat(candidate)
                    return candidate
                except ValueError:
                    logger.debug(
                        "_normalize_deadline: Turkce tarih parse basarisiz: %r",
                        s,
                    )

    # Fallback: mail tarihinden +30 gun veya bugunden +30 gun
    try:
        mail_date = date.fromisoformat(mail_tarih[:10])
        return (mail_date + timedelta(days=30)).isoformat()
    except Exception:
        return (date.today() + timedelta(days=30)).isoformat()


def create_app(
    testing: bool = False,
    llm_provider_override: Any = None,
    llm_enabled: bool = True,
    orders_path: Optional[str] = None,
    load_env: bool = True,
) -> Flask:
    """Flask uygulama factory.

    Parametreler
    ------------
    testing              : bool
        True ise test modu aktif.
    llm_provider_override: LLMProvider
        Test injection icin sahte saglayici. None = gercek Ollama.
    llm_enabled          : bool
        False ise LLM tamamen devre disi (test izolasyonu icin).
    orders_path          : str | None
        Siparis havuzu JSON dosya yolu. None ise varsayilan (data/orders.json).
        Test izolasyonu icin tmp_path gecirilebilir.
    """
    from pathlib import Path as _Path

    # .env varsa ortam degiskenlerini yukle (python-dotenv). override=False:
    # mevcut sistem/.bat env'i oncelikli kalir, .env yalniz eksikleri doldurur.
    # testing modunda ASLA yuklenmez (testler .env'deki gercek mail/parola ile
    # kirlenmesin; otonom testleri gercek IMAP'a baglanmaya calismasin).
    if load_env and not testing:
        try:
            from dotenv import load_dotenv
            load_dotenv(override=False)
        except Exception:
            pass

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    app.config["TESTING"] = testing

    # Yuklem buyuklugu siniri — yükleme DoS'a karsi (Bulgu 1)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

    # Durum: her create_app() cagrisinda sifirlanir (test izolasyonu)
    app.config["LAST_RESULT"] = None
    # NOT: CONVERSATION_TURNS artik Flask session'da (per-kullanici); bu kaldir.
    # Geriye donuk uyumluluk: app.config["CONVERSATION_TURNS"] diger testler
    # ile cakismamasi icin bos liste olarak baslatilmaya devam eder.
    app.config["CONVERSATION_TURNS"] = []

    # Siparis havuzu yolu
    if orders_path is not None:
        app.config["ORDERS_PATH"] = _Path(orders_path)
    else:
        app.config["ORDERS_PATH"] = None  # orders_store varsayilani kullanir

    # LLM bilesenleri: provider_override verildiyse LLM aktif; yoksa
    # llm_enabled=False ise tamamen kapali
    _effective_enabled = llm_enabled or (llm_provider_override is not None)
    _llm: Optional[Dict[str, Any]] = _load_llm_components(
        provider_override=llm_provider_override,
        enabled=_effective_enabled,
    )
    llm_active = _llm is not None
    # Baslangic saglik raporu (_startup_health_report) icin erisim
    app.config["LLM_COMPONENTS"] = _llm

    # Rate limiter (Bulgu 2) — flask-limiter yuklu degilse no-op
    if _LIMITER_AVAILABLE and Limiter is not None:
        _limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[],
            storage_uri="memory://",
        )
    else:
        _limiter = None

    _register_routes(app, llm_components=_llm, llm_active=llm_active, limiter=_limiter)
    return app


def _register_routes(
    app: Flask,
    llm_components: Optional[Dict[str, Any]] = None,
    llm_active: bool = False,
    limiter: Any = None,
) -> None:
    """Tum rotalari app'e kaydeder."""

    # Rate-limit dekorator yardimcisi — limiter None ise gecmis decorator doner
    def _limit(limit_string: str):
        if limiter is not None:
            return limiter.limit(limit_string)
        # no-op: ayni fonksiyonu olduğu gibi döndürür
        def _passthrough(f):
            return f
        return _passthrough

    # -----------------------------------------------------------------------
    # Guvenlik: admin oturum (session) + CSRF (uygulama geneli)
    # -----------------------------------------------------------------------
    # ADMIN_PASSWORD env'den okunur (kodda sabit YOK). Bossa login devre disi
    # (demo kolayligi). CSRF testing=False'ta aktif; testing=True'da mevcut
    # testleri kirmamak icin atlanir (Flask-WTF'in WTF_CSRF_ENABLED=False mantigi).
    _ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    _AUTH_EXEMPT = {"giris", "cikis", "health", "static"}   # oturum gerektirmez
    _CSRF_EXEMPT = {"health", "static"}                      # CSRF gerektirmez

    @app.before_request
    def _security_guard():
        # Her oturuma CSRF token garanti et (testte de — context_processor icin)
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)

        # Test izolasyonu: auth+csrf atlanir (mevcut testler token gondermez)
        if app.config.get("TESTING"):
            return

        ep = request.endpoint or ""

        # 1) Admin oturum (ADMIN_PASSWORD bossa login tamamen devre disi)
        if _ADMIN_PASSWORD and ep not in _AUTH_EXEMPT and not session.get("authed"):
            if request.method == "GET":
                return redirect(url_for("giris", next=request.path))
            return jsonify({"hata": "Oturum gerekli — lütfen giriş yapın."}), 401

        # 2) CSRF (durum degistiren metodlar)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and ep not in _CSRF_EXEMPT:
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
            if not (sent and hmac.compare_digest(sent, session.get("_csrf", ""))):
                return jsonify({"hata": "CSRF doğrulaması başarısız — sayfayı yenileyin."}), 403

    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": session.get("_csrf", "")}

    @app.route("/giris", methods=["GET", "POST"])
    def giris():
        """Admin giris ekrani. ADMIN_PASSWORD bossa dogrudan ana sayfaya gecer."""
        if not _ADMIN_PASSWORD:
            return redirect(url_for("index"))
        if request.method == "POST":
            # bytes karsilastirma: Turkce/unicode parolada compare_digest ASCII
            # kisitina takilmaz (str karsilastirma non-ASCII'de TypeError verir)
            _girilen = request.form.get("password", "").encode("utf-8")
            if hmac.compare_digest(_girilen, _ADMIN_PASSWORD.encode("utf-8")):
                session["authed"] = True
                _next = request.args.get("next") or url_for("index")
                # acik-yonlendirme korumasi: yalniz site-ici mutlak yol
                if not _next.startswith("/") or _next.startswith("//"):
                    _next = url_for("index")
                return redirect(_next)
            return render_template("giris.html", hata="Parola yanlış.")
        if session.get("authed"):
            return redirect(url_for("index"))
        return render_template("giris.html", hata=None)

    @app.route("/cikis", methods=["GET", "POST"])
    def cikis():
        """Oturumu kapat."""
        session.pop("authed", None)
        return redirect(url_for("giris"))

    # -----------------------------------------------------------------------
    # Arka plan poll (otomatik tetik): periyodik kutu kontrolu -> pipeline
    # -----------------------------------------------------------------------
    from src.runtime.mail_poller import MailPoller
    from src.runtime.pending_orders import PendingOrderStore
    from scripts.demo_pipeline import RICH_SCENARIO as _POLL_BASE_SCENARIO

    # Eksik-bilgi (ZIP var, adet yok) siparis deposu. Testte gecici dizine yazar
    # (test izolasyonu); aksi halde data/pending_orders. /otonom + poller buraya
    # kaydeder, /adet-gir buradan okur.
    if app.config.get("TESTING"):
        import tempfile as _tf
        _pending_root = Path(_tf.mkdtemp(prefix="pending_orders_"))
    else:
        _pending_root = _ROOT / "data" / "pending_orders"
    _pending_store = PendingOrderStore(_pending_root)
    app.config["PENDING_STORE"] = _pending_store

    def _poll_make_source():
        from src.runtime.mail_ingest import make_mail_source
        cfg = ({"source": "fake"} if app.config.get("TESTING")
               else _resolve_mail_source_config(_ROOT))
        return make_mail_source(cfg)

    def _poll_on_result(result):
        # Poll sonucu da /sonuc ekranina yazilir (tek-tik /run ile ayni yer)
        result["used_demo"] = False
        app.config["LAST_RESULT"] = result

    try:
        _poll_interval = int(os.environ.get("MAIL_POLL_INTERVAL", "120") or "120")
    except ValueError:
        _poll_interval = 120

    _poller = MailPoller(
        make_source=_poll_make_source,
        parser_role=(llm_components or {}).get("parser_role"),
        base_scenario=_POLL_BASE_SCENARIO,
        persist_root=str(_ROOT / "data" / "mail_stl"),
        interval_s=_poll_interval,
        on_result=_poll_on_result,
        now=time.time,
        pending_store=_pending_store,
    )
    app.config["MAIL_POLLER"] = _poller

    # Otomatik baslat: MAIL_POLL_ENABLED=1 (testte baslamaz)
    _poll_auto = os.environ.get("MAIL_POLL_ENABLED", "").strip().lower()
    if _poll_auto in ("1", "true", "yes", "on") and not app.config.get("TESTING"):
        _poller.start()

    @app.route("/poll/durum", methods=["GET"])
    def poll_durum():
        return jsonify(_poller.state.snapshot())

    @app.route("/poll/baslat", methods=["POST"])
    def poll_baslat():
        _poller.start()
        return jsonify({"ok": True, "durum": _poller.state.snapshot()})

    @app.route("/poll/durdur", methods=["POST"])
    def poll_durdur():
        _poller.stop()
        return jsonify({"ok": True, "durum": _poller.state.snapshot()})

    @app.route("/health", methods=["GET"])
    def health():
        """Demo oncesi saglik kontrolu: web ayakta + LLM (Ollama) hazir mi.

        Demo'dan ONCE `GET /health` ile LLM'in canli oldugu dogrulanir; Ollama
        kapaliysa veya model cekilmemisse demo sirasinda degil burada yakalanir.
        HTTP 200 = her sey hazir; 503 = LLM aktif ama probe basarisiz.
        """
        out: Dict[str, Any] = {"web": "ok", "llm_active": llm_active}

        if not llm_active:
            # LLM kapali (config yok / devre disi). Web calisiyor; LLM gerektiren
            # ozellikler (asistan, teklif, aciklama) calismaz.
            out["llm"] = "disabled"
            out["detail"] = (
                "LLM devre disi (configs/llm.local.json yok veya yuklenemedi). "
                "Nesting calisir; asistan/teklif/aciklama calismaz."
            )
            return jsonify(out), 200

        provider = (llm_components or {}).get("health_provider")
        checker = getattr(provider, "health_check", None)
        if not callable(checker):
            # Provider probe desteklemiyor (or. sahte saglayici) — aktif say.
            out["llm"] = "ok"
            out["detail"] = "LLM aktif (probe desteklenmeyen saglayici)."
            return jsonify(out), 200

        ok, detail = checker()
        out["llm"] = "ok" if ok else "fail"
        out["detail"] = detail
        return jsonify(out), (200 if ok else 503)

    @app.route("/", methods=["GET"])
    def index():
        """Ana sayfa: uygulama tanitimi + havuz ozeti + calistir dugmesi."""
        from scripts.demo_pipeline import SCENARIO, RICH_SCENARIO
        from src.webapp.orders_store import load_orders

        _opath = app.config.get("ORDERS_PATH")
        pool_orders = load_orders(_opath)
        pool_count = len(pool_orders)

        # Onizleme, SECILI radyo ile TUTARLI olmali: varsayilan 'rich' (zengin
        # senaryo, calistir dugmesinin de varsayilani). Eski hata: onizleme her
        # zaman SCENARIO (5 siparis) gosteriyordu ama varsayilan kosu RICH (3).
        scenario_type = (request.args.get("scenario") or "rich").strip()
        demo = RICH_SCENARIO if scenario_type == "rich" else SCENARIO

        # Senaryo ozeti: havuz doluysa havuzdan, bos ise SECILI demo senaryodan
        container = demo.get("container", {})
        capacity = demo.get("capacity", {})
        display_orders = pool_orders if pool_orders else demo.get("orders", [])

        return render_template(
            "index.html",
            orders=display_orders,
            container=container,
            capacity=capacity,
            llm_active=llm_active,
            pool_count=pool_count,
            pool_is_custom=bool(pool_orders),
            scenario_type=scenario_type,
        )

    @app.route("/run", methods=["POST"])
    def run():
        """Havuz doluysa havuz senaryosunu, bos ise demo senaryosunu kosturur.

        Form parametresi: scenario_type = 'standard' | 'rich' (varsayilan 'rich')
        """
        from scripts.demo_pipeline import SCENARIO, RICH_SCENARIO, run_pipeline
        from src.webapp.orders_store import load_orders, orders_to_scenario

        _opath = app.config.get("ORDERS_PATH")
        pool_orders = load_orders(_opath)

        if pool_orders:
            scenario = orders_to_scenario(pool_orders)
            used_demo = False
        else:
            # Senaryo tipi: form'dan al; default = zengin senaryo
            scenario_type = (request.form.get("scenario_type") or "rich").strip()
            scenario = RICH_SCENARIO if scenario_type == "rich" else SCENARIO
            used_demo = True

        # Nesting modu: "auto" (VARSAYILAN, veri-odaklı NFV/heightmap seçimi) | "nfv" | "heightmap".
        # auto → predict_nfv_benefit pipeline içinde çözer (cavity-zengin→NFV, kutu/ince-plaka→heightmap).
        _nm = request.form.get("nesting_mode", "auto")
        nesting_mode = _nm if _nm in ("auto", "nfv", "heightmap") else "auto"
        # NFV kalite seviyesi: "max" → donanım-tavanı oryantasyon (en kısa istif, en yavaş); default "fast" (n=8).
        nfv_quality = "max" if request.form.get("nfv_quality") == "max" else "fast"
        scenario = {**scenario, "nesting_mode": nesting_mode, "nfv_quality": nfv_quality}

        result = run_pipeline(scenario)
        result["used_demo"] = used_demo
        app.config["LAST_RESULT"] = result
        # Sohbet gecmisi: session'a sifirla (per-kullanici izolasyonu, Bulgu 5)
        session["conversation_turns"] = []
        app.config["CONVERSATION_TURNS"] = []  # geriye-donuk uyumluluk
        return redirect(url_for("sonuc"))

    @app.route("/sonuc", methods=["GET"])
    def sonuc():
        """Son kosun sonuclari."""
        result = app.config.get("LAST_RESULT")
        if result is None:
            return redirect(url_for("index"))

        ranked = result.get("ranked_orders", [])
        batches = result.get("batches", [])
        warnings = result.get("warnings", [])
        nesting_results = result.get("nesting_results", {})
        pricing_results = result.get("pricing_results", {})
        elapsed = result.get("elapsed_sec", 0.0)

        total_revenue = sum(
            pr.get("total_price", 0.0) for pr in pricing_results.values()
        )
        n_orders = len(ranked)
        n_batches = len(batches)
        n_warnings = len(warnings)

        used_demo = result.get("used_demo", False)

        # Katman-bazli maliyet + tasarruf (AM makine-zamani): her batch icin
        # height_mm -> katman sayisi -> EUR/saat. Tuner varsa baseline'a gore
        # tasarruf da hesaplanir (nesting Z-height dususu -> dogrudan euro).
        from src.pricing.layer_cost import (
            LayerCostParams, compute_cost, compute_savings,
        )
        _lc_params = LayerCostParams()  # default 0.12mm / 20sn / 10EUR
        for _nr in nesting_results.values():
            _h = _nr.get("height_mm", 0.0)
            if not _h:
                continue
            _nr["layer_cost"] = compute_cost(_h, _lc_params).to_dict()
            _impr = (_nr.get("tuner") or {}).get("improvement_mm", 0.0) or 0.0
            if _impr > 0:
                _nr["layer_savings"] = compute_savings(
                    _h + _impr, _h, _lc_params
                ).to_dict()

        # Sohbet gecmisi: session'dan oku (per-kullanici)
        _sohbet = session.get("conversation_turns", [])

        return render_template(
            "sonuc.html",
            ranked=ranked,
            batches=batches,
            warnings=warnings,
            nesting_results=nesting_results,
            pricing_results=pricing_results,
            elapsed=elapsed,
            total_revenue=total_revenue,
            n_orders=n_orders,
            n_batches=n_batches,
            n_warnings=n_warnings,
            llm_active=llm_active,
            llm_ozet=None,
            llm_ozet_hata=None,
            sohbet=_sohbet,
            used_demo=used_demo,
            has_portfolio=any(
                nesting_results.get(b.batch_id, {}).get("portfolio") is not None
                for b in batches
            ),
        )

    @app.route("/ozet", methods=["POST"])
    @_limit("10 per minute")
    def ozet():
        """LLM yonetici ozeti olustur.

        Yanit: JSON {ozet, hata, topraklama_uyarisi}
        """
        if not llm_active or llm_components is None:
            return jsonify({"hata": "LLM aktif degil.", "ozet": None}), 503

        result = app.config.get("LAST_RESULT")
        if result is None:
            return jsonify({"hata": "Once pipeline calistirin.", "ozet": None}), 400

        try:
            from src.llm.roles.report import ReportInput
            from src.llm.structured import ValidationStatus

            context = _build_grounded_context(result)

            pricing_results = result.get("pricing_results", {})
            total_revenue = sum(
                pr.get("total_price", 0.0) for pr in pricing_results.values()
            )

            report_input = ReportInput(
                is_id="demo-pipeline",
                n_orders=len(result.get("ranked_orders", [])),
                n_batches=len(result.get("batches", [])),
                n_warnings=len(result.get("warnings", [])),
                total_revenue_usd=total_revenue,
                context=context,
            )

            report_role = llm_components["report_role"]
            report_result = report_role.run(report_input)

            if report_result.grounding_blocked:
                return jsonify({
                    "ozet": None,
                    "hata": None,
                    "topraklama_uyarisi": (
                        "LLM ciktisi sayi-topraklama dogrulamasini gecemedi. "
                        f"Dogrulanamayan sayilar: {report_result.grounding_detail}. "
                        "Lutfen manuel ozet yazin."
                    ),
                }), 200

            if report_result.status == ValidationStatus.INVALID or report_result.fallback:
                fallback_text = ""
                if report_result.fallback:
                    fallback_text = report_result.fallback.raw_text
                return jsonify({
                    "ozet": None,
                    "hata": "LLM gecerli yanit uretemedi. Lutfen tekrar deneyin.",
                    "fallback_text": fallback_text[:300] if fallback_text else "",
                }), 200

            data = report_result.data or {}
            return jsonify({
                "ozet": data.get("govde_md", ""),
                "baslik": data.get("baslik", ""),
                "kaynaklar": data.get("kullanilan_kaynaklar", []),
                "hata": None,
                "topraklama_uyarisi": None,
            }), 200

        except Exception as exc:
            logger.exception("LLM ozet hatasi: %s", exc)
            return jsonify({"hata": "Sistem hatasi olustu, lutfen tekrar deneyin.", "ozet": None}), 500

    @app.route("/sor", methods=["POST"])
    @_limit("10 per minute")
    def sor():
        """LLM sorgu asistani paneli — niyet-yonlendirici ile rol secimi.

        Istek JSON: {soru: "..."}
        Yanit JSON: {cevap_md, alintilar|kaynaklar, ret, topraklama_uyarisi|sayi_bayragi,
                     kullanilan_rol, hata}

        Niyet-yonlendirici (deterministik, LLM degil):
          - "ozet/rapor/teklif/yonetici"  -> report rolu
          - "neden/nicin/hangi algoritma" -> explainer rolu
          - eslesme yok                   -> assistant rolu (default)

        READ-ONLY garantisi: LAST_RESULT hicbir rol cagirisinda degistirilmez.
        LLM kapali -> 503 (mevcut desen).
        """
        if not llm_active or llm_components is None:
            return jsonify({"hata": "LLM aktif degil.", "cevap": None}), 503

        result = app.config.get("LAST_RESULT")
        if result is None:
            return jsonify({"hata": "Once pipeline calistirin.", "cevap": None}), 400

        body = request.get_json(silent=True) or {}
        soru = (body.get("soru") or "").strip()
        if not soru:
            return jsonify({"hata": "Soru bos olamaz.", "cevap": None}), 400
        if len(soru) > MAX_SORU_LEN:
            return jsonify({"hata": "Soru cok uzun.", "cevap": None}), 400

        try:
            from src.llm.structured import ValidationStatus
            from src.webapp.intent_router import route_intent

            # Niyet-yonlendirici: deterministik, LLM cagirisi yok
            intent = route_intent(soru)

            # TAZE baglam: her cagri aninda yeniden kurulur (bayat baglam yok)
            context = _build_grounded_context(result)

            # --- REPORT rolu ---
            if intent.rol == "report":
                from src.llm.roles.report import ReportInput

                pricing_results = result.get("pricing_results", {})
                total_revenue = sum(
                    pr.get("total_price", 0.0) for pr in pricing_results.values()
                )
                report_input = ReportInput(
                    is_id="sorgu-report",
                    n_orders=len(result.get("ranked_orders", [])),
                    n_batches=len(result.get("batches", [])),
                    n_warnings=len(result.get("warnings", [])),
                    total_revenue_usd=total_revenue,
                    context=context,
                )
                report_role = llm_components["report_role"]
                report_result = report_role.run(report_input)

                if report_result.grounding_blocked:
                    return jsonify({
                        "cevap_md": None,
                        "kaynaklar": [],
                        "ret": False,
                        "topraklama_uyarisi": (
                            "Sayi-topraklama dogrulanamadi. "
                            f"Sayilar: {report_result.grounding_detail}."
                        ),
                        "sayi_bayragi": True,
                        "kullanilan_rol": "report",
                        "hata": None,
                    }), 200

                if report_result.status == ValidationStatus.INVALID or report_result.fallback:
                    return jsonify({
                        "cevap_md": None,
                        "kaynaklar": [],
                        "ret": False,
                        "topraklama_uyarisi": None,
                        "sayi_bayragi": False,
                        "kullanilan_rol": "report",
                        "hata": "LLM gecerli rapor uretemedi. Tekrar deneyin.",
                    }), 200

                data = report_result.data or {}
                return jsonify({
                    "cevap_md": data.get("govde_md", ""),
                    "baslik": data.get("baslik", ""),
                    "kaynaklar": data.get("kullanilan_kaynaklar", []),
                    "ret": False,
                    "topraklama_uyarisi": None,
                    "sayi_bayragi": False,
                    "kullanilan_rol": "report",
                    "hata": None,
                }), 200

            # --- EXPLAINER rolu ---
            if intent.rol == "explainer":
                from src.llm.roles.explainer import ExplainerInput

                # Sistem ciktisini ilk batch'ten veya genel metriklerden derliyoruz
                nesting_results = result.get("nesting_results", {})
                pricing_results = result.get("pricing_results", {})
                batches = result.get("batches", [])
                toplam_fiyat = sum(
                    pr.get("total_price", 0.0) for pr in pricing_results.values()
                )

                if batches:
                    first_batch = batches[0]
                    nr_first = nesting_results.get(first_batch.batch_id, {})
                    port_first = nr_first.get("portfolio") or nr_first.get("tuner") or {}
                    winner_name = (
                        port_first.get("winner")
                        or port_first.get("winning_config")
                        or "dblf"
                    )
                    _density_raw = nr_first.get("density", 0.0)
                    sistem_ciktisi: Dict[str, Any] = {
                        "kazanan_algoritma": winner_name,
                        "height_mm": nr_first.get("height_mm", 0.0),
                        "doluluk": f"{_density_raw:.1%}",
                        "n_parts": nr_first.get("n_parts", 0),
                        "toplam_fiyat": toplam_fiyat,
                        "n_orders": len(result.get("ranked_orders", [])),
                        "n_batches": len(batches),
                    }
                else:
                    sistem_ciktisi = {
                        "toplam_fiyat": toplam_fiyat,
                        "n_orders": len(result.get("ranked_orders", [])),
                    }

                exp_input = ExplainerInput(
                    karar_tipi=intent.karar_tipi or "algoritma",
                    sistem_ciktisi=sistem_ciktisi,
                )
                explainer_role = llm_components["explainer_role"]
                exp_result = explainer_role.explain(exp_input)

                if exp_result.status == ValidationStatus.INVALID or exp_result.fallback:
                    return jsonify({
                        "cevap_md": None,
                        "kaynaklar": [],
                        "ret": False,
                        "topraklama_uyarisi": None,
                        "sayi_bayragi": False,
                        "kullanilan_rol": "explainer",
                        "hata": "LLM gecerli aciklama uretemedi. Tekrar deneyin.",
                    }), 200

                exp_data = exp_result.data or {}
                return jsonify({
                    "cevap_md": exp_data.get("aciklama_md", ""),
                    "karar_tipi": exp_data.get("karar_tipi", intent.karar_tipi),
                    "alintilar": [],
                    "kaynaklar": exp_data.get("kullanilan_girdiler", []),
                    "ret": False,
                    "topraklama_uyarisi": (
                        "Aciklamada sistem ciktisinda olmayan rakam var."
                        if exp_result.number_flag else None
                    ),
                    "sayi_bayragi": exp_result.number_flag,
                    "kullanilan_rol": "explainer",
                    "hata": None,
                }), 200

            # --- ASSISTANT rolu (default) ---
            assistant_role = llm_components["assistant_role"]
            ask_result = assistant_role.ask(soru=soru, context=context)

            if ask_result.status == ValidationStatus.INVALID or ask_result.fallback:
                fallback_text = ""
                if ask_result.fallback:
                    fallback_text = ask_result.fallback.raw_text
                return jsonify({
                    "cevap_md": None,
                    "cevap": None,
                    "kullanilan_rol": "assistant",
                    "hata": "LLM gecerli yanit uretemedi.",
                    "fallback": fallback_text[:300] if fallback_text else "",
                }), 200

            data = ask_result.data or {}
            cevap_md = data.get("cevap_md", "")
            ret = data.get("ret", False)

            # Sohbet gecmisini guncelle — session (per-kullanici, Bulgu 5)
            turns = list(session.get("conversation_turns", []))
            turns.append({"soru": soru, "cevap": cevap_md})
            if len(turns) > 6:
                turns = turns[-6:]
            session["conversation_turns"] = turns

            return jsonify({
                "cevap_md": cevap_md,
                "cevap": cevap_md,  # geriye-donuk uyumluluk
                "alintilar": data.get("alintilar", []),
                "ret": ret,
                "ret_nedeni": data.get("ret_nedeni"),
                "topraklama_uyarisi": None,
                "sayi_bayragi": ask_result.number_flag,
                "topraklanamayan_sayilar": ask_result.ungrounded_numbers,
                "kullanilan_rol": "assistant",
                "hata": None,
            }), 200

        except Exception as exc:
            logger.exception("LLM soru hatasi: %s", exc)
            return jsonify({"hata": "Sistem hatasi olustu, lutfen tekrar deneyin.", "cevap": None}), 500

    # -----------------------------------------------------------------------
    # 3D Geometri rotasi (VİTRİN A)
    # -----------------------------------------------------------------------

    @app.route("/geometri/<batch_id>", methods=["GET"])
    def geometri(batch_id: str):
        """3D yerlesim sahnesini GLB olarak dondurur.

        Yanit: model/gltf-binary (GLB) veya 503 (export hazir degil).

        Zarif dusus: build_result_scene / scene_to_glb_bytes import HATASI
        veya batch_id bulunamadi -> 503 JSON.
        """
        result = app.config.get("LAST_RESULT")
        if result is None:
            return jsonify({
                "hata": "Once pipeline calistirin.",
                "preview": "hazir_degil",
            }), 503

        nesting_results = result.get("nesting_results", {})
        if batch_id not in nesting_results:
            return jsonify({
                "hata": f"Parti {batch_id!r} bulunamadi.",
                "preview": "hazir_degil",
            }), 503

        nr = nesting_results[batch_id]

        # Placements verisi: paralel builder export_stl.py'e ekleyince hazir olacak.
        # Simdilik nesting_results icinde 'placements' veya 'voxel_parts' YOK.
        placements = nr.get("placements")
        voxel_parts = nr.get("voxel_parts")
        pitch = nr.get("pitch_mm") or nr.get("pitch", 10.0)

        if placements is None or voxel_parts is None:
            return jsonify({
                "hata": "3D export verisi henuz hazir degil.",
                "preview": "hazir_degil",
            }), 503

        try:
            from src.nesting3d.export_stl import (
                build_result_scene,
                scene_to_glb_bytes,
            )
        except ImportError as exc:
            logger.warning("GLB export import hatasi: %s", exc)
            return jsonify({
                "hata": "3D export modulu yuklenemedi.",
                "preview": "hazir_degil",
            }), 503

        try:
            scene = build_result_scene(placements, voxel_parts, pitch=float(pitch))
            glb_bytes = scene_to_glb_bytes(scene)
        except Exception as exc:
            logger.warning("GLB export hatasi batch=%s: %s", batch_id, exc)
            return jsonify({
                "hata": f"3D export hatasi: {exc}",
                "preview": "hazir_degil",
            }), 503

        return Response(
            glb_bytes,
            mimetype="model/gltf-binary",
            headers={
                "Content-Disposition": f"inline; filename={batch_id}.glb",
                "Cache-Control": "no-store",
            },
        )

    # -----------------------------------------------------------------------
    # Teklif taslagi rotasi (VİTRİN B)
    # -----------------------------------------------------------------------

    @app.route("/teklif", methods=["POST"])
    @_limit("10 per minute")
    def teklif():
        """LLM ile musteri-yanit mail taslagi uret (TeklifRole — UYARI modu).

        Yanit JSON: {taslak, baslik, kaynaklar, topraklama_uyarisi, ungrounded, hata}
        LLM aktif degil -> 503.
        Pipeline kosulmamis -> 400.
        DEAD-END YOK: number_flag=True olsa bile taslak dolu, 200 doner.
        """
        if not llm_active or llm_components is None:
            return jsonify({"hata": "LLM aktif degil.", "taslak": None}), 503

        result = app.config.get("LAST_RESULT")
        if result is None:
            return jsonify({"hata": "Once pipeline calistirin.", "taslak": None}), 400

        teklif_role = llm_components.get("teklif_role") if llm_components else None
        if teklif_role is None:
            return jsonify({"hata": "Teklif bileşeni yuklenemedi.", "taslak": None}), 503

        try:
            from src.llm.roles.teklif import TeklifInput
            from src.llm.structured import ValidationStatus
            from src.llm.grounding import GroundedContext

            context = _build_grounded_context(result)

            pricing_results = result.get("pricing_results", {})
            total_revenue = sum(
                pr.get("total_price", 0.0) for pr in pricing_results.values()
            )

            ranked_orders = result.get("ranked_orders", [])
            musteri_adi = "Değerli Müşterimiz"
            if ranked_orders:
                # MED-3: cok-musterili guard — birden fazla farkli musteri varsa
                # yanlislikla spesifik bir isim yazilmamasi icin genel hitap kullan.
                musteri_adlari = set()
                for _o in ranked_orders:
                    if isinstance(_o, dict):
                        _m = _o.get("customer", "")
                    else:
                        _m = getattr(_o, "customer", "")
                    if _m:
                        musteri_adlari.add(_m)
                if len(musteri_adlari) == 1:
                    musteri_adi = musteri_adlari.pop()
                # >1 farkli musteri: musteri_adi "Değerli Müşterimiz" olarak kalir

            batches = result.get("batches", [])
            parca_ozeti = []
            for b in batches:
                if isinstance(b, dict):
                    bid = b.get("batch_id", "")
                    orders = b.get("orders", [])
                    for o in orders:
                        if isinstance(o, dict):
                            parts = o.get("parts", [])
                            for p in parts:
                                if isinstance(p, dict):
                                    parca_ozeti.append({
                                        "ad": p.get("name", p.get("part_id", bid)),
                                        "adet": p.get("quantity", 1),
                                    })

            if not parca_ozeti:
                parca_ozeti = [{"ad": "konteyner parcalari", "adet": len(ranked_orders)}]

            termin_ifadesi = "sipariş onayını takiben tarafınıza bildirilecektir"
            if ranked_orders:
                first = ranked_orders[0]
                if isinstance(first, dict):
                    termin_ifadesi = first.get("deadline", termin_ifadesi)

            teklif_input = TeklifInput(
                musteri_adi=musteri_adi,
                parca_ozeti=parca_ozeti,
                toplam_fiyat_usd=total_revenue,
                termin_ifadesi=str(termin_ifadesi),
                context=context,
            )

            teklif_result = teklif_role.draft(teklif_input)

            # INVALID+fallback -> 502 taslak=None+hata (dead-end yok ama LLM basarisiz)
            if teklif_result.status == ValidationStatus.INVALID or teklif_result.fallback:
                return jsonify({
                    "taslak": None,
                    "hata": "LLM gecerli taslak uretemedi. Tekrar deneyin.",
                    "topraklama_uyarisi": False,
                    "ungrounded": [],
                }), 502

            # VALID/PARTIAL — her zaman taslak dolu (BLOK YOK)
            data = teklif_result.data or {}
            return jsonify({
                "taslak": data.get("mail_govde_md", ""),
                "baslik": data.get("konu", ""),
                "kaynaklar": data.get("kullanilan_kaynaklar", []),
                "topraklama_uyarisi": teklif_result.number_flag,
                "ungrounded": teklif_result.ungrounded_numbers,
                "hata": None,
            }), 200

        except Exception as exc:
            logger.exception("Teklif taslagi hatasi: %s", exc)
            return jsonify({"hata": "Sistem hatasi olustu, lutfen tekrar deneyin.", "taslak": None}), 500

    # -----------------------------------------------------------------------
    # Mail parser rotasi
    # -----------------------------------------------------------------------

    @app.route("/parse", methods=["POST"])
    @_limit("20 per minute")
    def parse_mail():
        """Serbest metin/mail -> yapilandirilmis siparis JSON.

        Istek JSON : {"mail_text": "<serbest siparis metni>"}
        Yanit JSON :
          - Basarili  : {"status": "ok", "siparis": {...}, "eksik_alanlar": [...],
                         "injection_suphesi": bool}
          - LLM yok   : {"status": "llm_yok", "mesaj": "..."}
          - Parse hata: {"status": "parse_hatasi", "mesaj": "..."}
          - Bos girdi : {"status": "hata", "mesaj": "..."} (400)
        """
        body = request.get_json(silent=True) or {}
        mail_text = (body.get("mail_text") or "").strip()

        if not mail_text:
            return jsonify({
                "status": "hata",
                "mesaj": "mail_text bos olamaz.",
            }), 400

        if not llm_active or llm_components is None:
            return jsonify({
                "status": "llm_yok",
                "mesaj": (
                    "LLM aktif degil. Ollama calismiyor olabilir. "
                    "Siparis bilgilerini elle girin."
                ),
            }), 200

        try:
            from src.llm.roles.parser import parsed_to_order
            from src.llm.structured import ValidationStatus

            parser_role = llm_components.get("parser_role")
            if parser_role is None:
                return jsonify({
                    "status": "llm_yok",
                    "mesaj": "Parser rolu yuklenemedi. Elle girin.",
                }), 200

            parse_result = parser_role.parse(mail_text)

            if parse_result.status == ValidationStatus.INVALID or parse_result.fallback:
                raw = ""
                if parse_result.fallback:
                    raw = parse_result.fallback.raw_text[:300]
                return jsonify({
                    "status": "parse_hatasi",
                    "mesaj": (
                        "LLM siparis yapisini cikartamadiSimdi deneyin veya "
                        "bilgileri elle girin."
                    ),
                    "ham_cikti": raw,
                }), 200

            if parse_result.injection_suphesi:
                return jsonify({
                    "status": "guvenlik_suptesi",
                    "mesaj": (
                        "Guvenlik suptesi nedeniyle siparis islenmedi. "
                        "Lutfen icerik kontrolu yapin."
                    ),
                    "injection_suphesi": True,
                }), 422

            return jsonify({
                "status": "ok",
                "siparis": parse_result.order_dict,
                "eksik_alanlar": parse_result.eksik_alanlar or [],
                "injection_suphesi": parse_result.injection_suphesi,
            }), 200

        except Exception as exc:
            logger.exception("Mail parse hatasi: %s", exc)
            return jsonify({
                "status": "parse_hatasi",
                "mesaj": "Sistem hatasi olustu, lutfen tekrar deneyin.",
            }), 500

    # -----------------------------------------------------------------------
    # Otonom zincir rotasi (VİTRİN C)
    # -----------------------------------------------------------------------
    # Kalici is gecmisi: tamamlanan her otonom isi ozet olarak diske yazilir
    # (/gecmis sayfasi okur). Testte gecici dizin (izolasyon).
    from src.runtime.otonom_gecmis import OtonomGecmisStore
    if app.config.get("TESTING"):
        import tempfile as _tf2
        _gecmis_root = Path(_tf2.mkdtemp(prefix="otonom_gecmis_"))
    else:
        _gecmis_root = _ROOT / "data" / "otonom_gecmis"
    _otonom_gecmis = OtonomGecmisStore(_gecmis_root)
    app.config["OTONOM_GECMIS"] = _otonom_gecmis

    def _run_otonom_pipeline(otonom_nesting_mode, otonom_nfv_quality, on_stage=None):
        """Mail-cek → parse → onceliklendir → nesting → fiyat → acikla → teklif taslagi.

        SENKRON /otonom ve ASENKRON /otonom/baslat ORTAK govdesi (DRY). request
        objesi KULLANMAZ (mode/quality parametre) — arka-plan thread'inde request
        context yok. (dict, http_status) tuple doner; on_stage verilirse her asama
        eklendiginde CANLI haber verir (asenkron ilerleme paneli).

        Tum pipeline asamalarini otomatik kosturur; sonuclari agent-panosu formati
        ile dondurur. LLM olmadan mail parse edilemeyeceginden LLM gerekli.

        Yanit JSON:
        {
          "asamalar": [
            {"ad": "Mail-Cek", "durum": "tamam", "cikti": "4 mail cekildi"},
            {"ad": "Parse", "durum": "tamam", "cikti": "4 siparis cikarildi"},
            {"ad": "Onceliklendir", "durum": "tamam", "cikti": "Ford ACIL once secildi"},
            {"ad": "Nesting", "durum": "tamam", "cikti": "GA, 2 parti, 3 konteyner"},
            {"ad": "Fiyat", "durum": "tamam", "cikti": "Toplam 1200 USD"},
            {"ad": "Acikla", "durum": "tamam|llm_yok", "cikti": "SA en iyi..."},
            {"ad": "Teklif-Taslagi", "durum": "tamam|llm_yok", "cikti": "...(insan onay gerekli)"},
          ],
          "nesting_results": {...},
          "pricing_results": {...},
          "pipeline_ozet": {...},
          "toplam_fiyat": 1200.0,
          "aciklama_md": "...",
          "teklif_taslagi": "...",
          "teklif_onay_gerekli": true,
        }
        """
        def _emit(asama):
            # on_stage callback'i job'i ASLA dusurmemeli (asenkron ilerleme)
            if on_stage is not None:
                try:
                    on_stage(asama)
                except Exception:
                    logger.debug("on_stage callback hatasi yutuldu", exc_info=True)

        class _StageList(list):
            # append edildikce on_stage'e CANLI haber ver. Senkron yolda (on_stage
            # None) _emit no-op'tur; davranis BIREBIR ayni kalir.
            def append(self, item):
                super().append(item)
                _emit(item)

        if not llm_active or llm_components is None:
            return {
                "hata": (
                    "Otonom mod LLM gerektiriyor (mail parse icin). "
                    "Ollama calismiyor veya configs/llm.local.json eksik. "
                    "Manuel demo icin /run rotasini kullanin."
                ),
                "mesaj": "LLM gerekli",
                "asamalar": [],
            }, 503

        from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
        from src.runtime.mail_ingest import make_mail_source, ingest_order
        from src.llm.roles.parser import parsed_to_order
        from src.llm.roles.explainer import ExplainerInput
        from src.llm.structured import ValidationStatus

        asamalar: List[Dict[str, Any]] = _StageList()

        # ------------------------------------------------------------------
        # ASAMA 1: Mail-Cek
        # ------------------------------------------------------------------
        try:
            # Mail kaynagi: mail.local.json (UI) > .env MAIL_* > demo Fake.
            # Sifre asla kodda degil — dosya veya .env'den gelir.
            # TESTING: gercek IMAP'a baglanmamak icin her zaman fake.
            mail_cfg = ({"source": "fake"} if app.config.get("TESTING")
                        else _resolve_mail_source_config(_ROOT))

            mail_source = make_mail_source(mail_cfg)
            raw_mails = mail_source.fetch_new()
            n_mail = len(raw_mails)
            _kaynak_etiket = mail_cfg.get("provider") or mail_cfg.get("source", "fake")
            asamalar.append({
                "ad": "Mail-Cek",
                "durum": "tamam",
                "cikti": f"{n_mail} mail cekildi ({_kaynak_etiket})",
                "detay": [
                    {"gonderen": m.gonderen, "konu": m.konu}
                    for m in raw_mails
                ],
            })
        except Exception as exc:
            logger.warning("Otonom: Mail-Cek hatasi: %s", exc)
            asamalar.append({"ad": "Mail-Cek", "durum": "hata", "cikti": "Mail cekme basarisiz."})
            return {"hata": "Sistem hatasi olustu, lutfen tekrar deneyin.", "asamalar": asamalar}, 500

        # ------------------------------------------------------------------
        # ASAMA 2: Parse (her mail icin — ek varsa deterministik, yoksa LLM)
        # ------------------------------------------------------------------
        parser_role = llm_components.get("parser_role")
        parsed_orders: List[Dict[str, Any]] = []
        parse_hatalar: List[str] = []
        parse_eksik: List[Dict[str, Any]] = []  # ZIP var, adet yok -> operator girmeli
        parse_karantina: List[str] = []
        parse_kaynak_sayac: Dict[str, int] = {
            "attachment_zip_stl": 0, "attachment_excel": 0, "attachment_csv": 0, "llm_text": 0,
        }
        # ZIP-STL yolunda STL'ler buraya kalici yazilir (nesting voxelize edene
        # kadar yasamali); mesaj-bazli alt klasor ingest_order icinde acilir.
        _persist_root = str(_ROOT / "data" / "mail_stl")

        for mail in raw_mails:
            try:
                order = ingest_order(mail, parser_role, persist_root=_persist_root)
                if order is not None and order.get("needs_review"):
                    # EKSIK BILGI: ZIP'te STL var ama govdede adet yok. Otomatik
                    # ISLENMEZ — operatorun adet girmesi gerekir (karar: operatore
                    # sor/beklet). Genel "parse basarisiz" ile karistirilmaz.
                    # Operatorun /adet-gir'den adet girip yeniden kurabilmesi icin
                    # bekleyen siparis deposuna (STL'ler + meta) kaydet.
                    _saved_id = order.get("order_id", "")
                    try:
                        _saved_id = _pending_store.add(
                            order_id=order.get("order_id", ""),
                            customer=order.get("customer", ""),
                            sender=mail.gonderen,
                            deadline=_normalize_deadline(
                                order.get("deadline", ""), mail_tarih=mail.tarih,
                            ),
                            priority_class=(1 if ("acil" in mail.konu.lower()
                                                  or "acil" in mail.govde.lower())
                                            else order.get("priority_class", 2)),
                            konu=mail.konu,
                            stl_map=order.get("_stl_map", {}),
                            container=order.get("container"),
                        )
                    except Exception as exc:
                        logger.warning("Otonom: bekleyen siparis kaydedilemedi: %s", exc)
                    parse_eksik.append({
                        "order_id": _saved_id,
                        "gonderen": mail.gonderen,
                        "konu": mail.konu,
                        "stl_sayisi": len(order.get("stl_names", [])),
                        "stl_adlar": order.get("stl_names", []),
                    })
                elif order is not None:
                    # Mail gonderenden oncelik ipucu al
                    govde_lower = mail.govde.lower()
                    konu_lower = mail.konu.lower()
                    if "acil" in konu_lower or "acil" in govde_lower:
                        order["priority_class"] = 1

                    # Musteri adini gonderen domain'den zenginlestir (bos/bilinmiyor ise)
                    if not order.get("customer") or order["customer"] == "Bilinmiyor":
                        domain = mail.gonderen.split("@")[-1].split(".")[0].upper()
                        order["customer"] = domain

                    # Termin duzeltme
                    order["deadline"] = _normalize_deadline(
                        order.get("deadline", ""),
                        mail_tarih=mail.tarih,
                    )

                    # Kaynak sayaci
                    src = order.get("parse_source", "llm_text")
                    parse_kaynak_sayac[src] = parse_kaynak_sayac.get(src, 0) + 1

                    parsed_orders.append(order)
                else:
                    # None donus: injection suphesi karantina veya parse basarisiz.
                    # Ek yoksa LLM yolu denendiginden, parse_result'a erisim yok;
                    # ingest_order zaten karantina logunu yazmis olur — ozet icin
                    # gonderen bazli kayit yapiyoruz.
                    parse_hatalar.append(f"{mail.gonderen}: parse basarisiz veya karantinaya alindi")
            except Exception as exc:
                logger.warning("Otonom: Parse hatasi (mail=%s): %s", mail.gonderen, exc)
                parse_hatalar.append(f"{mail.gonderen}: {exc}")

        n_parsed = len(parsed_orders)
        parse_durum = "tamam" if n_parsed > 0 else "hata"

        # Kaynak ozeti icin etiket
        kaynak_parcalari = []
        if parse_kaynak_sayac.get("attachment_zip_stl", 0) > 0:
            kaynak_parcalari.append(
                f"{parse_kaynak_sayac['attachment_zip_stl']} ZIP-STL'den"
            )
        if parse_kaynak_sayac.get("attachment_excel", 0) > 0:
            kaynak_parcalari.append(
                f"{parse_kaynak_sayac['attachment_excel']} Excel'den"
            )
        if parse_kaynak_sayac.get("attachment_csv", 0) > 0:
            kaynak_parcalari.append(
                f"{parse_kaynak_sayac['attachment_csv']} CSV'den"
            )
        if parse_kaynak_sayac.get("llm_text", 0) > 0:
            kaynak_parcalari.append(
                f"{parse_kaynak_sayac['llm_text']} mailden (LLM)"
            )
        kaynak_ozet = ", ".join(kaynak_parcalari) if kaynak_parcalari else "bilinmiyor"

        parse_cikti = f"{n_parsed} siparis cikarildi ({kaynak_ozet})"
        if parse_hatalar:
            parse_cikti += f" — {len(parse_hatalar)} basarisiz"
        if parse_eksik:
            parse_cikti += f" — {len(parse_eksik)} eksik bilgi (adet yok)"
        asamalar.append({
            "ad": "Parse",
            "durum": parse_durum,
            "cikti": parse_cikti,
            "detay": {
                "siparis_sayisi": n_parsed,
                "hatalar": parse_hatalar,
                "eksik_bilgi": parse_eksik,
                "kaynak_sayac": parse_kaynak_sayac,
            },
        })

        if n_parsed == 0:
            # Eksik-bilgi siparisi varsa operatore net mesaj ver (genel "parse
            # basarisiz" degil — ZIP geldi, sadece adet eksik).
            if parse_eksik:
                _ek = parse_eksik[0]
                hata_msg = (
                    f"{len(parse_eksik)} siparis EKSIK BILGI nedeniyle islenemedi: "
                    f"ZIP ekinde STL var ama mail govdesinde adet belirtilmemis. "
                    f"Ornek: {_ek['gonderen']} ({_ek['stl_sayisi']} STL). "
                    f"Adetleri girmek icin 'Adet Girisi' (/adet-gir) sayfasini acin."
                )
            else:
                hata_msg = "Hic siparis cikartilamadi (LLM parse basarisiz)."
            return {
                "hata": hata_msg,
                "asamalar": asamalar,
            }, 500

        # ------------------------------------------------------------------
        # ASAMA 3-5: Onceliklendir + Nesting + Fiyat (run_pipeline)
        # ------------------------------------------------------------------
        # Bulgu 7: deepcopy yerine shallow + tek anahtar override (daha hizli)
        scenario = {**RICH_SCENARIO, "orders": parsed_orders}

        # Plaka politikasi (cekirdek). Oncelik:
        #   1. UI'dan girilen GERCEK plaka (configs/plate.local.json > env PLATE_*)
        #   2. Siparisin tasidigi container (varsa)
        #   3. Hicbiri yok -> None -> run_pipeline parcalardan otomatik turetir.
        # Demo container'i gercek STL siparisine ASLA dayatilmaz.
        from src.runtime.plate_config import resolve_plate as _resolve_plate_ui
        _pw, _pd, _ph = _resolve_plate_ui(_ROOT)
        if _pw and _pd:
            _container = {"width_mm": _pw, "depth_mm": _pd, "height_mm": _ph}
        else:
            _container = next(
                (o["container"] for o in parsed_orders if o.get("container")), None
            )
        scenario = {**scenario, "container": _container,  # None -> pipeline otomatik
                    "nesting_mode": otonom_nesting_mode,
                    "nfv_quality": otonom_nfv_quality}

        try:
            pipeline_result = run_pipeline(scenario)
        except Exception as exc:
            logger.exception("Otonom: pipeline hatasi: %s", exc)
            return {"hata": "Sistem hatasi olustu, lutfen tekrar deneyin.", "asamalar": asamalar}, 500

        # Detayli sonuc ekrani (/sonuc) icin: otonom sonucu da LAST_RESULT'a
        # yazilir; boylece kullanici "Detayli Sonucu Gor" ile tum tablolar +
        # 3D onizleme + maliyet ekranina gidebilir (tek-tik /run ile ayni deneyim).
        pipeline_result["used_demo"] = False
        app.config["LAST_RESULT"] = pipeline_result

        ranked = pipeline_result.get("ranked_orders", [])
        batches = pipeline_result.get("batches", [])
        warnings = pipeline_result.get("warnings", [])
        nesting_results = pipeline_result.get("nesting_results", {})
        pricing_results = pipeline_result.get("pricing_results", {})

        # ------------------------------------------------------------------
        # WATCHER: deterministik kontroller + opsiyonel LLM anlatimi
        # run_pipeline'a dokunmaz; READ-ONLY.
        # ------------------------------------------------------------------
        from src.watcher.checks import (
            check_parse, check_nest, check_price, check_priority,
        )

        watcher_role = (llm_components or {}).get("watcher_role") if llm_active else None

        def _watcher_narrate(findings):
            """Finding listesini LLM ile Turkce'ye cevirir; LLM yoksa ham bulgu."""
            if not findings:
                return []
            if watcher_role is not None:
                try:
                    wr = watcher_role.narrate(findings)
                    if wr is not None and wr.status.value != "INVALID" and wr.data:
                        return {
                            "anlatim_md": wr.data.get("anlatim_md", ""),
                            "kapsanan_bulgular": wr.data.get("kapsanan_bulgular", []),
                            "number_flag": wr.number_flag,
                            "kaynak": "llm",
                        }
                except Exception as exc:
                    logger.warning("Watcher LLM anlatim hatasi: %s", exc)
            # LLM yok veya basarisiz -> ham bulgu
            return {
                "anlatim_md": " ".join(
                    f"[{f.severity.upper()}] {f.baslik}: {f.ham_detay}"
                    for f in findings
                ),
                "kapsanan_bulgular": [f.kod for f in findings],
                "number_flag": False,
                "kaynak": "ham_bulgu",
            }

        # Parse watcher verisi: parsed_orders'tan parca listesi derle.
        # missing_field_ratio: parse edilemeyen mail orani (parse_hatalar / n_mail).
        # Her basarisiz/karantina mail eksik-veri sinyalidir; sabit 0.0 yerine
        # gercek oran beslenir ki PARSE_EKSIK_ALAN kontrolu canli yolda yasasin.
        _missing_field_ratio = (len(parse_hatalar) / n_mail) if n_mail > 0 else 0.0
        _parse_check_data = {
            "parts": [
                p
                for o in parsed_orders
                for p in o.get("parts", [])
            ],
            "missing_field_ratio": _missing_field_ratio,
        }
        _parse_findings = check_parse(_parse_check_data)

        # Istenen parca sayisi: order_id -> qty-toplami haritasi.
        # nesting_results[*]["n_parts"] motorda len(placements) ile doldurulur
        # (scripts/demo_pipeline.py: n_placed), yani YERLESEN sayidir. Istenen
        # sayi ise her parcanin adet (qty) toplamidir; voxel pipeline parcalari
        # qty kadar cogaltir (to_voxel_parts -> expand_quantities), bu yuzden
        # istenen-yerlesen kiyasi qty-toplami uzerinden dogru olur.
        _order_requested_parts = {
            o.get("order_id"): sum(int(p.get("qty", 1) or 1) for p in o.get("parts", []))
            for o in parsed_orders
        }

        # Nesting + Fiyat watcher verisi: her parti icin; kumulatif
        _nest_findings_all = []
        _price_findings_all = []
        for _b in batches:
            _nr = nesting_results.get(_b.batch_id, {})
            _pr = pricing_results.get(_b.batch_id, {})
            # Bu partinin icerdigi siparislerden ISTENEN toplam parca sayisi
            _requested_parts = sum(
                _order_requested_parts.get(_o.order_id, 0)
                for _o in getattr(_b, "orders", [])
            )
            # YERLESEN sayi: motorun n_parts anahtari (= len(placements)).
            _placed_parts = int(_nr.get("n_parts", 0))
            _nest_data = {
                "density": _nr.get("density", 0.0),
                "height_mm": _nr.get("height_mm", 0.0),
                "container_height_mm": parsed_orders[0].get("container_height_mm") if parsed_orders else None,
                "n_parts": _requested_parts,
                "n_placed": _placed_parts,
            }
            _nest_findings_all.extend(check_nest(_nest_data))
            _price_data = {
                "total_price": _pr.get("total_price", 0.0),
                "breakdown": [
                    {"rule_id": line.split(":")[0] if ":" in str(line) else str(line),
                     "subtotal_after": _pr.get("total_price", 0.0)}
                    for line in _pr.get("breakdown", [])
                ],
            }
            _price_findings_all.extend(check_price(_price_data))

        # Oncelik watcher verisi
        _priority_classes = [o.get("priority_class", 2) for o in parsed_orders]
        _priority_check_data = {
            "warnings": warnings,
            "priority_classes": _priority_classes,
        }
        _priority_findings = check_priority(_priority_check_data)

        # LLM anlatim (varsa)
        _watcher_parse = _watcher_narrate(_parse_findings)
        _watcher_nest = _watcher_narrate(_nest_findings_all)
        _watcher_price = _watcher_narrate(_price_findings_all)
        _watcher_priority = _watcher_narrate(_priority_findings)

        def _findings_to_serial(findings):
            return [
                {
                    "kod": f.kod,
                    "severity": f.severity,
                    "baslik": f.baslik,
                    "ham_detay": f.ham_detay,
                }
                for f in findings
            ]

        # Parse asamasini geriye donuk guncelle (watcher bilgisi ekle)
        for _i, _s in enumerate(asamalar):
            if _s.get("ad") == "Parse":
                _s["watcher"] = {
                    "bulgular": _findings_to_serial(_parse_findings),
                    "anlatim": _watcher_parse,
                }
                break

        # Onceliklendirme ozeti
        if ranked:
            ilk = ranked[0]
            oncelik_cikti = (
                f"{ilk.order_id} ({ilk.customer}) one alindi"
                f" — Sinif {ilk.priority_class}, termin {ilk.deadline}"
            )
        else:
            oncelik_cikti = "Siparis siralanamadi"

        asamalar.append({
            "ad": "Onceliklendir",
            "durum": "tamam",
            "cikti": oncelik_cikti,
            "detay": {
                "siralama": [
                    {
                        "sira": i + 1,
                        "order_id": o.order_id,
                        "customer": o.customer,
                        "deadline": str(o.deadline),
                        "priority_class": o.priority_class,
                    }
                    for i, o in enumerate(ranked)
                ],
                "uyari_sayisi": len(warnings),
            },
            "watcher": {
                "bulgular": _findings_to_serial(_priority_findings),
                "anlatim": _watcher_priority,
            },
        })

        # Nesting ozeti
        n_batches = len(batches)
        if batches:
            best_height = min(
                nesting_results.get(b.batch_id, {}).get("height_mm", 9999.0)
                for b in batches
            )
            winners = []
            for b in batches:
                nr = nesting_results.get(b.batch_id, {})
                port = nr.get("portfolio") or nr.get("tuner") or {}
                w = port.get("winner") or port.get("winning_config") or "dblf"
                winners.append(w)
            nesting_cikti = (
                f"{n_batches} parti, min yukseklik {best_height:.1f} mm"
                f" — algoritmalar: {', '.join(set(winners))}"
            )
        else:
            nesting_cikti = "Parti olusturulamadi"

        asamalar.append({
            "ad": "Nesting",
            "durum": "tamam" if batches else "hata",
            "cikti": nesting_cikti,
            "detay": {
                "parti_sayisi": n_batches,
                "batches": [
                    {
                        "batch_id": b.batch_id,
                        "customer": b.customer,
                        "height_mm": nesting_results.get(b.batch_id, {}).get("height_mm", 0),
                        "density": nesting_results.get(b.batch_id, {}).get("density", 0),
                        "n_parts": nesting_results.get(b.batch_id, {}).get("n_parts", 0),
                    }
                    for b in batches
                ],
            },
            "watcher": {
                "bulgular": _findings_to_serial(_nest_findings_all),
                "anlatim": _watcher_nest,
            },
        })

        # Fiyat ozeti
        toplam_fiyat = sum(
            pr.get("total_price", 0.0) for pr in pricing_results.values()
        )
        fiyat_cikti = f"Toplam {toplam_fiyat:.2f} USD ({n_batches} parti)"
        asamalar.append({
            "ad": "Fiyat",
            "durum": "tamam",
            "cikti": fiyat_cikti,
            "detay": {
                "toplam_fiyat": toplam_fiyat,
                "parti_fiyatlari": {
                    bid: {"total_price": pr.get("total_price", 0.0)}
                    for bid, pr in pricing_results.items()
                },
            },
            "watcher": {
                "bulgular": _findings_to_serial(_price_findings_all),
                "anlatim": _watcher_price,
            },
        })

        # ------------------------------------------------------------------
        # ASAMA 6: Acikla (LLM explainer -- ilk parti icin)
        # ------------------------------------------------------------------
        explainer_role = llm_components.get("explainer_role")
        aciklama_md = ""
        acikla_durum = "llm_yok"

        if explainer_role is not None and batches:
            try:
                first_batch = batches[0]
                nr_first = nesting_results.get(first_batch.batch_id, {})
                port_first = nr_first.get("portfolio") or nr_first.get("tuner") or {}
                winner_name = (
                    port_first.get("winner")
                    or port_first.get("winning_config")
                    or "dblf"
                )
                _density_raw_otonom = nr_first.get("density", 0.0)
                sistem_ciktisi = {
                    "kazanan_algoritma": winner_name,
                    "height_mm": nr_first.get("height_mm", 0.0),
                    "doluluk": f"{_density_raw_otonom:.1%}",
                    "n_parts": nr_first.get("n_parts", 0),
                    "toplam_fiyat": toplam_fiyat,
                }
                from src.llm.roles.explainer import ExplainerInput
                exp_input = ExplainerInput(
                    karar_tipi="algoritma",
                    sistem_ciktisi=sistem_ciktisi,
                )
                exp_result = explainer_role.explain(exp_input)

                if exp_result.status != ValidationStatus.INVALID and exp_result.data:
                    aciklama_md = exp_result.data.get("aciklama_md", "")
                    acikla_durum = "tamam"
                    if exp_result.number_flag:
                        acikla_durum = "tamam_uyari"
                else:
                    aciklama_md = "Aciklama uretilemedi (LLM yanit vermedi)."
                    acikla_durum = "parcali"
            except Exception as exc:
                logger.warning("Otonom: Acikla hatasi: %s", exc)
                aciklama_md = f"Aciklama hatasi: {exc}"
                acikla_durum = "hata"

        asamalar.append({
            "ad": "Acikla",
            "durum": acikla_durum,
            "cikti": aciklama_md[:200] if aciklama_md else "LLM aciklama atildi",
            "detay": {"aciklama_md": aciklama_md},
        })

        # ------------------------------------------------------------------
        # ASAMA 7: Teklif Taslagi (TeklifRole -- UYARI modu, INSAN ONAY KAPISI)
        # ------------------------------------------------------------------
        teklif_taslagi = ""
        teklif_konu = ""
        teklif_durum = "llm_yok"
        teklif_number_flag = False

        _teklif_role = llm_components.get("teklif_role")
        if _teklif_role is not None:
            try:
                from src.llm.roles.teklif import TeklifInput

                context = _build_grounded_context(pipeline_result)

                musteri_adi = "Değerli Müşterimiz"
                if ranked:
                    # MED-3: cok-musterili guard — birden fazla farkli musteri varsa
                    # yanlislikla spesifik bir isim yazilmamasi icin genel hitap kullan.
                    _otonom_musteri_adlari = set()
                    for _o in ranked:
                        if isinstance(_o, dict):
                            _m = _o.get("customer", "")
                        else:
                            _m = getattr(_o, "customer", "")
                        if _m:
                            _otonom_musteri_adlari.add(_m)
                    if len(_otonom_musteri_adlari) == 1:
                        musteri_adi = _otonom_musteri_adlari.pop()
                    # >1 farkli musteri: musteri_adi "Değerli Müşterimiz" olarak kalir

                parca_ozeti_list = []
                for b in batches:
                    if isinstance(b, dict):
                        bid = b.get("batch_id", "")
                        for o in b.get("orders", []):
                            if isinstance(o, dict):
                                for p in o.get("parts", []):
                                    if isinstance(p, dict):
                                        parca_ozeti_list.append({
                                            "ad": p.get("name", p.get("part_id", bid)),
                                            "adet": p.get("quantity", 1),
                                        })

                if not parca_ozeti_list:
                    parca_ozeti_list = [
                        {"ad": "konteyner parcalari", "adet": len(ranked)}
                    ]

                termin_ifadesi = "sipariş onayını takiben tarafınıza bildirilecektir"
                if ranked:
                    first = ranked[0]
                    if isinstance(first, dict):
                        termin_ifadesi = str(first.get("deadline", termin_ifadesi))

                teklif_input = TeklifInput(
                    musteri_adi=musteri_adi,
                    parca_ozeti=parca_ozeti_list,
                    toplam_fiyat_usd=toplam_fiyat,
                    termin_ifadesi=termin_ifadesi,
                    context=context,
                )
                teklif_result = _teklif_role.draft(teklif_input)

                from src.llm.structured import ValidationStatus as _VS
                if teklif_result.status in (_VS.VALID, _VS.PARTIAL) and teklif_result.data:
                    teklif_taslagi = teklif_result.data.get("mail_govde_md", "")
                    teklif_konu = teklif_result.data.get("konu", "")
                    teklif_number_flag = teklif_result.number_flag
                    # flagli_taslak: taslak DOLU ama uyari var (dead-end yok)
                    teklif_durum = "flagli_taslak" if teklif_number_flag else "taslak_hazir"
                else:
                    teklif_taslagi = ""
                    teklif_durum = "hata"
            except Exception as exc:
                logger.warning("Otonom: Teklif taslagi hatasi: %s", exc)
                teklif_taslagi = ""
                teklif_durum = "hata"

        asamalar.append({
            "ad": "Teklif-Taslagi",
            "durum": teklif_durum,
            "cikti": (
                "Taslak hazir — insan onay gerekli, otomatik gonderilmez"
                if teklif_durum in ("taslak_hazir", "flagli_taslak")
                else "Teklif taslagi uretilemedi"
            ),
            "detay": {
                "taslak": teklif_taslagi,
                "onay_gerekli": True,
                "otomatik_gonderildi": False,
                "topraklama_uyarisi": teklif_number_flag,
                "konu": teklif_konu,
            },
        })

        # ------------------------------------------------------------------
        # Kalici GECMISE yaz (senkron + async ortak yoldan gecer; /gecmis okur)
        # ------------------------------------------------------------------
        try:
            _g_musteri = "-"
            if ranked:
                _g_musteri = ranked[0].customer
                _farkli = len({getattr(o, "customer", "") for o in ranked})
                if _farkli > 1:
                    _g_musteri = f"{_g_musteri} +{_farkli - 1}"
            _g_yuk = [nr.get("height_mm", 0.0) for nr in nesting_results.values()
                      if nr.get("height_mm")]
            _otonom_gecmis.kaydet({
                "durum": "bitti",
                "mod": otonom_nesting_mode,
                "nfv_quality": otonom_nfv_quality,
                "musteri": _g_musteri,
                "siparis_sayisi": len(ranked),
                "parti_sayisi": n_batches,
                "min_yukseklik_mm": round(min(_g_yuk), 1) if _g_yuk else None,
                "toplam_fiyat": round(toplam_fiyat, 2),
                "sure_sn": round(pipeline_result.get("elapsed_sec", 0.0), 1),
            })
        except Exception:
            logger.debug("Otonom gecmise yazilamadi", exc_info=True)

        # ------------------------------------------------------------------
        # Yanit
        # ------------------------------------------------------------------
        return {
            "asamalar": asamalar,
            # Bulgu 6: paylasilan helper ile tutarli projeksiyon
            "nesting_results": {
                bid: _nesting_result_projection(nr)
                for bid, nr in nesting_results.items()
            },
            "pricing_results": {
                bid: {"total_price": pr.get("total_price", 0.0)}
                for bid, pr in pricing_results.items()
            },
            "pipeline_ozet": {
                "siparis_sayisi": len(ranked),
                "parti_sayisi": n_batches,
                "uyari_sayisi": len(warnings),
                "elapsed_sec": pipeline_result.get("elapsed_sec", 0.0),
            },
            "toplam_fiyat": toplam_fiyat,
            "aciklama_md": aciklama_md,
            "teklif_taslagi": teklif_taslagi,
            "teklif_onay_gerekli": True,
        }, 200

    # -----------------------------------------------------------------------
    # Senkron /otonom rotasi (geriye-uyum: mevcut testler + tek-tik JSON akisi)
    # -----------------------------------------------------------------------
    def _parse_otonom_istek():
        """JSON body'den (nesting_mode, nfv_quality) coz — senkron + asenkron ortak."""
        _body = request.get_json(silent=True) or {}
        _onm = _body.get("nesting_mode", "auto")
        _mode = _onm if _onm in ("auto", "nfv", "heightmap") else "auto"
        _quality = "max" if _body.get("nfv_quality") == "max" else "fast"
        return _mode, _quality

    @app.route("/otonom", methods=["POST"])
    @_limit("2 per minute")
    def otonom():
        """Senkron otonom: pipeline'i bekleyip tam JSON doner (mevcut davranis).

        Asenkron/canli-ilerleme isteyen UI /otonom/baslat + /otonom/durum kullanir.
        """
        _mode, _quality = _parse_otonom_istek()
        body, status = _run_otonom_pipeline(_mode, _quality)
        return jsonify(body), status

    # -----------------------------------------------------------------------
    # ASENKRON otonom: baslat (job + arka-plan thread) + durum (polling)
    # -----------------------------------------------------------------------
    # Uzun suren otonom isi (NFV CPU'da dakikalar) senkron istekte tarayici
    # timeout + sunucu blok yaratir. Job'i daemon thread'e alir; UI durumu
    # /otonom/durum/<id> ile yoklayarak CANLI gosterir. Tek-is politikasi
    # (OtonomJobStore): ayni anda en fazla 1 aktif is.
    from src.runtime.otonom_jobs import OtonomJobStore
    _otonom_jobs = OtonomJobStore()
    app.config["OTONOM_JOBS"] = _otonom_jobs

    @app.route("/otonom/baslat", methods=["POST"])
    @_limit("2 per minute")
    def otonom_baslat():
        """Otonom isi arka-planda baslat — ANINDA job_id doner (202).

        LLM yok -> 503 (senkron ile ayni kapi). Zaten calisan is varsa -> 409.
        """
        if not llm_active or llm_components is None:
            return jsonify({
                "hata": (
                    "Otonom mod LLM gerektiriyor (mail parse icin). "
                    "Ollama calismiyor veya configs/llm.local.json eksik."
                ),
                "mesaj": "LLM gerekli",
            }), 503

        _mode, _quality = _parse_otonom_istek()
        jid = _otonom_jobs.try_start(meta={"mode": _mode, "quality": _quality})
        if jid is None:
            return jsonify({
                "hata": "Zaten calisan bir otonom is var; bitmesini bekleyin.",
                "job_id": _otonom_jobs.active_job_id(),
            }), 409

        def _worker():
            # Arka-plan: request/session context YOK (pipeline bunlari kullanmaz).
            try:
                body, status = _run_otonom_pipeline(
                    _mode, _quality,
                    on_stage=lambda asama: _otonom_jobs.add_stage(jid, asama),
                )
                _otonom_jobs.finish(jid, sonuc=body, status=status)
            except Exception as exc:  # pragma: no cover - beklenmeyen
                logger.exception("Otonom job (%s) hatasi: %s", jid, exc)
                _otonom_jobs.fail(jid, hata="Sistem hatasi olustu, lutfen tekrar deneyin.")

        threading.Thread(target=_worker, daemon=True, name=f"otonom-{jid}").start()
        return jsonify({"job_id": jid, "durum": "calisiyor"}), 202

    @app.route("/otonom/durum/<job_id>", methods=["GET"])
    @_limit("600 per minute")  # hafif okuma; UI ~2sn'de bir yoklar (=30/dk), bol tolerans
    def otonom_durum(job_id: str):
        """Asenkron isin anlik durumu (polling). Bulunamazsa 404."""
        snap = _otonom_jobs.snapshot(job_id)
        if snap is None:
            return jsonify({"hata": "Is bulunamadi (suresi dolmus olabilir)."}), 404
        return jsonify(snap), 200

    # -----------------------------------------------------------------------
    # Is Gecmisi sayfasi (kalici — daha once islenen otonom isleri)
    # -----------------------------------------------------------------------
    @app.route("/gecmis", methods=["GET"])
    def gecmis():
        """Daha once islenen otonom nesting isleri (en yeni ustte)."""
        kayitlar = _otonom_gecmis.liste(limit=100)
        return render_template("gecmis.html", kayitlar=kayitlar)

    # -----------------------------------------------------------------------
    # Mail Ayarlari rotasi (UI'dan gercek gelen-kutusu baglama)
    # -----------------------------------------------------------------------

    _MAIL_SAGLAYICI_ETIKET = {
        "hotmail": "Hotmail / Outlook.com", "outlook": "Outlook (Office 365)",
        "gmail": "Gmail", "fake": "Demo", "imap": "IMAP",
    }

    def _mail_cfg_path():
        return _ROOT / "configs" / "mail.local.json"

    def _read_mail_cfg() -> Dict[str, Any]:
        p = _mail_cfg_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("mail.local.json okunamadi: %s", exc)
        return {}

    @app.route("/mail-ayar", methods=["GET"])
    def mail_ayar():
        """Mail ayar formunu goster (mevcut config'i doldurur, parola maskeli)."""
        cfg = _read_mail_cfg()
        provider = cfg.get("provider") or cfg.get("source") or "fake"
        return render_template(
            "mail_ayar.html",
            kayitli=(bool(cfg) and provider != "fake"),
            aktif_provider=provider,
            aktif_saglayici=_MAIL_SAGLAYICI_ETIKET.get(provider, provider),
            aktif_user=cfg.get("user", ""),
            aktif_folder=cfg.get("folder", "INBOX"),
            kaydedildi=(request.args.get("kaydedildi") == "1"),
        )

    def _mail_cfg_from_form() -> Dict[str, Any]:
        """Form verisinden mail config kur; bos parola mevcut parolayi korur."""
        provider = request.form.get("provider", "fake")
        if provider == "fake":
            return {"source": "fake"}
        pw = (request.form.get("password") or "").strip()
        if not pw:  # bos birakildi -> mevcut parolayi koru
            pw = _read_mail_cfg().get("password", "")
        return {
            "provider": provider,
            "user": (request.form.get("user") or "").strip(),
            "password": pw,
            "folder": (request.form.get("folder") or "INBOX").strip() or "INBOX",
        }

    @app.route("/mail-ayar", methods=["POST"])
    def mail_ayar_kaydet():
        """Form verisini configs/mail.local.json'a yaz (sifre yalniz sunucuda).

        Guvenlik: dosya owner-only (0o600), dizin 0o700 yazilir — app password
        baska kullanicilarca okunamaz (POSIX). Windows'ta mode kismen yoksayilir
        ama POSIX deployment'ta (on-prem Linux sunucu) gercek koruma saglar.
        """
        cfg = _mail_cfg_from_form()
        p = _mail_cfg_path()
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(cfg, ensure_ascii=False, indent=2)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        return redirect(url_for("mail_ayar") + "?kaydedildi=1")

    @app.route("/mail-ayar/test", methods=["POST"])
    @_limit("4 per minute")
    def mail_ayar_test():
        """Girilen bilgilerle GERCEK baglanti+login dene (fetch_new degil — o
        auth hatasinda sessizce bos doner). _connect login firlatirsa yakalanir."""
        from src.runtime.mail_ingest import make_mail_source, ImapMailbox
        cfg = _mail_cfg_from_form()
        if cfg.get("source") == "fake":
            return jsonify({"ok": True, "mesaj": "Demo modu — örnek mailler kullanılır, gerçek bağlantı yok."})
        if not cfg.get("user") or not cfg.get("password"):
            return jsonify({"ok": False, "mesaj": "E-posta ve uygulama şifresi gerekli."})
        try:
            src = make_mail_source(cfg)
            if not isinstance(src, ImapMailbox):
                return jsonify({"ok": False, "mesaj": "Geçersiz sağlayıcı."})
            conn = src._connect()  # login dener; auth/baglanti hatasi firlatir
            try:
                conn.logout()
            except Exception:
                pass
            return jsonify({"ok": True, "mesaj": "Bağlantı ve giriş başarılı. Gelen kutusu hazır."})
        except Exception as exc:
            logger.warning("Mail test baglanti hatasi: %s", exc)
            return jsonify({"ok": False, "mesaj": f"Bağlanılamadı / giriş reddedildi: {exc}"})

    # -----------------------------------------------------------------------
    # Plaka (yazici tabani) ayar rotalari — manuel sabit plaka girisi
    # -----------------------------------------------------------------------

    def _plate_cfg_path():
        return _ROOT / "configs" / "plate.local.json"

    @app.route("/plaka-ayar", methods=["GET"])
    def plaka_ayar():
        """Plaka ayar formunu goster (mevcut config'i doldurur)."""
        from src.runtime.plate_config import resolve_plate
        w, d, h = resolve_plate(_ROOT)
        return render_template(
            "plaka_ayar.html",
            aktif_w=("" if w is None else w),
            aktif_d=("" if d is None else d),
            aktif_h=("" if h is None else h),
            otomatik=(w is None and d is None),
            kaydedildi=(request.args.get("kaydedildi") == "1"),
        )

    @app.route("/plaka-ayar", methods=["POST"])
    def plaka_ayar_kaydet():
        """Plaka boyutunu configs/plate.local.json'a yaz.

        Bos birakilirsa (veya 'otomatik' secilirse) config dosyasi SILINIR ->
        plaka parcalardan otomatik turetilir (cekirdek politika). Boylece kullanici
        sabit plaka ile otomatik arasinda gecis yapabilir.
        """
        def _num(key):
            raw = (request.form.get(key) or "").strip().replace(",", ".")
            if not raw:
                return None
            try:
                v = float(raw)
                return v if v > 0 else None
            except ValueError:
                return None

        otomatik = request.form.get("otomatik") == "1"
        w, d, h = (None, None, None) if otomatik else (_num("width_mm"), _num("depth_mm"), _num("height_mm"))

        p = _plate_cfg_path()
        if w is None or d is None:
            # Eksik/otomatik -> sabit plaka kaldirilir (varsa dosyayi sil)
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            return redirect(url_for("plaka_ayar") + "?kaydedildi=1")

        cfg = {"width_mm": w, "depth_mm": d}
        if h is not None:
            cfg["height_mm"] = h
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return redirect(url_for("plaka_ayar") + "?kaydedildi=1")

    # -----------------------------------------------------------------------
    # Eksik-bilgi siparisleri: operator adet girisi (/adet-gir)
    # -----------------------------------------------------------------------
    # "ZIP ekinde STL var ama mailde adet yok" siparisleri otomatik islenmez
    # (karar: operatore sor/beklet). Operator burada her STL icin adet girer;
    # siparis yeniden kurulup pipeline'a sokulur.

    @app.route("/adet-gir", methods=["GET"])
    def adet_gir():
        """Bekleyen eksik-bilgi siparislerini listele (her STL icin adet formu)."""
        bekleyenler = _pending_store.list()
        return render_template(
            "adet_gir.html",
            bekleyenler=bekleyenler,
            hata=request.args.get("hata"),
            islenen=request.args.get("islenen"),
        )

    @app.route("/adet-gir/<order_id>", methods=["POST"])
    def adet_gir_isle(order_id):
        """Operatorun girdigi adetlerle siparisi yeniden kur + pipeline kos.

        Form: her STL icin 'qty_<ad>' alani. Adet>0 olan STL'ler dahil edilir;
        bos/0 birakilanlar atlanir (operator parcayi cikarmis sayilir). En az bir
        gecerli adet yoksa hata ile geri doner.
        """
        from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
        from src.nesting3d.instances.stl_order_loader import build_instance_from_order

        meta = _pending_store.get(order_id)
        if meta is None:
            return redirect(url_for("adet_gir") + "?hata=bulunamadi")

        stl_map = _pending_store.load_stl_map(order_id)
        if not stl_map:
            _pending_store.remove(order_id)
            return redirect(url_for("adet_gir") + "?hata=stl_kayip")

        # Form adetlerini topla (qty_<ad>); adet>0 olanlar dahil.
        quantities: Dict[str, int] = {}
        for name in stl_map:
            raw = (request.form.get(f"qty_{name}") or "").strip()
            if not raw:
                continue
            try:
                q = int(float(raw.replace(",", ".")))
            except ValueError:
                continue
            if q > 0:
                quantities[name] = q

        if not quantities:
            return redirect(url_for("adet_gir") + "?hata=adet_yok")

        # Plaka politikasi (cekirdek) — UI plakasi > siparis container > otomatik.
        from src.runtime.plate_config import resolve_plate as _resolve_plate_ui
        _pw, _pd, _ph = _resolve_plate_ui(_ROOT)
        if not (_pw and _pd):
            _c = meta.get("container") or {}
            _pw, _pd, _ph = _c.get("width_mm"), _c.get("depth_mm"), _c.get("height_mm")

        _persist_dir = _ROOT / "data" / "mail_stl" / f"adetgir_{order_id}"
        res = build_instance_from_order(
            stl_map, quantities,
            container_w_mm=_pw, container_d_mm=_pd, container_h_mm=_ph,
            persist_dir=_persist_dir,
        )
        if not res.instance.parts:
            return redirect(url_for("adet_gir") + "?hata=parca_yok")

        parts = [
            {
                "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
                "stl_path": p.stl_path, "width_mm": p.width_mm,
                "depth_mm": p.depth_mm, "height_mm": p.height_mm,
            }
            for p in res.instance.parts
        ]
        order = {
            "order_id": meta.get("order_id", order_id),
            "customer": meta.get("customer", ""),
            "deadline": _normalize_deadline(meta.get("deadline", "")),
            "priority_class": meta.get("priority_class", 2),
            "parts": parts,
            "parse_source": "operator_adet_girisi",
        }
        scenario = {**RICH_SCENARIO, "orders": [order]}
        if _pw and _pd:
            scenario["container"] = {"width_mm": _pw, "depth_mm": _pd, "height_mm": _ph}
        else:
            scenario["container"] = None  # run_pipeline parcalardan otomatik

        try:
            result = run_pipeline(scenario)
        except Exception as exc:
            logger.exception("adet-gir: pipeline hatasi: %s", exc)
            return redirect(url_for("adet_gir") + "?hata=pipeline")

        result["used_demo"] = False
        app.config["LAST_RESULT"] = result
        # Basariyla islendi -> bekleyen kayidi temizle, sonuc ekranina git.
        _pending_store.remove(order_id)
        return redirect(url_for("sonuc"))

    # -----------------------------------------------------------------------
    # Oncelik Plani rotasi (deterministik, LLM gerektirmez)
    # -----------------------------------------------------------------------

    @app.route("/oncelik", methods=["GET"])
    def oncelik():
        """Cok-sirketli siparis onceliklendirme + parti plani + termin/kapasite uyarilari.

        Tamamen deterministik: Ollama kapali olsa da calisir.
        today = date(2026, 6, 13) SABiT — demo tutarliligini garantiler.
        """
        from datetime import date as _date
        from src.scheduling.models import Order as _Order, Capacity as _Capacity
        from src.scheduling.rules import PriorityConfig as _PriorityConfig, rank_orders as _rank_orders
        from src.scheduling.batcher import build_batches as _build_batches
        from src.scheduling.feasibility import check_feasibility as _check_feasibility
        from src.scheduling.report import build_report as _build_report

        _today = _date(2026, 6, 13)

        _orders = [
            _Order("ORD-FORD-001",    "FORD",     "motor-govde-A",       20, 8500.0,  "2026-06-18", 1),
            _Order("ORD-FORD-002",    "FORD",     "dirsek-traversi-B",   12, 4200.0,  "2026-06-25", 2),
            _Order("ORD-BAYKAR-001",  "BAYKAR",   "uc-govde-kanat",       8, 6800.0,  "2026-06-20", 1),
            _Order("ORD-BAYKAR-002",  "BAYKAR",   "aviyonik-braket",     15, 3100.0,  "2026-07-05", 3),
            _Order("ORD-ASELSAN-001", "ASELSAN",  "radar-muhafaza",       6, 9200.0,  "2026-06-22", 1),
            _Order("ORD-ASELSAN-002", "ASELSAN",  "anten-tasiyi",        10, 5400.0,  "2026-07-10", 2),
            _Order("ORD-ASELSAN-003", "ASELSAN",  "elektronik-kutu",      5, 2800.0,  "2026-07-15", 3),
            _Order("ORD-TUSAS-001",   "TUSAS",    "kanat-nervuru",       18, 11000.0, "2026-06-19", 1),
            _Order("ORD-TUSAS-002",   "TUSAS",    "iniş-takimi-bağlantı", 7, 7300.0,  "2026-06-28", 2),
            _Order("ORD-TUSAS-003",   "TUSAS",    "yakıt-hücresi-kapak",  9, 4600.0,  "2026-07-08", 3),
            _Order("ORD-ROKETSAN-001","ROKETSAN", "firlatici-govde",      4, 13500.0, "2026-06-21", 1),
            _Order("ORD-ROKETSAN-002","ROKETSAN", "stabilizator-kanat",  11, 6100.0,  "2026-07-02", 2),
            _Order("ORD-ROKETSAN-003","ROKETSAN", "guvdeli-eklenti",      6, 3900.0,  "2026-07-18", 3),
        ]

        _capacity = _Capacity(
            num_machines=1,
            batch_duration_hours=8,
            shifts_per_day=1,
            max_volume_per_batch_cm3=20000.0,
        )

        for o in _orders:
            o.validate(_today)
        _capacity.validate()

        _ranked = _rank_orders(_orders, _PriorityConfig.default(), _today)
        _batches = _build_batches(_ranked, _capacity, allow_mixing=False)
        _warnings = _check_feasibility(_batches, _capacity, _today)
        _report = _build_report(_ranked, _batches, _warnings, _today)

        return render_template("oncelik.html", report=_report)

    # -----------------------------------------------------------------------
    # Siparis havuzu rotalar
    # -----------------------------------------------------------------------
    # CSRF (Bulgu 8): /siparisler, /siparisler/csv, /siparisler/sil state-mutating
    # form rotalaridir. flask-wtf CSRF token eklenmesi template degisikliği
    # gerektirir ve localhost demo'yu kırabilir.
    # ERTELENDI: localhost demo — SaaS fazinda flask-wtf CSRFProtect ekle.

    @app.route("/siparisler", methods=["GET"])
    def siparisler():
        """Havuz sayfasi: siparis tablosu + manuel form + CSV yukleme."""
        from src.webapp.orders_store import load_orders

        _opath = app.config.get("ORDERS_PATH")
        orders = load_orders(_opath)

        # Toplam parca sayisi ve hacim ozeti her siparis icin
        summaries = []
        for o in orders:
            parts = o.get("parts", [])
            n_parts = sum(p.get("qty", 1) for p in parts)
            vol_cm3 = sum(
                p.get("width_mm", 0) * p.get("depth_mm", 0)
                * p.get("height_mm", 0) / 1000.0 * p.get("qty", 1)
                for p in parts
            )
            summaries.append({
                "order_id": o["order_id"],
                "customer": o.get("customer", ""),
                "deadline": o.get("deadline", ""),
                "priority_class": o.get("priority_class", 2),
                "n_parts": n_parts,
                "vol_cm3": vol_cm3,
            })

        flash_errors = request.args.getlist("errors")
        flash_info = request.args.get("info", "")
        return render_template(
            "siparisler.html",
            summaries=summaries,
            errors=flash_errors,
            info=flash_info,
        )

    @app.route("/siparisler", methods=["POST"])
    def siparisler_ekle():
        """Manuel form ile yeni siparis ekle."""
        from src.webapp.orders_store import (
            add_order, load_orders, parse_parts_text,
        )

        order_id = (request.form.get("order_id") or "").strip()
        customer = (request.form.get("customer") or "").strip()
        deadline = (request.form.get("deadline") or "").strip()
        priority_str = (request.form.get("priority_class") or "2").strip()
        parts_text = (request.form.get("parts_text") or "").strip()

        errors: List[str] = []

        if not order_id:
            errors.append("Siparis ID bos olamaz (zorunlu alan).")
        if not customer:
            errors.append("Musteri adi bos olamaz.")
        if not deadline:
            errors.append("Termin tarihi bos olamaz.")
        if not parts_text:
            errors.append("En az bir parca satiri girilmeli.")

        try:
            priority = int(priority_str)
        except ValueError:
            priority = 2

        parts: List[Dict[str, Any]] = []
        if parts_text and not errors:
            parts, part_errors = parse_parts_text(parts_text)
            for line_no, msg in part_errors:
                errors.append(f"Satir {line_no}: {msg}")
            if not parts and not part_errors:
                errors.append("Parca listesi bos — en az bir gecerli satir gerekli.")
            elif parts and part_errors:
                # Kismen gecerli: sadece gecerli parcalari kullan, hatalari raporla
                pass

        if errors:
            _opath = app.config.get("ORDERS_PATH")
            orders = load_orders(_opath)
            summaries = _build_summaries(orders)
            return render_template(
                "siparisler.html",
                summaries=summaries,
                errors=errors,
                info="",
            ), 400

        new_order = {
            "order_id": order_id,
            "customer": customer,
            "deadline": deadline,
            "priority_class": priority,
            "parts": parts,
        }

        _opath = app.config.get("ORDERS_PATH")
        try:
            add_order(new_order, _opath)
        except ValueError as exc:
            orders = load_orders(_opath)
            summaries = _build_summaries(orders)
            return render_template(
                "siparisler.html",
                summaries=summaries,
                errors=[f"Siparis eklenemedi: {exc} — zaten mevcut bir siparis ID."],
                info="",
            ), 400

        return redirect(url_for("siparisler", info="Siparis eklendi."))

    @app.route("/siparisler/sil/<order_id>", methods=["POST"])
    def siparisler_sil(order_id: str):
        """Havuzdan siparis sil."""
        from src.webapp.orders_store import delete_order

        _opath = app.config.get("ORDERS_PATH")
        try:
            delete_order(order_id, _opath)
        except ValueError as exc:
            logger.warning("Siparis sil hatasi: %s", exc)
        return redirect(url_for("siparisler"))

    @app.route("/siparisler/sablon.csv", methods=["GET"])
    def siparisler_sablon():
        """Ornek CSV sablonu indir."""
        header = "order_id,customer,deadline,priority,part_name,width_mm,depth_mm,height_mm,qty\n"
        example = "ORD-ORNEK-001,MUSTERI-ADI,2027-01-15,1,parca_adi,80,60,40,2\n"
        content = header + example
        return Response(
            content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=siparis_sablon.csv"
            },
        )

    @app.route("/siparisler/csv", methods=["POST"])
    def siparisler_csv():
        """CSV dosyasi yukle; gecerli satirlari ekle, hatalilari raporla."""
        from src.webapp.orders_store import (
            add_order, load_orders, parse_csv_upload,
        )

        _opath = app.config.get("ORDERS_PATH")
        existing = load_orders(_opath)
        existing_ids = {o["order_id"] for o in existing}

        csv_file = request.files.get("csv_file")
        if not csv_file or not csv_file.filename:
            orders = load_orders(_opath)
            summaries = _build_summaries(orders)
            return render_template(
                "siparisler.html",
                summaries=summaries,
                errors=["CSV dosyasi secilmedi."],
                info="",
            ), 400

        try:
            csv_text = csv_file.read().decode("utf-8")
        except Exception as exc:
            orders = load_orders(_opath)
            summaries = _build_summaries(orders)
            return render_template(
                "siparisler.html",
                summaries=summaries,
                errors=[f"CSV okunamadi: {exc}"],
                info="",
            ), 400

        new_orders, parse_errors = parse_csv_upload(csv_text, existing_ids)

        added = 0
        add_errors: List[str] = []
        for order in new_orders:
            try:
                add_order(order, _opath)
                added += 1
            except ValueError as exc:
                add_errors.append(str(exc))

        all_errors = [f"Satir {ln}: {msg}" for ln, msg in parse_errors] + add_errors

        info_msg = f"{added} siparis eklendi."
        if parse_errors or add_errors:
            info_msg += f" {len(all_errors)} hata var (asagida listelendi)."

        orders = load_orders(_opath)
        summaries = _build_summaries(orders)
        return render_template(
            "siparisler.html",
            summaries=summaries,
            errors=all_errors,
            info=info_msg,
        )


def _build_summaries(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Siparis listesinden goruntu ozeti uretir."""
    summaries = []
    for o in orders:
        parts = o.get("parts", [])
        n_parts = sum(p.get("qty", 1) for p in parts)
        vol_cm3 = sum(
            p.get("width_mm", 0) * p.get("depth_mm", 0)
            * p.get("height_mm", 0) / 1000.0 * p.get("qty", 1)
            for p in parts
        )
        summaries.append({
            "order_id": o["order_id"],
            "customer": o.get("customer", ""),
            "deadline": o.get("deadline", ""),
            "priority_class": o.get("priority_class", 2),
            "n_parts": n_parts,
            "vol_cm3": vol_cm3,
        })
    return summaries


def _startup_health_report(app: Flask) -> None:
    """Sunucu acilirken konsola net 'demo hazir mi' raporu bas (canli probe).

    Demo'dan ONCE Ollama kapaliysa/model cekilmemisse burada gorunur — demo
    sirasinda surpriz olmaz. Probe asla baslatmayi engellemez (sadece uyarir).
    """
    llm = app.config.get("LLM_COMPONENTS")
    print("-" * 60)
    if not llm:
        print("  LLM: DEVRE DISI (configs/llm.local.json yok/yuklenemedi).")
        print("  -> Nesting calisir; asistan/teklif/aciklama calismaz.")
        print("-" * 60)
        return
    provider = llm.get("health_provider")
    checker = getattr(provider, "health_check", None)
    if not callable(checker):
        print("  LLM: aktif (saglayici probe desteklemiyor).")
        print("-" * 60)
        return
    try:
        ok, detail = checker()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, str(exc)
    if ok:
        print(f"  LLM HAZIR ✓  {detail}")
    else:
        print(f"  ⚠ LLM PROBE BASARISIZ: {detail}")
        print("  -> Demo asistan/teklif ozellikleri calismayabilir.")
        print("  -> Durumu sonra kontrol: http://127.0.0.1:8765/health")
    print("-" * 60)


def _main() -> None:
    """Sunucuyu dogrudan baslatir (python -m src.webapp.app)."""
    # Windows konsolu cp1254/cp437 olabilir; '✓'/'⚠' gibi karakterler
    # UnicodeEncodeError ile sunucuyu COKERTIR. Cikti kodlamasini UTF-8'e
    # (hata toleranslı) sabitle — boylece her kod sayfasinda guvenli.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — reconfigure yoksa sessizce gec
            pass
    logging.basicConfig(level=logging.INFO)
    app = create_app(testing=False, llm_enabled=True)
    _startup_health_report(app)
    # threaded=True: asenkron otonom job thread'i koşarken polling istekleri
    # (/otonom/durum) ve diger rotalar bloke olmadan islenebilsin.
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)


if __name__ == "__main__":
    _main()

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

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Flask, Response, jsonify, redirect, render_template,
    request, url_for,
)

# Proje kokunu sys.path'e ekle (dogrudan calistirma icin)
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


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
        else:
            # Gercek Ollama saglayicisi
            from src.llm.providers.openai_compat import OpenAICompatProvider

            prov_cfg = cfg.provider_for_role("report")
            provider = OpenAICompatProvider(
                base_url=prov_cfg.base_url or "http://localhost:11434",
                model=cfg.role("report").model,
                timeout_s=prov_cfg.timeout_s,
            )

        from src.llm.roles.explainer import ExplainerRole

        report_role = ReportRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("report"),
        )

        assistant_role = AssistantRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("assistant"),
            conversation=Conversation(),
        )

        parser_role = ParserRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("parser"),
        )

        explainer_role = ExplainerRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("explainer"),
        )

        return {
            "report_role": report_role,
            "assistant_role": assistant_role,
            "parser_role": parser_role,
            "explainer_role": explainer_role,
            "llm_active": True,
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
            pass

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
                    pass

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

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = "konteyner-nesting-demo-secret-2026"
    app.config["TESTING"] = testing

    # Durum: her create_app() cagrisinda sifirlanir (test izolasyonu)
    app.config["LAST_RESULT"] = None
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

    _register_routes(app, llm_components=_llm, llm_active=llm_active)
    return app


def _register_routes(
    app: Flask,
    llm_components: Optional[Dict[str, Any]] = None,
    llm_active: bool = False,
) -> None:
    """Tum rotalari app'e kaydeder."""

    @app.route("/", methods=["GET"])
    def index():
        """Ana sayfa: uygulama tanitimi + havuz ozeti + calistir dugmesi."""
        from scripts.demo_pipeline import SCENARIO
        from src.webapp.orders_store import load_orders

        _opath = app.config.get("ORDERS_PATH")
        pool_orders = load_orders(_opath)
        pool_count = len(pool_orders)

        # Senaryo ozeti: havuz doluysa havuzdan, bos ise demo'dan
        if pool_orders:
            container = SCENARIO.get("container", {})
            capacity = SCENARIO.get("capacity", {})
            display_orders = pool_orders
        else:
            display_orders = SCENARIO.get("orders", [])
            container = SCENARIO.get("container", {})
            capacity = SCENARIO.get("capacity", {})

        return render_template(
            "index.html",
            orders=display_orders,
            container=container,
            capacity=capacity,
            llm_active=llm_active,
            pool_count=pool_count,
            pool_is_custom=bool(pool_orders),
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

        result = run_pipeline(scenario)
        result["used_demo"] = used_demo
        app.config["LAST_RESULT"] = result
        app.config["CONVERSATION_TURNS"] = []
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
            sohbet=app.config.get("CONVERSATION_TURNS", []),
            used_demo=used_demo,
            has_portfolio=any(
                nesting_results.get(b.batch_id, {}).get("portfolio") is not None
                for b in batches
            ),
        )

    @app.route("/ozet", methods=["POST"])
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
            return jsonify({"hata": f"Sistem hatasi: {exc}", "ozet": None}), 500

    @app.route("/sor", methods=["POST"])
    def sor():
        """LLM asistan sorusu.

        Istek JSON: {soru: "..."}
        Yanit JSON: {cevap, alintilar, ret, sayi_bayragi, hata}
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

        try:
            from src.llm.structured import ValidationStatus

            context = _build_grounded_context(result)
            assistant_role = llm_components["assistant_role"]
            ask_result = assistant_role.ask(soru=soru, context=context)

            if ask_result.status == ValidationStatus.INVALID or ask_result.fallback:
                fallback_text = ""
                if ask_result.fallback:
                    fallback_text = ask_result.fallback.raw_text
                return jsonify({
                    "cevap": None,
                    "hata": "LLM gecerli yanit uretemedi.",
                    "fallback": fallback_text[:300] if fallback_text else "",
                }), 200

            data = ask_result.data or {}
            cevap_md = data.get("cevap_md", "")
            ret = data.get("ret", False)

            # Sohbet gecmisini guncelle
            turns = app.config.get("CONVERSATION_TURNS", [])
            turns.append({"soru": soru, "cevap": cevap_md})
            if len(turns) > 6:
                turns = turns[-6:]
            app.config["CONVERSATION_TURNS"] = turns

            return jsonify({
                "cevap": cevap_md,
                "alintilar": data.get("alintilar", []),
                "ret": ret,
                "ret_nedeni": data.get("ret_nedeni"),
                "sayi_bayragi": ask_result.number_flag,
                "topraklanamayan_sayilar": ask_result.ungrounded_numbers,
                "hata": None,
            }), 200

        except Exception as exc:
            logger.exception("LLM soru hatasi: %s", exc)
            return jsonify({"hata": f"Sistem hatasi: {exc}", "cevap": None}), 500

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
    def teklif():
        """LLM ile musteri yanit maili taslagi uret.

        Yanit JSON: {taslak, baslik, hata}
        LLM aktif degil -> 503.
        Pipeline kosulmamis -> 400.
        """
        if not llm_active or llm_components is None:
            return jsonify({"hata": "LLM aktif degil.", "taslak": None}), 503

        result = app.config.get("LAST_RESULT")
        if result is None:
            return jsonify({"hata": "Once pipeline calistirin.", "taslak": None}), 400

        try:
            from src.llm.roles.report import ReportInput
            from src.llm.structured import ValidationStatus

            context = _build_grounded_context(result)

            pricing_results = result.get("pricing_results", {})
            total_revenue = sum(
                pr.get("total_price", 0.0) for pr in pricing_results.values()
            )

            report_input = ReportInput(
                is_id="demo-teklif",
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
                    "taslak": None,
                    "hata": None,
                    "topraklama_uyarisi": (
                        "Sayi-topraklama dogrulanamadi. "
                        f"Sayilar: {report_result.grounding_detail}."
                    ),
                }), 200

            if report_result.status == ValidationStatus.INVALID or report_result.fallback:
                raw = ""
                if report_result.fallback:
                    raw = report_result.fallback.raw_text[:300]
                return jsonify({
                    "taslak": None,
                    "hata": "LLM gecerli taslak uretemedi. Tekrar deneyin.",
                    "ham_cikti": raw,
                }), 200

            data = report_result.data or {}
            return jsonify({
                "taslak": data.get("govde_md", ""),
                "baslik": data.get("baslik", ""),
                "kaynaklar": data.get("kullanilan_kaynaklar", []),
                "hata": None,
            }), 200

        except Exception as exc:
            logger.exception("Teklif taslagi hatasi: %s", exc)
            return jsonify({"hata": f"Sistem hatasi: {exc}", "taslak": None}), 500

    # -----------------------------------------------------------------------
    # Mail parser rotasi
    # -----------------------------------------------------------------------

    @app.route("/parse", methods=["POST"])
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
                "mesaj": f"Sistem hatasi: {exc}",
            }), 500

    # -----------------------------------------------------------------------
    # Otonom zincir rotasi (VİTRİN C)
    # -----------------------------------------------------------------------

    @app.route("/otonom", methods=["POST"])
    def otonom():
        """Mail-cek → parse → onceliklendir → nesting → fiyat → acikla → teklif taslagi.

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
        if not llm_active or llm_components is None:
            return jsonify({
                "hata": (
                    "Otonom mod LLM gerektiriyor (mail parse icin). "
                    "Ollama calismiyor veya configs/llm.local.json eksik. "
                    "Manuel demo icin /run rotasini kullanin."
                ),
                "mesaj": "LLM gerekli",
                "asamalar": [],
            }), 503

        from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
        from src.runtime.mail_ingest import make_mail_source
        from src.llm.roles.parser import parsed_to_order
        from src.llm.roles.explainer import ExplainerInput
        from src.llm.structured import ValidationStatus
        from src.llm.roles.report import ReportInput

        asamalar: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # ASAMA 1: Mail-Cek
        # ------------------------------------------------------------------
        try:
            mail_source = make_mail_source({"source": "fake"})
            raw_mails = mail_source.fetch_new()
            n_mail = len(raw_mails)
            asamalar.append({
                "ad": "Mail-Cek",
                "durum": "tamam",
                "cikti": f"{n_mail} mail cekildi (FakeMailbox)",
                "detay": [
                    {"gonderen": m.gonderen, "konu": m.konu}
                    for m in raw_mails
                ],
            })
        except Exception as exc:
            logger.warning("Otonom: Mail-Cek hatasi: %s", exc)
            asamalar.append({"ad": "Mail-Cek", "durum": "hata", "cikti": str(exc)})
            return jsonify({"hata": f"Mail cekme hatasi: {exc}", "asamalar": asamalar}), 500

        # ------------------------------------------------------------------
        # ASAMA 2: Parse (her mail icin)
        # ------------------------------------------------------------------
        parser_role = llm_components.get("parser_role")
        parsed_orders: List[Dict[str, Any]] = []
        parse_hatalar: List[str] = []

        for mail in raw_mails:
            try:
                parse_result = parser_role.parse(mail.govde)
                if parse_result.status != ValidationStatus.INVALID and parse_result.order_dict:
                    # Mail gonderenden oncelik ipucu al (FORD/BAYKAR/ASELSAN)
                    govde_lower = mail.govde.lower()
                    konu_lower = mail.konu.lower()
                    if "acil" in konu_lower or "acil" in govde_lower:
                        priority = 1
                    else:
                        priority = 2
                    order = parsed_to_order(
                        parse_result.data or {},
                        priority_class=priority,
                    )
                    # Musteri adini gonderen domain'den zenginlestir
                    if not order.get("customer") or order["customer"] == "Bilinmiyor":
                        domain = mail.gonderen.split("@")[-1].split(".")[0].upper()
                        order["customer"] = domain
                    # Termin duzeltme: bos/eksik veya ISO olmayan formatlari normalize et
                    order["deadline"] = _normalize_deadline(
                        order.get("deadline", ""),
                        mail_tarih=mail.tarih,
                    )
                    parsed_orders.append(order)
                else:
                    parse_hatalar.append(f"{mail.gonderen}: parse basarisiz")
            except Exception as exc:
                logger.warning("Otonom: Parse hatasi (mail=%s): %s", mail.gonderen, exc)
                parse_hatalar.append(f"{mail.gonderen}: {exc}")

        n_parsed = len(parsed_orders)
        parse_durum = "tamam" if n_parsed > 0 else "hata"
        parse_cikti = f"{n_parsed} siparis cikarildi"
        if parse_hatalar:
            parse_cikti += f" ({len(parse_hatalar)} basarisiz)"
        asamalar.append({
            "ad": "Parse",
            "durum": parse_durum,
            "cikti": parse_cikti,
            "detay": {"siparis_sayisi": n_parsed, "hatalar": parse_hatalar},
        })

        if n_parsed == 0:
            return jsonify({
                "hata": "Hic siparis cikartilamadi (LLM parse basarisiz).",
                "asamalar": asamalar,
            }), 500

        # ------------------------------------------------------------------
        # ASAMA 3-5: Onceliklendir + Nesting + Fiyat (run_pipeline)
        # ------------------------------------------------------------------
        import copy
        scenario = copy.deepcopy(RICH_SCENARIO)
        scenario["orders"] = parsed_orders

        try:
            pipeline_result = run_pipeline(scenario)
        except Exception as exc:
            logger.exception("Otonom: pipeline hatasi: %s", exc)
            return jsonify({"hata": f"Pipeline hatasi: {exc}", "asamalar": asamalar}), 500

        ranked = pipeline_result.get("ranked_orders", [])
        batches = pipeline_result.get("batches", [])
        warnings = pipeline_result.get("warnings", [])
        nesting_results = pipeline_result.get("nesting_results", {})
        pricing_results = pipeline_result.get("pricing_results", {})

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
                sistem_ciktisi = {
                    "kazanan_algoritma": winner_name,
                    "height_mm": nr_first.get("height_mm", 0.0),
                    "density": nr_first.get("density", 0.0),
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
        # ASAMA 7: Teklif Taslagi (LLM -- INSAN ONAY KAPISI)
        # ------------------------------------------------------------------
        teklif_taslagi = ""
        teklif_durum = "llm_yok"

        report_role = llm_components.get("report_role")
        if report_role is not None:
            try:
                context = _build_grounded_context(pipeline_result)
                report_input = ReportInput(
                    is_id="otonom-pipeline",
                    n_orders=len(ranked),
                    n_batches=n_batches,
                    n_warnings=len(warnings),
                    total_revenue_usd=toplam_fiyat,
                    context=context,
                )
                report_result = report_role.run(report_input)

                if not report_result.grounding_blocked and report_result.data:
                    teklif_taslagi = report_result.data.get("govde_md", "")
                    teklif_durum = "taslak_hazir"
                else:
                    teklif_taslagi = ""
                    teklif_durum = "topraklama_hatasi"
            except Exception as exc:
                logger.warning("Otonom: Teklif taslagi hatasi: %s", exc)
                teklif_taslagi = ""
                teklif_durum = "hata"

        asamalar.append({
            "ad": "Teklif-Taslagi",
            "durum": teklif_durum,
            "cikti": (
                "Taslak hazir — insan onay gerekli, otomatik gonderilmez"
                if teklif_durum == "taslak_hazir"
                else "Teklif taslagi uretilemedi"
            ),
            "detay": {
                "taslak": teklif_taslagi,
                "onay_gerekli": True,
                "otomatik_gonderildi": False,
            },
        })

        # ------------------------------------------------------------------
        # Yanit
        # ------------------------------------------------------------------
        return jsonify({
            "asamalar": asamalar,
            "nesting_results": {
                bid: {
                    "height_mm": nr.get("height_mm", 0.0),
                    "density": nr.get("density", 0.0),
                    "n_parts": nr.get("n_parts", 0),
                }
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
        }), 200

    # -----------------------------------------------------------------------
    # Siparis havuzu rotalar
    # -----------------------------------------------------------------------

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


def _main() -> None:
    """Sunucuyu dogrudan baslatir (python -m src.webapp.app)."""
    logging.basicConfig(level=logging.INFO)
    app = create_app(testing=False, llm_enabled=True)
    app.run(host="127.0.0.1", port=8765, debug=False)


if __name__ == "__main__":
    _main()

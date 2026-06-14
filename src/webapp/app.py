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

        return {
            "report_role": report_role,
            "assistant_role": assistant_role,
            "parser_role": parser_role,
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

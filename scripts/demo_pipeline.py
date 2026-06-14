"""demo_pipeline.py — Uçtan uca demo pipeline (§6.4 işleyiş zinciri).

Zincir:
    1. Sipariş havuzu → rank_orders (EDD ağırlıklı önceliklendirme)
    2. build_batches (allow_mixing=False) → parti planı
    3. check_feasibility → termin uyarıları
    4. Her parti için: NestingInstance kur → suggest_pitch (adaptif) →
       to_voxel_parts → Instance-Tuner (portföy + menü konfigleri) yerleşimi
       → yükseklik + doluluk metrikleri + tuner konfig kıyası
       + Algoritma-seçim tahmini (artefakt varsa; yoksa gizlenir)
    5. Her parti için: PricingEngine → fiyat dökümü
    6. results/demo_pipeline_report.md → bölümlü markdown raporu
    7. Konsola özet bas

Deterministik: sabit ref_date + seed; iki koşu aynı raporu üretir.

Tuner: build_menu() konfigleri (baseline portföy + 6 ek konfig) her parti
için aynı TUNER_BUDGET/seed ile koşar; en iyi monoton kabul garantisi ile
seçilir; kazanan konfig + DBLF'ye kazanç% rapora eklenir.

Selection: data/selection_model.json artefaktı varsa yüklenir; her parti için
is_easy + predicted_winner + explain bilgisi nesting_results'a eklenir
(BİLGİLENDİRME — çözüm her zaman tuner'dan gelir).

Kullanım:
    python scripts/demo_pipeline.py
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

# Proje kökü
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

RESULTS_DIR = _ROOT / "results"
REPORT_FILENAME = "demo_pipeline_report.md"

# Instance-Tuner demo bütçesi: demo süresi < ~15 s kalsın
TUNER_BUDGET = 70

# Algoritma-seçim model artefaktı
SELECTION_MODEL_PATH = _ROOT / "data" / "selection_model.json"

# ---------------------------------------------------------------------------
# Senaryo fixture — Ford/Baykar/ASELSAN havuzu + parça listeleri
# ---------------------------------------------------------------------------

SCENARIO: Dict[str, Any] = {
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    # Kapasite: 1 makine, 8 saatlik parti, 1 vardiya, 25 000 cm3 parti hacim sınırı
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 25_000.0,
    },
    # Konteyner boyutu (335x250 tabanlı kaba demo — pitch büyük tutuldu)
    "container": {
        "width_mm": 335.0,
        "depth_mm": 250.0,
    },
    # pitch artık suggest_pitch ile instance'tan türetilir; bu alan fallback
    "pitch": 15.0,
    "n_orientations": 4,
    # Portföy bütçesi: her çözücü başına iterasyon (demo hızı için 120)
    "portfolio_budget": 120,
    # Sipariş havuzu — her siparişe kutu parça listesi eklendi
    "orders": [
        {
            "order_id": "ORD-FORD-A1",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "ford_a1_p1", "name": "ford_bracket",
                 "qty": 4, "source": "box",
                 "width_mm": 80.0, "depth_mm": 60.0, "height_mm": 30.0},
                {"id": "ford_a1_p2", "name": "ford_cover",
                 "qty": 2, "source": "box",
                 "width_mm": 100.0, "depth_mm": 80.0, "height_mm": 20.0},
            ],
        },
        {
            "order_id": "ORD-FORD-A2",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "ford_a2_p1", "name": "ford_flange",
                 "qty": 3, "source": "box",
                 "width_mm": 70.0, "depth_mm": 70.0, "height_mm": 25.0},
            ],
        },
        {
            "order_id": "ORD-ASEL-A1",
            "customer": "ASELSAN",
            "deadline": "2026-06-20",
            "priority_class": 1,
            "parts": [
                {"id": "asel_a1_p1", "name": "asel_housing",
                 "qty": 2, "source": "box",
                 "width_mm": 120.0, "depth_mm": 90.0, "height_mm": 50.0},
                {"id": "asel_a1_p2", "name": "asel_plate",
                 "qty": 3, "source": "box",
                 "width_mm": 150.0, "depth_mm": 100.0, "height_mm": 15.0},
            ],
        },
        {
            "order_id": "ORD-BAYK-C1",
            "customer": "BAYKAR",
            "deadline": "2026-06-25",
            "priority_class": 2,
            "parts": [
                {"id": "bayk_c1_p1", "name": "bayk_rib",
                 "qty": 5, "source": "box",
                 "width_mm": 90.0, "depth_mm": 45.0, "height_mm": 20.0},
                {"id": "bayk_c1_p2", "name": "bayk_spar",
                 "qty": 2, "source": "box",
                 "width_mm": 200.0, "depth_mm": 30.0, "height_mm": 25.0},
            ],
        },
        {
            "order_id": "ORD-FORD-C1",
            "customer": "FORD",
            "deadline": "2026-06-28",
            "priority_class": 2,
            "parts": [
                {"id": "ford_c1_p1", "name": "ford_seal",
                 "qty": 6, "source": "box",
                 "width_mm": 50.0, "depth_mm": 50.0, "height_mm": 15.0},
            ],
        },
    ],
    # Portföy varsayılan senaryo: "küçük" — eski senaryoya benzer
    # (webapp'te ikon ile ayırt edilir; daha sıkı senaryo RICH_SCENARIO)
    "scenario_label": "standard",
    # Örnek fiyatlama kural seti
    "pricing_rules": {
        "version": "1.0",
        "name": "Demo kural seti v1",
        "rules": [
            {
                "id": "r_volume",
                "type": "unit_price",
                "input_field": "hacim_m3",
                "unit_price": 8000.0,
                "description": "Hacim bazlı birim fiyat (8000 $/m3)",
            },
            {
                "id": "r_konteyner",
                "type": "unit_price",
                "input_field": "konteyner_sayisi",
                "unit_price": 50.0,
                "description": "Konteyner kullanım ücreti (50 $/konteyner)",
            },
            {
                "id": "r_doluluk_bonus",
                "type": "conditional_multiplier",
                "condition_field": "doluluk_oran",
                "operator": ">=",
                "threshold": 0.6,
                "multiplier": 0.95,
                "description": "Yüksek doluluk indirimi (%5)",
            },
            {
                "id": "r_min",
                "type": "min_clamp",
                "min_price": 200.0,
                "description": "Minimum parti fiyatı",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Zengin demo senaryosu — portföyün ayırt edici olduğu yoğun vaka
# ~20 parça, sıkı taban (335×250), karışık boyutlar
# ---------------------------------------------------------------------------

RICH_SCENARIO: Dict[str, Any] = {
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 200_000.0,
    },
    "container": {
        "width_mm": 335.0,
        "depth_mm": 250.0,
    },
    "pitch": 12.0,
    "n_orientations": 4,
    "portfolio_budget": 120,
    "scenario_label": "rich",
    "orders": [
        {
            "order_id": "RICH-FORD-A1",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "r_f_p1", "name": "ford_bracket_L", "qty": 3, "source": "box",
                 "width_mm": 90.0, "depth_mm": 70.0, "height_mm": 40.0},
                {"id": "r_f_p2", "name": "ford_cover_lg", "qty": 2, "source": "box",
                 "width_mm": 110.0, "depth_mm": 85.0, "height_mm": 30.0},
                {"id": "r_f_p3", "name": "ford_seal_sm", "qty": 4, "source": "box",
                 "width_mm": 45.0, "depth_mm": 45.0, "height_mm": 18.0},
                {"id": "r_f_p4", "name": "ford_flange", "qty": 2, "source": "box",
                 "width_mm": 75.0, "depth_mm": 75.0, "height_mm": 28.0},
            ],
        },
        {
            "order_id": "RICH-ASEL-A1",
            "customer": "ASELSAN",
            "deadline": "2026-06-20",
            "priority_class": 1,
            "parts": [
                {"id": "r_a_p1", "name": "asel_housing_lg", "qty": 2, "source": "box",
                 "width_mm": 130.0, "depth_mm": 95.0, "height_mm": 55.0},
                {"id": "r_a_p2", "name": "asel_plate_thin", "qty": 3, "source": "box",
                 "width_mm": 160.0, "depth_mm": 110.0, "height_mm": 18.0},
                {"id": "r_a_p3", "name": "asel_bracket_sm", "qty": 4, "source": "box",
                 "width_mm": 55.0, "depth_mm": 40.0, "height_mm": 22.0},
            ],
        },
        {
            "order_id": "RICH-BAYK-C1",
            "customer": "BAYKAR",
            "deadline": "2026-06-25",
            "priority_class": 2,
            "parts": [
                {"id": "r_b_p1", "name": "bayk_rib_lg", "qty": 4, "source": "box",
                 "width_mm": 100.0, "depth_mm": 50.0, "height_mm": 24.0},
                {"id": "r_b_p2", "name": "bayk_spar_long", "qty": 2, "source": "box",
                 "width_mm": 220.0, "depth_mm": 35.0, "height_mm": 28.0},
                {"id": "r_b_p3", "name": "bayk_clip", "qty": 5, "source": "box",
                 "width_mm": 38.0, "depth_mm": 30.0, "height_mm": 20.0},
            ],
        },
    ],
    "pricing_rules": {
        "version": "1.0",
        "name": "Demo kural seti v1",
        "rules": [
            {
                "id": "r_volume",
                "type": "unit_price",
                "input_field": "hacim_m3",
                "unit_price": 8000.0,
                "description": "Hacim bazlı birim fiyat (8000 $/m3)",
            },
            {
                "id": "r_konteyner",
                "type": "unit_price",
                "input_field": "konteyner_sayisi",
                "unit_price": 50.0,
                "description": "Konteyner kullanım ücreti (50 $/konteyner)",
            },
            {
                "id": "r_doluluk_bonus",
                "type": "conditional_multiplier",
                "condition_field": "doluluk_oran",
                "operator": ">=",
                "threshold": 0.6,
                "multiplier": 0.95,
                "description": "Yüksek doluluk indirimi (%5)",
            },
            {
                "id": "r_min",
                "type": "min_clamp",
                "min_price": 200.0,
                "description": "Minimum parti fiyatı",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Yardımcı: hacim hesabı (cm3 → m3)
# ---------------------------------------------------------------------------

def _parts_volume_cm3(parts_list: List[Dict[str, Any]]) -> float:
    """Parça listesinden toplam hacmi cm3 cinsinden hesaplar."""
    total = 0.0
    for p in parts_list:
        if p.get("source") == "box":
            w = p.get("width_mm", 0.0)
            d = p.get("depth_mm", 0.0)
            h = p.get("height_mm", 0.0)
            qty = p.get("qty", 1)
            # mm3 → cm3: / 1000
            total += (w * d * h / 1000.0) * qty
    return total


# ---------------------------------------------------------------------------
# Yardımcı: NestingInstance + Bin3D kurucusu
# ---------------------------------------------------------------------------

def _build_nesting_instance(
    order_parts: List[Dict[str, Any]],
    container: Dict[str, Any],
) -> "NestingInstance":  # type: ignore[name-defined]  # noqa: F821
    """Sipariş parça listesinden NestingInstance oluşturur."""
    from src.nesting3d.instances.format import (
        ContainerSpec,
        NestingInstance,
        PartSpec,
    )

    container_spec = ContainerSpec(
        width_mm=float(container["width_mm"]),
        depth_mm=float(container["depth_mm"]),
        height_mm=container.get("height_mm"),
    )

    parts = []
    for p in order_parts:
        parts.append(
            PartSpec(
                id=p["id"],
                name=p["name"],
                qty=int(p["qty"]),
                source=p["source"],
                width_mm=p.get("width_mm"),
                depth_mm=p.get("depth_mm"),
                height_mm=p.get("height_mm"),
                stl_path=p.get("stl_path"),
            )
        )

    return NestingInstance(container=container_spec, parts=parts)


def _bin_factory(container: Dict[str, Any], pitch: float):
    """Bin3D fabrika fonksiyonu döndürür."""
    from src.nesting3d.bin3d import Bin3D

    def factory() -> Bin3D:
        return Bin3D(
            plate_w_mm=float(container["width_mm"]),
            plate_d_mm=float(container["depth_mm"]),
            pitch=pitch,
            z_clearance=1,
        )
    return factory


# ---------------------------------------------------------------------------
# Fiyat girdisi oluşturucu
# ---------------------------------------------------------------------------

def _build_pricing_inputs(
    batch_volume_cm3: float,
    height_mm: float,
    density: float,
    n_containers: int = 1,
) -> Dict[str, float]:
    """Nesting sonuçlarından fiyatlama girdisi dict'i üretir."""
    return {
        "hacim_m3": batch_volume_cm3 / 1_000_000.0,  # cm3 → m3
        "konteyner_sayisi": float(n_containers),
        "doluluk_oran": density,
        "mesafe_km": 0.0,   # demo: mesafe bilinmiyor
        "agirlik_kg": 0.0,  # demo: ağırlık bilinmiyor
    }


# ---------------------------------------------------------------------------
# Yardımcı: selection model zarif yükleme
# ---------------------------------------------------------------------------

def _load_selection_model_safe():
    """SELECTION_MODEL_PATH varsa (prefilter, model) yukle; yoksa (None, None).

    Zarif düşüş: dosya yoksa veya hata oluşursa sessizce (None, None) döner.
    Demo bu durumda selection tahminini gizler; tuner her zaman çalışır.
    """
    if not SELECTION_MODEL_PATH.exists():
        return None, None
    try:
        from src.nesting3d.selection.persistence import load_selection_model
        return load_selection_model(SELECTION_MODEL_PATH)
    except Exception:
        return None, None


def _predict_selection(
    prefilter,
    model,
    instance,
) -> Optional[Dict[str, Any]]:
    """Instance için selection tahmini üret.

    Zarif düşüş: prefilter/model None ise None döner.
    Dönüş: {"is_easy": bool, "predicted_winner": str, "explain": str} veya None.
    """
    if prefilter is None or model is None:
        return None
    try:
        from src.nesting3d.instances.features import extract_features
        from src.nesting3d.selection.selector import EASY_CONFIDENCE_THRESHOLD

        fv = extract_features(instance)
        features = fv.values

        is_easy, easy_conf = prefilter.predict(features)
        pf_explain = prefilter.explain()

        if is_easy and easy_conf >= EASY_CONFIDENCE_THRESHOLD:
            predicted_winner = "dblf"
            explain = f"KOLAY instance (prefilter guven={easy_conf:.1%}). {pf_explain}"
        else:
            solver_name, model_conf = model.predict(features)
            model_explain = model.explain()
            predicted_winner = solver_name
            explain = (
                f"ZOR instance; model tahmini={solver_name} "
                f"(guven={model_conf:.1%}). {model_explain}"
            )
        return {
            "is_easy": is_easy and easy_conf >= EASY_CONFIDENCE_THRESHOLD,
            "predicted_winner": predicted_winner,
            "explain": explain,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ana pipeline
# ---------------------------------------------------------------------------

def run_pipeline(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Sipariş havuzu → çizelgeleme → nesting → fiyatlama → rapor.

    Parametreler
    ------------
    scenario : senaryo dict (SCENARIO fixture formatında)

    Dönüş
    -----
    dict — ranked_orders, batches, warnings, nesting_results,
           pricing_results, elapsed_sec, report_path
    """
    from src.scheduling.models import Capacity, Order
    from src.scheduling.rules import PriorityConfig, rank_orders
    from src.scheduling.batcher import build_batches
    from src.scheduling.feasibility import check_feasibility
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.instances.pitch import suggest_pitch
    from src.nesting3d.tuner import tune as tuner_tune
    from src.pricing.schema import RuleSet
    from src.pricing.engine import PricingEngine

    t0 = time.perf_counter()
    today = scenario["ref_date"]
    container = scenario["container"]
    pitch_fallback = float(scenario.get("pitch", 15.0))
    n_orient = int(scenario.get("n_orientations", 4))
    seed = int(scenario.get("seed", 42))

    # Algoritma-seçim model zarif yükleme (model yoksa None, None)
    _sel_prefilter, _sel_model = _load_selection_model_safe()

    # --- 1. Sipariş nesnelerini kur + doğrula ---
    orders: List[Order] = []
    order_parts_map: Dict[str, List[Dict[str, Any]]] = {}

    for od in scenario["orders"]:
        parts_list = od.get("parts", [])
        vol_cm3 = _parts_volume_cm3(parts_list)

        o = Order(
            order_id=od["order_id"],
            customer=od["customer"],
            parts_ref=od["order_id"],
            total_quantity=sum(p.get("qty", 1) for p in parts_list),
            total_volume_cm3=vol_cm3,
            deadline=od["deadline"],
            priority_class=od["priority_class"],
        )
        o.validate(today)
        orders.append(o)
        order_parts_map[od["order_id"]] = parts_list

    cap_cfg = scenario["capacity"]
    capacity = Capacity(
        num_machines=int(cap_cfg["num_machines"]),
        batch_duration_hours=float(cap_cfg["batch_duration_hours"]),
        shifts_per_day=int(cap_cfg["shifts_per_day"]),
        max_volume_per_batch_cm3=cap_cfg.get("max_volume_per_batch_cm3"),
    )
    capacity.validate()

    # --- 2. Önceliklendirme + çizelgeleme ---
    config = PriorityConfig.default()
    ranked = rank_orders(orders, config, today)
    batches = build_batches(ranked, capacity, allow_mixing=False)
    warnings = check_feasibility(batches, capacity, today)

    # --- 3. Her parti için nesting + fiyatlama ---
    rule_set = RuleSet.from_dict(scenario["pricing_rules"])
    pricing_engine = PricingEngine(rule_set)

    nesting_results: Dict[str, Dict[str, Any]] = {}
    pricing_results: Dict[str, Dict[str, Any]] = {}
    batch_nesting_elapsed: Dict[str, float] = {}

    for batch in batches:
        # Parti parçalarını derle
        all_parts: List[Dict[str, Any]] = []
        for order in batch.orders:
            all_parts.extend(order_parts_map[order.order_id])

        if not all_parts:
            nesting_results[batch.batch_id] = {
                "height_mm": 0.0, "density": 0.0, "n_parts": 0,
                "elapsed_sec": 0.0, "note": "Parça yok",
                "portfolio": None, "tuner": None, "selection": None,
            }
            pricing_results[batch.batch_id] = {"total_price": 0.0, "breakdown": []}
            continue

        # NestingInstance kur
        instance = _build_nesting_instance(all_parts, container)

        # Adaptif pitch: instance'tan türet, fallback = senaryo değeri
        try:
            pitch = suggest_pitch(instance)
        except Exception:
            pitch = pitch_fallback

        # Algoritma-seçim tahmini (artefakt varsa; bilgilendirme amaçlı)
        selection_pred = _predict_selection(_sel_prefilter, _sel_model, instance)

        # Voxelize (adaptif pitch)
        t_nest_start = time.perf_counter()
        try:
            voxel_parts = to_voxel_parts(
                instance, pitch, n_orientations=n_orient, margin=0
            )
        except Exception as exc:
            nesting_results[batch.batch_id] = {
                "height_mm": 0.0, "density": 0.0, "n_parts": len(all_parts),
                "elapsed_sec": 0.0,
                "note": f"Voxelization hatasi: {exc}",
                "portfolio": None,
                "tuner": None,
                "selection": selection_pred,
            }
            pricing_results[batch.batch_id] = {"total_price": 0.0, "breakdown": []}
            continue

        # Instance-Tuner: TUNER_BUDGET ile portföy + menü konfigleri koşar
        factory = _bin_factory(container, pitch)
        try:
            tune_result = tuner_tune(
                voxel_parts,
                factory,
                budget=TUNER_BUDGET,
                seed=seed,
            )
        except Exception as exc:
            # Zarif düşüş: tuner başarısız → DBLF tek başına
            try:
                from src.nesting3d.dblf import dblf as _dblf
                _placements, bin3d = _dblf(voxel_parts, factory)
                t_nest_elapsed = time.perf_counter() - t_nest_start
                nesting_results[batch.batch_id] = {
                    "height_mm": bin3d.max_height_mm(),
                    "density": bin3d.packing_density(),
                    "n_parts": len(_placements),
                    "elapsed_sec": round(t_nest_elapsed, 3),
                    "note": f"Tuner hatasi (DBLF fallback): {exc}",
                    "portfolio": None,
                    "tuner": None,
                    "selection": selection_pred,
                }
            except Exception as exc2:
                nesting_results[batch.batch_id] = {
                    "height_mm": 0.0, "density": 0.0, "n_parts": len(voxel_parts),
                    "elapsed_sec": 0.0,
                    "note": f"Tuner hatasi: {exc}; DBLF fallback hatasi: {exc2}",
                    "portfolio": None,
                    "tuner": None,
                    "selection": selection_pred,
                }
                pricing_results[batch.batch_id] = {"total_price": 0.0, "breakdown": []}
                continue
            pricing_inputs = _build_pricing_inputs(
                batch_volume_cm3=batch.total_volume_cm3,
                height_mm=nesting_results[batch.batch_id]["height_mm"],
                density=nesting_results[batch.batch_id]["density"],
                n_containers=1,
            )
            try:
                p_result = pricing_engine.calculate(pricing_inputs)
                breakdown_lines = [str(line) for line in p_result.breakdown]
                pricing_results[batch.batch_id] = {
                    "total_price": p_result.total_price,
                    "breakdown": breakdown_lines,
                    "inputs": pricing_inputs,
                }
            except Exception as exc3:
                pricing_results[batch.batch_id] = {
                    "total_price": 0.0,
                    "breakdown": [f"Fiyatlama hatasi: {exc3}"],
                    "inputs": pricing_inputs,
                }
            batch_nesting_elapsed[batch.batch_id] = nesting_results[batch.batch_id]["elapsed_sec"]
            continue

        t_nest_elapsed = time.perf_counter() - t_nest_start
        winner_result = tune_result.result
        height_mm = winner_result.height_mm
        density = winner_result.density
        n_placed = len(winner_result.placements)
        winner_config = tune_result.winning_config_name
        baseline_height = tune_result.baseline_height_mm  # portföy (DBLF+SA+GA+Tabu) en iyisi

        # DBLF yüksekliğini bul: baseline konfigin içindeki DBLF sonucundan
        # Tuner all_results'ta "baseline" entry var; baseline = portföy winner.
        # Eski UI uyumu için dblf_height = baseline (portföy, yani eski karşılaştırma)
        dblf_height = baseline_height
        gain_pct = (
            (dblf_height - height_mm) / dblf_height * 100.0
            if dblf_height > 0
            else 0.0
        )

        # Tuner konfig kıyas verisi (her konfig için satır)
        tuner_rows = []
        for cfg_name, cfg_result in tune_result.all_results:
            is_win = cfg_result is winner_result
            cfg_gain = (
                (dblf_height - cfg_result.height_mm) / dblf_height * 100.0
                if dblf_height > 0
                else 0.0
            )
            tuner_rows.append({
                "config": cfg_name,
                "height_mm": round(cfg_result.height_mm, 2),
                "density": round(cfg_result.density, 4),
                "time_s": round(cfg_result.time_s, 3),
                "winner": is_win,
                "gain_pct": round(cfg_gain, 2),
            })

        # Geriye-uyum: "portfolio" anahtarını tuner baseline'dan sentetik olarak koru
        # (webapp/test uyumu; "rows" listesi tuner konfiglerinden üretilir)
        portfolio_data = {
            "winner": winner_config,
            "dblf_height_mm": round(dblf_height, 2),
            "gain_pct": round(gain_pct, 2),
            "table_md": "",
            "rows": tuner_rows,
        }

        nesting_results[batch.batch_id] = {
            "height_mm": height_mm,
            "density": density,
            "n_parts": n_placed,
            "elapsed_sec": round(t_nest_elapsed, 3),
            "note": "",
            "pitch_mm": round(pitch, 2),
            "portfolio": portfolio_data,
            "tuner": {
                "winning_config": winner_config,
                "baseline_height_mm": round(baseline_height, 2),
                "improvement_mm": round(tune_result.improvement_mm, 2),
                "gain_vs_baseline_pct": round(gain_pct, 2),
                "budget": TUNER_BUDGET,
                "configs_tried": len(tune_result.all_results),
                "rows": tuner_rows,
            },
            "selection": selection_pred,
            # 3D önizleme (gerçek geometri) için: webapp /geometri rotası bunları
            # build_result_scene'e geçirir. OBJE'ler — JSON'a girmez (pipeline_job
            # _make_serializable bu iki anahtarı çıkarır); yalnız in-memory webapp.
            "placements": winner_result.placements,
            "voxel_parts": {p.id: p for p in voxel_parts},
        }
        batch_nesting_elapsed[batch.batch_id] = t_nest_elapsed

        # Fiyatlama
        pricing_inputs = _build_pricing_inputs(
            batch_volume_cm3=batch.total_volume_cm3,
            height_mm=height_mm,
            density=density,
            n_containers=1,
        )
        try:
            p_result = pricing_engine.calculate(pricing_inputs)
            breakdown_lines = [str(line) for line in p_result.breakdown]
            pricing_results[batch.batch_id] = {
                "total_price": p_result.total_price,
                "breakdown": breakdown_lines,
                "inputs": pricing_inputs,
            }
        except Exception as exc:
            pricing_results[batch.batch_id] = {
                "total_price": 0.0,
                "breakdown": [f"Fiyatlama hatasi: {exc}"],
                "inputs": pricing_inputs,
            }

    elapsed_total = time.perf_counter() - t0

    # --- 4. Rapor oluştur ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / REPORT_FILENAME

    report_md = _build_report_markdown(
        today=today,
        ranked=ranked,
        batches=batches,
        warnings=warnings,
        nesting_results=nesting_results,
        pricing_results=pricing_results,
        elapsed_total=elapsed_total,
    )
    report_path.write_text(report_md, encoding="utf-8")

    # --- 5. Konsol özeti ---
    _print_console_summary(
        ranked=ranked,
        batches=batches,
        warnings=warnings,
        nesting_results=nesting_results,
        pricing_results=pricing_results,
        elapsed_total=elapsed_total,
    )

    return {
        "ranked_orders": ranked,
        "batches": batches,
        "warnings": warnings,
        "nesting_results": nesting_results,
        "pricing_results": pricing_results,
        "elapsed_sec": round(elapsed_total, 3),
        "report_path": str(report_path),
    }


# ---------------------------------------------------------------------------
# Rapor markdown oluşturucu
# ---------------------------------------------------------------------------

def _build_report_markdown(
    today: date,
    ranked: list,
    batches: list,
    warnings: list,
    nesting_results: Dict[str, Any],
    pricing_results: Dict[str, Any],
    elapsed_total: float,
) -> str:
    lines = []
    lines.append(f"# Demo Pipeline Raporu — {today.isoformat()}")
    lines.append("")
    lines.append(
        "> Bu rapor `scripts/demo_pipeline.py` tarafindan otomatik uretilmistir."
    )
    lines.append(
        f"> Toplam kosus suresi: **{elapsed_total:.2f} saniye**"
    )
    lines.append("")

    # --- Bölüm 1: Sipariş öncelik tablosu ---
    lines.append("## 1. Siparis Oncelik Tablosu")
    lines.append("")
    lines.append("| Sira | Siparis | Musteri | Termin | Oncelik | Hacim (cm3) |")
    lines.append("|------|---------|---------|--------|---------|-------------|")
    for i, o in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {o.order_id} | {o.customer} | {o.deadline} "
            f"| {o.priority_class} | {o.total_volume_cm3:.0f} |"
        )
    lines.append("")

    # --- Bölüm 2: Parti planı + termin/kapasite uyarıları ---
    lines.append("## 2. Parti Plani")
    lines.append("")
    lines.append("| Parti | Musteri | Siparisler | Hacim (cm3) | Asiri mi |")
    lines.append("|-------|---------|------------|-------------|----------|")
    for b in batches:
        order_ids = ", ".join(o.order_id for o in b.orders)
        lines.append(
            f"| {b.batch_id} | {b.customer} | {order_ids} "
            f"| {b.total_volume_cm3:.0f} | {'EVET' if b.oversized else 'Hayir'} |"
        )
    lines.append("")

    if warnings:
        lines.append("### Termin Uyarilari")
        lines.append("")
        lines.append("| Siparis | Termin | Tahmini Bitis | Gecikme (gun) | Parti |")
        lines.append("|---------|--------|---------------|---------------|-------|")
        for w in warnings:
            lines.append(
                f"| {w.order_id} | {w.deadline} | {w.estimated_completion} "
                f"| {w.delay_days} | {w.batch_id} |"
            )
        lines.append("")
    else:
        lines.append("_Termin asimi uyarisi yok._")
        lines.append("")

    # --- Bölüm 3: Nesting sonuçları ---
    lines.append("## 3. Nesting Sonuclari")
    lines.append("")
    lines.append(
        "| Parti | Pitch (mm) | Yukseklik (mm) | Doluluk (%) | Parca | Sure (s) | Kazanan | DBLF'ye Kazanc% | Not |"
    )
    lines.append(
        "|-------|------------|----------------|-------------|-------|----------|---------|-----------------|-----|"
    )
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        h = nr.get("height_mm", 0.0)
        d = nr.get("density", 0.0)
        n = nr.get("n_parts", 0)
        t = nr.get("elapsed_sec", 0.0)
        note = nr.get("note", "")
        pitch_mm = nr.get("pitch_mm", "-")
        port = nr.get("portfolio") or {}
        winner_name = port.get("winner", "dblf")
        gain_pct = port.get("gain_pct", 0.0)
        lines.append(
            f"| {b.batch_id} | {pitch_mm} | {h:.1f} | {d * 100:.1f} "
            f"| {n} | {t:.2f} | {winner_name} | {gain_pct:.1f}% | {note} |"
        )
    lines.append("")

    # --- Bölüm 3b: Instance-Tuner konfig kıyas tabloları ---
    lines.append("## 3b. Instance-Tuner Konfig Kiyasi")
    lines.append("")
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        tuner_data = nr.get("tuner")
        if not tuner_data:
            port = nr.get("portfolio")
            if not port:
                lines.append(f"### Parti {b.batch_id}: tuner verisi yok")
                lines.append("")
                continue
            # Eski format / fallback
            lines.append(f"### Parti {b.batch_id} — {b.customer}")
            lines.append(f"**Kazanan: `{port.get('winner','?')}` (fallback)**")
            lines.append("")
            continue
        winner_cfg = tuner_data.get("winning_config", "?")
        baseline_h = tuner_data.get("baseline_height_mm", 0.0)
        improvement = tuner_data.get("improvement_mm", 0.0)
        gain = tuner_data.get("gain_vs_baseline_pct", 0.0)
        n_configs = tuner_data.get("configs_tried", 0)
        budget = tuner_data.get("budget", 0)
        lines.append(f"### Parti {b.batch_id} — {b.customer}")
        lines.append(
            f"**Kazanan konfig: `{winner_cfg}` | "
            f"Portfoy baseline: {baseline_h:.2f} mm | "
            f"Kazanc: {improvement:.2f} mm ({gain:.1f}%) | "
            f"Denenen konfig: {n_configs} x budget={budget}**"
        )
        lines.append("")
        # Konfig kıyas tablosu
        rows = tuner_data.get("rows", [])
        if rows:
            lines.append("| Konfig | Yukseklik (mm) | Doluluk | Sure (s) | Baseline'a Kazanc% | Sonuc |")
            lines.append("|--------|----------------|---------|----------|---------------------|-------|")
            for row in rows:
                win_mark = "KAZANDI" if row.get("winner") else ""
                cfg_gain = row.get("gain_pct", 0.0)
                gain_str = f"+{cfg_gain:.1f}%" if cfg_gain > 0.01 else "0%"
                lines.append(
                    f"| {row['config']} | {row['height_mm']:.2f} | "
                    f"{row['density'] * 100:.1f}% | {row['time_s']:.3f} | "
                    f"{gain_str} | {win_mark} |"
                )
        lines.append("")

    # --- Bölüm 3c: Algoritma-seçim tahmini ---
    has_selection = any(
        nesting_results.get(b.batch_id, {}).get("selection") is not None
        for b in batches
    )
    if has_selection:
        lines.append("## 3c. Algoritma-Secim Tahmini (Bilgilendirme)")
        lines.append("")
        lines.append(
            "> NOT: Tahmin yalnizca bilgilendirme icin gosterilir. "
            "Cozum her zaman Instance-Tuner'dan gelir."
        )
        lines.append("")
        for b in batches:
            nr = nesting_results.get(b.batch_id, {})
            sel = nr.get("selection")
            if sel is None:
                continue
            is_easy_str = "KOLAY" if sel.get("is_easy") else "ZOR"
            predicted = sel.get("predicted_winner", "?")
            explain = sel.get("explain", "")
            lines.append(f"**{b.batch_id} ({b.customer})**: {is_easy_str} — "
                         f"tahmin={predicted}")
            if explain:
                lines.append(f"  _{explain}_")
            lines.append("")

    # --- Bölüm 4: Fiyat dökümü ---
    lines.append("## 4. Fiyat Dokumu")
    lines.append("")
    for b in batches:
        pr = pricing_results.get(b.batch_id, {})
        total = pr.get("total_price", 0.0)
        lines.append(f"### Parti {b.batch_id} — {b.customer}")
        lines.append("")
        lines.append(f"**Toplam Fiyat: {total:.2f} $**")
        lines.append("")
        for line_str in pr.get("breakdown", []):
            lines.append(f"- {line_str}")
        lines.append("")

    # --- Bölüm 5: Özet ---
    lines.append("## 5. Ozet")
    lines.append("")
    total_revenue = sum(
        pr.get("total_price", 0.0) for pr in pricing_results.values()
    )
    total_nesting_time = sum(
        nr.get("elapsed_sec", 0.0) for nr in nesting_results.values()
    )
    lines.append(f"| Metrik | Deger |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Toplam Ciro Onerisi | {total_revenue:.2f} $ |")
    lines.append(f"| Toplam Pipeline Suresi | {elapsed_total:.2f} s |")
    lines.append(f"| Toplam Nesting Suresi | {total_nesting_time:.2f} s |")
    lines.append(f"| Siparis Sayisi | {len(ranked)} |")
    lines.append(f"| Parti Sayisi | {len(batches)} |")
    lines.append(f"| Uyari Sayisi | {len(warnings)} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Konsol özeti
# ---------------------------------------------------------------------------

def _print_console_summary(
    ranked: list,
    batches: list,
    warnings: list,
    nesting_results: Dict[str, Any],
    pricing_results: Dict[str, Any],
    elapsed_total: float,
) -> None:
    sep = "=" * 72
    print(sep)
    print("DEMO PIPELINE OZETI")
    print(sep)
    print(f"Siparis sayisi   : {len(ranked)}")
    print(f"Parti sayisi     : {len(batches)}")
    print(f"Uyari sayisi     : {len(warnings)}")
    print()

    print("--- Oncelik Sirasi (ilk 5) ---")
    for i, o in enumerate(ranked[:5], 1):
        print(f"  {i}. {o.order_id:20s} termin={o.deadline}  oncelik={o.priority_class}")
    if len(ranked) > 5:
        print(f"  ... ve {len(ranked) - 5} siparis daha")
    print()

    total_rev = 0.0
    print("--- Parti Ozeti (Instance-Tuner) ---")
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        pr = pricing_results.get(b.batch_id, {})
        h = nr.get("height_mm", 0.0)
        d = nr.get("density", 0.0)
        price = pr.get("total_price", 0.0)
        total_rev += price
        tuner_data = nr.get("tuner") or {}
        winner_cfg = tuner_data.get("winning_config", nr.get("portfolio", {}) and nr["portfolio"].get("winner", "?") or "?")
        gain_pct = tuner_data.get("gain_vs_baseline_pct", 0.0)
        improvement_mm = tuner_data.get("improvement_mm", 0.0)
        gain_str = f" | kazanc={improvement_mm:.2f}mm ({gain_pct:.1f}%)" if gain_pct > 0.01 else ""
        sel = nr.get("selection")
        sel_str = ""
        if sel is not None:
            easy_tag = "kolay" if sel.get("is_easy") else "zor"
            sel_str = f" | secim-tahmin={sel.get('predicted_winner','?')}({easy_tag})"
        print(
            f"  {b.batch_id}: {b.customer:12s} | "
            f"yukseklik={h:.1f}mm | doluluk={d * 100:.1f}% | "
            f"kazanan-konfig={winner_cfg}{gain_str}{sel_str} | fiyat={price:.2f}$"
        )
    print()
    print(f"Toplam ciro onerisi : {total_rev:.2f} $")
    print(f"Pipeline suresi     : {elapsed_total:.2f} s")
    print(f"Tuner budget        : {TUNER_BUDGET} iter/konfig")
    print(sep)


# ---------------------------------------------------------------------------
# Doğrudan çalıştırma
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse as _argparse
    _ap = _argparse.ArgumentParser(description="Demo pipeline")
    _ap.add_argument(
        "--scenario", choices=["standard", "rich"], default="rich",
        help="Senaryo secimi: 'standard' (5 siparis) veya 'rich' (yogun, 3 siparis ~20 parca)",
    )
    _args = _ap.parse_args()
    _scenario = RICH_SCENARIO if _args.scenario == "rich" else SCENARIO
    result = run_pipeline(_scenario)
    print(f"\nRapor: {result['report_path']}")

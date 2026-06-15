"""src/runtime/pipeline_job.py — Demo pipeline'i job handler olarak sarar.

PLAN_SERVIS §9 madde 1+2: motor saf kalir (nesting3d'ye dokunulmaz),
pipeline sonucu JSON-serileştirilebilir dict olarak dondurulur.

Handler sozlesmesi (queue.py)
------------------------------
  pipeline_handler(job: Job) -> Dict[str, Any]

Job payload sozdizimi
---------------------
  {
    "scenario": { ... }   # scripts/demo_pipeline.SCENARIO formatinda
  }
  Eger "scenario" anahtari yoksa varsayilan SCENARIO fixture kullanilir.

Sonuc sozlugundeki ozel anahtarlar
-----------------------------------
  "_needs_approval" : True -> SynchronousQueue job'u AWAITING_APPROVAL'a alir.
                      Bu demo'da her basarili pipeline kullanici onayi ister
                      (PLAN_SERVIS §0 madde 6 — insan onay kapisı).

JSON-serileştirilebilirlik
--------------------------
  ranked_orders ve batches dogrudan JSON'a alınamaz (dataclass nesneleri).
  Bu sarici bunlari sozluklere cevirir (to_dict() veya manuel).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# Proje koku sys.path'e ekle (direkt cagirma senaryolari icin)
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.jobs import Job


# ---------------------------------------------------------------------------
# Serilestirme yardimcilari
# ---------------------------------------------------------------------------

def _serialize_order(o: Any) -> Dict[str, Any]:
    """Order nesnesini JSON-serileştirilebilir dict'e cevirir."""
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return {
        "order_id": getattr(o, "order_id", str(o)),
        "customer": getattr(o, "customer", ""),
        "deadline": str(getattr(o, "deadline", "")),
        "priority_class": getattr(o, "priority_class", 0),
        "total_volume_cm3": getattr(o, "total_volume_cm3", 0.0),
    }


def _serialize_batch(b: Any) -> Dict[str, Any]:
    """Batch nesnesini JSON-serileştirilebilir dict'e cevirir."""
    orders_serial = [_serialize_order(o) for o in getattr(b, "orders", [])]
    return {
        "batch_id": getattr(b, "batch_id", str(b)),
        "customer": getattr(b, "customer", ""),
        "orders": orders_serial,
        "total_volume_cm3": getattr(b, "total_volume_cm3", 0.0),
        "oversized": getattr(b, "oversized", False),
    }


def _serialize_warning(w: Any) -> Dict[str, Any]:
    """FeasibilityWarning nesnesini dict'e cevirir."""
    if hasattr(w, "to_dict"):
        return w.to_dict()
    return {
        "order_id": getattr(w, "order_id", str(w)),
        "deadline": str(getattr(w, "deadline", "")),
        "estimated_completion": str(getattr(w, "estimated_completion", "")),
        "delay_days": getattr(w, "delay_days", 0),
        "batch_id": getattr(w, "batch_id", ""),
    }


def _make_serializable(result: Dict[str, Any]) -> Dict[str, Any]:
    """run_pipeline() ciktisini tamamen JSON-serileştirilebilir yapar."""
    ranked = result.get("ranked_orders", [])
    batches = result.get("batches", [])
    warnings = result.get("warnings", [])
    # nesting_results 3D-önizleme için OBJE anahtarları taşıyabilir (placements,
    # voxel_parts) — JSON-serileştirilemez; çıkar (yalnız in-memory webapp kullanır).
    _GEOM_KEYS = ("placements", "voxel_parts")
    nr_clean = {}
    for bid, nr in result.get("nesting_results", {}).items():
        if not isinstance(nr, dict):
            continue
        nr_clean[bid] = {k: v for k, v in nr.items() if k not in _GEOM_KEYS}
    return {
        "ranked_orders": [_serialize_order(o) for o in ranked],
        "batches": [_serialize_batch(b) for b in batches],
        "warnings": [_serialize_warning(w) for w in warnings],
        "nesting_results": nr_clean,
        "pricing_results": result.get("pricing_results", {}),
        "elapsed_sec": result.get("elapsed_sec", 0.0),
        "report_path": result.get("report_path", ""),
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def pipeline_handler(job: Job) -> Dict[str, Any]:
    """Demo pipeline'i job handler olarak calistirir.

    - job.payload["scenario"] varsa onu kullanir; yoksa varsayilan SCENARIO.
    - Sonucu JSON-serileştirilebilir yapar.
    - "_needs_approval": True ile doner -> SynchronousQueue AWAITING_APPROVAL'a alir.
    - Motor nesting3d'ye dokunulmaz (saf read-only cagri).
    """
    from scripts.demo_pipeline import run_pipeline, SCENARIO

    scenario = job.payload.get("scenario", SCENARIO)
    raw_result = run_pipeline(scenario)
    serializable = _make_serializable(raw_result)
    serializable["_needs_approval"] = True  # PLAN_SERVIS §0 madde 6
    return serializable

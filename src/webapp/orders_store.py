"""orders_store.py — Kalici siparis havuzu yardimci modulu.

Depolama: data/orders.json (varsayilan) — her create_app() cagrisi
          orders_path parametresi ile override edilebilir (test izolasyonu).

Veri formati:
    [
        {
            "order_id": "ORD-001",
            "customer": "MUSTERI",
            "deadline": "2027-01-15",
            "priority_class": 1,
            "parts": [
                {
                    "name": "parca_adi",
                    "width_mm": 50.0,
                    "depth_mm": 40.0,
                    "height_mm": 30.0,
                    "qty": 2
                }
            ]
        },
        ...
    ]

Atomik yazim: tmp + rename (ayni dizin icinde; Windows'ta os.replace).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Varsayilan veri dosyasi
_DEFAULT_ORDERS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "orders.json"
)

# Pipeline icin kullanilan sabit konteyner/kapasite/fiyat konfigurasyonu
_DEFAULT_CONTAINER = {
    "width_mm": 335.0,
    "depth_mm": 250.0,
}

_DEFAULT_CAPACITY = {
    "num_machines": 1,
    "batch_duration_hours": 8.0,
    "shifts_per_day": 1,
    "max_volume_per_batch_cm3": 25_000.0,
}

_DEFAULT_PRICING_RULES = {
    "version": "1.0",
    "name": "Demo kural seti v1",
    "rules": [
        {
            "id": "r_volume",
            "type": "unit_price",
            "input_field": "hacim_m3",
            "unit_price": 8000.0,
            "description": "Hacim bazli birim fiyat (8000 $/m3)",
        },
        {
            "id": "r_konteyner",
            "type": "unit_price",
            "input_field": "konteyner_sayisi",
            "unit_price": 50.0,
            "description": "Konteyner kullanim ucreti (50 $/konteyner)",
        },
        {
            "id": "r_doluluk_bonus",
            "type": "conditional_multiplier",
            "condition_field": "doluluk_oran",
            "operator": ">=",
            "threshold": 0.6,
            "multiplier": 0.95,
            "description": "Yuksek doluluk indirimi (%5)",
        },
        {
            "id": "r_min",
            "type": "min_clamp",
            "min_price": 200.0,
            "description": "Minimum parti fiyati",
        },
    ],
}


# ---------------------------------------------------------------------------
# Yukle / Kaydet
# ---------------------------------------------------------------------------


def load_orders(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """JSON dosyasindan siparis listesini yukler.

    Dosya yoksa bos liste doner.
    Dosya bozuksa ValueError firlatir.

    Parametreler
    ------------
    path : Path | None
        Veri dosyasi yolu. None ise varsayilan kullanilir.
    """
    target = Path(path) if path is not None else _DEFAULT_ORDERS_PATH
    if not target.exists():
        return []
    try:
        text = target.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Kok eleman liste olmali.")
        return data
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Siparis havuzu dosyasi bozuk ({target}): {exc}"
        ) from exc


def save_orders(orders: List[Dict[str, Any]], path: Optional[Path] = None) -> None:
    """Siparis listesini JSON dosyasina atomik olarak yazar (tmp + rename).

    Parametreler
    ------------
    orders : siparis dict listesi
    path   : hedef dosya yolu; None ise varsayilan kullanilir.
    """
    target = Path(path) if path is not None else _DEFAULT_ORDERS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(orders, ensure_ascii=False, indent=2)

    # Atomik yazim: ayni dizinde gecici dosya olustur, sonra rename
    dir_path = target.parent
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dir_path), prefix=".orders_tmp_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(target))
    except Exception:
        # Gecici dosyayi temizle
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def add_order(order: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Havuza yeni siparis ekler.

    Ayni order_id zaten varsa ValueError firlatir.
    """
    target = Path(path) if path is not None else _DEFAULT_ORDERS_PATH
    orders = load_orders(target)
    existing_ids = {o["order_id"] for o in orders}
    if order["order_id"] in existing_ids:
        raise ValueError(
            f"order_id zaten mevcut: {order['order_id']}"
        )
    orders.append(order)
    save_orders(orders, target)


def delete_order(order_id: str, path: Optional[Path] = None) -> None:
    """Havuzdan siparis siler.

    order_id bulunamazsa ValueError firlatir.
    """
    target = Path(path) if path is not None else _DEFAULT_ORDERS_PATH
    orders = load_orders(target)
    new_orders = [o for o in orders if o["order_id"] != order_id]
    if len(new_orders) == len(orders):
        raise ValueError(f"Siparis bulunamadi: {order_id}")
    save_orders(new_orders, target)


# ---------------------------------------------------------------------------
# Havuz -> senaryo donusuumu (pipeline icin)
# ---------------------------------------------------------------------------


def orders_to_scenario(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Havuz siparis listesini run_pipeline() senaryo formatina donusturur.

    Her siparisteki parts listesi, demo_pipeline beklentisine uygun
    bicime getirilir:
        - source: "box" eklenir
        - id: "{order_id}_{part_name}_{index}" seklinde uretilir

    Doner
    -----
    dict — SCENARIO formatiyla uyumlu; ref_date bugun; seed=42;
           container, capacity, pricing_rules varsayilan degerlerle.
    """
    today = date.today()
    scenario_orders = []

    for order in orders:
        parts_raw = order.get("parts", [])
        parts = []
        for idx, p in enumerate(parts_raw):
            name = p.get("name", f"parca_{idx}")
            part_id = f"{order['order_id']}_{name}_{idx}"
            parts.append({
                "id": part_id,
                "name": name,
                "qty": int(p.get("qty", 1)),
                "source": "box",
                "width_mm": float(p.get("width_mm", 0.0)),
                "depth_mm": float(p.get("depth_mm", 0.0)),
                "height_mm": float(p.get("height_mm", 0.0)),
            })

        scenario_orders.append({
            "order_id": order["order_id"],
            "customer": order["customer"],
            "deadline": order["deadline"],
            "priority_class": int(order.get("priority_class", 2)),
            "parts": parts,
        })

    return {
        "ref_date": today,
        "seed": 42,
        "capacity": _DEFAULT_CAPACITY,
        "container": _DEFAULT_CONTAINER,
        "pitch": 15.0,
        "n_orientations": 4,
        "orders": scenario_orders,
        "pricing_rules": _DEFAULT_PRICING_RULES,
    }


# ---------------------------------------------------------------------------
# Form metin parser (manuel siparis girisi)
# ---------------------------------------------------------------------------


def parse_parts_text(parts_text: str) -> tuple[list, list]:
    """Cok satirli parca metnini parse eder.

    Her satir formati: "ad, genislik, derinlik, yukseklik, adet"
    Bos satirlar atlanir.

    Doner
    -----
    (parts, errors) — gecerli parca listesi + (satir_no, mesaj) hata listesi.
    """
    parts = []
    errors = []
    for line_no, raw_line in enumerate(parts_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        cols = [c.strip() for c in line.split(",")]
        if len(cols) != 5:
            errors.append((line_no, f"5 sutun bekleniyor (ad, gen, der, yuk, adet); {len(cols)} bulundu"))
            continue
        name_val, w_str, d_str, h_str, qty_str = cols
        if not name_val:
            errors.append((line_no, "Parca adi bos olamaz"))
            continue
        try:
            w = float(w_str)
            d = float(d_str)
            h = float(h_str)
            qty = int(qty_str)
        except ValueError:
            errors.append((line_no, "Sayisal deger gecersiz (genislik/derinlik/yukseklik/adet)"))
            continue
        if w <= 0 or d <= 0 or h <= 0 or qty <= 0:
            errors.append((line_no, "Boyutlar ve adet sifirdan buyuk olmali"))
            continue
        parts.append({
            "name": name_val,
            "width_mm": w,
            "depth_mm": d,
            "height_mm": h,
            "qty": qty,
        })
    return parts, errors


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------


def parse_csv_upload(
    csv_text: str,
    existing_ids: set,
) -> tuple[list, list]:
    """CSV metnini parse eder; ayni order_id'li satirlari gruplayarak siparis uretir.

    Kolonlar (baslik satiri zorunlu):
        order_id, customer, deadline, priority,
        part_name, width_mm, depth_mm, height_mm, qty

    Parametreler
    ------------
    csv_text    : CSV dosyasi icerigi (str)
    existing_ids: mevcut havuzdaki order_id'leri (cakisma kontrolu icin)

    Doner
    -----
    (orders, errors) — gecerli siparis listesi + (satir_no, mesaj) hata listesi.
    Hatalı satirlar atlanir; gecerli satirlar eklenir.
    """
    import csv as _csv

    REQUIRED_COLS = {
        "order_id", "customer", "deadline", "priority",
        "part_name", "width_mm", "depth_mm", "height_mm", "qty",
    }

    orders_map: Dict[str, Dict[str, Any]] = {}
    errors: list = []

    reader = _csv.DictReader(csv_text.splitlines())
    if reader.fieldnames is None:
        return [], [(0, "CSV bos veya baslik satiri eksik")]

    missing = REQUIRED_COLS - set(f.strip() for f in (reader.fieldnames or []))
    if missing:
        return [], [(0, f"Eksik kolonlar: {', '.join(sorted(missing))}")]

    for line_no, row in enumerate(reader, start=2):
        order_id = (row.get("order_id") or "").strip()
        customer = (row.get("customer") or "").strip()
        deadline = (row.get("deadline") or "").strip()
        priority_str = (row.get("priority") or "").strip()
        part_name = (row.get("part_name") or "").strip()
        w_str = (row.get("width_mm") or "").strip()
        d_str = (row.get("depth_mm") or "").strip()
        h_str = (row.get("height_mm") or "").strip()
        qty_str = (row.get("qty") or "").strip()

        if not order_id:
            errors.append((line_no, "order_id bos"))
            continue
        if not customer:
            errors.append((line_no, "customer bos"))
            continue
        if not deadline:
            errors.append((line_no, "deadline bos"))
            continue

        try:
            priority = int(priority_str)
        except ValueError:
            errors.append((line_no, f"priority gecersiz: '{priority_str}'"))
            continue

        if not part_name:
            errors.append((line_no, "part_name bos"))
            continue

        try:
            w = float(w_str)
            d = float(d_str)
            h = float(h_str)
            qty = int(qty_str)
        except ValueError:
            errors.append((line_no, "Sayisal deger gecersiz (width/depth/height/qty)"))
            continue

        if w <= 0 or d <= 0 or h <= 0 or qty <= 0:
            errors.append((line_no, "Boyutlar ve adet sifirdan buyuk olmali"))
            continue

        part = {
            "name": part_name,
            "width_mm": w,
            "depth_mm": d,
            "height_mm": h,
            "qty": qty,
        }

        if order_id not in orders_map:
            if order_id in existing_ids:
                errors.append((line_no, f"order_id zaten mevcut: {order_id}"))
                continue
            orders_map[order_id] = {
                "order_id": order_id,
                "customer": customer,
                "deadline": deadline,
                "priority_class": priority,
                "parts": [part],
            }
        else:
            orders_map[order_id]["parts"].append(part)

    return list(orders_map.values()), errors

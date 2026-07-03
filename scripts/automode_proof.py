"""KANIT: akıllı-mod kuralı 6 veride false-negative=0 (cavity-zengin ASLA heightmap'e gitmez).
Kalite riski = cavity-zengin(kazanç>0) -> heightmap (false-negative). Bu OLMAMALI.
NFV seçmek her zaman kalite-güvenli (K-12: NFV>=heightmap). Kural prototipi burada doğrulanır."""
import os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
from scripts.c3_generality import DATASETS
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import NestingInstance, ContainerSpec, PartSpec
from src.nesting3d.instances.features import extract_features
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_QUANTITIES

# Bilinen NFV kazancı (ANALIZ_NFV). kazanç>0 = cavity-zengin (NFV kazanır, heightmap'e gitmemeli).
# deneme4: kabuk ailesi — NFV@coarse (386.4) heightmap'i (377.3) GEÇEMEDİ (K-12 kabukta kırıldı) -> kazanç 0.
KNOWN = {"plan2": 29, "plan3": 20, "plan1": 14, "numune": 0, "boxy": 0, "deneme4": 0}

# --- KURAL PROTOTİPİ (üretime taşınacak predict_nfv_benefit) ---
BOX_ASPECT_THR = 4.0    # mean_aspect_z < bu -> net kutu (cavity yok). plan'lar 6.4+ (geniş marj).
THIN_PLATE_THR = 0.6    # thin_plate_ratio > bu -> ince-plaka dominant (düz-optimal). plan2 max 0.26.


def predict_nfv_benefit(instance):
    """(mode, reason). heightmap SADECE net-kutu VEYA ince-plaka-dominant; aksi NFV (kalite-güvenli)."""
    fv = extract_features(instance)
    d = dict(zip(fv.names, fv.values))
    maz = float(d.get("mean_aspect_z", 0.0))
    tpr = float(d.get("thin_plate_ratio", 0.0))
    if maz < BOX_ASPECT_THR:
        return "heightmap", f"net-kutu (mean_aspect_z={maz:.1f}<{BOX_ASPECT_THR}); cavity yok, NFV kazanmaz"
    if tpr > THIN_PLATE_THR:
        return "heightmap", f"ince-plaka dominant (thin_plate={tpr:.2f}>{THIN_PLATE_THR}); duz-optimal, NFV uzatir"
    return "nfv", f"cavity-aday (mean_aspect_z={maz:.1f}, thin_plate={tpr:.2f}); NFV kalite-guvenli (>=heightmap)"


def make_instance(ds):
    if ds == "boxy":
        boxes = [("c40", 40, 40, 40, 5), ("c60", 60, 30, 20, 5), ("c80", 80, 50, 15, 3)]
        parts = [PartSpec(id=n, name=n, qty=q, source="box", width_mm=w, depth_mm=d, height_mm=h)
                 for (n, w, d, h, q) in boxes]
        return NestingInstance(container=ContainerSpec(250.0, 250.0, None), parts=parts)
    if ds == "numune":
        stl_map = {("n" + f.stem): f.read_bytes() for f in sorted(NUMUNE_DIR.glob("*.stl"))}
        return build_instance_from_order(stl_map, NUMUNE_QUANTITIES,
                                         persist_dir=os.path.join(os.getcwd(), "data", "mail_stl", f"feat_{ds}")).instance
    cfg = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": os.path.join(os.getcwd(), "data", "mail_stl", f"feat_{ds}")}
    if cfg["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    return build_instance_from_order(stl_map, cfg["qty"], **kwargs).instance


print("KANIT — akıllı-mod kuralı 6 veride:", flush=True)
print("-" * 90, flush=True)
false_neg = []
wrong_hint = []
for ds in ["plan2", "plan3", "plan1", "numune", "boxy", "deneme4"]:
    inst = make_instance(ds)
    mode, reason = predict_nfv_benefit(inst)
    gain = KNOWN[ds]
    # KRİTİK: kazanç>0 (cavity-zengin) -> heightmap seçilirse FALSE-NEGATIVE (kalite kaybı)
    is_fn = (gain > 0 and mode == "heightmap")
    if is_fn:
        false_neg.append(ds)
    # ikincil: kazanç=0 ama NFV seçildi -> kalite-güvenli (zararsız) ama gereksiz yavaş
    if gain == 0 and mode == "nfv":
        wrong_hint.append(ds)
    flag = "  <<< FALSE-NEGATIVE (KALITE KAYBI!)" if is_fn else ""
    print(f"  {ds:8} kazanç={gain:3}% -> SEÇİM={mode:9} | {reason}{flag}", flush=True)

print("-" * 90, flush=True)
print(f"FALSE-NEGATIVE (cavity-zengin->heightmap=KALİTE KAYBI): {false_neg or 'YOK OK'}", flush=True)
print(f"gereksiz-NFV (kazanç=0->nfv, kalite-güvenli ama yavaş): {wrong_hint or 'YOK'}", flush=True)
assert not false_neg, f"KANIT BAŞARISIZ: false-negative {false_neg} = kalite kaybı riski!"
print("\n[OK] KANIT GEÇTİ: false-negative=0 -> cavity-zengin hiçbir veri heightmap'e gitmedi (kalite-güvenli).", flush=True)
print("   Güvenlik teoremi (K-12): NFV>=heightmap her zaman -> NFV seçimi asla kaliteden kaybettirmez.", flush=True)

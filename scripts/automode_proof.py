"""KANIT: akilli-mod kurali (F5 aile-farkinda v2) 6 veride false-negative=0.

Kalite riski = cavity-zengin (kazanc>0) -> heightmap (false-negative). Bu OLMAMALI.
NFV secmek cavity-DISI her zaman kalite-guvenli (K-12: NFV>=heightmap). URETIM
predict_nfv_benefit (src/nesting3d/adaptive_params.py) burada gercek-veride dogrulanir.

F5 v2 (2026-07-04): kural sirasinin BASINA aile katmani eklendi. Kabuk ailesi
(thin_shell/tube) + guven>=WALL_AWARE_CONF_THRESHOLD -> heightmap + wall_aware onerisi.
=> deneme4 ince-kabuk artik "net-kutu" DEGIL "kabuk" gerekcesiyle heightmap'e gider
   (K-19: NFV-max@kaba 386.4 > heightmap@cidar-pitch 282.0 -> K-12 kabukta gecersiz).
Diger 5 set icin MOD DEGISMEZ (aile katmani tetiklemez; guven<esik) -> false-negative=0 korunur.

NOT: bu kanit OPT-IN aile-katmani (v2) davranisini olcer -> predict_nfv_benefit
family_routing=True ile cagrilir. Default (family_routing=False) = v1 (aile katmani
kapali, deneme4 "net-kutu" gerekcesiyle heightmap; asimetri yok, F5 asama 1).
"""
import os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
from scripts.c3_generality import DATASETS
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import NestingInstance, ContainerSpec, PartSpec
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_QUANTITIES
# URETIM karar fonksiyonu (prototip degil — gercek kod burada dogrulanir).
from src.nesting3d.adaptive_params import predict_nfv_benefit

# Bilinen NFV kazanci (ANALIZ_NFV). kazanc>0 = cavity-zengin (NFV kazanir, heightmap'e gitmemeli).
# deneme4: kabuk ailesi — NFV@coarse (386.4) heightmap@cidar-pitch'i (282.0) GECEMEDI
#          (K-12 kabukta kirildi, K-19) -> kazanc 0; DOGRU yol cidar-duyarli heightmap.
KNOWN = {"plan2": 29, "plan3": 20, "plan1": 14, "numune": 0, "boxy": 0, "deneme4": 0}


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


print("KANIT — akilli-mod kurali (F5 aile-farkinda v2) 6 veride:", flush=True)
print("-" * 100, flush=True)
false_neg = []
wrong_hint = []
deneme4_reason = None
deneme4_wall_aware = None
for ds in ["plan2", "plan3", "plan1", "numune", "boxy", "deneme4"]:
    inst = make_instance(ds)
    dec = predict_nfv_benefit(inst, family_routing=True)  # opt-in v2 kaniti; default=v1
    mode, reason = dec.mode, dec.reason
    wall_aware = getattr(dec, "wall_aware", False)
    gain = KNOWN[ds]
    # KRITIK: kazanc>0 (cavity-zengin) -> heightmap secilirse FALSE-NEGATIVE (kalite kaybi)
    is_fn = (gain > 0 and mode == "heightmap")
    if is_fn:
        false_neg.append(ds)
    # ikincil: kazanc=0 ama NFV secildi -> kalite-guvenli (zararsiz) ama gereksiz yavas
    if gain == 0 and mode == "nfv":
        wrong_hint.append(ds)
    if ds == "deneme4":
        deneme4_reason = reason
        deneme4_wall_aware = wall_aware
    flag = "  <<< FALSE-NEGATIVE (KALITE KAYBI!)" if is_fn else ""
    wa = "  [wall_aware]" if wall_aware else ""
    print(f"  {ds:8} kazanc={gain:3}% -> SECIM={mode:9}{wa} | {reason}{flag}", flush=True)

print("-" * 100, flush=True)
print(f"FALSE-NEGATIVE (cavity-zengin->heightmap=KALITE KAYBI): {false_neg or 'YOK OK'}", flush=True)
print(f"gereksiz-NFV (kazanc=0->nfv, kalite-guvenli ama yavas): {wrong_hint or 'YOK'}", flush=True)

# Beklenen modlar (F5 v2): plan1/2/3->nfv, numune/boxy->heightmap, deneme4->heightmap+wall_aware.
assert not false_neg, f"KANIT BASARISIZ: false-negative {false_neg} = kalite kaybi riski!"

# F5 v2 asil kaniti: deneme4 gerekcesi artik "net-kutu" DEGIL "kabuk" (dogru mekanizma)
# + wall_aware onerisi (cidar-pitch yolu). Mod ayni (heightmap) ama gerekce DUZELDI.
assert deneme4_reason is not None, "deneme4 karari alinamadi"
assert "kabuk" in deneme4_reason.lower(), \
    f"F5 BASARISIZ: deneme4 gerekcesi kabuk-ailesi DEGIL: {deneme4_reason}"
assert "net-kutu" not in deneme4_reason.lower(), \
    f"F5 BASARISIZ: deneme4 hala 'net-kutu' (yanlis gerekce): {deneme4_reason}"
assert deneme4_wall_aware is True, \
    f"F5 BASARISIZ: deneme4 wall_aware onerisi eksik (cidar-pitch yolu isaretlenmeli)"

print("\n[OK] KANIT GECTI: false-negative=0 -> cavity-zengin hicbir veri heightmap'e gitmedi.", flush=True)
print("[OK] F5 v2: deneme4 gerekcesi 'kabuk' (net-kutu DEGIL) + wall_aware onerisi aktif.", flush=True)
print("   Guvenlik teoremi (K-12, kabuk-DISI): NFV>=heightmap -> NFV secimi kaliteden kaybettirmez.", flush=True)
print("   Kabuk istisnasi (K-19): K-12 kabukta gecersiz -> aile katmani cidar-pitch heightmap secer.", flush=True)

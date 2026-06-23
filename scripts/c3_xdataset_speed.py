"""c3_xdataset_speed.py — Cross-dataset NFV hız+bellek doğrulama (backlog #3 + #5a).

#3: Paralellik hız oranı (CPU Kol A vs GPU-resident) SADECE Plan2'de ölçülmüştü (2.3×/5.5×).
    Mekanizma genel+BİREBİR ama oran veriye bağlı → Plan1/Plan3/boxy'de de ölç.
#5a: Gerçek üretim pitch'inde (suggest_nfv_pitch) NFV bellek/hız profili + guard doğru mu.
    (Eski "0.5mm sertleştirme" amacı backlog #1 ile değişti: artık suggest_nfv_pitch en kaba
     güvenli pitch seçer, 0.5mm seçilmez; burada her veride seçilen pitch + feasible doğrulanır.)

Her veri için: suggest_nfv_pitch → pitch/feasible/reason | heightmap(kıyas) | NFV CPU Kol A süre+h |
NFV GPU-resident süre+h | BİREBİR(h_cpu==h_gpu) | hız oranı. ÜRETİME DOKUNMAZ — scripts/.

Kullanım: python scripts/c3_xdataset_speed.py [plan1|plan3|boxy|all]
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.fft_backend import get_backend
from src.nesting3d.parallel_decode import decode, decode_gpu

# c3_generality ile aynı dataset config'leri (tek kaynak için oradan da import edilebilir;
# bağımsızlık için burada kopya — qty'ler RESUME §7 + c3_generality ile birebir).
VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
N_OR, MARGIN = 4, 1
DATASETS = {
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "plate": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "plate": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def _boxy_instance():
    import trimesh
    specs = {"box_60x40x30": (60, 40, 30), "box_50x50x50": (50, 50, 50),
             "box_80x30x20": (80, 30, 20), "box_45x45x70": (45, 45, 70),
             "box_35x90x25": (35, 90, 25)}
    qty = {"box_60x40x30": 20, "box_50x50x50": 14, "box_80x30x20": 16,
           "box_45x45x70": 10, "box_35x90x25": 12}
    stl_map = {}
    for name, ext in specs.items():
        data = trimesh.creation.box(extents=list(ext)).export(file_type="stl")
        stl_map[name] = data if isinstance(data, (bytes, bytearray)) else data.encode()
    return stl_map, qty


def _load(ds):
    if ds == "boxy":
        stl_map, qty = _boxy_instance()
        kwargs = {}
    else:
        c = DATASETS[ds]
        stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
        qty = c["qty"]
        kwargs = {}
        if c["plate"]:
            kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    res = build_instance_from_order(stl_map, qty,
                                    persist_dir=_ROOT / "data" / "mail_stl" / f"xspeed_{ds}", **kwargs)
    return res.instance


def run_one(ds, caps):
    print(f"\n{'=' * 74}\n[{ds}]", flush=True)
    inst = _load(ds)
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, feasible, reason = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd,
                                                ram_bytes=caps.ram_bytes)
    print(f"  pitch seçici: {reason}  | feasible={feasible}", flush=True)
    parts = to_voxel_parts(inst, pitch, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(pw // pitch), int(pd // pitch)
    print(f"  {len(parts)} parça, plaka {pw:.0f}x{pd:.0f} ({nx}x{ny} voxel)", flush=True)

    # heightmap (kıyas kalite)
    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(pw, pd, pitch, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"  heightmap : {hm:7.1f} mm  ({time.perf_counter() - t:.0f}s)", flush=True)

    # NFV CPU Kol A
    fm, _ = get_backend("scipy")
    t = time.perf_counter()
    h_cpu = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch)
    t_cpu = time.perf_counter() - t
    print(f"  NFV CPU-A : {h_cpu:7.1f} mm  ({t_cpu:.0f}s)", flush=True)

    # NFV GPU-resident
    h_gpu = t_gpu = None
    if caps.gpu and caps.gpu_fp64:
        try:
            t = time.perf_counter()
            h_gpu = decode_gpu(parts, nx, ny, pitch=pitch)
            t_gpu = time.perf_counter() - t
            print(f"  NFV GPU   : {h_gpu:7.1f} mm  ({t_gpu:.0f}s)", flush=True)
        except Exception as e:
            print(f"  NFV GPU   : HATA {type(e).__name__}: {e}", flush=True)

    # özet
    nfv_delta = (hm - h_cpu) / hm * 100 if hm else 0.0
    birebir_cg = (h_gpu is None) or abs(h_cpu - h_gpu) < 1e-6
    spd = (t_cpu / t_gpu) if t_gpu else None
    print(f"  --> NFV vs heightmap: {nfv_delta:+.1f}% | CPU-A vs GPU birebir: "
          f"{'EVET' if birebir_cg else 'HAYIR'} | GPU hiz: "
          f"{(f'{spd:.1f}x' if spd else '-')}", flush=True)
    return ds, pitch, hm, h_cpu, t_cpu, h_gpu, t_gpu


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    caps = probe_capabilities()
    print("=" * 74)
    print(f"CROSS-DATASET NFV HIZ/BELLEK — {caps.summary()}")
    print("=" * 74, flush=True)
    todo = ["plan1", "plan3", "boxy"] if arg == "all" else [arg]
    rows = []
    for ds in todo:
        try:
            rows.append(run_one(ds, caps))
        except Exception as e:
            print(f"\n[{ds}] HATA: {type(e).__name__}: {e}", flush=True)

    print(f"\n{'=' * 74}\nOZET (GPU hiz orani veriye bagli mi?)")
    print(f"{'veri':>7} | {'pitch':>6} | {'heightmap':>9} | {'NFV':>7} | {'delta%':>6} | "
          f"{'CPU-A':>7} | {'GPU':>7} | {'hiz':>6}")
    for ds, pitch, hm, h_cpu, t_cpu, h_gpu, t_gpu in rows:
        d = (hm - h_cpu) / hm * 100 if hm else 0
        spd = f"{t_cpu / t_gpu:.1f}x" if t_gpu else "-"
        print(f"{ds:>7} | {pitch:6.2f} | {hm:8.1f} | {h_cpu:7.1f} | {d:+5.1f} | "
              f"{t_cpu:6.0f}s | {(f'{t_gpu:.0f}s' if t_gpu else '-'):>7} | {spd:>6}")
    print("=" * 74)


if __name__ == "__main__":
    main()

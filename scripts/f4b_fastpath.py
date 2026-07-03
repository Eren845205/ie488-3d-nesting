"""f4b_fastpath.py — F4-B OZDES-GRUP HIZLI YOL (olc-once prototip, URETIME DOKUNMAZ).

HIPOTEZ (F4-B; MDPI Appl.Sci 16(1):148 'identical-part layer replication' +
bizim kabuk-telescoping ek hipotezi):
  Deneme4 = 13 tip / 588 adet, cogunlugu OZDES ince-cidarli kabuk dugme
  (200x '03 Tek Fonksiyonlu', 126x ASY-0176446-1, 62x ASY-0176446, 56x '04'...).
  K-19: heightmap @0.5mm = 282.0mm ama 131 DAKIKA (588 parcanin tek tek drop'u).

  Ozdes-grup hizli yol: her TIP icin TEK voxelize + TEK optimal plaka-katmani
  (grid dizilim) + dikey coğaltma. Iki kazanc:
    (1) SURE: tip basi TEK voxelize (13 voxelize, 588 degil) -> dakikalar.
    (2) YUKSEKLIK: kabuk parcalarda ust kopya alttakinin oyuguna oturur
        (telescoping / bardak-istifi). Aligned-drop bunu GEOMETRIDEN olcer:
        nest_advance = kopya-basi dikey ilerleme = max_kolon(top - bottom).
        Duz-cidarli kutu -> advance = tam yukseklik (istif YOK).
        Kubbeli/konik ince kabuk -> her kolon z'de ince -> advance kucuk
        (DERIN istif). Yani model solid ile nesting-kabugu DOGRU ayirir.

TASARIM (iskelet, gerekceli sapmalarla):
  1. Dataset'i yukle (c3_generality.DATASETS + build_instance_from_order deseni).
     Parcalar to_voxel_parts ile qty-genisletilir AMA ayni tip orientation
     verisini PAYLASIR -> voxelize zaten tip-basi (13x), maliyet orada.
  2. Grupla (parca.name), her grup icin en iyi stacking-oryantasyonunu sec:
     tower_vox = h_part + (n_vertical - 1) * (nest_advance + tampon)
     minimize eden oryantasyon. per_layer = grid dizilim (floor(nx/fw)*floor(ny/fh)).
     n_vertical = ceil(qty / per_layer).
  3. nest_advance = aligned ozdes kopyanin drop-z'si = max_dolu_kolon(top-bottom)
     (Bin3D drop kurali ile birebir; +tampon = z_clearance analogu).
  4. Kompozisyon (KABA/TAHMIN, tam cozucu DEGIL):
     (A) block-stack (KORUYUCU ust sinir): her gruba TAM plaka-katmani ver,
         grup-bloklarini ust uste koy -> toplam = SUM(tower).
     (B) shared-plate columnar (IYIMSER): tum kopyalar plakada telescoped
         kule; ikili-arama ile alan-sigan min tepe (alan-paketleme kaybi
         ihmal; buyuk duz parca varsa infeasible -> block-stack gecerli).
  5. ASCII tablo + kule ozetleri + kompozisyon + kiyas satiri.
  6. Erisilebilirlik sanity: baskin tipin kulesi +Z sokulebilir mi (accessibility).

KULLANIM:
  python -m scripts.f4b_fastpath selftest            # sentetik dogrulama (RAM-siz)
  python -m scripts.f4b_fastpath deneme4 0.5          # TAM olcum (ayri surecte kos!)
  python -m scripts.f4b_fastpath deneme4 0.5 8        # +oryantasyon sayisi

UYARI: TAM deneme4 @0.5mm voxelize AGIR (2 dev ROBT plakasi); RAM/sure ister.
Bu script UYGULAMAYA/uretime dokunmaz — sadece scripts/, src/ SALT-OKUNUR.
Print SAF ASCII (cp1254 guvenli).
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np

from src.nesting3d.voxelize import Orientation, VoxelPart
from src.nesting3d.accessibility import check_accessibility

# Kiyas referanslari (memory + YONTEM_HARITASI, Deneme4)
REF_K19 = 282.0     # heightmap @0.5mm cidar-pitch (131 dk)
REF_NFV = 386.4     # NFV-max (6 dk)
REF_MAGICS = 250.24  # Magics referansi

DEFAULT_BUFFER_VOX = 1   # tampon = uretim z_clearance analogu (>=1mm garanti)


# ---------------------------------------------------------------------------
# Kolon-profil / kule geometrisi (Bin3D drop kurali ile birebir)
# ---------------------------------------------------------------------------

def part_top_vox(o: Orientation) -> int:
    """Parca tam yukseklik (voxel) bu oryantasyonda = max dolu-kolon top."""
    if not o.filled.any():
        return 0
    return int(o.top[o.filled].max())


def nest_advance_vox(o: Orientation) -> int:
    """Aligned ozdes kopyanin drop-z'si (kopya-basi dikey ilerleme, voxel).

    Bin3D.drop kurali: z_B = max_dolu_kolon(H[i,j] - bottom_B[i,j]). Ozdes+
    hizali kopyada H = A'nin top-profili, bottom_B = A'nin bottom-profili ->
    z_B = max_dolu_kolon(top - bottom) = en kalin kolonun z-acikligi.
      solid  -> her kolon 0..H dolu -> advance = H (istif yok)
      kabuk  -> her kolon ince z-bant -> advance kucuk (derin telescoping)
    """
    f = o.filled
    if not f.any():
        return 0
    span = (o.top[f].astype(np.int64) - o.bottom[f].astype(np.int64))
    return int(span.max())


def per_layer_count(fw: int, fh: int, nx: int, ny: int) -> int:
    """Tek plaka-katmaninda kac kopya sigar (eksen-hizali grid dizilim).

    Kaba ama seffaf: floor(nx/fw)*floor(ny/fh). Orientation.filled zaten yatay
    margin-dilate edilmis (to_voxel_parts margin=1) -> tampon dahil."""
    if fw <= 0 or fh <= 0 or fw > nx or fh > ny:
        return 0
    return (nx // fw) * (ny // fh)


def per_layer_area_ub(footprint_cells: int, plate_cells: int) -> int:
    """Alan-tabani UST SINIR: tek katmana en fazla kac kopya sigabilir.

    Hicbir yerlesim (grid, dobek, rotasyon...) tek katmana bundan fazla kopya
    koyamaz — cunku footprint_cells * kopya <= plate_cells (toplam-alan kisiti).
    Grid `per_layer_count` bunun ALTINDA kalabilir (eksen-hizali dizilim gercek
    maks-yerlesimi ALT-sayar); dolayisiyla grid n_dik gercek katman sayisini
    UST-sayar. GECERLI alt sinir icin bu UST sinir kullanilir:
        n_vert_lb = ceil(qty / per_layer_area_ub)   (gercek katman sayisi >= bu)
    """
    if footprint_cells <= 0 or plate_cells <= 0:
        return 0
    return plate_cells // footprint_cells


def best_group_tower(orientations, qty: int, nx: int, ny: int,
                     buffer_vox: int):
    """Grup icin kule yuksekligini minimize eden oryantasyonu sec.

    Doner: dict(oi, per_layer, n_vertical, h_part_vox, advance_vox, fw, fh,
                tower_vox) veya None (hicbir oryantasyon sigmaz)."""
    best = None
    for oi, o in enumerate(orientations):
        fw, fh = int(o.filled.shape[0]), int(o.filled.shape[1])
        per = per_layer_count(fw, fh, nx, ny)
        if per <= 0:
            continue
        n_vert = math.ceil(qty / per)
        h_part = part_top_vox(o)
        adv = nest_advance_vox(o) + buffer_vox
        tower = h_part + (n_vert - 1) * adv
        cand = {
            "tower_vox": tower, "oi": oi, "per_layer": per, "n_vertical": n_vert,
            "h_part_vox": h_part, "advance_vox": adv, "fw": fw, "fh": fh,
        }
        if best is None or (cand["tower_vox"], oi) < (best["tower_vox"], best["oi"]):
            best = cand
    return best


# ---------------------------------------------------------------------------
# Kompozisyon (B) — shared-plate columnar (ikili-arama, IYIMSER alt-tahmin)
# ---------------------------------------------------------------------------

def shared_plate_vox(rows, plate_cells: int, hi_vox: int):
    """Tum kopyalari plakada telescoped kule olarak koyup min tepe (voxel).

    rows: [(qty, a_cells, h_part_vox, advance_vox), ...]. Alan-paketleme kaybi
    IHMAL (yalniz toplam-alan kisiti) -> IYIMSER. Buyuk duz parca sigmazsa None.
    advance_vox >= 1 (tampon) garantili."""
    lo = max((r[2] for r in rows), default=0)

    def feasible(H: int) -> bool:
        area = 0
        for qty, a, h, adv in rows:
            if H < h:
                return False
            stack = 1 + (H - h) // adv
            cols = math.ceil(qty / stack)
            area += cols * a
            if area > plate_cells:
                return False
        return True

    if not feasible(hi_vox):
        return None
    while lo < hi_vox:
        mid = (lo + hi_vox) // 2
        if feasible(mid):
            hi_vox = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------------------
# Erisilebilirlik sanity: baskin tipin kulesi +Z sokulebilir mi
# ---------------------------------------------------------------------------

def tower_accessible(o: Orientation, advance_vox: int, k: int):
    """k kopyayi hizali z=i*advance ile istifle, +Z sokulebilirligi dogrula.

    Doner: (all_accessible: bool, summary: str)."""
    grid = np.asarray(o.grid, dtype=bool)
    scene = [(f"copy{i}", grid, 0, 0, i * advance_vox) for i in range(k)]
    rep = check_accessibility(scene)
    return rep.all_accessible, rep.summary()


# ---------------------------------------------------------------------------
# Sentetik dogrulama (RAM-siz, STL/voxelize maliyeti YOK)
# ---------------------------------------------------------------------------

def _orient_from_grid(grid: np.ndarray) -> Orientation:
    """Ham bool grid -> Orientation (filled/bottom/top profilleri hesaplanir)."""
    grid = np.asarray(grid, dtype=bool)
    filled = grid.any(axis=2)
    bottom = np.argmax(grid, axis=2).astype(np.int64)
    top = (grid.shape[2] - np.argmax(grid[:, :, ::-1], axis=2)).astype(np.int64)
    top = np.where(filled, top, 0)
    return Orientation(
        rot_matrix=np.eye(4), voxel_origin=np.zeros(3), grid=grid,
        filled=filled, bottom=bottom, top=top, voxel_count=int(grid.sum()),
    )


def _funnel_grid(side: int, height: int, wall: int = 2) -> np.ndarray:
    """Basamakli huni/kase ince kabugu: seviye k'de kenar-halka yaricapi=k
    (yukari genisler). Her (i,j) kolonu yalniz tek seviye civarinda dolu ->
    z-acikligi kucuk -> aligned kopya DERIN nest eder (bardak-istifi)."""
    c = side // 2
    g = np.zeros((side, side, height), dtype=bool)
    ii, jj = np.meshgrid(np.arange(side), np.arange(side), indexing="ij")
    ring = np.maximum(np.abs(ii - c), np.abs(jj - c))  # (side,side) Chebyshev
    for k in range(height):
        r = min(k + 2, c)  # seviye ile genisleyen halka yaricapi
        band = (ring == r)
        for dz in range(wall):
            if k + dz < height:
                g[:, :, k + dz] |= band
    return g


def _solid_box_grid(side: int, height: int) -> np.ndarray:
    return np.ones((side, side, height), dtype=bool)


def run_selftest() -> int:
    print("=" * 72)
    print("F4-B SELF-TEST (sentetik, RAM-siz) - istif mekanigi dogrulamasi")
    print("=" * 72, flush=True)
    nx = ny = 60          # kucuk sentetik plaka (voxel)
    pitch = 1.0
    buf = DEFAULT_BUFFER_VOX
    ok = True

    # --- 1) HUNI/KABUK: derin telescoping beklenir (advance << h_part) ---
    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    fp = VoxelPart("funnel", "funnel", None, [funnel], int(funnel.grid.sum()))
    h_f = part_top_vox(funnel)
    adv_f = nest_advance_vox(funnel)
    print(f"[1] HUNI kabuk: h_part={h_f} vox, nest_advance={adv_f} vox "
          f"(+tampon={buf}) -> {'TELESCOPING' if adv_f + buf < h_f else 'ISTIF-YOK'}")
    if not (adv_f + buf < h_f):
        print("    [FAIL] kabuk telescoping bekleniyordu"); ok = False

    tw = best_group_tower([funnel], qty=40, nx=nx, ny=ny, buffer_vox=buf)
    print(f"    grup qty=40: per_layer={tw['per_layer']}, n_vertical="
          f"{tw['n_vertical']}, tower={tw['tower_vox']} vox")
    naive = h_f * math.ceil(40 / tw["per_layer"])   # istif-yok kulesi
    print(f"    kule {tw['tower_vox']} vs istif-yok {naive} vox "
          f"-> kazanc {(naive - tw['tower_vox']) / naive * 100:+.0f}%")
    if tw["tower_vox"] >= naive:
        print("    [FAIL] telescoping kazanci yok"); ok = False

    # --- 2) SOLID kutu: istif YOK beklenir (advance = tam yukseklik) ---
    box = _orient_from_grid(_solid_box_grid(side=20, height=16))
    h_b = part_top_vox(box)
    adv_b = nest_advance_vox(box)
    print(f"[2] SOLID kutu: h_part={h_b} vox, nest_advance={adv_b} vox "
          f"-> {'ISTIF-YOK (dogru)' if adv_b >= h_b else 'BEKLENMEDIK NEST'}")
    if adv_b < h_b:
        print("    [FAIL] solid parca nest etmemeli"); ok = False

    # --- 3) Erisilebilirlik: huni kulesi +Z sokulebilir mi ---
    acc, summary = tower_accessible(funnel, adv_f + buf, k=5)
    print(f"[3] erisim (5-huni kule): {summary}")
    if not acc:
        print("    [FAIL] +Z sokulemiyor"); ok = False

    # --- 4) shared-plate ikili-arama tutarliligi ---
    rows = [(40, tw["fw"] * tw["fh"], h_f, adv_f + buf)]
    sp = shared_plate_vox(rows, plate_cells=nx * ny, hi_vox=tw["tower_vox"])
    print(f"[4] shared-plate columnar: {sp} vox (block-stack tek-grup "
          f"{tw['tower_vox']} vox ile tutarli: {sp is not None and sp <= tw['tower_vox']})")
    if sp is None or sp > tw["tower_vox"]:
        print("    [FAIL] shared-plate tutarsiz"); ok = False

    print("-" * 72)
    print(f"SELF-TEST: {'PASS' if ok else 'FAIL'}")
    print("=" * 72, flush=True)
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# TAM olcum (dataset yukle -> tip-basi voxelize -> grup kuleleri -> kompozisyon)
# ---------------------------------------------------------------------------

def run_dataset(ds: str, pitch: float, n_or: int) -> int:
    from scripts.c3_generality import DATASETS
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order
    from src.nesting3d.instances.format import to_voxel_parts

    buf = DEFAULT_BUFFER_VOX
    print("=" * 72)
    print(f"F4-B HIZLI YOL - dataset={ds}  pitch={pitch}mm  n_or={n_or}  tampon={buf}vox")
    print("=" * 72, flush=True)

    cfg = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    qty = cfg["qty"]
    plate = cfg["plate"]
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"f4b_{ds}"}
    if plate is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = plate

    t0 = time.perf_counter()
    res = build_instance_from_order(stl_map, qty, **kwargs)
    # to_voxel_parts: tip-basi TEK voxelize (13x), qty PAYLASIMLI orientation ->
    # ana sure kazanci burada (588 degil 13 voxelize).
    parts = to_voxel_parts(res.instance, pitch, n_orientations=n_or, margin=1)
    cont = res.instance.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // pitch), int(pd // pitch)
    t_vox = time.perf_counter() - t0
    print(f"voxelize: {len(parts)} parca-kopya, plaka {pw:.0f}x{pd:.0f}mm "
          f"({nx}x{ny} voxel)  [{t_vox:.0f}s]", flush=True)

    # Grupla (name) — ayni tip orientation paylasir
    groups: dict = {}
    for p in parts:
        groups.setdefault(p.name, []).append(p)

    print("-" * 80)
    # katUB = alan-tabani kat UST-siniri (gecerli); nLB = ceil(qty/katUB) =
    #   katmanin GECERLI alt-siniri. kat/lay + n_dik = grid TAHMINI (alt-sayar).
    hdr = ("grup", "adet", "or", "kat/lay", "katUB", "n_dik", "nLB",
           "layH", "nestA", "kuleH")
    print("{:<24}{:>5}{:>4}{:>8}{:>7}{:>6}{:>5}{:>8}{:>7}{:>8}".format(*hdr))
    print("-" * 80, flush=True)

    plate_cells = nx * ny
    t1 = time.perf_counter()
    block_sum_vox = 0
    max_tower_vox = 0         # grid-kule TAHMINI icin (garantili DEGIL)
    total_vol_vox = 0
    h_single_lb_vox = 0       # gruplar-arasi max( oryantasyonlar-arasi min h )
                             #   = en yuksek tek parca -> GECERLI alt sinir
    n_nesting = 0      # kac grup GERCEKTEN telescope ediyor (advance < layH)
    rows = []          # shared-plate icin (qty, a_cells, h_part_vox, advance_vox)
    dominant = None    # (qty, orientation, advance, name)
    for name in sorted(groups, key=lambda n: -len(groups[n])):
        g = groups[name]
        orients = g[0].orientations
        q = len(g)
        total_vol_vox += g[0].volume_voxels * q
        # GECERLI tek-parca alt siniri: parca hangi oryantasyonda olursa olsun
        # en az bu kadar yuksek -> or-larin MIN yuksekligi kuleye sigmali.
        h_min_or = min((part_top_vox(o) for o in orients), default=0)
        h_single_lb_vox = max(h_single_lb_vox, h_min_or)
        tw = best_group_tower(orients, q, nx, ny, buf)
        if tw is None:
            print(f"{name[:24]:<24}{q:>5}  -- SIGMIYOR (plaka < parca)")
            continue
        # Alan-tabani GECERLI ust-sinir / n_dik alt-siniri (grid alt-saydigi icin)
        o_chosen = orients[tw["oi"]]
        footprint_cells = int(o_chosen.filled.sum())
        per_layer_ub = per_layer_area_ub(footprint_cells, plate_cells)
        n_vert_lb = math.ceil(q / per_layer_ub) if per_layer_ub else 0
        block_sum_vox += tw["tower_vox"]
        max_tower_vox = max(max_tower_vox, tw["tower_vox"])
        nests = tw["advance_vox"] < tw["h_part_vox"]
        n_nesting += 1 if nests else 0
        rows.append((q, tw["fw"] * tw["fh"], tw["h_part_vox"], tw["advance_vox"]))
        print("{:<24}{:>5}{:>4}{:>8}{:>7}{:>6}{:>5}{:>8.1f}{:>7.1f}{:>8.1f}{}".format(
            name[:24], q, tw["oi"], tw["per_layer"], per_layer_ub,
            tw["n_vertical"], n_vert_lb,
            tw["h_part_vox"] * pitch, tw["advance_vox"] * pitch,
            tw["tower_vox"] * pitch, "  <nest" if nests else ""))
        if dominant is None or q > dominant[0]:
            dominant = (q, orients[tw["oi"]], tw["advance_vox"], name)
    t_comp = time.perf_counter() - t1

    print("-" * 72)
    # --- GECERLI (kanitlanabilir) ALT SINIRLAR ---
    # (1) hacim tabani: tum malzeme hacmi / plaka alani <= tepe (her voxel sigmali)
    lb_vol_mm = total_vol_vox * pitch ** 3 / (pw * pd) if pw * pd else 0.0
    # (2) en yuksek tek parca (oryantasyonlar-arasi min, gruplar-arasi max) ->
    #     bu parca hangi oryantasyonda konursa konsun kuleye sigmali -> trivial LB
    lb_single_mm = h_single_lb_vox * pitch
    lb_valid_mm = max(lb_vol_mm, lb_single_mm)   # iki gecerli LB'nin sikisi

    # --- UST SINIR / TAHMINLER ---
    # block-stack: her gruba TAM plaka-katmani + gruplari ust uste -> INSA
    # EDILEBILIR somut duzen -> GECERLI UST SINIR.
    block_mm = block_sum_vox * pitch
    best_ub_mm = block_mm                        # TEK gecerli UST SINIR
    # grid-kule: per_layer alt-saydigi icin n_dik ust-sayilir -> kule sisebilir;
    # ne iyimser ne garantili -> yalnizca TAHMIN.
    tower_est_mm = max_tower_vox * pitch
    # shared-plate: alan-testi paketleme kaybini yok sayar -> IYIMSER TAHMIN
    # (gecerli UST SINIR DEGIL; karsi-ornek: 2x(15x13) parca 20x20'de H=8 der,
    #  gercek 16). best_ub'a KATILMAZ.
    sp_vox = shared_plate_vox(rows, nx * ny, hi_vox=block_sum_vox)
    sp_mm = sp_vox * pitch if sp_vox is not None else None

    print(f"telescope eden grup: {n_nesting}/{len(rows)}  "
          f"(advance<layH = kabuk-istifi aktif)")
    print(f"LB (hacim tabani, 100% paket)        : {lb_vol_mm:7.1f} mm  [gecerli ALT SINIR]")
    print(f"LB (en yuksek tek parca, or-min)     : {lb_single_mm:7.1f} mm  [gecerli ALT SINIR]")
    print(f"LB (garantili = ikisinin sikisi)     : {lb_valid_mm:7.1f} mm  [KANITLI ALT SINIR]")
    print(f"UB (block-stack, insa edilebilir)    : {block_mm:7.1f} mm  [gecerli UST SINIR]")
    print(f"~  hizali-kule (grid)                : {tower_est_mm:7.1f} mm  "
          f"[TAHMINI - grid, iyimser DEGIL garantili DEGIL]")
    if sp_mm is not None:
        print(f"~  shared-plate columnar            : {sp_mm:7.1f} mm  "
              f"[IYIMSER TAHMIN - paketleme kaybi ihmal, gecerli UST SINIR DEGIL]")
    print(f"    hizli-yol compute suresi: {t_comp:.2f}s  "
          f"(voxelize {t_vox:.0f}s dahil toplam {t_vox + t_comp:.0f}s)")
    if pitch > 1.0:
        print("    [UYARI] pitch>1mm: ince-kabuk cozunmez -> advance sisirilir, "
              "telescoping BASTIRILIR. Anlamli olcum icin pitch<=0.5mm.")

    # Erisilebilirlik sanity — baskin tipin kulesi
    if dominant is not None:
        _, o, adv, dname = dominant
        acc, summary = tower_accessible(o, adv, k=min(5, dominant[0]))
        print("-" * 72)
        print(f"erisim sanity (baskin '{dname[:30]}' {min(5, dominant[0])}-kule): {summary}")

    print("-" * 72)
    print(f"KIYAS: K-19 heightmap {REF_K19}mm/131dk | NFV-max {REF_NFV}mm/6dk | "
          f"Magics {REF_MAGICS}mm")
    print(f"  GARANTILI BRACKET: [{lb_valid_mm:.1f} .. {best_ub_mm:.1f}] mm "
          f"(gercek optimum arada) | tahmini kule {tower_est_mm:.1f} mm | "
          f"sure ~131dk -> {t_vox + t_comp:.0f}s "
          f"({131 * 60 / max(t_vox + t_comp, 1):.0f}x hizli)")
    # LOW: verdict tek esige baglanmaz -> bracket K-19'u kapsiyorsa hukum ASKIDA.
    if best_ub_mm < REF_K19:
        verdict = ("gecerli UST SINIR K-19'un ALTINDA -> hizli-yol K-19'u "
                   "KESIN yener (kanitli)")
    elif lb_valid_mm > REF_K19:
        verdict = ("gecerli ALT SINIR K-19'un USTUNDE -> hizli-yol bu pitch/"
                   "oryantasyonda K-19'a KESIN yenik")
    elif tower_est_mm < REF_K19:
        verdict = ("tahmini kule K-19'un ALTINDA ama bracket K-19'u kapsiyor "
                   "-> POTANSIYEL kazanc; kesin hukum icin gercek yerlesim gerekir")
    else:
        verdict = ("tahmini kule K-19'un USTUNDE ama bracket K-19'u kapsiyor "
                   "-> belirsiz; kesin hukum icin gercek yerlesim gerekir")
    print(f"  -> {verdict}")
    print("=" * 72, flush=True)
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] == "selftest":
        return run_selftest()
    ds = sys.argv[1]
    pitch = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    n_or = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    return run_dataset(ds, pitch, n_or)


if __name__ == "__main__":
    raise SystemExit(main())

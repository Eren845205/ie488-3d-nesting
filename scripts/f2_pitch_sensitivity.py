"""f2_pitch_sensitivity.py — F2 erisilebilirlik voxel-cozunurluk probu (opt-in).

Uretime bagli DEGIL. Ayni sentetik sahneyi 2 farkli voxel cozunurlugunde
(pitch) denetleyip yanlis-pozitif farkini yazdirir.

Hipotez: DAR bir gecis kanali KABA voxel'de KAPALI gorunur -> gercekte +Z'de
serbest cikan bir parca, kaba cozunurlukte kilitli sanilir (yanlis-pozitif).

Sahne: ic-ice gecmis DIS (comb / tarak) parcalar.
  Parca A: yukari bakan dis-cubuklari (x = 0-1, 2-3, 4-5 mm), tam yukseklik.
  Parca B: A'nin cubuklari ARASINA (x = 1-2, 3-4, 5-6 mm) oturan kisa disler.
  Aralarinda 1 mm yatay bosluk (clearance) var -> B gercekte +Z'ye serbest
  cekilir (dislerin arasindan yukari cikar).

  - INCE pitch (< 1 mm bosluk): kanallar acik kalir -> A ve B sutun PAYLASMAZ
    -> kilit YOK (dogru).
  - KABA pitch (>= bosluk): kaba voxel yan yana disleri BIRLESTIRIR -> A ve B
    ayni sutunlari kaplar, A yuksek/B alcak -> karsilikli +Z blogu -> KILIT
    (yanlis-pozitif; asiri-tutucu / konservatif voxelizasyon yan etkisi).

SAF ASCII cikti (cp1254 guvenli).

Kullanim:
    python -m scripts.f2_pitch_sensitivity
"""

import numpy as np

from src.nesting3d.accessibility import (
    check_accessibility,
    placed_voxels_from_scene,
)

# Konservatif (overlap) rasterizasyon: bir hucre, herhangi bir kati kutu ile
# POZITIF hacimde kesisiyorsa dolar. Gercek yuzey-voxelizasyonun (_surface_cells)
# dar bosluklari kapatan "sarma" davranisini taklit eder -> pitch buyudukce
# yan yana ozellikler birlesir.
def _rasterize(boxes_mm, pitch, extent_mm):
    """boxes_mm: [(x0,x1,y0,y1,z0,z1), ...] mm. -> bool (nx,ny,nz) grid."""
    ex, ey, ez = extent_mm
    nx = max(1, int(np.ceil(ex / pitch)))
    ny = max(1, int(np.ceil(ey / pitch)))
    nz = max(1, int(np.ceil(ez / pitch)))
    grid = np.zeros((nx, ny, nz), dtype=bool)
    for (x0, x1, y0, y1, z0, z1) in boxes_mm:
        i0 = int(np.floor(x0 / pitch)); i1 = int(np.ceil(x1 / pitch))
        j0 = int(np.floor(y0 / pitch)); j1 = int(np.ceil(y1 / pitch))
        k0 = int(np.floor(z0 / pitch)); k1 = int(np.ceil(z1 / pitch))
        grid[i0:i1, j0:j1, k0:k1] = True
    return grid


def _comb_scene(pitch):
    """Ic-ice gecmis iki tarak (comb) parca, 1 mm yatay bosluk."""
    depth = (0.0, 4.0)            # y: tek slab
    a_boxes = [(x0, x0 + 1.0, depth[0], depth[1], 0.0, 6.0)
               for x0 in (0.0, 2.0, 4.0)]        # dik cubuklar, tam yukseklik
    b_boxes = [(x0, x0 + 1.0, depth[0], depth[1], 2.0, 4.0)
               for x0 in (1.0, 3.0, 5.0)]        # arada oturan kisa disler
    extent = (6.0, 4.0, 6.0)
    a_grid = _rasterize(a_boxes, pitch, extent)
    b_grid = _rasterize(b_boxes, pitch, extent)
    return [("comb_A", a_grid, 0, 0, 0), ("comb_B", b_grid, 0, 0, 0)]


def _run(pitch):
    scene = _comb_scene(pitch)
    report = check_accessibility(placed_voxels_from_scene(scene))
    return report


def main():
    print("F2 pitch-duyarlilik probu (ic-ice tarak, +Z sokulebilirlik)")
    print("-" * 66)
    print("hipotez: kaba pitch 1 mm kanali kapatir -> tarak yanlis-pozitif kilit")
    print()

    fine_pitch = 0.5
    coarse_pitch = 2.0

    results = {}
    for label, pitch in (("INCE ", fine_pitch), ("KABA ", coarse_pitch)):
        report = _run(pitch)
        results[label.strip()] = report
        status = "LOCKED (yanlis-pozitif)" if report.n_locked else "serbest (dogru)"
        print(f"{label} pitch={pitch:>4.1f} mm | n_locked={report.n_locked} "
              f"-> {status}")
        print(f"       {report.summary()}")

    print()
    delta = results["KABA"].n_locked - results["INCE"].n_locked
    print(f"yanlis-pozitif farki (kaba - ince) = {delta} kilitli parca")
    if delta > 0:
        print("SONUC: kaba voxel 1 mm kanali kapatti -> denetim asiri-tutucu.")
        print("       Oneri: erisilebilirlik denetimini parcalarin en kucuk")
        print("       ozelligini/boslugunu kaybetmeyen pitch'te kos")
        print("       (bkz. instances.pitch.suggest_pitch).")
    else:
        print("SONUC: bu olcekte cozunurluk farki yanlis-pozitif uretmedi.")


if __name__ == "__main__":
    main()

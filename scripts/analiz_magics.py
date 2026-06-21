"""analiz_magics.py — Magics kalite farkını SAYISALLAŞTIR.

Soru: Magics bizden neyi farklı yapıyor, kalite farkını ne belirliyor?
Görsel (Plan2.jpg): Magics büyük parçaları dizip küçük/ince parçaları aralarındaki
boşluklara dolduruyor (cavity/gap-fill). Burada sayısal kanıt:
- teorik min yükseklik = toplam_hacim / plaka_alanı (mükemmel paketleme tabanı)
- Magics yoğunluğu (492.39mm) vs bizim (~621mm kesin)
- parça-bazlı "kutuluk" (hacim/bbox) — oyuk potansiyeli nerede
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import trimesh

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")

PLAN2_QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}
PLATE_W, PLATE_D = 328.74, 328.19
MAGICS_H = 492.39
BIZIM_H_KESIN = 621.0


def main():
    stl_dir = VERILER / "Plan2" / "Plan2"
    plate_area = PLATE_W * PLATE_D
    total_vol = 0.0
    total_bbox = 0.0
    rows = []
    for name, qty in PLAN2_QTY.items():
        f = stl_dir / f"{name}.stl"
        if not f.exists():
            print(f"YOK: {name}")
            continue
        m = trimesh.load(f, force="mesh")
        vol = abs(m.volume)
        ext = m.extents  # bbox boyutları
        bbox = float(ext[0] * ext[1] * ext[2])
        boxiness = vol / bbox if bbox > 0 else 0
        total_vol += vol * qty
        total_bbox += bbox * qty
        rows.append((name, qty, vol, bbox, boxiness, max(ext), min(ext)))

    print("=" * 92)
    print(f"{'parça':<34}{'adet':>5}{'hacim_mm3':>12}{'kutuluk':>9}{'enbüyük':>9}{'enküçük':>9}")
    print("-" * 92)
    for name, qty, vol, bbox, bx, mx, mn in sorted(rows, key=lambda r: -r[2]*r[1]):
        print(f"{name[:33]:<34}{qty:>5}{vol:>12.0f}{bx:>9.2f}{mx:>9.1f}{mn:>9.2f}")

    theo_h = total_vol / plate_area  # mükemmel paketleme min yükseklik
    print("=" * 92)
    print(f"Toplam parça hacmi      : {total_vol:,.0f} mm3")
    print(f"Toplam bbox hacmi       : {total_bbox:,.0f} mm3  (kutuluk ort {total_vol/total_bbox:.2f})")
    print(f"Plaka alanı             : {plate_area:,.0f} mm2 ({PLATE_W}x{PLATE_D})")
    print(f"TEORİK min yükseklik    : {theo_h:.1f} mm  (hacim/alan, %100 paketleme)")
    print("-" * 92)
    print(f"Magics yüksekliği       : {MAGICS_H:.1f} mm  -> yoğunluk {theo_h/MAGICS_H*100:.1f}% (teoriğe oran)")
    print(f"Bizim (kesin)           : {BIZIM_H_KESIN:.1f} mm  -> yoğunluk {theo_h/BIZIM_H_KESIN*100:.1f}%")
    print(f"Magics/teorik           : {MAGICS_H/theo_h:.2f}x  | Bizim/teorik: {BIZIM_H_KESIN/theo_h:.2f}x")
    print(f"Bizim/Magics            : {BIZIM_H_KESIN/MAGICS_H:.3f}x  (kalite açığı)")
    # bbox-paketleme tabanı: parçaları bbox kutusu olarak dizsek
    bbox_h = total_bbox / plate_area
    print(f"bbox-paketleme tabanı   : {bbox_h:.1f} mm  (parça=bbox, %100 bbox paketleme)")
    print(f"  -> Magics bbox tabanının {MAGICS_H/bbox_h:.2f}x'i (bbox'tan {'İYİ=oyuk içine girmiş' if MAGICS_H<bbox_h else 'kötü'})")


if __name__ == "__main__":
    main()

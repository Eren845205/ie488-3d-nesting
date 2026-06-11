"""compact_stl.py — final yerleşim STL'sinin paylaşım boyu kopyasını üretir.

Orijinal dosyaya DOKUNMAZ; yanına *_compact.stl yazar.  Kademeli quadric
decimation (models._decimate_display ile aynı desen): adım başına en çok %60
küçültme, her adımda ORİJİNALE karşı hacim sapması kontrolü — sapma sınırı
aşılırsa adım geri alınır.  Düz yüzeylerdeki gereksiz üçgenler birleşir;
kavis/kabartma yazı bölgeleri quadric metrikçe korunur.

Kullanım: python -m scripts.compact_stl [hedef_üçgen] [max_hacim_sapma]
Default : 1_000_000 üçgen (~50 MB), %0.2 hacim sapması
"""

import sys
from pathlib import Path

import trimesh

_ROOT = Path(__file__).resolve().parent.parent
SRC = _ROOT / "results" / "numune_sa" / "nesting3d_result_numune.stl"
DST = _ROOT / "results" / "numune_sa" / "nesting3d_result_numune_compact.stl"

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
MAX_DRIFT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.002


def main() -> None:
    import fast_simplification

    mesh = trimesh.load(str(SRC), force="mesh")
    v0 = abs(mesh.volume)
    print(f"Kaynak : {len(mesh.faces):,} üçgen, hacim {v0:,.0f} mm³")

    best = mesh
    while len(best.faces) > TARGET:
        reduction = min(0.6, 1.0 - TARGET / len(best.faces))
        v, f = fast_simplification.simplify(
            best.vertices, best.faces, target_reduction=reduction, agg=7
        )
        cand = trimesh.Trimesh(vertices=v, faces=f, process=False)
        no_progress = len(cand.faces) > 0.95 * len(best.faces)
        drift = abs(abs(cand.volume) - v0) / v0
        if no_progress or drift > MAX_DRIFT:
            print(f"  durdu: {len(cand.faces):,} üçgen, sapma %{drift*100:.3f} "
                  f"(sınır %{MAX_DRIFT*100:.1f})")
            break
        best = cand
        print(f"  adım  : {len(best.faces):,} üçgen, hacim sapması %{drift*100:.3f}")

    best.export(str(DST))
    mb = DST.stat().st_size / 1024 / 1024
    drift = abs(abs(best.volume) - v0) / v0
    print(f"Çıktı  : {DST.name} — {len(best.faces):,} üçgen, {mb:.1f} MB, "
          f"toplam hacim sapması %{drift*100:.3f}")


if __name__ == "__main__":
    main()

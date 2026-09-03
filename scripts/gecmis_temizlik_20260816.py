"""Is gecmisi toplu temizlik (yedek: D:\\ie488\\yedek\\otonom_gecmis_20260816).

TUTULAN: kaynak=otomatik gercek mail kosulari (demo* id'leri haric) +
"Demo Musteri" notlu demo kosulari. SILINEN: FORD/ASELSAN/BAYKAR demo
senaryo kosulari, bos "hata" kayitlari, demoford/demoasel tohumlari.
"""
import json
import os
from pathlib import Path

ROOT = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project\data\otonom_gecmis")
P = ROOT / "gecmis.jsonl"


def tutulsun(k):
    mid = str(k.get("id") or "")
    musteri = str(k.get("musteri") or "")
    kaynak = k.get("kaynak")
    if kaynak == "arsiv":
        return True  # hoca verisi arsiv kayitlari (gecmis_arsiv_yukle.py)
    if musteri.startswith("Demo Musteri"):
        return True
    if kaynak == "otomatik" and not mid.startswith("demo"):
        return True
    return False


kayitlar = []
for line in P.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        kayitlar.append(json.loads(line))
    except Exception:
        pass

kalan = [k for k in kayitlar if tutulsun(k)]
silinen = [k for k in kayitlar if not tutulsun(k)]
print(f"toplam={len(kayitlar)} kalan={len(kalan)} silinen={len(silinen)}")
for k in kalan:
    print("  TUT:", k.get("id"), "|", k.get("musteri"), "|", k.get("kaynak"),
          "|", k.get("zaman"))

# jsonl'i atomik yeniden yaz
tmp = P.with_suffix(".jsonl.tmp")
icerik = "\n".join(json.dumps(k, ensure_ascii=False, default=str) for k in kalan)
if icerik:
    icerik += "\n"
tmp.write_text(icerik, encoding="utf-8")
os.replace(tmp, P)

# silinenlerin detay + glb artifact'larini kaldir
n_detay = n_glb = 0
for k in silinen:
    mid = str(k.get("id") or "")
    if not mid:
        continue
    d = ROOT / "detay" / f"{mid}.json"
    if d.exists():
        d.unlink()
        n_detay += 1
    for g in (ROOT / "glb").glob(f"{mid}_*.glb"):
        g.unlink()
        n_glb += 1
print(f"artifact temizligi: detay={n_detay} glb={n_glb}")
print("BITTI")

"""gecmis_arsiv_yukle.py — Hoca verisi sampiyon kosularini Is Gecmisi'ne yukle.

Bu kosular script-tabanli yapildigi icin app gecmisinde yoktu (Eren istegi
2026-08-16: "hocaya gosterecegim"). Kayitlar 'arsiv' kaynagiyla DURUST
etiketlenir; plan7-a2 ve deneme6 icin hoca paketindeki kendi-icinde rehberli
sokum HTML'leri baglanir (data/otonom_gecmis/arsiv/). Idempotent: ayni id
varsa atlanir. Metrik kaynagi: MOTOR/YONTEM_HARITASI §2C sampiyon tablosu.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "otonom_gecmis" / "gecmis.jsonl"

KAYITLAR = [
    {
        "musteri": "FSM — Plan 7 (a2 durus-kilitli)",
        "min_yukseklik_mm": 488.4,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-26T12:00:00",
        "arsiv_html": "plan7_a2_kilitli_rehberli_sokum.html",
        "arsiv_not": "Rehberli sokum (3D, hoca paketi)",
    },
    {
        "musteri": "FSM — Deneme 6",
        "min_yukseklik_mm": 68.5,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-26T12:00:00",
        "arsiv_html": "deneme6_68p5_rehberli_sokum.html",
        "arsiv_not": "Rehberli sokum (3D, hoca paketi)",
    },
    {
        "musteri": "FSM — Plan 1 (kanopi zinciri)",
        "min_yukseklik_mm": 127.2,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-08-06T19:24:00",
        "arsiv_not": "K-62 v20 sampiyonu (LEGAL)",
    },
    {
        "musteri": "FSM — Plan 3",
        "min_yukseklik_mm": 577.62,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-14T12:00:00",
        "arsiv_not": "Manuel referansa gore -%2.6",
    },
    {
        "musteri": "FSM — Deneme 4",
        "min_yukseklik_mm": 220.69,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-14T12:00:00",
        "arsiv_not": "Manuel referansa gore -%11.8",
    },
    {
        "musteri": "FSM — Plan 2",
        "min_yukseklik_mm": 529.04,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-14T12:00:00",
        "arsiv_not": "Sampiyon tablosu kaydi",
    },
    {
        "musteri": "FSM — Deneme 5",
        "min_yukseklik_mm": 214.64,
        "siparis_sayisi": 1, "parti_sayisi": 1,
        "zaman": "2026-07-14T12:00:00",
        "arsiv_not": "Sampiyon tablosu kaydi",
    },
]


def _id(k):
    return hashlib.sha256(k["musteri"].encode("utf-8")).hexdigest()[:12]


mevcut = set()
if P.exists():
    for line in P.read_text(encoding="utf-8").splitlines():
        try:
            mevcut.add(json.loads(line).get("id"))
        except Exception:
            pass

eklenen = 0
with P.open("a", encoding="utf-8") as fh:
    for k in KAYITLAR:
        kid = _id(k)
        if kid in mevcut:
            print(f"  atlandi (var): {k['musteri']}")
            continue
        kayit = {
            "durum": "bitti",
            "kaynak": "arsiv",
            "mod": "nfv",
            "nfv_quality": "fast",
            "musteri": k["musteri"],
            "siparis_sayisi": k["siparis_sayisi"],
            "parti_sayisi": k["parti_sayisi"],
            "min_yukseklik_mm": k["min_yukseklik_mm"],
            "doluluk": None,
            "toplam_fiyat": 0,
            "sure_sn": 0.0,
            "asamalar": [],
            "id": kid,
            "zaman": k["zaman"],
            "arsiv_html": k.get("arsiv_html"),
            "arsiv_not": k.get("arsiv_not", ""),
        }
        fh.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        eklenen += 1
        print(f"  EKLENDI: {k['musteri']} ({k['min_yukseklik_mm']} mm)")

print(f"BITTI — {eklenen} arsiv kaydi eklendi.")

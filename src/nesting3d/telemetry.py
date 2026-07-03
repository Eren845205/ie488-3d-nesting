"""telemetry.py — Kalici kosu telemetrisi (PLAN_DEMO1 §2 + §6.3.1 veri temeli).

Append-only JSONL formati: her kosu bir satir JSON.

Amac
----
Bu dosya ileride algoritma secim modelinin (§6.3.1) egitim verisini biriktirir.
Her satir bir "kosu gozlemi"dir: hangi instance ozellikleriyle hangi cozucunun
ne kadar iyi sonuc verdigi.  Model bu gozlemlerden "bu ozellik vektorune hangi
cozucu daha iyi uyar?" kuralini ogrenecek.

Sema (v1 — genisletilebilir)
-----------------------------
{
  "ts":            float,    # zaman damgasi (Unix epoch)
  "kaynak":        str,      # "benchmark" | "pipeline"
  "instance_id":   str,      # instance benzersiz kimlik
  "aile":          str,      # synthetic aile adi veya "bischoff_ratcliff" vb.
  "feature_names": list[str], # FEATURE_NAMES (sabit siralama referansi)
  "feature_vector": list[float], # FEATURE_NAMES sirasiyla ozellik degerleri
  "cozucu":        str,      # "dblf" | "sa3d" | ...
  "pitch":         float,    # mm (voxelizasyon adimi)
  "budget":        int,      # iterasyon butcesi
  "seed":          int,      # raslantisallik tohumu
  "height_mm":     float,    # elde edilen maksimum yukseklik (mm)
  "density":       float,    # doluluk orani 0..1
  "time_s":        float,    # cozucu suresi (saniye)
  "winner_flag":   bool,     # bu satirin kosucusu bu instance icin kazanan mi?
  ... ek alanlar (eski satirlari bozmaz — anahtar-deger eklenebilir)
}

Kural: yeni alan ekleme eski satirlari bozmaz (eksik anahtar = None).
Sema versiyonu gerekirse "schema_version" alani eklenerek izlenebilir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, List, Optional, Union

from src.nesting3d.instances.features import FEATURE_NAMES


def append_run(
    path: Union[str, Path],
    *,
    kaynak: str,
    instance_id: str,
    aile: str,
    feature_vector: List[float],
    cozucu: str,
    pitch: float,
    budget: int,
    seed: int,
    height_mm: float,
    density: float,
    time_s: float,
    winner_flag: bool,
    suggested_pitch_mm: Optional[float] = None,
    applied_pitch_mm: Optional[float] = None,
    **extra: Any,
) -> None:
    """Bir kosu sonucunu JSONL dosyasina ekle (append-only).

    Args:
        path:           JSONL dosya yolu (yoksa olusturulur, varsa eklenir).
                        Mutlak ya da normalize edilmis yol gecilmesi cagiran
                        kodun sorumlulugundadir; bu fonksiyon yolu degistirmez
                        (lokal arac — sert kisit eklenmedi).
        kaynak:         "benchmark" veya "pipeline".
        instance_id:    Instance benzersiz kimlik string'i.
        aile:           Instance ailesi (synthetic aile adi veya BR sinifi).
        feature_vector: FEATURE_NAMES sirasiyla float listesi.
        cozucu:         Cozucu adi ("dblf", "sa3d", ...).
        pitch:          Voxelizasyon adimi (mm).
        budget:         Iterasyon butcesi.
        seed:           Raslantisallik tohumu.
        height_mm:      Elde edilen maksimum yukseklik (mm).
        density:        Doluluk orani 0..1.
        time_s:         Cozucu calisma suresi (saniye).
        winner_flag:    Bu satir bu instance icin en iyi cozucu mu?
        suggested_pitch_mm: Cozucu-oncesi ONERILEN pitch (mm). None ise satira
                        YAZILMAZ (geriye-uyum). Neden ayri: musait RAM bellek
                        pre-flight'i sessizce geri-kabalastirabilir; onerilen vs
                        uygulanan ayri kayit -> cidar-duyarli faz "etkisiz"
                        gorunmesin (suggested ince, applied kaba fark eder).
        applied_pitch_mm: Cozucude FIILEN uygulanan pitch (mm). None ise yazilmaz.
        **extra:        Ileride sema genislemesi icin ek alanlar
                        (eski satirlari bozmaz).

    Not: feature_vector uzunlugu FEATURE_NAMES uzunluguna esit olmali.
    Dogrulama sadece DEBUG modda yapilir (performans icin).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    row: dict = {
        "ts": time.time(),
        "kaynak": kaynak,
        "instance_id": instance_id,
        "aile": aile,
        "feature_names": list(FEATURE_NAMES),
        "feature_vector": list(feature_vector),
        "cozucu": cozucu,
        "pitch": float(pitch),
        "budget": int(budget),
        "seed": int(seed),
        "height_mm": float(height_mm),
        "density": float(density),
        "time_s": float(time_s),
        "winner_flag": bool(winner_flag),
    }
    # Opsiyonel pitch alanlari — yalniz verildiginde yaz (None -> satira KONULMAZ,
    # eski davranis birebir korunur; okurken eksik anahtar = None).
    if suggested_pitch_mm is not None:
        row["suggested_pitch_mm"] = float(suggested_pitch_mm)
    if applied_pitch_mm is not None:
        row["applied_pitch_mm"] = float(applied_pitch_mm)
    # Ek alanlari ekle (sema genislemesi)
    row.update(extra)

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_telemetry(
    path: Union[str, Path],
) -> List[dict]:
    """JSONL dosyasindaki tum satirlari liste olarak dondur.

    Args:
        path: JSONL dosya yolu.

    Returns:
        List[dict] — her eleman bir kosu satiri.
        Dosya yoksa bos liste doner (hata firlatmaz).
    """
    path = Path(path)
    if not path.exists():
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows

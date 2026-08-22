"""m4_koprusu.py — M4 portföy etiketlerini eğitim tablosuna bağlayan köprü.

Kök-sebep (2026-08-21 A4 teşhisi): M4 portföy koşusu etiketlerini kendi
dosyasına (`results/m4_portfoy_etiket.jsonl`) yazar; mod-seçici eğitim
tablosu (`build_training_table_v2`) ise YALNIZ telemetri v2'den okur.
Aradaki köprü yoktu — tablo 49 instance'ta sabit kalıyordu ve fsm610-SINIFI
aile (mass_plate_rod_mix) eğitimde hiç görünmüyordu (Aşama-1 kapı (a)
değerlendirilemiyordu).

Kurallar:
- YALNIZ üretim kolları (heightmap / nfv_fast / nfv_max) tabloya girer.
  Kafes kolları MEKANIZMA_KATALOGU §C gereği kablo onayından önce seçiciye
  ÖĞRETİLMEZ — satırdaki kafes kolları sayaçla raporlanır, atılır.
- winner üretim kollarından YENİDEN türetilir (etiketteki winner_mode kafes
  olabilir; dataset_v2 konvansiyonu: argmin legal, eşitlikte alfabetik).
- Legal kararı etiketteki `invalid_reasons` alanından okunur (M4'ün 5-yön
  konservatif kararı tek-kaynak; burada yeniden hesap YOK).
- instance_id `@{scale}` ekiyle benzersizleştirilir (m4 kimliği scale
  içermiyordu; mass kucuk/orta aynı kimliği paylaşıyordu).
- Held-out dışlama (Y-2) ve mevcut-tablo kimlik çakışması filtreleri
  uygulanır; her düşen satır/instance sayaçta görünür.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.dataset_v2 import HEIGHTMAP_ARM

URETIM_KOLLARI = ("heightmap", "nfv_fast", "nfv_max")

# Arm-eşdeğerlik haritası (M8-düzeltme #1, 2026-08-21): üretim "nfv kalite"
# yolu quality verilmezse "fast" koşar (demo_pipeline.py 890-892 + 1051)
# ⇒ M4'ün nfv_fast kolu telemetri tablosundaki nfv_kalite arm'ının TA
# KENDİSİDİR. İki ada bölmek arm-uzayı hizasızlığı yaratıp kötümser-ceza
# artefaktı üretti (tur-3 thin_shell 8,37→22,68; ASAMA1_KAPI_RAPORU §3b).
# nfv_max ayrı (gerçekten yeni karşı-olgusal kol) — kendi adıyla kalır.
ARM_ESDEGER = {"nfv_fast": "nfv_kalite"}

# Kafes kolları (Eren onayı 2026-08-21 "kafes de öğretilsin"): seçici
# eğitimine kafes/kafes_duruskoru kolları da alınabilir. Varsayılan KAPALI
# kalır ki tur-4 kıyası (arm-eşleme hipotezi) tek-değişkenli kalsın;
# tur-5 `kafes_dahil=True` ile koşar. Üretim kablosu (MK-03) ayrı karar —
# model artefaktı zaten promote edilmedikçe üretime dokunmaz (Y-1/Y-4).
KAFES_KOLLARI = ("kafes", "kafes_duruskoru")

# feature_resolver: etiket satırı -> (values, names) veya None (üretilemedi)
FeatureResolver = Callable[[dict], Optional[Tuple[List[float], List[str]]]]


def m4_benzersiz_id(satir: dict) -> str:
    """m4 etiket satırının tablo kimliği: '<instance_id>@<scale>'."""
    return f"{satir.get('instance_id')}@{satir.get('scale')}"


def m4_training_rows(
    satirlar: Iterable[dict],
    feature_resolver: FeatureResolver,
    *,
    uretim_kollari: Sequence[str] = URETIM_KOLLARI,
    kafes_dahil: bool = False,
    epsilon_mm: float = 0.5,
    exclude_instance_ids: Optional[set] = None,
    mevcut_ids: Optional[set] = None,
    istatistik: Optional[dict] = None,
) -> List[TrainingRow]:
    """M4 etiket satırları -> TrainingRow listesi (instance_id sıralı).

    Aynı benzersiz-kimliğe birden çok satır düşerse SON satır kazanır
    (append-only dosyada en yeni koşu).
    """
    exclude = exclude_instance_ids or set()
    mevcut = mevcut_ids or set()
    ist = istatistik if istatistik is not None else {}
    for k in ("m4_n_satir", "m4_n_tekrar_satir", "m4_n_kafes_kol_atlandi",
              "m4_n_invalid_kol", "m4_n_legal_armsiz", "m4_n_heldout_dislanan",
              "m4_n_id_cakisan", "m4_n_ozelliksiz"):
        ist.setdefault(k, 0)

    secili: Dict[str, dict] = {}
    for satir in satirlar:
        if satir.get("instance_id") is None:
            continue
        ist["m4_n_satir"] += 1
        uid = m4_benzersiz_id(satir)
        if uid in secili:
            ist["m4_n_tekrar_satir"] += 1
        secili[uid] = satir  # son satır kazanır

    tablo: List[TrainingRow] = []
    for uid in sorted(secili):
        satir = secili[uid]
        if uid in exclude or satir.get("instance_id") in exclude:
            ist["m4_n_heldout_dislanan"] += 1
            continue
        if uid in mevcut:
            ist["m4_n_id_cakisan"] += 1
            continue
        arms = satir.get("arms") or {}
        invalid = satir.get("invalid_reasons") or {}
        izinli = set(uretim_kollari) | (set(KAFES_KOLLARI) if kafes_dahil
                                        else set())
        legal: Dict[str, float] = {}
        for kol, veri in arms.items():
            if kol not in izinli:
                ist["m4_n_kafes_kol_atlandi"] += 1
                continue
            if not isinstance(veri, dict) or veri.get("height_mm") is None:
                ist["m4_n_invalid_kol"] += 1
                continue
            if invalid.get(kol) is not None:
                ist["m4_n_invalid_kol"] += 1
                continue
            arm = ARM_ESDEGER.get(kol, kol)
            h = float(veri["height_mm"])
            if arm not in legal or h < legal[arm]:
                legal[arm] = h
        if not legal:
            ist["m4_n_legal_armsiz"] += 1
            continue
        oz = feature_resolver(satir)
        if oz is None:
            ist["m4_n_ozelliksiz"] += 1
            continue
        values, names = oz
        best = min(legal.values())
        winner = min(a for a, h in legal.items() if h == best)
        hm = legal.get(HEIGHTMAP_ARM)
        tablo.append(TrainingRow(
            instance_id=uid,
            is_easy=(hm is not None) and (hm - best < epsilon_mm),
            winner=winner,
            dblf_height=hm,
            best_height=best,
            feature_vector=[float(x) for x in values],
            feature_names=list(names),
            aile=satir.get("aile") or "unknown",
            per_solver_heights=dict(sorted(legal.items())),
        ))
    return tablo

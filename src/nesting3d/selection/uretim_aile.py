"""uretim_aile.py — egitim satiri -> URETIM ailesi (classify_prelim) + uretim
KURAL kolu + kapili-karar LOO + guvenli-aile secimi + karar-probu.

AC-10 (2026-09-02, YONTEM 3.1 16:10): mode_model allowlist'i m4/devset etiket
adlariyla (devset_plan3, thin_plates...) yaziliyor, uretim ise
`karar(features, classify_prelim(instance))` ile URETIM aile adiyla
(thin_shell/tube/thin_plate/long_rod/solid_bulk/mixed_scale) soruyordu ->
kapi HIC acilmadi. Ayrica yarismalar ham `predict` regret'ini olctu; uretim
semantigi (conformal-tekil AND allowlist -> model, aksi KURAL) hic olculmedi.

Bu modul egitim tarafini uretim semantigine baglar:
  - satir_uretim_bilgisi: her egitim satiri icin uretim ailesi + gercek
    uretim kural kolu (instance yeniden kurulur; predict_nfv_benefit ile).
  - kapili_loo: uretim semantigiyle LOO regret (aile kirilimli).
  - guvenli_aileler_sec: LOO'da model <= kural olan uretim aileleri.
  - karar_probu: yuklu artefaktin egitim satirlarinda konusma orani
    (0 ise promote OLU — RUNBOOK P-7).
stdlib + mevcut secici API'leri; saf ASCII log.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Set, Tuple

from src.nesting3d.selection.dataset import TrainingRow

URETIM_AILELERI = frozenset(
    {"thin_shell", "tube", "thin_plate", "long_rod", "solid_bulk", "mixed_scale"})

_M4_ID = re.compile(r"^m4_(.+)_s(\d+)@(\w+)$")
_DEVSET_ID = re.compile(r"^devset_(\w+?)(?:@\w+)?$")
_DEVSET_ADLARI = ("plan1", "plan2", "plan3", "deneme4", "deneme5")


def mode_decision_kolu(dec: Any) -> str:
    """ModeDecision -> etiket kol adi (m4_koprusu ARM_ESDEGER ile ayni dil):
    heightmap -> "heightmap"; nfv+max -> "nfv_max"; nfv (fast/None) ->
    "nfv_kalite" (uretim kalite yolu = fast recete)."""
    mode = str(getattr(dec, "mode", "") or "")
    if mode != "nfv":
        return "heightmap"
    q = getattr(dec, "nfv_quality", None)
    return "nfv_max" if str(q or "").lower() == "max" else "nfv_kalite"


def instance_kur(instance_id: str, aile: str, builders: Dict[str, Callable],
                 devset_builder: Callable, stl_dir=None, seed: int = 42):
    """instance_id/aile -> NestingInstance (m4 sentetik / devset / telemetri
    devset-adi / fsm610). Kurulamazsa None (satir uretim-bilgisiz kalir)."""
    m = _M4_ID.match(instance_id)
    if m:
        b = builders.get(m.group(1))
        return b(int(m.group(2)), m.group(3), stl_dir) if b else None
    d = _DEVSET_ID.match(instance_id)
    if d and d.group(1) in _DEVSET_ADLARI:
        return devset_builder(d.group(1))(seed, "gercek", stl_dir)
    kok = instance_id.split("@")[0]
    if kok in _DEVSET_ADLARI:
        return devset_builder(kok)(seed, "gercek", stl_dir)
    b = builders.get(aile) or builders.get(kok)
    if b:
        return b(seed, "gercek", stl_dir)
    return None


def satir_uretim_bilgisi(table: Sequence[TrainingRow], *,
                         builders: Dict[str, Callable], devset_builder: Callable,
                         classify: Callable, kural_fn: Callable,
                         kural_map: Optional[Dict[str, str]] = None,
                         stl_dir=None, log: Callable = print
                         ) -> Dict[str, Dict[str, Any]]:
    """Her satir -> {"uretim_aile": str|None, "kural_arm": str|None, "kaynak"}.
    Oncelik: instance kurulursa classify + kural_fn(instance) (GERCEK uretim
    kurali); kurulamazsa aile zaten uretim adiysa o, kural regret_raporu
    haritasindan (kural_map) — yoksa None (KURAL bilinmiyor; kiyasa girmez)."""
    kural_map = kural_map or {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in table:
        bilgi: Dict[str, Any] = {"uretim_aile": None, "kural_arm": None,
                                 "kaynak": "yok"}
        inst = None
        try:
            inst = instance_kur(r.instance_id, r.aile, builders,
                                devset_builder, stl_dir)
        except Exception as exc:  # noqa: BLE001 — satir bilgisiz kalir
            log(f"UYARI uretim-bilgi instance kurulamadi {r.instance_id}: "
                f"{type(exc).__name__}: {str(exc)[:80]}")
        if inst is not None:
            try:
                bilgi["uretim_aile"] = str(classify(inst)[0])
                bilgi["kural_arm"] = mode_decision_kolu(kural_fn(inst))
                bilgi["kaynak"] = "instance"
            except Exception as exc:  # noqa: BLE001
                log(f"UYARI uretim-bilgi hesaplanamadi {r.instance_id}: "
                    f"{type(exc).__name__}: {str(exc)[:80]}")
        if bilgi["uretim_aile"] is None and r.aile in URETIM_AILELERI:
            bilgi["uretim_aile"] = r.aile
            bilgi["kaynak"] = "telemetri-aile"
        if bilgi["kural_arm"] is None:
            km = kural_map.get(r.instance_id) or kural_map.get(
                r.instance_id.split("@")[0])
            if km:
                bilgi["kural_arm"] = str(km)
                bilgi["kaynak"] += "+kural_map"
        out[r.instance_id] = bilgi
    return out


def _regret(r: TrainingRow, pred: Optional[str]) -> float:
    hs = r.per_solver_heights or {}
    if not hs:
        return 0.0
    best = min(hs.values())
    if pred in hs:
        return float(hs[pred] - best)
    return float(max(hs.values()) - best)   # kotumser ceza (mod_yarismasi)


def kapili_loo(table: Sequence[TrainingRow], bilgi: Dict[str, Dict[str, Any]],
               base_factory: Callable, alpha: float, allow: Iterable[str],
               conformal_cls: Optional[type] = None) -> Dict[str, Any]:
    """Uretim semantigiyle LOO: conformal esigi tam-tablo LOO skorlarindan
    (alpha'ya bagli tek quantile), taban model dis-LOO; karar =
    uretim_aile in allow AND kume tekil -> model, aksi KURAL (kural_arm;
    bilinmiyorsa satir KIYAS DISI sayilir ve 'kural_bilinmeyen' sayilir)."""
    from src.nesting3d.selection.conformal import ConformalSelector, _arm_skorlari
    if conformal_cls is None:
        conformal_cls = ConformalSelector
    allow = set(allow)
    conf = conformal_cls(base_factory, alpha=alpha)
    conf.fit(list(table))
    q = conf._esik()
    aile: Dict[str, Dict[str, float]] = {}
    toplam_model = 0.0
    toplam_kural = 0.0
    n_kiyas = 0
    konustu = 0
    isabet = 0
    kural_bilinmeyen = 0
    for i, r in enumerate(table):
        b = bilgi.get(r.instance_id, {})
        fam = b.get("uretim_aile") or "?"
        kural = b.get("kural_arm")
        if kural is None:
            kural_bilinmeyen += 1
            continue
        m = base_factory()
        m.fit(list(table[:i]) + list(table[i + 1:]))
        p = _arm_skorlari(m, r.feature_vector)
        kume = {a for a in conf._armlar if 1.0 - p.get(a, 0.0) <= q}
        if not kume and p:
            kume = {max(p, key=p.get)}
        k = fam in allow and len(kume) == 1
        pred = next(iter(kume)) if k else kural
        rg_m = _regret(r, pred)
        rg_k = _regret(r, kural)
        d = aile.setdefault(fam, {"n": 0, "kural": 0.0, "model": 0.0,
                                  "konustu": 0, "isabet": 0})
        d["n"] += 1
        d["kural"] += rg_k
        d["model"] += rg_m
        if k:
            d["konustu"] += 1
            konustu += 1
            if pred == r.winner:
                d["isabet"] += 1
                isabet += 1
        toplam_model += rg_m
        toplam_kural += rg_k
        n_kiyas += 1
    return {"esik": q, "alpha": alpha, "n": n_kiyas,
            "kural_bilinmeyen": kural_bilinmeyen,
            "regret_model": (toplam_model / n_kiyas) if n_kiyas else None,
            "regret_kural": (toplam_kural / n_kiyas) if n_kiyas else None,
            "konustu": konustu, "isabet": isabet,
            "aile": {f: {**d, "kural_ort": d["kural"] / d["n"],
                         "model_ort": d["model"] / d["n"]}
                     for f, d in sorted(aile.items())}}


def guvenli_aileler_sec(table: Sequence[TrainingRow],
                        bilgi: Dict[str, Dict[str, Any]],
                        base_factory: Callable, alpha: float, *,
                        min_n: int = 3, conformal_cls: Optional[type] = None
                        ) -> Tuple[Set[str], Dict[str, Any]]:
    """Guvenli aile = allowlist'siz kapili LOO'da model_ort < kural_ort olan
    (KESIN kucuk: esitlik kanit degildir — 2026-09-02 thin_shell 48,3=48,3
    vakasi) ve n >= min_n URETIM aileleri. Dondurur (kume, rapor)."""
    rapor = kapili_loo(table, bilgi, base_factory, alpha, URETIM_AILELERI,
                       conformal_cls=conformal_cls)
    guvenli = {f for f, d in rapor["aile"].items()
               if f in URETIM_AILELERI and d["n"] >= min_n
               and d["model_ort"] < d["kural_ort"]}
    return guvenli, rapor


def karar_probu(model: Any, table: Sequence[TrainingRow],
                bilgi: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Yuklu artefakt (LoadedModeModel API: karar(features, aile)) egitim
    satirlarinda uretim ailesiyle kac kez konusuyor? konustu==0 -> OLU."""
    n = 0
    konustu = 0
    isabet = 0
    aileler: Dict[str, int] = {}
    for r in table:
        fam = (bilgi.get(r.instance_id) or {}).get("uretim_aile")
        if not fam:
            continue
        n += 1
        s = model.karar(list(r.feature_vector), fam)
        if s is not None:
            konustu += 1
            aileler[fam] = aileler.get(fam, 0) + 1
            if s[0] == r.winner:
                isabet += 1
    return {"n": n, "konustu": konustu, "isabet": isabet, "aileler": aileler,
            "olu": konustu == 0}

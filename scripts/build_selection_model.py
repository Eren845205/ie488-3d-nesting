"""scripts/build_selection_model.py — Telemetriyi oku, prefilter+model egit, raporla.

Kullanim:
    python -m scripts.build_selection_model
    python -m scripts.build_selection_model --jsonl data/telemetry/runs.jsonl

Cikti:
  - Ogrenilenkulrallar (prefilter + model aciklamasi)
  - DONUST degerlendirme: selector vs hep-DBLF(SBS) vs hep-portfoy-oracle(VBS)
  - Veri yetersizse acik uyari (sahte dogruluk uydurma yok)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Proje koku sys.path'e ekle (dogrudan betik olarak calistirilinca)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.telemetry import load_telemetry
from src.nesting3d.selection.dataset import build_training_table
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.persistence import save_selection_model


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

DEFAULT_JSONL = _ROOT / "data" / "telemetry" / "runs.jsonl"
MIN_INSTANCES_FOR_HOLDOUT = 10  # bu altinda hold-out anlamli degil
MIN_INSTANCES_FOR_MODEL = 4     # bu altinda model ogrenilemez


# ---------------------------------------------------------------------------
# Degerlendir: SBS (hep-DBLF), VBS (oracle), Selector
# ---------------------------------------------------------------------------

def _evaluate(
    table,
    prefilter: EasyInstancePrefilter,
    model: AlgorithmSelector,
    *,
    holdout_ids: set,
) -> dict:
    """Hold-out kume uzerinde SBS / VBS / selector karsilastirmasi.

    Returns dict: {
      n_holdout, sbs_mean, vbs_mean, selector_mean,
      selector_vs_sbs_pct, selector_vs_vbs_pct,
      instance_details: list[dict]
    }
    """
    holdout = [r for r in table if r.instance_id in holdout_ids]
    if not holdout:
        return {"n_holdout": 0}

    details = []
    for row in holdout:
        sbs_h = row.dblf_height if row.dblf_height is not None else row.best_height
        vbs_h = row.best_height

        # Selector karar simule et (gercek cozucu calistirmadan)
        is_easy, easy_conf = prefilter.predict(row.feature_vector)
        if is_easy and easy_conf >= 0.7:
            sel_h = sbs_h  # kolay: DBLF
            sel_path = "easy_dblf"
        else:
            sol_name, conf = model.predict(row.feature_vector)
            psh = row.per_solver_heights or {}
            if conf < 0.6:
                # Guvensiz: gercek uretimde TUM portfoy kosar ve en iyiyi alir.
                # Sparse telemetride best_height (oracle) yaniltici-dusuk olur;
                # bu yol VBS savunulabilir AMA kosulan cozuculerin GERCEK min'ini
                # kullaniyoruz -- olmayan cozucu skorunu kredilendirmiyoruz.
                sel_h = min(psh.values()) if psh else vbs_h
                sel_path = "full_portfolio"
            else:
                # Secili cozucu: O COZUCUNUN GERCEK kaydedilmis yuksekligini kullan
                # (oracle-best DEGIL -- aksi halde selector_mean yapay duser ve
                # kapi kotu modeli promote edebilir). Cozucu telemetride yoksa
                # konservatif DBLF baseline'a (sbs_h) dusulur.
                sel_path = f"selected:{sol_name}"
                sel_h = psh.get(sol_name, sbs_h)

        details.append({
            "instance_id": row.instance_id,
            "sbs_h": sbs_h,
            "vbs_h": vbs_h,
            "sel_h": sel_h,
            "path": sel_path,
        })

    n = len(holdout)
    sbs_mean = sum(d["sbs_h"] for d in details) / n
    vbs_mean = sum(d["vbs_h"] for d in details) / n
    sel_mean = sum(d["sel_h"] for d in details) / n

    def pct_gain(base, sel):
        if abs(base) < 1e-9:
            return 0.0
        return (base - sel) / base * 100.0

    return {
        "n_holdout": n,
        "sbs_mean": sbs_mean,
        "vbs_mean": vbs_mean,
        "selector_mean": sel_mean,
        "selector_vs_sbs_pct": pct_gain(sbs_mean, sel_mean),
        "selector_vs_vbs_pct": pct_gain(vbs_mean, sel_mean),
        "instance_details": details,
    }


# ---------------------------------------------------------------------------
# Hold-out bolme (deterministik: son %20, min 1 instance)
# ---------------------------------------------------------------------------

def _split(table, holdout_ratio: float = 0.2):
    n = len(table)
    if n == 0:
        return [], []
    n_holdout = max(1, round(n * holdout_ratio))
    # Son n_holdout instance -> hold-out (sirali, deterministik)
    train = table[: n - n_holdout]
    holdout = table[n - n_holdout:]
    return train, holdout


# ---------------------------------------------------------------------------
# Ana
# ---------------------------------------------------------------------------

def main(jsonl_path: Path, save_path: Path | None = None) -> None:
    print("=" * 70)
    print("build_selection_model.py — Algoritma Secim Modeli Olusturucu")
    print("=" * 70)

    # 1. Telemetri yukle
    rows = load_telemetry(jsonl_path)
    print(f"\n[1] Telemetri: {len(rows)} satir, dosya: {jsonl_path}")

    if not rows:
        print("  UYARI: Telemetri bos. Model kurulamaz.")
        print("  ONERI: Benchmark calistirin (scripts/benchmark.py).")
        return

    # 2. Egitim tablosu
    table = build_training_table(rows, epsilon_mm=0.5)
    n_instances = len(table)
    n_easy = sum(1 for r in table if r.is_easy)
    n_hard = n_instances - n_easy

    print(f"\n[2] Egitim tablosu: {n_instances} instance")
    print(f"    Kolay (is_easy=True):  {n_easy}")
    print(f"    Zor  (is_easy=False): {n_hard}")
    print(f"    Cozucu dagilimi (kazananlar):")
    winner_counts: dict = {}
    for r in table:
        winner_counts[r.winner] = winner_counts.get(r.winner, 0) + 1
    for s, c in sorted(winner_counts.items(), key=lambda x: -x[1]):
        print(f"      {s}: {c} instance")

    # Veri yetersizlik uyarisi
    if n_instances < MIN_INSTANCES_FOR_MODEL:
        print(
            f"\n  UYARI: Cok az instance ({n_instances} < {MIN_INSTANCES_FOR_MODEL}). "
            f"Model anlamsiz. Fallback: tam portfoy."
        )
        print("  ONERI: Daha fazla benchmark kosusu yapilsin.")
        return

    # 3. Hold-out bolme
    if n_instances >= MIN_INSTANCES_FOR_HOLDOUT:
        train_table, holdout_table = _split(table)
        print(
            f"\n[3] Hold-out bolme: train={len(train_table)}, "
            f"holdout={len(holdout_table)}"
        )
    else:
        train_table = table
        holdout_table = []
        print(
            f"\n[3] Hold-out: ATLANDI (n={n_instances} < "
            f"{MIN_INSTANCES_FOR_HOLDOUT}). "
            f"Tum veri egitimde kullaniliyor. "
            f"Sahte dogruluk HESAPLANMIYOR."
        )

    # 4. Model egit
    prefilter = EasyInstancePrefilter()
    prefilter.fit(train_table)

    model = AlgorithmSelector()
    model.fit(train_table)

    print("\n[4] Ogrenilenkulrallar:")
    print(f"    Prefilter: {prefilter.explain()}")
    print(f"    Model:     {model.explain()}")

    # 4b. Kaydet (--save verilmisse)
    if save_path is not None:
        save_selection_model(prefilter, model, save_path)
        print(f"\n[4b] Artefakt kaydedildi: {save_path}")

    # 5. Hold-out degerlendirmesi
    if holdout_table:
        holdout_ids = {r.instance_id for r in holdout_table}
        eval_result = _evaluate(table, prefilter, model, holdout_ids=holdout_ids)
        print(f"\n[5] Hold-out Degerlendirme (n={eval_result['n_holdout']}):")
        print(f"    SBS (hep-DBLF):         {eval_result['sbs_mean']:.4f} mm (ortalama yukseklik)")
        print(f"    VBS (oracle/portfoy):   {eval_result['vbs_mean']:.4f} mm")
        print(f"    Selector (bu model):    {eval_result['selector_mean']:.4f} mm")
        sbs_gain = eval_result["selector_vs_sbs_pct"]
        vbs_gain = eval_result["selector_vs_vbs_pct"]
        sign = lambda x: ("+" if x > 0 else "")
        print(f"    Selector vs SBS:  {sign(sbs_gain)}{sbs_gain:.1f}% iyilestirme")
        print(f"    Selector vs VBS:  {sign(-vbs_gain)}{abs(vbs_gain):.1f}% kayip (0 = oracle kadar iyi)")
        print("\n    Instance detaylari:")
        for d in eval_result["instance_details"]:
            print(
                f"      {d['instance_id']:20s}  sbs={d['sbs_h']:.2f}  "
                f"vbs={d['vbs_h']:.2f}  sel={d['sel_h']:.2f}  "
                f"yol={d['path']}"
            )

        # Dürüst yorum
        if n_instances < MIN_INSTANCES_FOR_HOLDOUT:
            print("\n    NOT: Hold-out istatistikleri az veriyle GURESLEMEZ.")
    else:
        print("\n[5] Hold-out degerlendirmesi atlandi (yetersiz veri).")

    # 6. Ozet / karar
    print("\n[6] Karar / Risk Notu:")
    if n_instances < MIN_INSTANCES_FOR_MODEL:
        print("    KARAR: Model kullanima HAZIR DEGIL. Fallback: tam portfoy.")
    elif n_instances < MIN_INSTANCES_FOR_HOLDOUT:
        print(
            f"    KARAR: Model kuruldu AMA veri az ({n_instances} instance). "
            f"Hold-out guvenilir degil. "
            f"Kullanim icin daha fazla benchmark kosusu ONERILIYOR."
        )
        print("    RISK: Ezber riski yuksek; prefilter konservatif (yanlis-kolay = sadece kayip, yanlis sonuc degil).")
        print("    ONERI: Sentetik uretici ile benchmark calistirin (scripts/benchmark.py) -> 50+ instance hedefle.")
    else:
        print("    KARAR: Model kullanilabilir. Hold-out skoru yukarida.")
        if sbs_gain > 0:
            print(f"    SONUC: Selector SBS'ten {sbs_gain:.1f}% daha iyi.")
        else:
            print("    SONUC: Selector SBS ile es duzey veya geri. Veri arttikca iyilesebilir.")

    print("\n" + "=" * 70)
    print("Tamamlandi.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Telemetriyi oku, selection modeli egit ve raporla."
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=DEFAULT_JSONL,
        help=f"Telemetri JSONL dosyasi (varsayilan: {DEFAULT_JSONL})",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        metavar="PATH",
        help="Egitilmis modeli JSON artefaktina kaydet (ornek: data/selection_model.json)",
    )
    args = parser.parse_args()
    main(args.jsonl, save_path=args.save)

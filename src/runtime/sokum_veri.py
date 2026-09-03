"""sokum_veri.py — nesting sonuc dict'ini rehberli-sokum veri sozlesmesine cevirir.

nesting_results[bid] (parca_kimlik / sokum_sirasi / sokum_plani /
siparis_ozeti) -> build_rehberli_sokum_html'in bekledigi "data" dict'i
(meta / siparisler / adimlar / kilitli). Bu modul yalniz VERI DONUSUMU
yapar — motor koduna (src/nesting3d/) BAGIMLILIK yoktur.

sokum_sirasi gecikmis-uyumluluk: entry hem duz string (part_id) hem de
dict ({"part_id":..., "yon": "+X"}) olabilir (duz-cekme yon alani ana
hatta YENI ekleniyor) — alan yoksa "+Z" varsayilana duser, COKMEZ.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _adim_yon_ve_pid(entry: Any) -> "tuple[Optional[str], Optional[str]]":
    """sokum_sirasi ogesinden (part_id, yon) cikar — string veya dict kabul eder."""
    if isinstance(entry, dict):
        return entry.get("part_id"), entry.get("yon")
    return entry, None


def _adimlar_uret(nr: Dict[str, Any]) -> List[Dict[str, Any]]:
    kimlik = nr.get("parca_kimlik") or {}
    sira = nr.get("sokum_sirasi") or []
    plan_by_pid = {
        e.get("part_id"): e for e in (nr.get("sokum_plani") or []) if e.get("part_id")
    }

    adimlar: List[Dict[str, Any]] = []
    for i, entry in enumerate(sira):
        pid, yon_duz = _adim_yon_ve_pid(entry)
        if pid is None:
            continue
        k = kimlik.get(pid) or {}
        plan = plan_by_pid.get(pid)
        if plan:
            yontem = "dondurmeli"
            yon = plan.get("yon") or "+Z"
            dondurme = {
                "eksen": plan.get("eksen") or "Z",
                "aci_deg": float(plan.get("aci_deg") or 0.0),
                "lift_mm": float(plan.get("lift_vox") or 0.0),
            }
        else:
            yontem = "duz"
            yon = yon_duz or "+Z"  # alan yoksa varsayilan — cokmez
            dondurme = None
        adimlar.append({
            "sira": i + 1,
            "part_id": pid,
            "ad": k.get("ad") or pid,
            "kopya": k.get("kopya_no"),
            "siparis": k.get("order_id"),
            "yontem": yontem,
            "yon": yon,
            "dondurme": dondurme,
            "node": pid,
        })
    return adimlar


def sokum_veri_hazirla(kayit: Dict[str, Any], nr: Dict[str, Any]) -> Dict[str, Any]:
    """Bir gecmis kaydi + tek partinin nesting sonucundan rehberli-sokum
    veri sozlesmesini uretir (bkz. modul docstring / gorev sozlesmesi)."""
    adimlar = _adimlar_uret(nr)
    n_duz = sum(1 for a in adimlar if a["yontem"] == "duz")
    n_dondurmeli = sum(1 for a in adimlar if a["yontem"] == "dondurmeli")

    siparisler = [
        {"id": o.get("order_id"), "musteri": o.get("musteri")}
        for o in (nr.get("siparis_ozeti") or [])
    ]

    meta = {
        "etiket": kayit.get("musteri") or kayit.get("id") or "",
        "yukseklik_mm": nr.get("height_mm"),
        "n_parca": nr.get("n_parts", len(adimlar)),
        "clearance_mm": nr.get("clearance_mm", nr.get("min_clearance_mm")),
        "n_duz": n_duz,
        "n_dondurmeli": n_dondurmeli,
        "uretim_notu": f"nesting motoru, {kayit.get('zaman', '')}".strip(", "),
    }

    return {
        "meta": meta,
        "siparisler": siparisler,
        "adimlar": adimlar,
        "kilitli": [],
    }

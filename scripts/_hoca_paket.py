# -*- coding: utf-8 -*-
"""_hoca_paket.py — held-out / musteri teslim paketi yardimcisi.

evaluate_set(export_cb=...) paketinden (bkz. scripts/eval_gate.py) hoca
teslim dosyalarini uretir:

  <etiket>_yerlesim.stl     multi-solid ASCII STL — her solid'in adi parca
                            kimligi tasir (hoca istegi 2026-07-06: STL icinde
                            parca adi/adet gorunsun; Magics multi-solid'i
                            ayri parcalar olarak acar).
  <etiket>_placements.json  deterministik yerlesim dokumu (arsiv + yeniden
                            uretim; k47c deseni).
  <etiket>_sokum_plani.json adim adim sokum plani (makine-okur).
  <etiket>_sokum_plani.md   ayni planin insan-okur Turkce ozeti.

Kimlik esleme kurali (m{i} sozlesmesi, nfv_solve/demo_pipeline ile ayni):
meshes[i] <-> placements[i]; rot sertifika anahtari "m{i}" -> placements[i].

Not: bu modul OLCUM YOLUNA DOKUNMAZ — evaluate_set metrikleri olusduktan
sonra cagrilir (export_cb). SAF ASCII stdout; dosya icerikleri UTF-8.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_AD_TEMIZ = re.compile(r"[^A-Za-z0-9_.\-]+")


def _guvenli_ad(s) -> str:
    """STL solid adi icin ASCII/tek-parca guvenli isim."""
    return _AD_TEMIZ.sub("_", str(s)).strip("_") or "parca"


def solid_adi(vp, part_id) -> str:
    """Solid adi: insan-okur model adi + benzersiz instance kimligi."""
    ad = getattr(vp, "name", None) or str(part_id)
    uid = getattr(vp, "parca_uid", None) or str(part_id)
    if str(ad) == str(uid):
        return _guvenli_ad(uid)
    return _guvenli_ad(f"{ad}__{uid}")


def _solid_bloku(mesh, ad: str) -> str:
    """Tek mesh'in ASCII STL govdesi, solid adi `ad` ile."""
    txt = mesh.export(file_type="stl_ascii")
    if isinstance(txt, bytes):
        txt = txt.decode("ascii", errors="replace")
    lines = txt.splitlines()
    i0 = next(i for i, l in enumerate(lines) if l.lstrip().startswith("solid"))
    i1 = max(i for i, l in enumerate(lines) if l.lstrip().startswith("endsolid"))
    lines[i0] = f"solid {ad}"
    lines[i1] = f"endsolid {ad}"
    return "\n".join(lines[i0:i1 + 1])


def multi_solid_stl_yaz(meshes, adlar, out_path) -> Path:
    """Multi-solid ASCII STL: her parca kendi adiyla ayri solid blogu."""
    if len(meshes) != len(adlar):
        raise ValueError(f"mesh sayisi ({len(meshes)}) != ad sayisi "
                         f"({len(adlar)}) — esleme bozuk, STL yazilamaz")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="ascii", newline="\n") as fh:
        for mesh, ad in zip(meshes, adlar):
            fh.write(_solid_bloku(mesh, ad))
            fh.write("\n")
    return out_path


def _binary_stl_adli(mesh, ad: str) -> bytes:
    """Binary STL; 80-byte header'a parca adi yazilir (mail_ingest'in
    okudugu konvansiyon — dosya adi kaybolsa da kimlik iceride kalir)."""
    data = bytearray(mesh.export(file_type="stl"))
    baslik = _guvenli_ad(ad).encode("ascii", errors="replace")[:79]
    data[0:80] = baslik + b" " * (80 - len(baslik))
    return bytes(data)


def tip_binary_stl_yaz(meshes, placements, parts, out_dir, etiket) -> dict:
    """Model tipi basina TEK binary STL (tum kopyalar yerlestirilmis pozda).

    Buyuk setlerde ASCII multi-solid dosyasi GB'lara sisiyor (Plan7:
    345 instance x buyuk kaynak mesh ~ 870MB binary esdegeri); tip-basina
    binary + dosya adinda ad/adet ayni kimlik bilgisini tasinabilir boyutta
    verir. STL koordinatlari mutlak — Magics'e birlikte import edilince
    yerlesim aynen kurulur."""
    import trimesh

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gruplar: dict = {}
    for i, pl in enumerate(placements):
        vp = parts.get(getattr(pl, "part_id", None))
        ad = getattr(vp, "name", None) or str(getattr(pl, "part_id", i))
        gruplar.setdefault(str(ad), []).append(meshes[i])
    yollar = {}
    for ad, grup in gruplar.items():
        birlesik = (trimesh.util.concatenate(grup)
                    if len(grup) > 1 else grup[0])
        yol = out_dir / f"{etiket}_{_guvenli_ad(ad)}_{len(grup)}adet.stl"
        yol.write_bytes(_binary_stl_adli(birlesik, f"{ad} x{len(grup)}"))
        yollar[str(ad)] = str(yol)
    return yollar


def _mesh_idx(anahtar) -> int | None:
    """'m{i}' sozlesme anahtarindan indeks; uymayan anahtar None."""
    s = str(anahtar)
    if s.startswith("m"):
        try:
            return int(s[1:])
        except ValueError:
            return None
    return None


def _cert_alanlari(cert) -> dict:
    return {
        "eksen": getattr(cert, "eksen", None) if not isinstance(cert, dict)
        else cert.get("eksen"),
        "aci_deg": float((cert.get("aci_deg") if isinstance(cert, dict)
                          else getattr(cert, "aci_deg", 0.0)) or 0.0),
        "yon": (cert.get("yon") if isinstance(cert, dict)
                else getattr(cert, "yon", None)),
        "lift_vox": int((cert.get("lift_vox") if isinstance(cert, dict)
                         else getattr(cert, "lift_vox", 0)) or 0),
    }


def sokum_plani_derle(paket: dict) -> dict:
    """export_cb paketinden sokum planini derle.

    Kaynak onceligi: (1) rot_rep (ayni kosuda yeniden denetim — en taze),
    (2) nfv_tel.rot_kabul.sokum_plani (solve icindeki kabul denetimi),
    (3) nfv_tel.r11.sokum_plani. Hicbiri yoksa ve 5-yon kilit 0 ise tum
    parcalar duz +Z ceker (denetim kaniti: n_locked=0)."""
    placements = paket.get("placements") or []
    parts = paket.get("voxel_parts") or {}
    metrik = paket.get("metrikler") or {}
    tel = paket.get("nfv_tel") or {}

    def _kimlik(i):
        pl = placements[i]
        pid = getattr(pl, "part_id", None)
        vp = parts.get(pid)
        return {"part_id": pid,
                "ad": getattr(vp, "name", None) or str(pid),
                "kopya_no": int(getattr(vp, "kopya_no", 0) or 0),
                "siparis": getattr(vp, "order_id", None)}

    dondurmeli = []
    cikis_sirasi = None
    rot_rep = paket.get("rot_rep")
    if rot_rep is not None and getattr(rot_rep, "certificates", None):
        for anahtar, cert in rot_rep.certificates.items():
            i = _mesh_idx(anahtar)
            kayit = (_kimlik(i) if i is not None and i < len(placements)
                     else {"part_id": str(anahtar), "ad": str(anahtar),
                           "kopya_no": 0, "siparis": None})
            kayit.update(_cert_alanlari(cert))
            dondurmeli.append(kayit)
        sira = list(getattr(rot_rep, "removable_order", None) or [])
        if sira:
            cikis_sirasi = []
            for anahtar in sira:
                i = _mesh_idx(anahtar)
                cikis_sirasi.append(
                    _kimlik(i)["part_id"] if i is not None
                    and i < len(placements) else str(anahtar))
    else:
        kaynak = ((tel.get("rot_kabul") or {}).get("sokum_plani")
                  or (tel.get("r11") or {}).get("sokum_plani"))
        for e in kaynak or []:
            e = dict(e)
            i = e.pop("mesh_idx", None)
            if e.get("part_id") is None and i is not None \
                    and 0 <= int(i) < len(placements):
                e.update(_kimlik(int(i)))
            e.setdefault("ad", e.get("parca") or e.get("part_id"))
            dondurmeli.append(e)
        cikis_sirasi = (tel.get("rot_kabul") or {}).get("sokum_sirasi")

    dondurmeli_idler = {e.get("part_id") for e in dondurmeli}
    duz_cekme = [_kimlik(i) for i in range(len(placements))
                 if _kimlik(i)["part_id"] not in dondurmeli_idler]

    return {
        "kilit_5yon": metrik.get("n_locked"),
        "rot_kilit": metrik.get("n_locked_rot"),
        "sokum_planli": bool(metrik.get("sokum_planli")),
        "n_parca": len(placements),
        "n_duz_cekme": len(duz_cekme),
        "n_dondurmeli": len(dondurmeli),
        "duz_cekme": duz_cekme,
        "dondurmeli": dondurmeli,
        "cikis_sirasi": cikis_sirasi,
        "aciklama": ("5-yon denetimi: parca herhangi bir turda +-X/+-Y/+Z "
                     "yonunden engelsiz cekilerek cikar; 'dondurmeli' "
                     "parcalar sertifikali eksen/aci ile hafif dondurulerek "
                     "cikar (rot-sokum denetimi, ~1mm voxel cozunurlugu)."),
    }


def _sokum_md(plan: dict, metrik: dict, etiket: str) -> str:
    """Insan-okur Turkce sokum plani (hoca paketi)."""
    s = [f"# Söküm Planı — {etiket}", ""]
    lh = metrik.get("legal_height_mm")
    s.append(f"- Yerleşim yüksekliği: **{lh} mm**" if lh is not None
             else f"- SONUÇ GEÇERSİZ: {metrik.get('invalid_reason')}")
    s.append(f"- Parça sayısı: {plan['n_parca']} "
             f"(yerleşen {metrik.get('n_placed')}/{metrik.get('n_total')})")
    s.append(f"- Minimum parça arası boşluk: "
             f"{metrik.get('min_clearance_mm'):.2f} mm"
             if metrik.get("min_clearance_mm") is not None else
             "- Minimum parça arası boşluk: ölçülmedi")
    s.append(f"- Doğrudan çekilerek çıkan parça: {plan['n_duz_cekme']}")
    s.append(f"- Hafif döndürme gerektiren parça: {plan['n_dondurmeli']}")
    s.append("")
    if plan["n_dondurmeli"]:
        s += ["## Döndürme gerektiren parçalar", "",
              "| # | Parça | Eksen | Açı (°) | Çekme yönü | Kaldırma (~mm) |",
              "|---|---|---|---|---|---|"]
        for i, e in enumerate(plan["dondurmeli"], 1):
            s.append(f"| {i} | {e.get('ad')} | {e.get('eksen')} | "
                     f"{e.get('aci_deg'):.0f} | {e.get('yon')} | "
                     f"{e.get('lift_vox')} |")
        s.append("")
        s.append("Bu parçalar dışındaki tüm parçalar sırayla, engelsiz "
                 "yönlerinden (±X, ±Y veya +Z) doğrudan çekilerek çıkar.")
    else:
        s.append("Tüm parçalar doğrudan (döndürmesiz) çekilerek çıkar; "
                 "söküm sırası serbesttir.")
    if plan.get("cikis_sirasi"):
        s += ["", "## Önerilen çıkış sırası", ""]
        s.append(", ".join(str(x) for x in plan["cikis_sirasi"]))
    s += ["", f"_Üretim: nesting motoru, {time.strftime('%Y-%m-%d')}; "
          "söküm denetimi 2 mm boşluk sözleşmesiyle koşuldu._", ""]
    return "\n".join(s)


def paket_uret(paket: dict, out_dir, etiket: str,
               stl_bicim: str = "oto") -> dict:
    """Tam teslim paketi: STL + placements JSON + sokum plani JSON/MD.

    stl_bicim: "oto" (boyuta gore) | "ascii" (multi-solid tek dosya) |
    "tip_binary" (model tipi basina binary). Donus: yazilan dosya yollari +
    ozet sayilar (log icin)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    placements = paket.get("placements") or []
    parts = paket.get("voxel_parts") or {}
    meshes = paket.get("meshes")
    metrik = paket.get("metrikler") or {}

    yollar = {}

    # 1) placements dokumu (k47c deseni — kucuk, her zaman yazilir)
    pl_dump = {
        "etiket": etiket,
        "pitch_mm": paket.get("pitch"),
        "r11_dz": paket.get("dz"),
        "metrikler": {k: v for k, v in metrik.items()
                      if k != "sure_kirilim"},
        "placements": [
            {"part_id": getattr(p, "part_id", None),
             "ad": getattr(parts.get(getattr(p, "part_id", None)), "name",
                           None),
             "siparis": getattr(parts.get(getattr(p, "part_id", None)),
                                "order_id", None),
             "oi": int(getattr(p, "orientation_idx", 0)),
             "x": int(getattr(p, "x", 0)), "y": int(getattr(p, "y", 0)),
             "z": int(getattr(p, "z", 0))}
            for p in placements],
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    p = out_dir / f"{etiket}_placements.json"
    p.write_text(json.dumps(pl_dump, ensure_ascii=True, indent=1),
                 encoding="utf-8")
    yollar["placements_json"] = str(p)

    # 2) sokum plani JSON + MD
    plan = sokum_plani_derle(paket)
    p = out_dir / f"{etiket}_sokum_plani.json"
    p.write_text(json.dumps(plan, ensure_ascii=True, indent=1),
                 encoding="utf-8")
    yollar["sokum_json"] = str(p)
    p = out_dir / f"{etiket}_sokum_plani.md"
    p.write_text(_sokum_md(plan, metrik, etiket), encoding="utf-8")
    yollar["sokum_md"] = str(p)

    # 3) STL (mesh sahnesi olculen sahneyle AYNI: dz'li). Bicim otomatik:
    # kucuk sette ASCII multi-solid TEK dosya (hoca istegi 2026-07-06:
    # ad/adet STL icinde); buyuk sette tip-basina binary (ASCII GB'lara
    # siser — Plan7 ~4-5GB olurdu).
    if meshes:
        toplam_facet = sum(len(m.faces) for m in meshes)
        if stl_bicim == "oto":
            stl_bicim = "ascii" if toplam_facet * 260 <= 200e6 else "tip_binary"
        yollar["stl_bicim"] = stl_bicim
        yollar["toplam_facet"] = int(toplam_facet)
        if stl_bicim == "ascii":
            adlar = [solid_adi(parts.get(getattr(pl, "part_id", None)),
                               getattr(pl, "part_id", None))
                     for pl in placements]
            p = out_dir / f"{etiket}_yerlesim.stl"
            multi_solid_stl_yaz(meshes, adlar, p)
            yollar["stl"] = str(p)
            yollar["stl_mb"] = round(Path(p).stat().st_size / 1e6, 1)
        else:
            tipler = tip_binary_stl_yaz(meshes, placements, parts,
                                        out_dir / f"{etiket}_stl", etiket)
            yollar["stl"] = str(out_dir / f"{etiket}_stl")
            yollar["stl_dosyalari"] = len(tipler)
            yollar["stl_mb"] = round(sum(
                Path(v).stat().st_size for v in tipler.values()) / 1e6, 1)
    else:
        yollar["stl"] = None  # skip_clearance kosusunda mesh uretilmez

    yollar["n_parca"] = len(placements)
    yollar["n_dondurmeli"] = plan["n_dondurmeli"]
    return yollar

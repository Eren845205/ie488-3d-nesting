# -*- coding: utf-8 -*-
"""rehberli_sokum_uret.py — hoca paketi STL'lerinden REHBERLI SOKUM verisi +
GLB + (packer hazirsa) tek-dosya interaktif HTML uretir.

Girdi (cozumu YENIDEN KOSMAZ — paketteki nihai-poz STL'leri kullanir):
  results/hoca_paketi_2026-07/<etiket>_sokum_plani.json   (cikis_sirasi, dondurmeli)
  results/hoca_paketi_2026-07/<etiket>_placements.json    (part_id, siparis, dz)
  deneme6: <etiket>_yerlesim.stl (ASCII multi-solid; solid adi = part_id)
  plan7:   <etiket>_stl/ (tip-basina binary; split + min-kose eslemesi)

Cikti: results/rehberli_sokum/<etiket>_adimlar.json + <etiket>.glb
       + <etiket>_rehberli_sokum.html (src/runtime/rehberli_sokum hazirsa)

Yonler: rapor_5yon_meshes(@1.0) — uretim sokum_sirasi ile ayni mekanik;
removable_yonler ADDITIVE alani (accessibility, 2026-07-26).
Buyuk sahnede FACE_BUTCE asilirsa mesh'ler voxel+marching-cubes ile
kabalastirilir (yalniz GORSEL rehber icin; hassas geometri STL paketinde).

Kosum:  python -m scripts.rehberli_sokum_uret deneme6_68p5
        python -m scripts.rehberli_sokum_uret plan7_488p4
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

def _paket_kok() -> Path:
    """Teslim paketinin bulundugu klasor.

    Paket buyuk (>1GB) oldugundan repo icinde de, repo'nun yanindaki ortak
    `Veriler/` klasorunde de durabilir; ikisi de aranir (2026-07-27: paket
    ortak Veriler'e tasindi). Bulunamazsa repo-ici yol dondurulur ki hata
    mesaji beklenen konumu gostersin.
    """
    adaylar = (_ROOT / "Veriler" / "hoca_paketi_2026-07",
               _ROOT.parent / "Veriler" / "hoca_paketi_2026-07")
    for p in adaylar:
        if p.is_dir():
            return p
    return adaylar[0]


PAKET = _paket_kok()
OUT = _ROOT / "results" / "rehberli_sokum"
FACE_BUTCE = 400_000          # HTML/GLB gorsel butcesi (toplam ucgen)
# 2026-07-27: 1.5M -> 400K. 345 parcalik sahnede 1.8M ucgen tarayicida
# agir kaliyordu (Eren geri bildirimi). 400K = parca basina ~1160 ucgen;
# rehber gorsel amacli, olcuye esas geometri STL paketinde.
ESLEME_TOL_MM = 6.0           # min-kose eslesme toleransi (r11 dz + kuantizasyon)


def log(m=""):
    print(m, flush=True)


# ---------------------------------------------------------------------------
# mesh kaynaklari
# ---------------------------------------------------------------------------

_AD_TEMIZ = re.compile(r"[^A-Za-z0-9_.\-]+")


def _guvenli_ad(s) -> str:
    """_hoca_paket._guvenli_ad ile BIREBIR ayni sanitize (esleme anahtari)."""
    return _AD_TEMIZ.sub("_", str(s)).strip("_") or "parca"


def _ascii_multi_solid_oku(p: Path, placements):
    """ASCII multi-solid STL -> {part_id: trimesh}.

    Solid adi sozlesmesi (_hoca_paket.solid_adi): "<ad>__<uid>" veya "<uid>",
    _guvenli_ad sanitize'iyla. Esleme: solid adinin '__' sonrasi (yoksa tamami)
    == _guvenli_ad(part_id)."""
    log(f"  ascii multi-solid okunuyor: {p.name} ({p.stat().st_size/1e6:.0f}MB)")
    pid_map = {_guvenli_ad(pl["part_id"]): pl["part_id"] for pl in placements}
    metin = p.read_text(encoding="ascii", errors="replace")
    sonuc = {}
    for blok in re.finditer(r"solid[ \t]+(.+?)[ \t]*\r?\n.*?endsolid",
                            metin, re.S):
        solid_ad, govde = blok.group(1).strip(), blok.group(0)
        anahtar = solid_ad.rsplit("__", 1)[-1]
        pid = pid_map.get(anahtar) or pid_map.get(solid_ad)
        if pid is None:
            log(f"  UYARI: solid eslesmedi: {solid_ad}")
            continue
        m = trimesh.load(io.BytesIO(govde.encode("ascii")), file_type="stl")
        sonuc[pid] = m
    log(f"  {len(sonuc)} solid parse edildi + eslendi")
    return sonuc


def _tip_binary_esle(stl_dir: Path, placements):
    """Tip-basina binary STL'leri govdelere ayir, placements'a min-kose ile esle.

    RAM DISIPLINI (2026-07-26 OOM dersi): dosyalar TEK TEK islenir — yukle ->
    split(repair=False; fill_holes cagrilmaz) -> esle -> GEREKIYORSA HEMEN
    kabalastir -> tam-cozunurluk birakilir + gc. Tum tipleri ayni anda RAM'de
    tutmak 16GB makinede OOM verdi (8. dosyada 3MB tahsis reddi).

    Beklenen konum: (x*pitch, y*pitch, z*pitch - dz)  [placed_meshes semantigi:
    oriented grid min-kosesi]. Govde sayisi != adet -> HATA (cok-govdeli parca).
    Doner: (meshes_dict, kaba_pitch_veya_None).
    """
    import gc

    dosyalar = sorted(stl_dir.glob("*.stl"))
    toplam_bytes = sum(f.stat().st_size for f in dosyalar)
    tahmini_ucgen = toplam_bytes / 50.0  # binary STL ~50B/ucgen
    kaba_pitch = None
    kaba_oran = 1.0
    if tahmini_ucgen > FACE_BUTCE:
        oran = kaba_oran = tahmini_ucgen / FACE_BUTCE
        kaba_pitch = max(1.5, round(0.8 * oran ** (1 / 3), 1) + 1.0)
        log(f"  kaynak ~{tahmini_ucgen/1e6:.1f}M ucgen > butce -> "
            f"dosya-basi ANINDA kabalastirma @{kaba_pitch}mm")

    sonuc = {}
    tipler = {pl["ad"] for pl in placements}
    for f in dosyalar:
        m = re.match(r"^(.*)_(\d+)adet\.stl$", f.name)
        if not m:
            raise RuntimeError(f"ad deseni cozulmedi: {f.name}")
        govde, adet = m.group(1), int(m.group(2))
        # Tip adinin kendisi alt cizgi tasiyabilir (ornek: 288101640-a1_1) —
        # bu yuzden tip ad DESENINDEN degil, placements'taki gercek tip
        # adlarina karsi en uzun suffix eslesmesiyle cozulur.
        eslesen = [t for t in tipler if govde == t or govde.endswith("_" + t)]
        if not eslesen:
            raise RuntimeError(
                f"tip cozulmedi: {f.name} — placements'taki adlarla eslesmiyor")
        tip = max(eslesen, key=len)
        log(f"  {f.name}: yukleniyor ({f.stat().st_size/1e6:.0f}MB, {adet} adet)")
        mesh = trimesh.load(f, file_type="stl")
        govdeler = mesh.split(only_watertight=False, repair=False)
        del mesh
        if len(govdeler) != adet:
            raise RuntimeError(
                f"{f.name}: govde={len(govdeler)} != adet={adet} "
                f"(cok-govdeli parca — esleme guvensiz)")
        adaylar = [pl for pl in placements if pl["ad"] == tip]
        if len(adaylar) != adet:
            raise RuntimeError(f"{tip}: placements={len(adaylar)} != adet={adet}")
        bekl = np.array([a["_bekl"] for a in adaylar])
        kullanildi = set()
        for g in govdeler:
            dif = np.linalg.norm(bekl - np.asarray(g.bounds[0]), axis=1)
            for idx in np.argsort(dif):
                if idx not in kullanildi:
                    break
            if dif[idx] > ESLEME_TOL_MM:
                raise RuntimeError(
                    f"{tip}: esleme hatasi {dif[idx]:.2f}mm > {ESLEME_TOL_MM}")
            kullanildi.add(int(idx))
            pid = adaylar[int(idx)]["part_id"]
            if kaba_pitch is not None:
                try:
                    sonuc[pid] = _kaba_mesh(g, kaba_oran, kaba_pitch)
                except Exception as e:
                    log(f"  UYARI {pid}: kabalastirma olmadi "
                        f"({type(e).__name__}) — orijinal kaldi")
                    sonuc[pid] = g
            else:
                sonuc[pid] = g
        del govdeler
        gc.collect()
    return sonuc, kaba_pitch


def _kaba_mesh(mesh, oran: float, pitch: float):
    """Tek mesh'in gorsel kabalastirmasi (hassas geometri STL paketinde kalir).

    Once quadric decimation (fast_simplification): ucgen sayisini `oran` kadar
    duserir, kose konumlarini korur -> konum kaymasi YOK. O yoksa voxel+
    marching-cubes'a duser (skimage gerekir; kurulu olmayabilir). Ikisi de
    yoksa cagiran orijinali tutar.
    """
    hedef = max(200, int(len(mesh.faces) / max(oran, 1.0)))
    aday = None
    if hedef < len(mesh.faces):
        try:
            aday = mesh.simplify_quadric_decimation(face_count=hedef)
        except Exception:
            aday = None
    if aday is not None and len(aday.faces) <= hedef * 1.5:
        return aday
    # Decimation geometrik tabana dayandi (delikli/karmasik yuzey ~%8'in
    # altina inmiyor, 2026-07-27 olcumu). Voxel adayini da uret, KUCUK olani
    # sec: duz plakalarda voxel kazanir, delikli parcalarda decimation.
    # Ince-parca korumasi: adim en ince bbox boyutunun yarisini gecmesin
    # (4mm plaka 3.8mm voxelde yok olur).
    try:
        ep = max(1.0, min(pitch, float(min(mesh.extents)) / 2.0))
        v = mesh.voxelized(ep)
        mc = v.marching_cubes
        mc.apply_translation(np.asarray(mesh.bounds[0])
                             - np.asarray(mc.bounds[0]))
        if aday is None or len(mc.faces) < len(aday.faces):
            return mc
    except Exception:
        pass
    if aday is None:
        raise RuntimeError("decimation ve voxel ikisi de basarisiz")
    return aday


def _kabalastir(meshes: dict):
    """FACE_BUTCE asiliyorsa gorsel kabalastirma (bkz. _kaba_mesh)."""
    toplam = sum(len(m.faces) for m in meshes.values())
    log(f"  toplam ucgen: {toplam:,}")
    if toplam <= FACE_BUTCE:
        return meshes, toplam, None
    oran = toplam / FACE_BUTCE
    pitch = max(1.5, round(0.8 * oran ** (1 / 3), 1) + 1.0)
    log(f"  FACE_BUTCE asildi ({oran:.1f}x) -> voxel-mc kabalastirma @{pitch}mm")
    yeni = {}
    for pid, m in meshes.items():
        try:
            yeni[pid] = _kaba_mesh(m, oran, pitch)
        except Exception as e:
            log(f"  UYARI {pid}: kabalastirma olmadi ({type(e).__name__}) "
                f"— orijinal kaldi")
            yeni[pid] = m
    t2 = sum(len(m.faces) for m in yeni.values())
    log(f"  kabalastirma sonrasi ucgen: {t2:,}")
    return yeni, t2, pitch


# ---------------------------------------------------------------------------


def main(etiket: str, repack: bool = False):
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    if repack:
        # hizli yol: mevcut adimlar.json + glb'den yalniz HTML'i yeniden bas
        # (sablon degisikliklerinde 5-yon/mesh analizini tekrarlama)
        from src.runtime.rehberli_sokum import build_rehberli_sokum_html
        veri = json.loads((OUT / f"{etiket}_adimlar.json")
                          .read_text(encoding="utf-8"))
        glb = (OUT / f"{etiket}.glb").read_bytes()
        hp = OUT / f"{etiket}_rehberli_sokum.html"
        hp.write_text(build_rehberli_sokum_html(veri, glb), encoding="utf-8")
        log(f"REPACK: {hp.name} ({hp.stat().st_size/1e6:.1f}MB)")
        return
    sokum = json.loads((PAKET / f"{etiket}_sokum_plani.json")
                       .read_text(encoding="utf-8"))
    pj = json.loads((PAKET / f"{etiket}_placements.json")
                    .read_text(encoding="utf-8"))
    pitch = float(pj["pitch_mm"])
    dzler = pj.get("r11_dz") or [0.0] * len(pj["placements"])
    placements = []
    for i, pl in enumerate(pj["placements"]):
        pl = dict(pl)
        dz = float(dzler[i]) if i < len(dzler) else 0.0
        pl["_bekl"] = (pl["x"] * pitch, pl["y"] * pitch, pl["z"] * pitch - dz)
        placements.append(pl)
    log(f"[{etiket}] {len(placements)} parca; pitch={pitch}")

    on_kaba_pitch = None
    tek = PAKET / f"{etiket}_yerlesim.stl"
    if tek.exists():
        meshes = _ascii_multi_solid_oku(tek, placements)
    else:
        meshes, on_kaba_pitch = _tip_binary_esle(
            PAKET / f"{etiket}_stl", placements)
    eksik = [pl["part_id"] for pl in placements if pl["part_id"] not in meshes]
    if eksik:
        raise RuntimeError(f"mesh eslesmeyen parcalar: {eksik[:5]} ...")

    # dogrulama: sahne tavani = metriklerdeki yukseklik
    hmax = max(float(m.bounds[1][2]) for m in meshes.values())
    href = float(pj["metrikler"]["height_mm"])
    # voxel-raporlu metrik >= mesh-gercek tavan (bilinen fark ~1-2.5mm, d5
    # METODOLOJI SERHI); esleme suphesi ancak buyuk sapmada.
    log(f"  sahne z-max {hmax:.2f} vs metrik {href:.2f} (voxel-raporlu)")
    if hmax > href + 1.0 or hmax < href - 5.0:
        raise RuntimeError("sahne/metrik yukseklik uyusmuyor — esleme suphesi")

    # yonler (uretimle ayni mekanik: rapor_5yon_meshes @1.0)
    from src.nesting3d.continuous_settle import rapor_5yon_meshes
    # cikis_sirasi paket kaydinda null olabilir (kilit 0 -> "sira serbest");
    # rehber yine de somut bir sira verir: 5-yon denetiminin urettigi sira.
    sira_pid = list(sokum.get("cikis_sirasi") or [])
    log(f"  5-yon denetimi ({len(placements)} mesh @1.0) ...")
    t1 = time.perf_counter()
    rapor = rapor_5yon_meshes([meshes[pl["part_id"]] for pl in placements],
                              pitch=1.0)
    log(f"  5-yon: {time.perf_counter()-t1:.0f}s; "
        f"cikan={len(rapor.removable_order)} kilit={rapor.n_locked}")
    idx2pid = {f"m{i}": pl["part_id"] for i, pl in enumerate(placements)}
    yon_map = {idx2pid[mid]: yon for mid, yon in
               zip(rapor.removable_order, rapor.removable_yonler)}
    yeni_sira = [idx2pid[mid] for mid in rapor.removable_order]
    if not sira_pid:
        # Paket "sira serbest" demis (kilit 0) — rehber somut bir sira verir.
        sira_pid = yeni_sira
    elif yeni_sira != sira_pid:
        # PAKET SIRASI ESASTIR: teslim edilen sokum plani, tam-cozunurluklu
        # gercek cozumun rot-kabul denetiminden gelir ve TUM parcalari kapsar.
        # Buradaki 5-yon kosusu GORSEL sahne uzerinde doner; kabalastirma
        # mesh'leri ~0.5mm sasirtir, 2mm bosluklu sikisik sahnede bu sahte
        # kilit uretir (plan7: 15 gercek kilit -> 95 sahte). Bu yuzden gorsel
        # kosu sira/kapsam kaynagi DEGIL, yalniz yon ipucu kaynagidir.
        log(f"  NOT: gorsel-sahne 5-yon sirasi paketten farkli "
            f"({len(yeni_sira)} vs {len(sira_pid)} parca) — PAKET sirasi esas, "
            f"gorsel kosu yalniz yon ipucu")

    kapsanmayan = [pl["part_id"] for pl in placements
                   if pl["part_id"] not in set(sira_pid)]
    if kapsanmayan:
        log(f"  UYARI: sirada olmayan {len(kapsanmayan)} parca sona eklendi")
        sira_pid = list(sira_pid) + kapsanmayan

    dond = {d["part_id"]: d for d in sokum.get("dondurmeli", [])}
    sip_gorulen = {}
    adimlar = []
    for n, pid in enumerate(sira_pid, 1):
        pl = next(p for p in placements if p["part_id"] == pid)
        kopya = int(pid.rsplit("_", 1)[1]) if "_" in pid else 1
        d = dond.get(pid)
        adimlar.append({
            "sira": n, "part_id": pid, "ad": pl["ad"], "kopya": kopya,
            "siparis": pl.get("siparis"),
            "yontem": "dondurmeli" if d else "duz",
            "yon": (d.get("yon") if d else None) or yon_map.get(pid, "+Z"),
            "dondurme": ({"eksen": d["eksen"], "aci_deg": d["aci_deg"],
                          "lift_mm": float(d.get("lift_vox", 0))} if d else None),
            "node": pid,
        })
        s = pl.get("siparis")
        if s:
            sip_gorulen.setdefault(s, {"id": s, "musteri": None})

    # Rehber, teslim edilen plandaki HER parcayi icermek zorundadir — eksik
    # adim, operatore "bu parca cikmiyor" izlenimi verir ve teslim edilen
    # sokum planiyla celisir (2026-07-26 dersi).
    if len(adimlar) != len(placements):
        raise RuntimeError(
            f"adim sayisi {len(adimlar)} != parca sayisi {len(placements)} "
            f"— rehber eksik kalirdi")

    if on_kaba_pitch is not None:
        kaba_meshes, kaba_pitch = meshes, on_kaba_pitch
        n_face = sum(len(m.faces) for m in kaba_meshes.values())
        log(f"  toplam ucgen (on-kabalastirilmis): {n_face:,}")
    else:
        kaba_meshes, n_face, kaba_pitch = _kabalastir(meshes)
    sahne = trimesh.Scene()
    for pid in sira_pid:
        sahne.add_geometry(kaba_meshes[pid], node_name=pid, geom_name=pid)
    glb = sahne.export(file_type="glb")
    log(f"  GLB: {len(glb)/1e6:.1f}MB ({n_face:,} ucgen"
        + (f", kabalastirma @{kaba_pitch}mm" if kaba_pitch else "") + ")")

    veri = {
        "meta": {"etiket": etiket,
                 "yukseklik_mm": href,
                 "n_parca": len(placements),
                 "clearance_mm": float(pj["metrikler"].get(
                     "min_clearance_mm", 0.0)),
                 "n_duz": sum(1 for a in adimlar if a["yontem"] == "duz"),
                 "n_dondurmeli": sum(1 for a in adimlar
                                     if a["yontem"] == "dondurmeli"),
                 "uretim_notu": "nesting motoru rehberli sokum, 2026-07-26"
                 + (f" (gorsel kabalastirma @{kaba_pitch}mm)" if kaba_pitch
                    else "")},
        "siparisler": list(sip_gorulen.values()),
        "adimlar": adimlar,
        "kilitli": [],
    }
    (OUT / f"{etiket}_adimlar.json").write_text(
        json.dumps(veri, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / f"{etiket}.glb").write_bytes(glb)

    try:
        from src.runtime.rehberli_sokum import build_rehberli_sokum_html
    except Exception:
        log("  packer henuz yok — HTML atlandi (adimlar.json + glb hazir)")
    else:
        html = build_rehberli_sokum_html(veri, glb)
        hp = OUT / f"{etiket}_rehberli_sokum.html"
        hp.write_text(html, encoding="utf-8")
        log(f"  HTML: {hp.name} ({hp.stat().st_size/1e6:.1f}MB)")
    log(f"BITTI ({(time.perf_counter()-t0)/60:.1f} dk)")


if __name__ == "__main__":
    _args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(_args[0] if _args else "deneme6_68p5",
         repack="--repack" in sys.argv)

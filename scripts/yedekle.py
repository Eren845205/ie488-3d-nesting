# -*- coding: utf-8 -*-
"""yedekle.py — algoritma anlik-yedegi (Eren karari 2026-08-30: "her
degisiklik oncesi yedek; geri donulemez duruma dusmeyelim").

Ne yedeklenir (kod + model + karar dokumanlari; VERI ve KOSU CIKTILARI DEGIL):
  src/            tum motor + secim modeli kodu
  scripts/*.py    deney/kosu scriptleri (STL, log, cache haric)
  tests/          regresyon/anchor testleri
  configs/        *.local.json HARIC (kimlik bilgisi)
  data/mode_model.json, data/registry.json, data/selection_archive/
  STRATEJI/, MOTOR/*.md, kok *.md, CLAUDE.md

Nereye: <repo>/yedekler/<zaman>_<git>_<etiket>.zip  +  D:\\ie488\\yedekler\\
(cift kopya). Her zip icinde MANIFEST.json (git HEAD, kirli dosyalar, sha256).
<repo>/yedekler/INDEX.md'ye satir eklenir (append-only).

Kullanim:
  python -m scripts.yedekle --etiket asama2_oncesi      # anlik yedek al
  python -m scripts.yedekle --liste                     # yedekleri listele
  python -m scripts.yedekle --dogrula <zip>             # sha256 dogrula
  python -m scripts.yedekle --geri-yukle <zip>          # yedekler/geri_<ad>/ altina AC
      (yerinde uzerine yazma YOK — geri donus elle/diff ile, bilincli)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
YEDEK_DIR = _ROOT / "yedekler"
D_YEDEK_DIR = Path(r"D:\ie488\yedekler")

KOK_DOSYALAR = ("CLAUDE.md",)
DIZINLER = ("src", "tests", "configs", "STRATEJI")
DATA_DOSYALAR = ("data/mode_model.json", "data/registry.json")
DATA_DIZINLER = ("data/selection_archive",)
HARIC_DIZIN = {"__pycache__", ".pytest_cache", "zincir_stl", ".git"}
HARIC_SON_EK = {".pyc", ".pyo", ".log", ".err", ".out", ".stl", ".glb"}


def _log(m: str = "") -> None:
    try:
        print(m, flush=True)
    except OSError:  # boru kapandi (| head) — yedek akisini bozmasin
        pass


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(_ROOT), capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _uygun(p: Path) -> bool:
    if any(par in HARIC_DIZIN for par in p.parts):
        return False
    if p.suffix.lower() in HARIC_SON_EK:
        return False
    if p.name.endswith(".local.json"):
        return False
    return p.is_file()


def _dosyalar() -> List[Path]:
    secilen: List[Path] = []
    for ad in KOK_DOSYALAR:
        f = _ROOT / ad
        if f.is_file():
            secilen.append(f)
    for f in _ROOT.glob("*.md"):
        if f.is_file():
            secilen.append(f)
    for d in DIZINLER:
        kok = _ROOT / d
        if kok.is_dir():
            secilen += [p for p in kok.rglob("*") if _uygun(p)]
    sd = _ROOT / "scripts"
    if sd.is_dir():
        secilen += [p for p in sd.glob("*.py") if _uygun(p)]
    for ad in DATA_DOSYALAR:
        f = _ROOT / ad
        if f.is_file():
            secilen.append(f)
    for d in DATA_DIZINLER:
        kok = _ROOT / d
        if kok.is_dir():
            secilen += [p for p in kok.rglob("*") if _uygun(p)]
    md = _ROOT / "MOTOR"
    if md.is_dir():
        secilen += [p for p in md.glob("*.md") if p.is_file()]
    # tekillestir + kararli sira
    uniq = sorted({p.resolve() for p in secilen})
    return [Path(p) for p in uniq]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blok in iter(lambda: fh.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def _temiz_etiket(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", s.strip())
    return s.strip("_")[:48] or "yedek"


def yedek_al(etiket: str, not_: str = "") -> Path:
    zaman = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    head = _git("rev-parse", "--short", "HEAD") or "nogit"
    kirli = [s for s in _git("status", "--short").splitlines()
             if s and not s.startswith("??")]
    ad = f"{zaman}_{head}_{_temiz_etiket(etiket)}"
    YEDEK_DIR.mkdir(exist_ok=True)
    hedef = YEDEK_DIR / f"{ad}.zip"
    dosyalar = _dosyalar()
    manifest: Dict[str, object] = {
        "ad": ad, "zaman": zaman, "git_head": head,
        "git_dal": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_kirli_dosyalar": kirli, "etiket": etiket, "not": not_,
        "kok": str(_ROOT), "n_dosya": len(dosyalar), "sha256": {},
    }
    toplam = 0
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in dosyalar:
            rel = p.relative_to(_ROOT).as_posix()
            manifest["sha256"][rel] = _sha(p)  # type: ignore[index]
            toplam += p.stat().st_size
            z.write(p, rel)
        z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False,
                                               indent=1))
    mb = hedef.stat().st_size / 1e6
    _log(f"YEDEK: {hedef.name}  dosya={len(dosyalar)}  ham={toplam/1e6:.1f}MB"
         f"  zip={mb:.1f}MB  git={head}  kirli={len(kirli)}")
    # cift kopya (D)
    try:
        if D_YEDEK_DIR.parent.exists():
            D_YEDEK_DIR.mkdir(exist_ok=True)
            kopya = D_YEDEK_DIR / hedef.name
            kopya.write_bytes(hedef.read_bytes())
            _log(f"KOPYA: {kopya}")
    except Exception as exc:  # D yoksa yedek yine gecerli
        _log(f"UYARI: D kopyasi yazilamadi: {exc}")
    # index
    idx = YEDEK_DIR / "INDEX.md"
    yeni = not idx.exists()
    with idx.open("a", encoding="utf-8") as fh:
        if yeni:
            fh.write("# YEDEKLER INDEX (append-only; her satir bir anlik-yedek)\n\n"
                     "| zaman | git | etiket | dosya | zip MB | kirli | not |\n"
                     "|---|---|---|---|---|---|---|\n")
        fh.write(f"| {zaman} | {head} | {etiket} | {len(dosyalar)} | {mb:.1f} "
                 f"| {len(kirli)} | {not_} |\n")
    return hedef


def liste() -> None:
    zips = sorted(YEDEK_DIR.glob("*.zip")) if YEDEK_DIR.exists() else []
    if not zips:
        _log("yedek yok")
        return
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                m = json.loads(zf.read("MANIFEST.json"))
            _log(f"{z.name:60s} git={m.get('git_head')} n={m.get('n_dosya')}"
                 f" kirli={len(m.get('git_kirli_dosyalar', []))}"
                 f" not={m.get('not', '')}")
        except Exception as exc:
            _log(f"{z.name:60s} MANIFEST okunamadi: {exc}")


def dogrula(zip_yolu: Path) -> int:
    with zipfile.ZipFile(zip_yolu) as zf:
        m = json.loads(zf.read("MANIFEST.json"))
        bozuk = 0
        for rel, sha in m["sha256"].items():
            h = hashlib.sha256(zf.read(rel)).hexdigest()
            if h != sha:
                bozuk += 1
                _log(f"BOZUK: {rel}")
    _log(f"DOGRULAMA: {zip_yolu.name} n={len(m['sha256'])} bozuk={bozuk}")
    return 0 if bozuk == 0 else 1


def fark(zip_yolu: Path) -> None:
    """Yedek ile CALISMA AGACI arasindaki farki listele (hangi dosya degisti)."""
    with zipfile.ZipFile(zip_yolu) as zf:
        m = json.loads(zf.read("MANIFEST.json"))
    simdi = {p.relative_to(_ROOT).as_posix(): _sha(p) for p in _dosyalar()}
    eski = m["sha256"]
    degisen = [r for r in eski if r in simdi and simdi[r] != eski[r]]
    silinen = [r for r in eski if r not in simdi]
    yeni = [r for r in simdi if r not in eski]
    _log(f"FARK ({zip_yolu.name} -> simdi): degisen={len(degisen)} "
         f"silinen={len(silinen)} yeni={len(yeni)}")
    for r in degisen:
        _log(f"  M {r}")
    for r in silinen:
        _log(f"  D {r}")
    for r in yeni:
        _log(f"  A {r}")


def geri_yukle(zip_yolu: Path) -> Path:
    hedef = YEDEK_DIR / f"geri_{zip_yolu.stem}"
    if hedef.exists():
        _log(f"HATA: {hedef} zaten var — once sil/tasi")
        sys.exit(2)
    with zipfile.ZipFile(zip_yolu) as zf:
        zf.extractall(hedef)
    _log(f"GERI YUKLENDI (yerine DEGIL, yan dizine): {hedef}")
    _log("Sonraki adim: fark bak -> `python -m scripts.yedekle --fark <zip>`; "
         "geri almak istedigin dosyalari BILINCLI kopyala; sonra testleri kos.")
    return hedef


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etiket", help="anlik yedek al (etiket = ne oncesi)")
    ap.add_argument("--not", dest="not_", default="", help="kisa aciklama")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--dogrula", metavar="ZIP")
    ap.add_argument("--fark", metavar="ZIP")
    ap.add_argument("--geri-yukle", metavar="ZIP")
    a = ap.parse_args()

    def _zip(s: str) -> Path:
        p = Path(s)
        if not p.exists():
            p = YEDEK_DIR / s
        if not p.exists():
            _log(f"HATA: zip yok: {s}")
            sys.exit(2)
        return p

    if a.liste:
        liste()
        return 0
    if a.dogrula:
        return dogrula(_zip(a.dogrula))
    if a.fark:
        fark(_zip(a.fark))
        return 0
    if a.geri_yukle:
        geri_yukle(_zip(a.geri_yukle))
        return 0
    if a.etiket:
        yedek_al(a.etiket, a.not_)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

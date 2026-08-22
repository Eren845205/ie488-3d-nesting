# -*- coding: utf-8 -*-
"""gece_zinciri.py - GECE KOSU ZINCIRI: A9 tam suite -> (yesilse) M4 dalgasi.

Eren istegi (2026-08-20): gece kosulari zamanlayiciyla zincirlensin.
Zincir-script dersi (RUNBOOK P-5 / 9-saat kaybi) PAZARLIKSIZ uygulanir:
  - HER adim guard'li: onceki adim yesil degilse sonraki BASLAMAZ.
  - Kaynak guard'lari: baska agir python kosusu varsa BASLAMAZ (munhasirlik
    K-57a); RAM alt siniri saglanmadan M4 baslamaz.
  - GECE_DRY=1 duman modu: adimlar KOSULMAZ, tum guard'lar + komut kurulumu
    dogrulanir (zincire alinmadan once duman testi sarti).
  - Her adim ayri subprocess + ayri log; zincir ozeti JSON'a (D + OneDrive).

Kosum: D:\\ie488'den  python -m scripts.detach_run gece_zinciri
Env:
  GECE_DRY=1        duman modu (kosu yok, dogrulama var)
  GECE_ADIMLAR      virgullu adim listesi (default: suite,m4)
  GECE_M4_SEEDS     M4 seed sayisi (default 6)
  GECE_M4_SCALE     M4 olcek (default orta)
  GECE_M4_FAMILIES  M4 aile listesi (default mass_plate_rod_mix -
                    kafes kollarinin tetiklendigi aile; diger ailelerin
                    kucuk-dalga etiketleri zaten mevcut, cift-satir yasak)
  GECE_RAM_MIN_GB   M4 icin RAM alt siniri (default 4.0)
SAF ASCII stdout (cp1254). A11: kosu orkestrasyon araci - mekanizma degil.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "gece_zinciri.log"
OUT = _ROOT / "results" / "gece_zinciri_ozet.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def _bos_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip()) * 1024 / 1e9
    except Exception:
        return -1.0


def _agir_python_var_mi() -> list:
    """Isim-filtresiz proses taramasi (store-python dersi): bu prosesin ve
    webapp'in disindaki python'lar agir-kosu adayi sayilir."""
    benim = os.getpid()
    supheli = []
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object "
             "{ $_.Name -match 'python' } | ForEach-Object "
             "{ '{0}|{1}' -f $_.ProcessId, $_.CommandLine }"],
            capture_output=True, text=True, timeout=60)
        for satir in (r.stdout or "").splitlines():
            satir = satir.strip()
            if not satir or "|" not in satir:
                continue
            pid_s, cmd = satir.split("|", 1)
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            if pid in (benim, os.getppid()):
                continue
            if "src.webapp.app" in cmd:      # webapp bosta servis - muaf
                continue
            if "detach_run gece_zinciri" in cmd or "gece_zinciri" in cmd:
                continue
            supheli.append(f"pid={pid} cmd={cmd[:90]}")
    except Exception as exc:
        supheli.append(f"tarama-hatasi: {exc}")
    return supheli


def _adim_kos(ad: str, cmd: list, env_ek: dict, adim_log: Path,
              dry: bool) -> dict:
    kayit = {"adim": ad, "cmd": " ".join(cmd), "env": env_ek,
             "baslangic": datetime.now().isoformat(timespec="seconds")}
    log(f"[{ad}] komut: {kayit['cmd']}  env_ek={env_ek}")
    if dry:
        kayit["durum"] = "DRY-ATLANDI"
        return kayit
    env = dict(os.environ)
    env.update({k: str(v) for k, v in env_ek.items()})
    t0 = time.time()
    with adim_log.open("ab") as fh:
        p = subprocess.run(cmd, cwd=str(_ROOT), env=env,
                           stdout=fh, stderr=subprocess.STDOUT)
    kayit["sure_s"] = round(time.time() - t0, 1)
    kayit["exit"] = p.returncode
    kayit["durum"] = "YESIL" if p.returncode == 0 else "FAIL"
    log(f"[{ad}] {kayit['durum']}  exit={p.returncode}  "
        f"sure={kayit['sure_s']/60:.1f}dk  log={adim_log}")
    return kayit


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    dry = os.environ.get("GECE_DRY") == "1"
    adimlar = [a.strip() for a in os.environ.get(
        "GECE_ADIMLAR", "suite,m4").split(",") if a.strip()]
    ram_min = float(os.environ.get("GECE_RAM_MIN_GB", "4.0"))
    log("=" * 70)
    log(f"GECE ZINCIRI  dry={int(dry)}  adimlar={adimlar}")
    log("=" * 70)
    ozet = {"tarih": datetime.now().isoformat(timespec="seconds"),
            "dry": dry, "adimlar": [], "sonuc": None}

    def _kaydet():
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(ozet, indent=2, ensure_ascii=True),
                       encoding="utf-8")
        try:
            ek = ONEDRIVE / "results" / OUT.name
            if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
                ek.write_text(json.dumps(ozet, indent=2, ensure_ascii=True),
                              encoding="utf-8")
        except Exception as exc:
            log(f"uyari: OneDrive kopyasi yazilamadi ({exc})")

    # Zincir-basi guard: munhasirlik (K-57a)
    supheli = _agir_python_var_mi()
    if supheli:
        log("GUARD FAIL: baska python kosusu var - zincir BASLAMADI:")
        for s in supheli:
            log(f"  {s}")
        ozet["sonuc"] = "GUARD-FAIL-MUNHASIRLIK"
        ozet["supheli"] = supheli
        _kaydet()
        return 1
    log("[guard] munhasirlik OK (agir python kosusu yok)")

    for ad in adimlar:
        if ad == "suite":
            kayit = _adim_kos(
                "suite", [sys.executable, "-m", "pytest", "tests", "-q",
                          "-p", "no:cacheprovider"],
                {}, Path(__file__).parent / "gece_a9_suite.log", dry)
        elif ad == "m4":
            ram = _bos_ram_gb()
            log(f"[guard] RAM bos: {ram:.1f} GB (esik {ram_min})")
            if not dry and 0 <= ram < ram_min:
                kayit = {"adim": "m4", "durum": "GUARD-FAIL-RAM",
                         "ram_gb": round(ram, 1)}
                log("[m4] GUARD FAIL: RAM esigi altinda - adim atlandi")
                ozet["adimlar"].append(kayit)
                ozet["sonuc"] = "GUARD-FAIL-RAM"
                _kaydet()
                return 1
            kayit = _adim_kos(
                "m4", [sys.executable, "-m", "scripts.m4_portfoy_kosu"],
                {"M4_SEEDS": os.environ.get("GECE_M4_SEEDS", "6"),
                 "M4_SCALE": os.environ.get("GECE_M4_SCALE", "orta"),
                 "M4_FAMILIES": os.environ.get(
                     "GECE_M4_FAMILIES", "mass_plate_rod_mix"),
                 "M4_KAFES": "1"},
                Path(__file__).parent / "gece_m4_dalga.log", dry)
        else:
            log(f"HATA: bilinmeyen adim '{ad}'")
            ozet["sonuc"] = f"HATA-BILINMEYEN-ADIM-{ad}"
            _kaydet()
            return 2
        ozet["adimlar"].append(kayit)
        _kaydet()
        if not dry and kayit.get("durum") != "YESIL":
            log(f"ZINCIR DURDU: '{ad}' yesil degil - sonraki adimlar "
                "BASLATILMADI (zincir-script dersi).")
            ozet["sonuc"] = f"DURDU-{ad}"
            _kaydet()
            return 1

    ozet["sonuc"] = "DRY-OK" if dry else "TAMAM"
    _kaydet()
    log(f"ZINCIR {ozet['sonuc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

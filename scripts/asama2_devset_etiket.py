# -*- coding: utf-8 -*-
"""asama2_devset_etiket.py - Asama-2 dev-set etiket kampanyasi (Eren onayi
2026-08-22 karar paketi madde-4; ML plani §2.1 + §4 Asama-2 on-kosulu).

Her dev-set icin karsi-olgusal portfoy etiketi uretir (fsm610 deseninin
dev-set genellemesi): uretim kollari (heightmap / nfv_fast / nfv_max;
kafes_zinciri KAPALI - saflik) + tetikli kafes kollari. Satirlar
`results/m4_portfoy_etiket.jsonl`'a APPEND (aile=devset_<set>).

p2/d4 SIFIR-DOKUNUS kaniti YAN URUN: kafes kolu tetik atesLEMEZSE satirda
kol yoktur = kafes bu seti degistirmiyor (KIRMIZI serh kapanir).

Disiplin: setler SIRALI (K-57a munhasir); her set oncesi RAM kapisi
(bos < 4GB -> bekle, 30dk asilirsa atla + kayit). SAF ASCII stdout.
Kosum: D:\\ie488'den detach; setler A2_SETS env ile secilir
(default: plan1,plan2,plan3,deneme4,deneme5).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import subprocess

from scripts.m4_portfoy_kosu import (  # noqa: E402
    ARMS, FAMILY_BUILDERS, KAFES_ARMS, OUT_ETIKET, SIDECAR_DIR,
    etiket_hesapla)

RAM_ESIK_GB = 4.0
RAM_BEKLE_S = 1800


def log(m: str = "") -> None:
    print(m, flush=True)


def _bos_ram_gb() -> float:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / (1024 ** 3)


def _sidecar_bul(kaynak: str, mode: str, q: Optional[str]) -> Optional[dict]:
    """Bugun yazilmis en yeni ham sidecar'i bul (olcum tekrar edilmez):
    yalniz TAM yerlesimli + hatasiz kol yeniden kullanilir."""
    if os.environ.get("A2_REUSE_SIDECAR", "1") != "1":
        return None
    ad = f"{kaynak}_{mode}{('_' + q) if q else ''}"
    ad = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in ad)
    adaylar = sorted(SIDECAR_DIR.glob(f"{ad}_*.json"))
    for yol in reversed(adaylar):
        try:
            d = json.loads(yol.read_text(encoding="utf-8"))
        except Exception:
            continue
        kol = d.get("kol_ozet") or {}
        if (kol.get("hata") or not kol.get("height_mm")
                or int(kol.get("n_placed") or 0) != int(kol.get("n_total") or -1)):
            continue
        kol = dict(kol)
        kol["sidecar"] = str(yol)
        kol["yeniden_kullanildi"] = True
        return kol
    return None


def _kol_alt_surec(aile: str, kol_adi: str, kaynak: str, clearance: float,
                   seed: int = 42, scale: str = "gercek") -> Optional[dict]:
    """Kolu TAZE surecte kos (bellek birikimi dersi 2026-08-30); sonucu JSON'dan
    oku. Cikti dict (kol sonucu) veya None (kafes tetik yok). Hata -> {'hata'}."""
    out = SIDECAR_DIR / f"_tek_{aile}_{kol_adi}.json"
    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    cmd = [sys.executable, "-m", "scripts.m4_kol_tek", "--aile", aile,
           "--kol", kol_adi, "--seed", str(seed), "--scale", scale,
           "--clearance", str(clearance), "--kaynak", kaynak,
           "--out", str(out)]
    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, cwd=str(_ROOT))
    except Exception as exc:
        return {"hata": f"alt surec baslatilamadi: {exc}"}
    bekci = _bekci(proc, f"{aile}/{kol_adi}")
    rc = proc.returncode
    if bekci:
        return {"hata": bekci, "wall_s": round(time.time() - t0, 2)}
    if not out.exists():
        return {"hata": f"alt surec cikti yazmadi (rc={rc}, "
                        f"{time.time()-t0:.0f}s) - muhtemel cokme/OOM"}
    try:
        d = json.loads(out.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"hata": f"alt surec ciktisi okunamadi: {exc}"}
    if d.get("hata"):
        return {"hata": d["hata"]}
    if not d.get("tetik", True):
        return None
    kol = d.get("sonuc") or {"hata": "alt surec sonucu bos"}
    if isinstance(kol, dict) and kol.get("wall_s") is None:
        kol["wall_s"] = d.get("wall_s")
    return kol


GPU_ESIK_MB = 600.0


def _gpu_kullanim_mb() -> Optional[float]:
    """nvidia-smi memory.used (MiB); yoksa None (kapı uygulanmaz)."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        return float(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


BEKCI_PRIV_GB = float(os.environ.get("A2_BEKCI_PRIV_GB", "12"))
BEKCI_TIKANMA_S = float(os.environ.get("A2_BEKCI_TIKANMA_S", "240"))
BEKCI_TIKANMA_PRIV_GB = float(os.environ.get("A2_BEKCI_TIKANMA_PRIV_GB", "6"))


def _bekci(proc, etiket: str) -> Optional[str]:
    """Alt-surec bekcisi (2026-08-30 plan2/kanopi dersi): private > esik veya
    (private > tikanma-esigi VE CPU ilerlemiyor) -> takas/tikanma -> oldur,
    sebep dondur. Normal bitiste None. 15 sn orneklem; 10 dk'da bir nabiz."""
    try:
        import psutil
        ps = psutil.Process(proc.pid)
    except Exception:
        proc.wait()
        return None
    t0 = time.time()
    son_cpu = 0.0
    son_cpu_t = t0
    son_nabiz = t0
    while proc.poll() is None:
        time.sleep(15)
        try:
            mi = ps.memory_info()
            ct = ps.cpu_times()
            cpu = ct.user + ct.system
            priv = mi.private / 1e9
        except Exception:
            break
        if cpu - son_cpu >= 3.0:
            son_cpu, son_cpu_t = cpu, time.time()
        if time.time() - son_nabiz >= 600:
            son_nabiz = time.time()
            log(f"    [nabiz {etiket}] {time.time()-t0:.0f}s priv={priv:.1f}GB "
                f"ws={mi.rss/1e9:.1f}GB cpu={cpu:.0f}s")
        sebep = None
        if priv > BEKCI_PRIV_GB:
            sebep = (f"BEKCI: private {priv:.1f}GB > {BEKCI_PRIV_GB}GB "
                     f"(takas) - kol iptal, {time.time()-t0:.0f}s")
        elif (priv > BEKCI_TIKANMA_PRIV_GB
              and time.time() - son_cpu_t > BEKCI_TIKANMA_S):
            sebep = (f"BEKCI: CPU {BEKCI_TIKANMA_S:.0f}s ilerlemedi "
                     f"(priv {priv:.1f}GB, takas/tikanma) - kol iptal, "
                     f"{time.time()-t0:.0f}s")
        if sebep:
            log(f"    {sebep}")
            try:
                for c in ps.children(recursive=True):
                    c.kill()
                ps.kill()
            except Exception:
                pass
            proc.wait()
            return sebep
    return None


def _ram_kapisi(set_adi: str) -> bool:
    """RAM + GPU bosalma kapisi (2026-08-30 dersi: oldurulen GPU-agir surecin
    ardindan hemen baslatilan kol 14 GB'a sisip takasa girdi; GPU tabani
    ~20 MiB'a donmeden yeni kol baslatilmaz)."""
    t0 = time.time()
    while True:
        gb = _bos_ram_gb()
        gpu = _gpu_kullanim_mb()
        if gb >= RAM_ESIK_GB and (gpu is None or gpu < GPU_ESIK_MB):
            return True
        if gpu is not None and gpu >= GPU_ESIK_MB:
            log(f"{set_adi}: GPU bosalmasi bekleniyor ({gpu:.0f} MiB >= "
                f"{GPU_ESIK_MB:.0f}) ...")
        if time.time() - t0 > RAM_BEKLE_S:
            log(f"{set_adi}: RAM kapisi ASILAMADI ({gb:.1f}GB < "
                f"{RAM_ESIK_GB}) - set atlandi (sonraki dalgaya)")
            return False
        log(f"{set_adi}: RAM bekleniyor ({gb:.1f}GB) ...")
        time.sleep(60)


def main() -> int:
    from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
    clearance_req = float(WEB_MIN_CLEARANCE_MM)
    setler = [s.strip() for s in os.environ.get(
        "A2_SETS", "plan1,plan2,plan3,deneme4,deneme5").split(",")
        if s.strip()]
    log("=" * 70)
    log("ASAMA-2 DEV-SET ETIKET KAMPANYASI (karar paketi madde-4)")
    log(f"setler={setler}  clearance_req={clearance_req}mm")
    log("NOT: etiket uretimi - kazanc ilani DEGILDIR (A11); nfv kollari")
    log("     kafes_zinciri KAPALI (karsi-olgusal saflik); no-go/pin")
    log("     uretim kosullari tasinmaz (SERH - kollar ic-tutarli).")
    log("     A2 rot-sokum katmani ETIKETTE (2026-08-30); ham sidecar results/m4_kollar/")
    log("     kollar AYRI SURECTE (bellek birikimi dersi); sidecar yeniden-kullanim="
        + os.environ.get("A2_REUSE_SIDECAR", "1"))
    log("=" * 70)
    t0 = time.time()
    n_hata = 0
    for set_adi in setler:
        aile = f"devset_{set_adi}"
        builder = FAMILY_BUILDERS.get(aile)
        if builder is None:
            log(f"{set_adi}: builder yok - atlandi")
            n_hata += 1
            continue
        if not _ram_kapisi(set_adi):
            n_hata += 1
            continue
        ts = time.time()
        try:
            inst = builder(42, "gercek", None)
        except Exception as exc:
            log(f"{set_adi}: INSTANCE KURULAMADI: {exc}")
            n_hata += 1
            continue
        n_total = sum(int(p.qty) for p in inst.parts)
        log(f"\n[{set_adi}] {n_total} parca")
        del inst  # bellek: instance yalniz sayim icindi; kollar alt surecte
        arms = {}
        kaynak = f"asama2:{set_adi}"
        for ad, mode, q in ARMS:
            kol = _sidecar_bul(kaynak, mode, q)
            if kol is not None:
                log(f"  kol {ad}: SIDECAR yeniden kullanildi "
                    f"({Path(kol['sidecar']).name})")
            else:
                if not _ram_kapisi(f"{set_adi}/{ad}"):
                    kol = {"hata": "RAM kapisi asilamadi (kol atlandi)"}
                else:
                    log(f"  kol {ad} ... (alt surec)")
                    kol = _kol_alt_surec(aile, ad, kaynak, clearance_req) or {
                        "hata": "alt surec bos dondu"}
            arms[ad] = kol
            log(f"    h={kol.get('height_mm')} "
                f"cl={kol.get('min_clearance_mm')} "
                f"kilit5={kol.get('n_locked_5dir')} "
                f"rot={kol.get('n_locked_rot')} "
                f"sure={kol.get('wall_s')}s"
                f" sidecar={'OK' if kol.get('sidecar') else 'YOK'}"
                + (f" HATA={kol['hata']}" if kol.get("hata") else ""))
        for ad, durus in KAFES_ARMS:
            if not _ram_kapisi(f"{set_adi}/{ad}"):
                arms[ad] = {"hata": "RAM kapisi asilamadi (kol atlandi)"}
                continue
            kol = _kol_alt_surec(aile, ad, kaynak, clearance_req)
            if kol is None:
                log(f"  kol {ad}: tetik YOK (sifir-dokunus kaniti)")
                continue
            arms[ad] = kol
            log(f"  kol {ad}: h={kol.get('height_mm')} "
                f"cl={kol.get('min_clearance_mm')} "
                f"sure={kol.get('wall_s')}s"
                + (f" HATA={kol['hata']}" if kol.get("hata") else ""))
        et = etiket_hesapla(arms, clearance_req)
        satir = {"ts": time.time(), "instance_id": f"devset_{set_adi}",
                 "aile": aile, "seed": 42, "scale": "gercek",
                 "n_total": n_total, "clearance_req_mm": clearance_req,
                 "arms": arms, **et}
        OUT_ETIKET.parent.mkdir(exist_ok=True)
        with OUT_ETIKET.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(satir, ensure_ascii=False) + "\n")
        log(f"  ETIKET: winner={et['winner_mode']} n_legal={et['n_legal']}"
            f"  ({(time.time()-ts)/60:.1f} dk)")
    log(f"\nKAMPANYA BITTI ({(time.time()-t0)/60:.1f} dk; hata/atlanan="
        f"{n_hata}) -> {OUT_ETIKET}")
    return 0 if n_hata == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""plan1_toplayici.py — 5 paralel tek-seed kosuyu bekler, en iyisini
plan1_uretim335.log'a ozetler + BITTI yazar (ax24 kuyrugu bunu bekliyor)."""
import re, sys, time
from pathlib import Path
H = Path(__file__).parent
SEEDS = (42, 13, 7, 5, 21)
ANA = H / "plan1_uretim335.log"

def main():
    while True:
        logs = {s: (H / f"plan1_s{s}_335.log") for s in SEEDS}
        durum = {s: (p.read_text(encoding="utf-8", errors="ignore") if p.exists() else "")
                 for s, p in logs.items()}
        if all("BITTI" in t for t in durum.values()):
            break
        time.sleep(60)
    en_iyi = None
    with ANA.open("a", encoding="utf-8") as fh:
        for s, t in durum.items():
            m = re.search(r"SONUC: h=([\d.]+)\s+legal=([\w.()<>; /%]+)", t)
            satir = m.group(0) if m else "SONUC yok (EXCEPTION?)"
            fh.write(f"[s{s}] {satir}\n")
            if m:
                try:
                    lg = float(m.group(2))
                    if en_iyi is None or lg < en_iyi[1]:
                        en_iyi = (s, lg)
                except ValueError:
                    pass
        if en_iyi:
            fh.write(f"KAZANAN s{en_iyi[0]}: {en_iyi[1]}mm\n")
        fh.write("BITTI\n")
    print("toplayici bitti", en_iyi)

if __name__ == "__main__":
    main()

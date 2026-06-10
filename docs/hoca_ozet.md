# IE 488 Donem Projesi — Hoca Ozeti (1 Sayfa)
## AM Nesting Baseline Prototipi · 2D · AABB · Constructive Heuristic

---

## Ne Yaptim

1. **Kodlama:** Python'da 2B AM nesting prototipi gelistirdim. Iki constructive heuristic implemente ettim: **Bottom-Left (BL)** — parcalari sol-alttan baslayarak yerlestirir; **Best-Fit Decreasing (BFD)** — parcalari alana gore buyukten kucuge siralar, her parca icin en az artik birakacak bos alani secer. Parca temsili AABB (dikdortgen bounding box), platform 220x220 mm FDM tablasi, rotation {0 derece, 90 derece}.

2. **Test setleri:** Deterministik (seed=42) uc CSV seti uzerinde kostu: **small** (10 parca), **medium** (25 parca), **stress** (50 parca). Her set, her iki algoritma ile hem rotation-on hem rotation-off modunda kostu — toplam 12 senaryo.

3. **Metrikler ve ciktilar:** Her senaryo icin doluluk orani (%), atik orani (%), yerlestirilemyen parca sayisi ve calisma suresi (ms) hesaplandi; `results/summary.csv` ve `results/summary.md` dosyalarina yazildi. 12 adet yerlesim PNG'si ve algoritma karsilastirma bar grafigi uretildi.

---

## Nasil Yaptim

**Algoritma secim gerekceleri:**

- **Neden AABB (2D bounding box)?** Tang vd. (2025) review'i bu yontemi "E-IM (Extended Image Mapping) — en eski ve en yaygin baslangic noktasi" olarak tanimlar. 48 saatlik prototip icin implementasyon maliyeti en dusuk, savunulabilirligi en yuksek secidir.

- **Neden BL + BFD?** Her ikisi de literaturde E\P\S kutusunda (Extended image mapping / Pure placement / Single algorithm) konumlanir. BL, en sade constructive heuristic olarak temel referanstir; BFD, siralamanin doluluk oranina etkisini olcen ikinci pivot saglar ve hocayla somut bir algoritma tartismasi acar.

- **Neden skyline tabani?** BFD implementasyonu icin maximal-rectangles yerine skyline secildi — 2 gun butcesine daha rahat sigan, yeterli doluluk saglar.

- **Tang E\P\S kutusuyla uyum:** (E) AABB image mapping; (P) pure placement — yonelim enumeration yapilir ama birlikte optimize edilmez; (S) tek constructive heuristic kosu, hibrit degil.

**Secici sonuclar (summary.md'den):**

| Algoritma | Set | Rotation | Doluluk | Yerlestirilemyen |
|-----------|-----|----------|---------|-----------------|
| BL | medium | on | **%86.90** | 7 / 25 |
| BL | stress | on | %82.66 | 32 / 50 |
| BFD | stress | off | **%86.48** | 33 / 50 |
| BFD | medium | on | %80.07 | 12 / 25 |

BL orta buyuklukte parcalarda BFD'yi geciyor (%86.90 vs %80.07); BFD buyuk setlerde rotation-off modda onu yakalayabiliyor (%86.48). Algoritma secimi parca setinin istatistiklerine baglidir.

---

## Sonraki Hafta Nereye Gotururum

Uc secenegi hocayla tartismak uzere hazir tutuyorum — yön hocayla birlikte secilebilir:

**(a) Polygon image mapping (N-IM) + NFP:** AABB'den gercek 2B kontür geometrisine gecis. No-Fit Polygon (NFP) hesabi ile daha siki yerlesim. Tang E\P\S --> N\P\S adimi.

**(b) 3B voxel temsile sicrayis:** Araujo vd. (2019) taksonomisi + voxel-OCCS yaklasimi. FDM/SLM tablasina gercek hacimsel nesting. Prototip 2+1|Ou|Of|ll notasyonundan 3|Ou|Of|ll'ye gecer.

**(c) Metasezgisel iyilestirme (GA / SA):** BL veya BFD'yi inner-loop olarak kullanip parca siralamasi uzerinden Genetic Algorithm veya Simulated Annealing. Doluluk oraninda tahmin edilebilir kazanim, hesaplama maliyeti artar.

---

*Gosterilecek dosyalar: bu sayfa + `results/summary.md` + `results/bl_medium_on.png`*
*Demo komutu: `python src/run.py --algo bl --set medium`*

# GENELLİK KAPISI — NFV cavity Plan2-overfit mi, GENEL mi? (2026-06-23)

> **Kullanıcı sorusu:** "Bu yöntem genel, bütün verilerde algoritmayı iyileştirecek bir
> yöntem mi, yoksa sadece bu plan üzerinde çalışacak, overfit riski olan bir yöntem mi?"
>
> **CEVAP: GENEL — overfit DEĞİL.** Dört bağımsız veride (doluluk spektrumu boyunca)
> NFV-greedy aynı kaba pitch'te heightmap'i %9–25 GEÇTİ, **hiçbirinde regresyon yok**
> (saf katı kutuda bile). Script: `scripts/c3_generality.py` (deney; `src/` DOKUNULMADI).

## Ölçüm (kaba pitch=2.0, n_or=4, MARGIN=1; aynı plakada NFV vs heightmap-DBLF)

| Veri | kutuluk* | heightmap (dblf) | NFV-greedy | delta | decode |
|---|---|---|---|---|---|
| kutu-sentetik (saf katı kutu) | 0.995 | 1070 | **970** | **+9.3%** | 77s |
| plan1 (braket/bobbin) | 0.440 | 142 | **128** | **+9.9%** | 180s |
| plan3 (kullanıcı adetleri) | 0.295 | 1072 | **872** | **+18.7%** | 884s |
| plan2 (ÇAPA, oyuklu) | 0.616 | 740 | **556** | **+24.9%** | 344s |

\* **kutuluk = parça-başı doluluk ortalaması** (volume_voxels / bbox_voxels). DİKKAT: bu,
handoff'taki "Plan2 0.07" ile AYNI metrik DEĞİL — o, plan-seviyesi paketleme yoğunluğu
(cavity fırsatı). Parça-başı metrik delta'yı temiz izlemiyor (boxy 0.995→+9.3 vs plan2
0.616→+24.9) çünkü kazanç plan-seviyesi paket yapısından geliyor, parça kutuluğundan değil.

## Çıkarımlar

1. **Yöntem GENEL, Plan2'ye overfit DEĞİL.** Kodda Plan2'ye ayarlı tek sabit yok (saf
   geometrik `fftconvolve` + BLB + largest-first). Dört farklı veride tutarlı kazanç bunu
   ampirik doğruluyor.

2. **Kazanç sadece "cavity" değil — NFV genel olarak daha iyi bir yerleştirme.** Saf katı
   kutuda (oyuk YOK) bile +%9.3. Sebep: NFV TÜM feasible uzayda BLB seçer (parçayı yan
   boşluğa/alt-z'ye sokabilir); heightmap "üstten-düşürme" buna giremez. **Cavity bunun
   ÜSTÜNE ekstra** (Plan2 +%25 vs diğerleri +%9-19).

3. **Plan2 reprodüksiyonu birebir:** 740→556 (+%24.9), handoff değeriyle aynı.

## ⚠️ DÜRÜST SINIR (overfit sorusunun cevabı ≠ üretimi geçti)

- Bu kıyas **NFV vs heightmap-DBLF** (kaba, aynı pitch — adil same-pitch kıyas).
- **Üretim ≠ ham DBLF.** Üretim = `coarse_to_fine` + SA (Plan2 fine = 621). Yani "+%9-25 vs
  dblf" **"+%9-25 vs üretim" DEĞİL.** NFV'nin üretimi (fine+SA) geçip geçmediği AYRI soru =
  **fine doğrulama (B)**, hâlâ açık; önce **hız (C)** gerekir (fine decode mevcut hızla saatler).
- **Bu kapının yanıtladığı:** "yöntem genel mi / overfit mi" → **GENEL.** Yanıtlamadığı:
  "üretimi (621 fine) geçer mi" → henüz ölçülmedi.

## Yan bulgu (hız)
- plan3 decode **884s** — plan2'den (344s) yavaş, daha az parçaya rağmen. Sebep: çok yüksek
  istif (1072→872) → z-dilimleri büyük, kademeli-dilim 2× büyüyor. Hız işi (C) hâlâ kritik.

## Sıradaki (değişmedi, artık sağlam zeminde)
Genellik kanıtlandı → C3 yatırımı meşru. Bağımlı sıra: **(C) hız** (xy-bbox/O-FFT, 376→~50s)
→ **(B) fine doğrulama** (556 kaba → fine, üretim 621 + Magics 492 ile adil kıyas) →
**(A) üretime opt-in/adaptif bağla** (heightmap paralel = regresyon yok). Rollback tag
`checkpoint-2026-06-22-faz1-2`.

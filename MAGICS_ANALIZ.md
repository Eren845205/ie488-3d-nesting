# MAGICS ANALİZİ — Kalite Farkını Ne Belirliyor?

> Hocanın verisi: `Veriler/Plan{1,2,3}/` (43 STL) + Plan2 Magics sonuç ekran
> görüntüsü (`Veriler/Plan2.jpg`, 226 parça, 328.74×328.19×492.39mm).
> Script: `scripts/analiz_magics.py`.

## 1. GÖRSEL ANALİZ (Plan2.jpg — Magics nesting sonucu)
- Büyük açılı/kutu parçalar ortada **istiflenmiş ve birbirine geçecek şekilde**
  oryante edilmiş (diyagonal kesim yüzleri birbirine oturuyor).
- İnce/silindirik parçalar (93× nylon kablo koruma, bobbinler, çubuklar) büyük
  parçaların **YANINDAKİ ve ARASINDAKİ boşluklara doldurulmuş** — solda dikey
  ince-parça kolonları, aralara dik çubuklar.
- Yani Magics **boşluk/oyuk doldurma (cavity nesting)** yapıyor: küçük parçalar
  büyüklerin boş hacmine yerleşiyor.

## 2. SAYISAL ANALİZ (Plan2)
| Metrik | Değer |
|---|---|
| Parça ortalama "kutuluk" (hacim/bbox) | **0.07** (parçalar %93 BOŞ — ince/oyuk) |
| Teorik min yükseklik (hacim/alan) | 41.6 mm |
| **Katı-bbox paketleme tabanı** | **585.9 mm** |
| **Biz (kesin)** | **621 mm** → bbox tabanının 1.06×'i |
| **Magics** | **492 mm** → bbox tabanının **0.84×'i (ALTINDA!)** |

## 3. KRİTİK ÇIKARIM — farkı ne belirliyor
- **Biz katı-bbox paketlemenin TAVANINDAYIZ** (621 ≈ 586). Heightmap motoru işini
  iyi yapıyor; parçaları katı kutu olarak neredeyse optimal diziyoruz. Rotasyon/
  poz/arama ile kazanılacak yer ~yok (deneylerle de görüldü: n=8 sonrası sıfır).
- **Magics katı-bbox tabanının %16 ALTINA iniyor** (492 < 586). Bu fiziksel olarak
  **yalnız parçaları birbirinin oyuğuna geçirerek (cavity nesting)** mümkün —
  katı kutu mantığıyla 586'nın altına inilemez.
- → **Kalite açığının TAMAMI cavity nesting.** Parçalar %93 boş; Magics iç içe
  geçiriyor, biz (üstten-düşürme heightmap) geçiremiyoruz.

## 4. SONUÇ
- Tek kalite lever'ı = **cavity-aware 3B (NFV)**. Headroom büyük (%93 boşluk).
- Heightmap'i daha fazla zorlamak boşuna (bbox tavanındayız).
- 621 "kötü" değil — heightmap'in TAVANI; sorun mimari (drop), motor zayıflığı değil.
- Devamı: Magics'in GENEL algoritma yaklaşımı/karar mantığı araştırması (ayrı,
  overfit'ten kaçınmak için genel prensibi anlamak) → bkz. MAGICS_ALGORITMA_ARASTIRMA.md.

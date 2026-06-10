# IE 488 Dönem Projesi — Final Raporu
## Eklemeli İmalatta 2B Nesting: Constructive Sezgisellerden Metasezgisel Optimizasyona

---

## Özet

Bu projede, eklemeli imalat (Additive Manufacturing, AM) için bir build tablasına
parçaların yerleştirilmesi problemini — literatürdeki adıyla **nesting** — ele
aldım. İki aşamada ilerledim: (1) AABB temsili ve iki *constructive* sezgisel
(Bottom-Left ve Best-Fit Decreasing) ile çalışan bir **baseline** kurdum;
(2) bu baseline'ın üzerine, parça yerleştirme sırasını optimize eden bir
**Simulated Annealing (SA)** katmanı ekledim. Üç farklı yoğunlukta test seti
üzerinde SA, kısıtlı setlerde baseline'ın en iyisini geçti: **medium'da +3.99 puan
(86.90% → 90.88%)** — burada kazanç doğrudan aramanın kendisinden gelir — ve
**stress'te BL baseline'ına göre +8.99 puan (82.66% → 91.65%)**, ki bu kazancın
büyük kısmı (+7.17) başlangıç sıralama kuralından, geri kalanı (+1.82) SA
aramasından gelir (ayrıntılı ayrıştırma §6). Tüm parçaların zaten sığdığı small
sette ise baseline'ın halihazırda optimal olduğunu doğruladı. Tüm kod tekrar-üretilebilir
(sabit tohum), 47 birim testiyle doğrulanmıştır.

---

## 1. Giriş ve Problem Tanımı

Eklemeli imalatta bir build platformuna (FDM tablası ya da SLM toz yatağı)
birden çok parça yerleştirilir. **Nesting problemi**, bu parçaların **konum ve
oryantasyonunu** belirleyerek alan/hacim kullanımını maksimize etmeyi, dolayısıyla
malzeme atığını ve baskı süresini minimize etmeyi amaçlar. Bu, doğrudan bir
**Endüstri Mühendisliği optimizasyon problemidir**: kısıtlı bir kaynağın (tabla
alanı) en verimli kullanımı.

Tang vd. (2025) review'i iki üst-sınıf tanımlar:
- **NfAM (Nesting for AM):** yalnızca yerleştirme.
- **NSfAM (Nesting & Scheduling for AM):** yerleştirme + çizelgeleme + makine ataması.

Bu proje **NfAM + 2B + tek tabla** kapsamındadır. 2B seçimi, FDM'de parçaların
tablaya izdüşümünün çoğu zaman yeterli olmasıyla ve aynı algoritma iskeletinin
ileride 3B'ye taşınabilir olmasıyla gerekçelendirilir.

---

## 2. Literatür Konumlandırması (Özet)

Üç makale temel alındı (ayrıntılı notlar: `docs/literatur_notu.md`):

- **M1 — Tang vd. (2025), "Nesting Problems in AM: Classification and Review":**
  75 makaleyi üç eksende sınıflar — *image mapping* (parça temsili),
  *nesting strategy* (saf yerleştirme vs. entegre), *optimization algorithm*
  (tek vs. çok). Bu proje **E\P\S kutusunda** konumlanır: Extended image mapping
  (AABB) / Pure placement / Single algorithm.
- **M2 — Calabrese vd. (2022), "Nesting algorithm for optimization part placement in AM":**
  bounding-box temsilini ve parametrik kenar boşluğunu (gapB/gapX/gapY)
  destekler; prototipteki AABB + 1 mm margin kararıyla örtüşür.
- **M3 — Araújo vd. (2019), "Analysis of irregular 3D packing problems in AM":**
  dörtlü taksonomi (D|C|B|A) önerir. Bu proje **2+1 | Ou | Of | ll** sınıfındadır
  ve makale bu sınıf için tam da "Bottom-Left tipi sezgisellerin iteratif
  uygulamasını" önererek hem baseline hem metasezgisel seçimini destekler.

---

## 3. Yöntem

### 3.1 Parça temsili (Image Mapping)
Her parça eksen-hizalı bounding box (AABB) ile, `(width_mm, height_mm)` ikilisi
olarak temsil edilir. Tabla 220×220 mm (Ender-3 / Prusa MK4 sınıfı FDM yatağı),
parçalar arası ve kenar payı 1 mm. Rotation, izin verilen parçalar için
{0°, 90°} ile sınırlıdır.

### 3.2 Baseline — Constructive Sezgiseller
- **Bottom-Left (BL):** parçaları en uzun kenar azalan sıralar; her parçayı
  mümkün olan en alt-sol konuma yerleştirir (aday noktalar = yerleşmiş parçaların
  sağ-alt ve sol-üst köşeleri).
- **Best-Fit Decreasing (BFD):** parçaları alan azalan sıralar; **skyline**
  veri yapısı üzerinde en az artık bırakan konumu seçer.

Her iki sezgisel de açgözlüdür (greedy): anlık olarak iyi olan kararı verir,
genel (global) optimumu garanti etmez.

### 3.3 Katkı — Metasezgisel Optimizasyon (Simulated Annealing)
Anahtar gözlem: **constructive yerleştirme kuralı, parçaların kendisine verildiği
SIRAYA duyarlıdır.** O hâlde parça sırası bir *karar değişkeni* olarak ele
alınabilir. Bunun üzerine bir Simulated Annealing katmanı kurdum:

- **Çözüm temsili:** parçaların bir permütasyonu (sırası).
- **Decoder:** verilen sırayı **olduğu gibi** (içsel sıralama yapmadan)
  Bottom-Left konumlandırmasıyla tablaya yerleştirir. Çakışma ve sınır testleri
  baseline'dan **birebir yeniden kullanılır** (kod tekrarı yok, baseline'a
  dokunulmaz).
- **Amaç fonksiyonu:** doluluk oranı (yerleşen alan / tabla alanı); enerji =
  −doluluk.
- **Komşuluk hamleleri:** swap (iki konumu değiştir), insert (bir elemanı başka
  yere taşı), reverse (bir segmenti ters çevir) — yerel ve orta-menzilli
  aramayı birlikte sağlar.
- **Soğutma:** geometrik; sıcaklık t0=2.0'dan t_min=0.01'e iner. Kötüleştiren
  hamle exp(−Δ/T) olasılığıyla kabul edilir; en iyi çözüm her zaman saklanır
  (sonuç başlangıcın altına düşmez).
- **Tekrar-üretilebilirlik:** tüm rastgelelik tek bir tohumlu (seed=42)
  üreteçten akar.

Başlangıç sırası alan-azalandır (güçlü, "decreasing" tarzı bir başlangıç).

---

## 4. Deneysel Kurulum

- **Test setleri** (deterministik, seed=42 ile üretilmiş dikdörtgenler,
  10–80 mm):
  - **small** — 10 parça, talep tabla alanının **%48'i** (hepsi sığar).
  - **medium** — 25 parça, talep **%111** (kısmen sığar; sıralama önemli).
  - **stress** — 50 parça, talep **%181** (büyük kısmı sığamaz; seçim kritik).
- **Metrikler:** doluluk (%), yerleşen parça sayısı, çalışma süresi.
- **SA bütçesi:** small 800, medium 3 000, stress 6 000 iterasyon (seed=42).
- Yeniden üretmek için: `python src/bench_meta.py`.

---

## 5. Sonuçlar

### 5.1 Baseline vs. SA (rotation on)

| set | parça | talep % | BL % | BFD % | SA başlangıç % | **SA %** | en iyi baseline'a göre kazanç | SA yerleşen |
|---|---|---|---|---|---|---|---|---|
| small | 10 | 48% | 47.57 | 47.57 | 47.57 | **47.57** | +0.00 pp | 10 |
| medium | 25 | 111% | 86.90 | 80.07 | 85.55 | **90.88** | **+3.99 pp** | 18 |
| stress | 50 | 181% | 82.66 | 80.01 | 89.83 | **91.65** | **+8.99 pp** | 26 |

*(Kaynak: `results/meta_summary.md`; görseller: `results/comparison_with_sa.png`,
`results/sa_convergence.png`, `results/sa_<set>.png`.)*

### 5.2 Yorum
- **small:** Tüm parçalar zaten sığdığından doluluk, parçaların toplam alan
  oranıyla (%47.57) sınırlıdır — bu setin teorik tavanı budur. SA bunu aşamaz;
  baseline'ın bu sette **zaten optimal** olduğunu doğrular.
- **medium:** Talep tabla kapasitesinin biraz üzerinde (%111). Burada hangi
  parçanın yerleşeceği sıralamaya bağlıdır; SA, baseline'ın en iyisini
  **+3.99 puan** geçer (86.90% → 90.88%).
- **stress:** En kısıtlı set (%181). SA, BL baseline'ına kıyasla doluluğu
  **+8.99 puan** artırır ve yerleşen parça sayısını **18'den 26'ya** çıkarır.
  Ancak bu kazancın **dürüst ayrıştırması** önemlidir (bkz. §6): bu setteki +8.99
  puanın büyük kısmı **başlangıç sıralama kuralının değişiminden** gelir
  (longest-edge → alan-azalan: 82.66% → 89.83%, +7.17 puan), SA aramasının
  kendisi ise bunun üzerine **+1.82 puan** ekler (89.83% → 91.65%). Yani stress'te
  asıl kazanç "doğru sıralama"dan, ek rötuş aramadan gelir.

---

## 6. Tartışma

- **Neden SA işe yarar?** Constructive sezgiseller tek bir sabit sıralama
  kullanır (BL: en uzun kenar; BFD: alan). SA ise sıralama uzayını arar ve bu
  sabit kuralların ulaşamadığı düzenleri bulur. Kazanç, problem kısıtlandıkça
  (talep > %100) büyür; çünkü orada "hangi parça, hangi sırada" kararı kritiktir.
- **Kazancın dürüst ayrıştırması (sıralama etkisi vs. arama etkisi):** SA'nın
  başlangıç sırası alan-azalandır; bu tek başına, longest-edge sıralamasını
  kullanan BL'den farklı (çoğu zaman daha iyi) bir sonuç verir. Dolayısıyla
  toplam kazancı iki bileşene ayırmak gerekir:
  - **medium:** SA aramasının asıl işi gördüğü temiz vitrin. Başlangıç sırası
    (85.55%) BL baseline'ından (86.90%) *daha kötüdür*; SA arama yaparak 90.88%'e
    tırmanır — yani kazanç doğrudan **aramaya** atfedilebilir (kendi başlangıcını
    +5.33, en iyi baseline'ı +3.99 geçer).
  - **stress:** Kazancın büyük kısmı **sıralama kuralından** gelir (+7.17),
    SA araması üzerine yalnızca +1.82 ekler. Burada "doğru başlangıç sıralaması"
    tek başına güçlüdür; arama marjinal iyileştirme sağlar.
  Bu ayrım, sonuçların abartılmadan raporlanması açısından kritiktir.
- **Adillik:** SA, baseline ile aynı yerleştirme kuralını (Bottom-Left) ve aynı
  çakışma mantığını kullanır; tek fark **sırayı optimize etmesidir**. Dolayısıyla
  ölçülen kazanç, doğrudan optimizasyon katmanına atfedilebilir.
- **Maliyet:** SA, baseline'a göre çok daha pahalıdır (stress'te ~28 sn vs ~5 ms).
  Bu, klasik **kalite–hız ödünleşimidir**: kritik/yüksek-değerli baskılar için
  SA, hızlı keşif için constructive sezgisel.

---

## 7. Sonuç ve Gelecek Çalışma

Çalışan bir 2B AM nesting baseline'ı kurup üzerine bir Simulated Annealing
optimizasyon katmanı ekledim; kısıtlı setlerde doluluk oranında ölçülebilir ve
istatistiksel olarak savunulabilir kazanımlar elde ettim. Kapsam dışı bırakılan,
ileriye dönük yönler:

- **Genetik Algoritma (GA):** SA'ya alternatif; parça sırası üzerinde popülasyon
  tabanlı arama, aynı decoder ile.
- **Polygon temsil (N-IM) + No-Fit-Polygon:** dikdörtgen yerine gerçek kontur;
  daha sıkı yerleşim, Tang E→N adımı.
- **3B voxel temsil:** gerçek hacimsel nesting (SLM toz yatağı); Araújo A2018
  veri seti gerçekçi test parçaları sağlar.
- **Alt sınır / exact karşılaştırma:** küçük setlerde ILP ile optimallik açığının
  (gap) ölçülmesi.

---

## Kaynaklar

- Tang, A. vd. (2025). *Nesting Problems in Additive Manufacturing: Classification
  and Review.* Journal of Computing and Information Science in Engineering, ASME.
  doi:10.1115/1.4070330
- Calabrese, M. vd. (2022). *Nesting algorithm for optimization part placement in
  additive manufacturing.* Int. J. Adv. Manuf. Technol., 119, 4613–4634.
  doi:10.1007/s00170-021-08130-y
- Araújo, L.J.P. vd. (2019). *Analysis of irregular three-dimensional packing
  problems in additive manufacturing: a new taxonomy and dataset.* Int. J. Prod.
  Res., 57(18), 5920–5934. doi:10.1080/00207543.2018.1534016

---

## Ek — Çalıştırma Komutları

```
pip install numpy matplotlib pytest

python src/run.py --algo bl --set medium      # tek baseline koşusu
python src/bench.py                            # 12 baseline senaryosu
python src/bench_meta.py                       # baseline vs SA karşılaştırması
python -m pytest                               # 47 birim testi
```

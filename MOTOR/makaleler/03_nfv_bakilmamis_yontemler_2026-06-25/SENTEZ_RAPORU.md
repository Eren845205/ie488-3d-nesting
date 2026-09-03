# NFV Literatür Araştırması — Bakılmamış Yöntem Aileleri (2026-06-25)

> **Amaç:** Bizim denediğimiz yöntemleri (NFV/greedy/BLB, SA/ALNS-sıra, oryantasyon/pitch sweep,
> tie-break, GPU/FFT hız işleri) DIŞLAYIP, güvenilir akademik kaynaklardan **bakmadığımız** yöntem
> ailelerini haritalamak; sonra en umut verici birkaç yeni yönü öne çıkarmak. İki eksen: **KALİTE**
> (Magics ~%6 açığı) ve **HIZ** (NFV heightmap'ten ~10-40× yavaş, kaliteyi bozmadan).
>
> **Yöntem:** iki paralel `deep-research` workflow (fan-out web arama → kaynak çekme → adversarial
> doğrulama → sentez). Arama+çekme tamamlandı (kalite 22 kaynak/106 iddia, hız 23 kaynak/96 iddia);
> otomatik doğrulama+sentez adımı API session limitinde çöktü → sentez bu dosyada **elle** yapıldı.
>
> **Güvenilirlik etiketi:** `[DOĞRULANDI n-m]` = adversarial 3-oylu doğrulamadan geçti.
> `[KAYNAK]` = makale fetch edildi, alıntı gerçek, ama limit yüzünden çapraz-oy alınamadı (çürütülmedi
> de). `[ELENDİ]` = kısıtı ihlal ettiği için kapsam dışı.

---

## A. KALİTE — Magics açığını kapatabilecek bakılmamış aileler

### A1. Phi-fonksiyonu / quasi-phi-fonksiyonu NLP + SÜREKLİ rotasyon  ⭐ EN GÜÇLÜ
**Okul:** Stoyan, Romanova, Pankratov (IPMach, NAS Ukrayna, Kharkiv) + Bennell (Univ. of Southampton).
**Temsilci kaynaklar:**
- Romanova, Bennell, Stoyan et al., *"Packing of concave polyhedra with continuous rotations using
  nonlinear optimisation"*, **EJOR** (European Journal of Operational Research), 2018
  (eprints.whiterose.ac.uk/139289). `[KAYNAK]`
- *"Optimal packing of irregular 3D objects... minimum height under continuous rotations"*, IFAC-
  PapersOnLine (sciencedirect S2405896319314831). `[DOĞRULANDI 3-0]`
- Decomposition algoritması: Springer LNCS 978-3-030-33585-4_21. `[DOĞRULANDI 2-0]`

**Çekirdek fikir:** Çakışmama + içerme kısıtlarını **analitik** olarak (radical-free quasi-phi-
functions) yaz — phi-fonksiyonu obje konumlarının sürekli fonksiyonu: çakışmıyorsa +, değiyorsa 0,
çakışıyorsa −. Böylece **voxel/FFT'ye hiç gerek kalmadan** problem sürekli bir NLP olur; parçalar
**sürekli rotasyon + öteleme** ile (diskret oryantasyon seti DEĞİL) minimum yükseklikli kutuya
yerleşir. Concave parçalar convex parçaların birleşimine ayrıştırılır (quasi-phi). Off-the-shelf NLP
solver (**IPOPT**) ile çözülür. `[DOĞRULANDI 3-0]` (analitik makine), `[DOĞRULANDI 3-0]` (min-height
+ sürekli rotasyon).

**Neden bizim için önemli:** Bu, **Magics'in muhtemel gerçek sırrı.** Bizim kalite doygunluğumuz
DİSKRET eksende (n=8→12 %1.1, pitch %1) — çünkü 24-simetri + birkaç eğik açıyla sınırlıyız. Phi-
function SÜREKLİ rotasyonu açar: parçayı oyuğa tam oturacak *herhangi* bir açıya döndürebilir. Açığın
kaynağı muhtemelen tam burası (diskret→sürekli geçiş), pitch değil (bizim ANALIZ_NFV §6 bulgusuyla
tutarlı: pitch doygun).

**Engel — hesap maliyeti:** EJOR'da 20-98 parça için tek instance **binlerce saniye ila ~44 saat**
(IPOPT, tek CPU). `[KAYNAK]` Tam NLP modeli N>15 (rastgele başlangıç) / N>30 (feasible başlangıç)
üzerinde state-of-the-art solver'da bile **tıkanıyor**. `[KAYNAK]` Çözüm: O(n²) kısıtlı problemi
O(n) boyutlu **NLP alt-problemleri dizisine** indirgeyen decomposition (başlangıç algoritması
FAPA/FPPA + **COMPOLY** compaction). `[DOĞRULANDI 2-0]` Bizim 226 parça ölçeğimiz → mutlaka
decomposition + **süper bilgisayar** (bizim "n=28+0.5mm" planından daha derin bir iş).

**Prototip için gerekenler:** (1) STL→convex decomposition (V-HACD gibi), (2) quasi-phi-function
implementasyonu (analitik, zor kısım), (3) IPOPT/pyomo NLP, (4) decomposition/compaction scaffold.
Büyük iş; küçük N (örn. 20-30 parça alt-küme) ile **kavram doğrulama** önce yapılmalı.

### A2. Global compaction — layout-sonrası boşluk kapatma (swap/replace/insert)  ⭐ 6GB-UYUMLU
**Temsilci kaynak:** *"... irregular packing with free rotation"*, **Computer Graphics Forum** (CGF
13490, Eurographics), arbitrary konteyner+obje, tam serbest rotasyon. `[KAYNAK]`

**Çekirdek fikir:** Sürekli yerel optimizasyonun ÜZERİNE bir **kombinatoryal aşama**: objeleri
**yer değiştir / değiştir / araya sok** ederek obje-arası boşlukları aktif kapatır. Bu, bizim sıfır
kazanç aldığımız **sıra-metaheuristiklerinden (SA/ALNS) farklı** — sıra değil, *yerleşim-sonrası
global kompaksiyon*. `[KAYNAK]`

**Neden bizim için önemli:** Bizim denediğimiz her metaheuristic SIRA üzerindeydi (largest-first
zaten optimal → sıfır). Layout *bittikten sonra* parçaları söküp daha iyi boşluğa sokmayı (eject-
reinsert + compaction) HİÇ denemedik. Ve tie-break testimiz (max-support) tek-parça-yerel'di; bu
çok-parça-global. **6GB'de denenebilir** (FFT-NFV feasibility'yi yeniden kullanır, sadece dış döngü
farklı). En düşük-riskli, en hızlı prototiplenebilir YENİ kalite kaldıracı.

### A3. Öğrenme-tabanlı: DRL / diffusion / GNN  (orta-düşük öncelik)
- IR-BPP (Irregular Bin Packing, github.com/alexfrom0815/IR-BPP) — irregular parçalar için derin RL.
  `[KAYNAK]`
- DiffPack (arxiv 2310.19814) — score-based **diffusion**, öğrenilen gradyan alanları, coarse-to-fine.
  AMA: 2D, **sadece öteleme (rotasyon yok)**, 3D implemente edilmemiş. `[KAYNAK]`
**Değerlendirme:** Çoğu ML işi *online bin-packing* (parçalar tek tek gelir) veya 2D; bizim *offline,
3D, yükseklik-min* kurulumumuzla tam örtüşmüyor. Eğitim maliyeti + genelleme riski yüksek. Magics
açığı için dolaylı; **şimdilik düşük öncelik** (alan hızlı gelişiyor, 1-2 yıl sonra tekrar bakılmalı).

### A4. Exact / matheuristic (MIP / MINLP / CP)  (düşük öncelik)
Bu açı arandı; bulgular A1'in NLP koluna bağlandı (irregular 3D'de saf MIP/CP nadir, NLP baskın).
Exact yöntemler 226 parça ölçeğinde tıkanır; sadece küçük alt-problem / alt-sınır için anlamlı.

---

## B. HIZ — kaliteyi BOZMADAN (birebir/exact) hızlandırma

### B1. İkili (binary) korelasyon: AND+popcount / tensor-core 1-bit  ⭐ EN SOMUT, 6GB-UYUMLU
**Temsilci kaynaklar:**
- Turing tensor-core native 1-bit hesaplama: bit matrix-mult + **bit convolution** donanım primitifi
  (arxiv 2006.16578). `[KAYNAK]`
- GPU'da XNOR convolution: 3×3 kernel'de **~42.6× hız**; XNOR+popcount, fp çarpma yerine (arxiv
  2007.14178). `[KAYNAK]`

**Çekirdek fikir:** Bizim occupancy ve parçalar **boolean (0/1)**. Çakışma testi = bit-AND'in popcount'u
(örtüşen voxel sayısı); feasible ⇔ popcount==0. Bu **fp64 FFT'ye gerek olmadan, EXACT** (yaklaşık
değil — 0/1 için kayıpsız). `__popc` / bit-tensor-core RTX 3060'ta çok hızlı.

**Neden bizim için önemli + uyarı:** Bu, brief'imdeki "binary için FFT'yi yenen exact yöntem"
sorusunun birebir cevabı. **Dikkat — bizim "bit-pack NO-GO"muzdan FARKLI:** o, occupancy'yi bit-pack
*saklama*ydı; bu, korelasyonu *bit-AND+popcount ile hesaplama*. Denenmedi. Risk: FFT, kernel büyükse
N·logN ile kazanır; brute bit-correlation O(grid×kernel). Bizim parçalar küçük-orta + grid xy-bbox ile
zaten kırpık → bit-correlation rekabetçi olabilir, ÖZELLİKLE küçük parçalarda (decode sonu, çok sayıda
küçük parça). **Hibrit:** büyük parça→FFT, küçük parça→bit-popcount. **6GB'de prototiplenebilir**
(custom cupy RawKernel veya bitwise + popcount). ÖLÇ-ÖNCE: tek parça-boyut sınıfında bit-corr vs FFT
süresi + birebirlik kapısı.

### B2. Seyrek (sparse) voxel: VDB / sparse-convolution  (kısmi, dikkatli)
- **OpenVDB** (Museth, *TOG* 2013) — seyrek hiyerarşik voxel; bellek sadece aktif voxel'le ölçeklenir,
  O(1) erişim, boolean bitmask + boolean ops/dilation. `[KAYNAK]` %93-boş parçalarımıza ideal *depolama*.
- **Submanifold sparse conv** (Graham, *CVPR* 2018) — hesabı aktif voxel'lere kısıtlar, az FLOP. AMA
  submanifold variant **çıktıyı her yerde üretmez** (sparsity yayılmaz) → bizim NFV'nin TAM feasible
  set'ine **uymayabilir** (uyarı). `[KAYNAK]`
**Değerlendirme:** Depolama/bellek için cazip (OOM'ları gevşetir → daha ince pitch'e izin verebilir,
dolaylı kalite!). Ama feasibility correlation'ı tam üretmek için submanifold yetmez; tam sparse conv
karmaşık. Orta öncelik — özellikle **bellek** darboğazı için (ince pitch'i açabilir).

### B3. Hiyerarşik broad-phase: BVH / octree / OBB-tree / RT-core  (EK, exact değiştirmez)
- RT-core donanımıyla mesh-mesh collision (arxiv 2409.09918) `[DOĞRULANDI 2-0]` — ama *continuous*
  variant yaklaşık (bizim birebir kısıtı ihlal). `[DOĞRULANDI 3-0 ihlal]`
- O(n) GPU sparse-volume BVH (Köln Üniv.) `[DOĞRULANDI 2-0]`; 3D nesting'de OBB-tree + clearance
  early-reject (Springer s00170-021-07954-y). `[KAYNAK]`
**Değerlendirme:** Bunlar **kaba-eleme** (broad-phase) — çoğu konumu ucuza reddet, kalanı exact test et.
NFV'yi *değiştirmez*, *önüne eklenir*. Bizim xy-bbox + kademeli-z zaten bir tür broad-phase; ek kazanç
sınırlı olabilir ama küçük-parça-çok-konum durumunda yardımcı.

### B4. ELENENLER (birebirlik kısıtını ihlal)
- **Sparse-FFT** (MIT sFFT) O(k log n) — ama **yaklaşık / block-sparse**, bit-identical değil. `[ELENDİ]`
- RT-core continuous CD — hız/doğruluk takası, exact değil. `[ELENDİ]`

---

## C. SIRALAMA + SONRAKİ ADIM

### KALİTE (Magics açığı)
| # | Yön | Kazanç potansiyeli | Donanım | Risk/efor |
|---|---|---|---|---|
| 1 | **Global compaction** (eject-reinsert/swap, A2) | orta (denenmemiş, gerçek) | **6GB ✓** | düşük efor, FFT-NFV'yi yeniden kullanır → **İLK DENENECEK** |
| 2 | **Phi-function sürekli rotasyon NLP** (A1) | yüksek (Magics'in sırrı) | **süper bilgisayar** | yüksek efor (decomposition+IPOPT+quasi-phi); önce küçük-N kavram doğrulama |
| 3 | DRL/diffusion (A3) | belirsiz | GPU+eğitim | yüksek; 1-2 yıl sonra |

### HIZ (kaliteyi bozmadan)
| # | Yön | Hız potansiyeli | Donanım | Risk/efor |
|---|---|---|---|---|
| 1 | **Binary AND+popcount korelasyon** (B1, hibrit: küçük parça→popcount) | yüksek, EXACT | **6GB ✓** | orta efor (custom kernel); **İLK DENENECEK**, ÖLÇ-ÖNCE birebir kapısı |
| 2 | **VDB sparse occupancy** (B2) | bellek→ince pitch (dolaylı) | 6GB ✓ | orta; OOM'ları gevşetir |
| 3 | BVH/OBB broad-phase (B3) | sınırlı (xy-bbox zaten var) | 6GB ✓ | düşük |

### Net öneri (ÖLÇ-ÖNCE disiplini)
İki **6GB-uyumlu, denenmemiş, somut** ilk hedef var:
1. **KALİTE → global compaction** (A2): layout bittikten sonra parçaları söküp daha iyi boşluğa sok.
   Sıra-metaheuristiğinden ve tek-parça tie-break'ten farklı; tek gerçek denenmemiş 6GB kalite kaldıracı.
2. **HIZ → binary popcount korelasyon** (B1): boolean için FFT'yi atla, AND+popcount; küçük parçalarda
   hibrit. Bit-pack NO-GO'dan farklı (depolama değil, hesaplama).

Süper bilgisayar yolu artık daha net: sadece "n=28+0.5mm" değil, asıl kazanç **diskret→sürekli rotasyon**
(phi-function NLP, A1) — Magics'in muhtemel sırrı.

---

## EK — kaynak künyeleri (izlenebilirlik)
**Kalite (22 kaynak, öne çıkanlar):** EJOR concave-polyhedra continuous-rotation (whiterose 139289);
IFAC min-height continuous rotation (S2405896319314831); Springer decomposition (978-3-030-33585-4_21);
JORS 2015 (10.1057/jors.2015.94); EJOR 2018 (S0377221718300468); CGF free-rotation+compaction (13490);
IR-BPP (github alexfrom0815); DiffPack diffusion (arxiv 2310.19814).
**Hız (23 kaynak, öne çıkanlar):** Turing 1-bit tensor-core (arxiv 2006.16578); GPU XNOR conv 42×
(arxiv 2007.14178); OpenVDB (Museth TOG 2013); submanifold sparse conv (Graham CVPR 2018); O(n) sparse
BVH (Köln); OBB-tree 3D nesting (Springer s00170-021-07954-y); RT-core collision (arxiv 2409.09918);
MIT sFFT (csail netmit); AM pixel-based packing (optimization-online 2022); 3D-NFP slicing (T&F 2025.2604312).

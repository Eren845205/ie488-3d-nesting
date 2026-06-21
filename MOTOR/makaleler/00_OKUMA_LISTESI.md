# Makaleler — Okuma Listesi + Araştırma Planı

> **2026-06-21 MAGICS KIYASI turu → [02_magics_kiyas_literatur_2026-06-21/](02_magics_kiyas_literatur_2026-06-21/)**
> Magics açığını (kalite 1.26× + hız 78dk) kapatmak için 22 peer-reviewed kaynak.
> Sentez + künye + 3 indirilen PDF (EJOR 2018 quasi-phi, SFF 2015 Araujo, NVIDIA
> 2010 octree). Yol haritası: repo kökü `PLAN_IYILESTIRME_YOLHARITASI.md`.

> **2026-06-14 deep-research turu tamamlandı → [01_ARASTIRMA_BULGULAR.md](01_ARASTIRMA_BULGULAR.md)**
> (Gap 1-2 doğrulanmış 9 makale + "önce entegre et" top-3; Gap 3-5 ikinci tur bekliyor).

> "Makale → KOD" hattı (§5.1): makale yüklenir → okunur → çözücü/operatör kodu
> yazılır → benchmark'tan geçer. Makale doğrudan modele yüklenmez; tekniği
> kodlanır. Geçemeyen teknik MERGE EDİLMEZ (makale iddiası ≠ bizim veride iyi).

## Cevap: makale yükleyelim mi? → EVET, ama amaca göre küratörlü

Rastgele makale yığını gürültü olur. Zaten **8 makale repoda var** (aşağıda).
Yöntem: (1) elimizdekileri sınıflandır → motorun hangi parçasını besliyor;
(2) eksik aileler için en iyi okulların (MIT/Stanford/ETH/TU Delft/Lancaster OR
ekolü vb.) makalelerini araştır; (3) her birini kodla + benchmark kapısı.

## A. Repoda MEVCUT makaleler (`MOTOR/makaleler/pdf/`)

> ✅ 2026-06-18: 8 PDF + çıkarılmış `.pdf.txt` metinleri proje kökünden
> `MOTOR/makaleler/pdf/` altına taşındı (motor bölümünde toplandı).
>
> ⚠️ **Bu 8 PDF önceden-var (workflow ÖNCESİ) makalelerdir** — eklemeli üretim
> nesting'i konulu. Deep-research workflow'unun BULDUĞU makaleler ayrı (aşağıda).

### A.2 Araştırma WORKFLOW'undan inen makaleler (`WORKFLOW_*.pdf`)

> ✅ 2026-06-18: 01_ARASTIRMA_BULGULAR'da doğrulanan 9 künyenin açık-erişimli
> (arXiv) 4'ü indirildi → workflow'un ürettiği makaleler artık fiziksel olarak da
> elde. Geri kalan 5 künye dergi-erişimli (DOI ile 01 dosyasında).

| Dosya | Künye | Motora karşılığı (kodda) |
|---|---|---|
| `WORKFLOW_SATzilla_Xu2008_algorithm-selection.pdf` | Xu ve ark. 2008 (arXiv 1111.2249) | Algoritma-seçim modeli `selection/` |
| `WORKFLOW_Kerschke2019_algorithm-selection-survey.pdf` | Kerschke ve ark. 2019 (arXiv 1811.11597) | Özellik mühendisliği / tasarım |
| `WORKFLOW_RenauHart2024_easy-instance-prefilter.pdf` | Renau & Hart 2024 (arXiv 2406.16999) | Kolay-instance ön-filtresi `selection/prefilter.py` |
| `WORKFLOW_Kostovska2023_portfolio-selection.pdf` | Kostovska ve ark. 2023 (arXiv 2310.10685) | Çözücü-seti budama yön (kavramsal) |

| Makale | Konu | Motorun neyini besler | Durum |
|---|---|---|---|
| Nesting Problems in AM — Classification and Review 2025 | **Genel literatür haritası** | hangi algoritma aileleri var, taksonomi | 📖 okunmalı (öncelik 1) |
| Analysis of irregular 3D packing problems in AM — taxonomy and dataset | **Benchmark dataset + taksonomi** | gerçek-veri benchmark (R7 panzehiri) | 📖 öncelik 1 (dataset!) |
| Nesting algorithm for optimization part placement in AM | yerleştirme algoritması | DBLF/constructive + metaheuristik fikirleri | 📖 okunmalı |
| A 3D nesting method based on convex-concave coding similarity (voxelized) | **voxel tabanlı** nesting | bizim voxel yaklaşımımızın yakını | 📖 öncelik 2 (en yakın) |
| 3D Placement Problem in AM | yerleştirme problemi formülasyonu | amaç fonksiyonu / kısıt modeli | 📖 okunmalı |
| Energy-aware nesting and scheduling on single SLM machine | **nesting + çizelgeleme** (MILP) | hocanın alanı; §6.4 çizelgeleme katmanı | 📖 öncelik 2 |
| 1-s2.0-S0360835218304649 | (içerik teyit edilecek) | — | 📖 sınıflandırılacak |
| 1-s2.0-S2214860420308642 | (içerik teyit edilecek) | — | 📖 sınıflandırılacak |

**Not:** `.pdf.txt` çıkarılmış metinler bazıları için var (review + irregular
packing + nesting algorithm) — okuma/analiz buradan hızlı başlar.

## B. ARAŞTIRILACAK makaleler (eksik aileler — en iyi okullar)

| Konu | Neden gerek | Motorun neyini besler |
|---|---|---|
| **Algorithm selection / per-instance portfolios (SATzilla deseni)** | §6.3.1 — hangi veri tipine hangi algoritma | Algoritma-seçim modeli (telemetri→karar ağacı) |
| **Hyper-heuristics / instance-specific configuration** | §6 Instance-Tuner'ın teorik temeli | Tuner menü seçimi + LLM önericisi |
| **3D irregular bin packing — modern metaheuristik (GA/ALNS) operatörleri** | GA/tabu operatörlerini iyileştirmek | GA crossover/mutasyon, ALNS ekleme adayı |
| **Deepest-bottom-left / heightmap yerleştirme varyantları** | DBLF'yi güçlendirmek (overhang sınırı R5) | DBLF + tam-3D yerleştirme kararı |
| **Voxel/SDF tabanlı çarpışma + yerleştirme** | pitch/çözünürlük + hız | adaptif pitch + drop_map |

## C. Makale → kod entegrasyon kapısı (her makale için)

1. Oku → tekniği özetle (hangi aile/operatör, hangi veri tipinde iyi iddiası).
2. Bu dosyada satırını "kodlandı" durumuna getir + `01_ALGORITMALAR.md`'ye not.
3. Çözücü/operatör olarak kodla (`03_GENISLETME.md` A adımları).
4. **Benchmark kapısı:** ortalamayı geçmiyorsa MERGE YOK. Sonuç `02_PERFORMANS.md`.

## Sıradaki somut adım (öneri)

1. Öncelik-1 üçlüsünü oku: **Review 2025** (harita) + **irregular packing dataset**
   (gerçek benchmark) + **voxel convex-concave** (bize en yakın).
2. Web'den "algorithm selection for packing" + "hyper-heuristic 3D packing" en iyi
   2-3 makaleyi araştır, buraya ekle.
3. Dataset makalesindeki test setini benchmark'a örnek olarak almayı değerlendir
   (R7'nin gerçek-veri ayağı).

_Bu araştırmayı (web taraması + analiz) ayrı bir iş olarak yürütebilirim — iste yeter._

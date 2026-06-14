# 01 — Algoritmalar (mevcut sistem, tam detay)

> Sistemde ŞU AN olan her algoritma ayrı ayrı. Her değişiklikten önce buradan
> oku, üstüne ekle. Durum etiketleri: ✅ kurulu+test, 🟡 iskelet, ❌ yok/plan.

## 0. Mimari özet — nasıl bir arada çalışıyorlar

```
İNSTANCE (parçalar + konteyner)
        │  voxelize (instances/pitch.suggest_pitch ile adaptif pitch)
        ▼
   VoxelPart'lar  ──►  ÇÖZÜCÜLER (ortak Solver protokolü)
                         ├── DBLF      (constructive baseline)
                         ├── SA        (+ adaptif t0)
                         ├── GA
                         ├── Tabu
                         └── MultiStartSA
                         │   hepsi AYNI decode'u kullanır (dblf.place_in_order)
                         ▼
                    PORTFÖY (hepsini koş, en iyiyi seç)
                         ▼
                    INSTANCE-TUNER (örneğe özel konfig menüsü, monoton kabul)
                         ▼
                    en iyi yerleşim (SolveResult)
```

**Ortak sözleşme (kritik):** tüm çözücüler `Solver` protokolünü uygular —
`solve(parts, bin_factory, *, budget, seed, order_key) -> SolveResult`
(`src/nesting3d/solvers/base.py`). Çözüm = sıralı `[(parça, oryantasyon_idx)]`;
decode = `dblf.place_in_order` (HERKES aynı decode → kalite kıyası adil).
Bu sözleşme sayesinde yeni algoritma eklemek motoru bozmaz (bkz 03_GENISLETME).

---

## 1. DBLF — Deepest-Bottom-Left-Fill ✅

- **Dosya:** `src/nesting3d/dblf.py`, sarmalayıcı `solvers/dblf_solver.py`
- **Tür:** Deterministik constructive (greedy) — metaheuristik DEĞİL.
- **Ne yapar:** Parçaları bir sıraya göre tek tek alıp her birini "en derin,
  en sol-alt" geçerli konuma indirir (heightmap üstüne damlatma). Çıkar tabanı:
  **hiçbir metaheuristik bunun altına düşemez** (hepsi DBLF'yi tohum alır).
- **Sıralama (`order_key`):** default (hacim-azalan) + `plates_first_key`
  (aynı tip plakaları ardışık) + `tower_order_key` (numune fazından).
- **Çekirdek maliyet:** `bin3d.drop_map` (her parça×oryantasyon için tüm
  konumlara damlama yüksekliği). Bkz §8 (hız).
- **Sınır:** heightmap → overhang ALTINA parça sokamaz (bilinen, kabul edilmiş
  takas; PLAN_3D §2.4 / R5).
- **Durum:** ✅ olgun, tüm portföyün temeli.

## 2. SA — Simulated Annealing ✅ (+ adaptif t0, R2)

- **Dosya:** `src/nesting3d/sa3d.py` (mantık), `solvers/sa_solver.py` (sarmalayıcı)
- **Ne yapar:** DBLF tohumundan başlar; (sıra + oryantasyon) uzayında komşu
  hamlelerle arar. **Enerji = max_yükseklik + 0.1·RMS** (RMS = sıkışıklık
  gradyanı; düz manzaradan çıkmayı sağlar). Geometrik soğuma, best-so-far korunur
  (asla baseline altına düşmez).
- **Komşu hamleleri (`_neighbour`):** swap / insert / segment-reverse / oryantasyon-flip.
- **t0 (başlangıç sıcaklığı):**
  - `t0=3.0` (default, elle kalibre 2026-06-09) — **numune 181.5 rekoru bu yola bağlı.**
  - `t0="auto"` (**R2, 2026-06-14**): ana döngü ÖNCESİ 50 rastgele komşu delta
    istatistiğinden türetilir → `t0 = medyan(pozitif delta)/ln(1/0.5)`. Farklı
    ölçekli veri setlerinde "3 mm sabiti" anlamsızlaşmasını çözer.
- **Parametreler:** `budget`=iterasyon, `seed`, `t0`, `t_min=0.05`.
- **DEĞER (ölçülen):** few_large'da sabit-t0 tek-start 269.3'te takılı; **auto-t0
  → 211.6 (%21 kaçış)** (02_PERFORMANS).
- **Durum:** ✅ olgun; R2 eklendi.

## 3. GA — Genetik Algoritma ✅

- **Dosya:** `src/nesting3d/solvers/ga_solver.py`
- **Ne yapar:** Birey = ortak genotip (sıra + poz listesi). Operatörler: sıra için
  OX/PMX crossover, poz için uniform crossover; mutasyon = SA `_neighbour`
  hamleleri (yeniden kullanım); elitizm + best-so-far; DBLF baseline popülasyona
  tohumlanır (asla baseline altına düşmez).
- **DEĞER:** few_large gibi büyük+küçük karışım/yüksek-adetli setlerde GA
  genellikle KAZANIYOR (hocanın A12 sinyaliyle uyumlu — "GA bu tip veride iyi").
- **Durum:** ✅ portföyde; operatör/popülasyon parametre taraması backlog.

## 4. Tabu — Tabu Search ✅

- **Dosya:** `src/nesting3d/solvers/tabu_solver.py`
- **Ne yapar:** Aynı komşuluk hamle seti; tabu listesi (hamle imzası, parametrik
  tenure); aspirasyon (best'i geçen hamle serbest). Best-so-far + DBLF tohum.
- **Durum:** ✅ portföyde.

## 5. MultiStartSA — Çok-Başlangıçlı SA ✅ (R4)

- **Dosya:** `src/nesting3d/solvers/sa_solver.py` (`MultiStartSA`)
- **Ne yapar:** N bağımsız SA start'ı **deterministik** türetilen seed'lerle
  (`_derive_seed(seed_base, run_seed, start_idx)`), toplam bütçe bölünür, en iyi
  otomatik seçilir. Meta: **median + best + std** ("şanslı seed" değil "tipik"
  kalite görünür — R4'ün overfit panzehiri).
- **Koşu modeli:** SIRALI (Windows multiprocessing pickle tuzağından kaçınır;
  paralellik HPC fazında bin_factory picklable yapılınca).
- **DEĞER:** few_large'da multistart5 → 211.6 (tek-start 269.3'ten %21 iyi).
- **Durum:** ✅ registry'de `"multistart"`.

## 6. Portföy — hepsini koş, en iyiyi seç ✅

- **Dosya:** `src/nesting3d/solvers/portfolio.py`
- **Ne yapar:** Aynı instance'ı seçili çözücülerle koşar, kıyas tablosu + en iyi
  seçimi üretir. "Tek algoritmaya güvenme" ilkesi — overfit'e karşı güvenli.
- **DEĞER:** her instance'ta FARKLI çözücü kazanıyor (02_PERFORMANS) → tek
  çözücü domine etmiyor, portföy en iyiyi alıyor.
- **Durum:** ✅; benchmark `_SOLVER_REGISTRY` = dblf, sa3d, ga, tabu, multistart.

## 7. Instance-Tuner — örneğe özel ince ayar ✅ (çekirdek; LLM'siz)

- **Dosya:** `src/nesting3d/tuner.py`
- **Ne yapar:** Genel portföy çözdükten SONRA, o örneğe özel sabit bir KONFİG
  MENÜSÜNÜ dener (sa_auto, multistart 3/5, order_key varyantları, tekil çözücüler),
  **monoton kabul** ile en iyiyi seçer: **çıktı asla genel sonuçtan KÖTÜ olamaz.**
  Motor KODUNU değiştirmez; sadece konfig seçer. Menü PLUGGABLE (`menu=None` →
  ileride LLM önericisi aynı arayüze takılır).
- **Neden overfit DEĞİL:** çözüm anında bu zor örneğe daha çok hesap harcamak;
  özelleşme motorun kalıcı koduna sızmaz (yapısal yasak).
- **Durum:** ✅ deterministik çekirdek + 16 test. ❌ LLM önericisi (sonraki faz).

## 8. Yardımcı motor parçaları (algoritma kalitesini doğrudan etkiler)

- **Adaptif pitch** (`instances/pitch.py`, R6) ✅ — voxel çözünürlüğü her örneğin
  en küçük parçasından türetilir (`min_dim/2.5`, [0.5,15]). Tek-konfig kuralı
  artık pitch SAYISINA değil bu KURALA uygulanır.
- **24 eksen-hizalı poz** (`voxelize.py`, R1) ✅ — 8→24 poz (Ry dahil). DEĞER:
  long_rods 8 poz 46.8 → 24 poz 41.6 (%11, çubukları yatırma).
- **drop_map hızlı yol** (`bin3d.py`) ✅ — kutu parçalar için ayrılabilir
  kaydırmalı-maksimum (38× hız; benchmark 520s→90s). Konkav/gerçek-STL genel
  döngüye düşer (numune hızlanmadı; backlog).
- **Voxel bütçesi skip** (`benchmark.py`, `MAX_VOXELS_PER_AXIS=170`) ✅ — aşırı
  ince parça benchmark'ı patlatmasın; aşan instance ATLA+LOGLA.

## 9. ❌ Henüz YOK (plan)

- **MLP / sinir ağı:** YOK ve **planda doğrudan yerleştirme için YOK** (kasıtlı).
  "Öğrenme" = düz istatistik + okunabilir kural (karar ağacı), kara-kutu değil.
- **Algoritma-seçim modeli** (§6.3.1): özellik vektörü → kazanan algoritma tahmini
  (karar ağacı/random forest). Veri temeli (telemetri) birikiyor; model YOK.
- **Instance-Tuner LLM önericisi:** menü pluggable, LLM katmanı YOK.
- **MILP / kesin çözüm** (küçük instance): YOK (A1/A12'ye bağlı).
- **Genel-yol drop_map hızı** (numune): YOK (temiz numpy/scipy çözümü yok; numba
  gerekir — dep yükü).

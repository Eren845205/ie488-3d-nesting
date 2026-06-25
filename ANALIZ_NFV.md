# NFV Kalite Modu — Toplam Gelişim & Overfit Analizi

> **Tarih:** 2026-06-24 · **Branch:** `m1-cavity-nfv` · **Durum:** kod + UI uçtan uca doğrulandı (git temiz)
> **Kapsam:** NFV cavity "kalite modu" çekirdeği + hız optimizasyonları + oryantasyon/pitch kaldıraçları.
> Kaynak ölçümler: `scripts/c3_*` deney scriptleri + `RESUME_2026-06-22..24.md` + memory backlog.

---

## ⚠️ ÖNCE KRİTİK AYRIM: bu bir TAKAS, tek yönlü "hızlanma" değil

NFV, **kalite için hızdan feragat eden opt-in bir mod**. Günlük (default) akış **heightmap**'tir ve
**hiç değişmedi** — aynı hız, aynı sonuç, aynı kod yolu. Kod teyidi:
- `scripts/demo_pipeline.py:550` → `nesting_mode = payload.get("nesting_mode", "heightmap")` (default).
- NFV yalnızca UI checkbox / `scenario["nesting_mode"]="nfv"` ile devreye girer.

Dolayısıyla "toplam gelişme" iki ayrı eksende okunmalı; yoksa yanıltıcı olur:
1. **Kalite** — NFV modu AÇIKKEN ne kadar kısa istif.
2. **Hız** — iki farklı anlam (aşağıda ayrıştırıldı).

---

## 1) KALİTE — istif yüksekliği (mm, DÜŞÜK = İYİ)

| Veri | Heightmap (default) | NFV n=4 | NFV n=8 | **Kazanç (n=8 vs heightmap)** |
|---|---|---|---|---|
| **Plan2** | 740 | 556 | **522** | **~%29 daha kısa** |
| **Plan1** | 147.3 | 132.1 | ~127 (n=8 +%3.8) | **~%14** |
| **Plan3** | 1165 | 930 | (n=8 ölçülmedi) | **%20+** |
| boxy (sentetik saf-kutu) | — | — | — | **%0 — NFV burada kazanmaz** |

**Yorum:** 3 bağımsız gerçek veride **%14–29 daha kısa istif** — ölçülmüş, tek veriye dayanmayan kazanç.
Referans: **Magics Plan2 = 492mm** (0.5mm fine). Bizim açık n=4'te %13 → **n=8'de %6**'ya kapandı.
⚠️ Adalet notu: bizim 522 KABA pitch (2.0mm), Magics 492 FINE (0.5mm) — adil kıyas için süper
bilgisayarda n=28 + 0.5mm fine gerekir (bu makinede OOM).

---

## 2) HIZ — iki farklı "hız" var, karıştırmamak şart

### (a) NFV'nin KENDİ içindeki hızlandırma (NFV'yi KULLANILABİLİR kılan iş)
| Optimizasyon | Etki |
|---|---|
| Kademeli z-dilim | 985s → 376s (**2.6×**) |
| xy-bbox daraltma | 985s → 281s (**3.5×**) |
| GPU-resident (Plan2, RTX 3060 6GB) | **5.5×** |
| Cross-dataset GPU kazancı | plan1 **2.7×**, plan3 **3.3×**, plan2 **5.5×** |

Pitch + bellek guard sayesinde NFV "5 saat / OOM (Plan2 0.5mm)" → "**~2 dk (2.0mm)**" haline geldi.

### (b) NFV vs DEFAULT heightmap — burada NFV bir MALİYET
- NFV Plan2 ~112–376s **vs** heightmap ~9s → **NFV hâlâ ~10–40× YAVAŞ**.
- Default akışın hızı **DEĞİŞMEDİ**.

**Net:** "Algoritma genelinde hızlandı" demek **YANLIŞ**. Doğru ifade:
> *Kaliteyi açan yeni bir (yavaş) mod eklendi ve o mod kendi içinde 3–5× hızlandırılarak kullanılabilir kılındı.*

---

## 3) OVERFIT RİSKİ — bileşen bileşen

| Bileşen | Risk | Gerekçe |
|---|---|---|
| **n=8 default** | ✅ **YOK (matematiksel garanti)** | 4⊂8 küme-içerme → NFV greedy n=8'de **her veride** ≥ n=4 kadar iyi. Veriye uydurma değil, set teorisi. `NFV_DEFAULT_ORIENTATIONS=8`. |
| **Pitch seçici** | ✅ **Giderildi** (`a26d180`) | İlk hali (tek-oran 0.5) Plan2-overfit'ti, **Plan1'i çökertiyordu**. Düzeltme: güvenli 1.0'dan başla → bellek için adaptif kabalaştır → sığmazsa heightmap'e düş. plan1/2/3/boxy **hiçbiri çökmüyor**. |
| **Plaka guard** (`621936c`) | ✅ Sigorta | En büyük parça + 2·margin plakaya sığmalı; sığmazsa feasible=False. boxy çökmesi giderildi; gerçek veride tetiklenmez. |
| **quality="max"** | ✅ YOK | Sabit sayı değil — RAM'den türeyen donanım-tavanı (`_hw_max_orientations`: 16GB→12, datacenter→28). |

**Genel değerlendirme:** Bu oturumun ANA İŞİ zaten **bir overfit'i bulup gidermekti** (pitch Plan1 çökmesi).
Şu an her parametre türetilmiş: pitch ← min_feature (geometri) + RAM + plaka; oryantasyon ← küme-içerme +
RAM. "SABİT-SAYI YASAK" kuralına uyuluyor. **Aktif overfit riski görülmüyor.**

---

## 4) GENELLEME — bütün setlerde geçerli mi?

**Kalite genellemesi:** ✅ Evet — 3 bağımsız gerçek veride kazanç (%14 / %20 / %29), tek veride değil.
n=8'in ≥ n=4 garantisi de veri-bağımsız (matematiksel).

**Hız genellemesi:** ✅ GPU kazancı her veride birebir (CPU-A = GPU yükseklik) + grid büyüdükçe artıyor
(2.7× → 5.5×). NFV'nin default'tan yavaş olması da her veride tutarlı şekilde geçerli.

### İki DÜRÜST çekince (overfit DEĞİL, NFV'nin doğası)
1. **Sentetik saf-kutu (boxy):** NFV burada kazanmaz — cavity (oyuk) yoksa NFV'nin avantajı yoktur.
   Kazanç parçanın boşluk/kutuluk oranıyla orantılı. Guard sayesinde çökmez, sadece fayda yoktur.
2. **Numune verisi YANILTICI:** kutuluk düşük (0.35) olduğu için NFV cavity testbed'i DEĞİL. Gerçek
   değerlendirme Plan2/Plan3 gibi cavity-zengin (kutuluk ~0.07) verilerde yapılmalı. (Memory'de
   "⚠️ ÖNEMLİ DERS: numune cavity testbed'i YANILTIR — Plan2 kullan" olarak kayıtlı.)

---

## 5) ÖZET (tek paragraf)

NFV, **opt-in** olarak gerçek verilerde **%14–29 daha kısa istif** sağlıyor; bedeli default'tan ~10–40×
yavaşlık (ama mod kendi içinde 3–5× hızlandırılıp kullanılabilir kılındı). Default heightmap akışı hiç
değişmedi — hızı aynı. **Overfit riski aktif olarak yönetildi**: bu oturumda bir pitch overfit'i bulunup
giderildi; n=8 ve quality parametreleri matematik/donanımdan türetildi (sabit-sayı yok). Kalite kazancı
3 bağımsız veride doğrulandı; tek çekinceler NFV'nin doğası gereği (saf-kutuda ve düşük-kutuluk numunede
kazanmaması) — bunlar overfit değil. Magics açığı %13'ten %6'ya kapandı; kalan fark büyük ölçüde KABA
pitch kaynaklı (adil kıyas için süper bilgisayarda fine pitch + yüksek-n gerekli).

---

## 6) MAGICS AÇIĞI — 6GB ALGORİTMA KALDIRACI TÜKENDİ (2026-06-25 oturumu)

**Soru:** Kalan %6 Magics açığı (NFV n=8 = 522 vs Magics 492) süper bilgisayar BEKLEMEDEN,
algoritma tarafında kapatılabilir mi?

**Yöntem:** Açığın kaynağını kanıtlarla daralt → kalan tek ucuz kaldıracı (yerleştirme tie-break) ÖLÇ.

### Açığın kaynağı: tüm parametre eksenleri 6GB'de doygun/kilitli
| Kaldıraç | Durum | Kanıt |
|---|---|---|
| **Pitch** (2.0→0.5mm) | DOYGUN | 2.0=556 → 1.5=550.5 = **%1** (n=4, `c3_pitch_curve`). Açık pitch DEĞİL. |
| **Eksen-hizalı oryantasyon** | DOYGUN | n=8=522 → n=12=516 = **%1.1** (`c3_quality_levers`). |
| **Eğik açılar** (20-35° Rx) | DENENMİŞ | `voxelize.py:93` — eğik pozlar `mats[8:12]`'de; n=12 onları içeriyor → marjinal. |
| **Sıra** (SA / multi-start) | ÖLÜ | largest-first zaten optimal (556→556). |
| **Donanım** | KİLİTLİ | 6GB'de tek çalışan pitch 2.0mm (1.5mm GPU OOM, 1.0mm CPU OOM). |

> ⚠️ DÜZELTME: önceki "açık büyük ölçüde KABA pitch kaynaklı" tahmini **ZAYIF** — pitch eğrisi
> doygun olduğu için açık pitch değil, parametre eksenleri 6GB'de tükenmiş durumda.

### Son ucuz kaldıraç: yerleştirme tie-break ("free void fill") — ÖLÇÜLDÜ → ÖLÜ
Parametre eksenleri tükendiğinden geriye greedy'nin KENDİSİNİ değiştirmek kaldı. En ucuz aday:
decode tie-break key `(max(z+fh, cur_max), z+fh, z, y, x, oi)` mevcut zarf içine sığan TÜM
pozisyonları eşit-skorlu sayıp aralarından "köşe" (min y,x) seçiyor. Magics "free void fill"
hipotezi: bu eşit-skorlu pozisyonlar arasında EN İYİ OTURAN'ı (footprint en çok alttan
desteklenen = max-support) seçmek, yüksekliği bozmadan greedy myopia'yı azaltabilir.

**ÖLÇÜM (`scripts/c3_tiebreak.py`, Plan2 @2.0mm n=8 GPU):**
| tie-break | yükseklik | not |
|---|---|---|
| baz BLB (köşe) | **522.0mm** | sanity: mevcut `decode_gpu` ile BİREBİR |
| max-support | **522.0mm** | **fark %0.0 — TAM SIFIR** |

**Neden 0:** tie-break yalnız (x,y) seçer, zstar (yükseklik) HER MODDA sabit. Plan2 cavity-zengin
(bol feasible bölge) → (x,y) dağılımı sonraki parçaların yükseklik sonucunu değiştirmiyor.
En zorlu cavity testbed'inde (Plan2) %0 → cross-dataset gereksiz; tie-break kaldıracı **ÖLÜ**.

### KARAR: 6GB'de algoritma yolu KAPANDI
Pitch + oryantasyon + sıra + tie-break — **dördü de** 6GB'de tükendi/etkisiz. Kalan %6 açık
greedy'nin pratik tavanı bu çözünürlükte; Magics 492'si **fine pitch (0.5mm) + yüksek/sürekli
oryantasyon** birleşik etkisinden (her ikisi de 6GB'de OOM) geliyor. Adil kıyas + gerçek NFV
tavanı için **SÜPER BİLGİSAYAR (n=28 + 0.5mm fine, bol VRAM)** tek yol. Bu, A14 coarse-to-fine
rotasyon planıyla ([[project-konteyner-app-plani]]) ve datacenter batched-FFT backlog'uyla örtüşür.
DERS: kaynak-daraltma + Plan2 (en zorlu testbed) ölçümü, belirsiz bir kaldıracı (tie-break) tek
deneyde net "ölü"ye taşıdı — boş cross-dataset turundan korudu.

---

## §7 — Global compaction (top-K eject + best-fit repack) — NO-GO (2026-06-25)

Literatür araştırması (`MOTOR/makaleler/03_nfv_bakilmamis_yontemler_2026-06-25/`, A2/CGF) global
compaction'ı "6GB-uyumlu, denenmemiş ilk kalite hedefi" olarak işaret etti: layout BİTTİKTEN sonra
parçaları söküp daha iyi boşluğa sok (sıra-metaheuristiğinden ve tek-parça tie-break'ten farklı,
çok-parça + layout-sonrası). `scripts/c3_compaction.py` ile Plan2 @2.0mm n=8 GPU'da ölçüldü.

**KOD-ÖNCESİ MONOTONİKLİK TEOREMİ:** Bir parça yerleştirildiğinde occ'ta yalnız daha büyükler vardı;
greedy minimal z+fh'ye koydu. Sonraki parçalar occ'u yalnız BÜYÜTTÜ. -> TEK parçayı söküp geri koymak
(occ artık daha dolu) z+fh'yi ASLA düşüremez. Gerçek kazanç ancak >=2 parçayı BİRLİKTE eject edip occ'u
gerçekten küçültünce gelebilir (tavan parçaları birbirinin yerini açar). Tek serbestlik = repack SIRASI.

**ÖLÇÜM (baz 522.0mm = bilinen değer; sanity geçti):**

| repack politikası | sonuç | yorum |
|---|---|---|
| largest-first K=all (sanity) | 522.0mm = baz, **+0.0%** | birebir -> monotoniklik teoremi doğrulandı |
| best-fit K=2 / K=5 | 522.0mm, **+0.0%** | tavan parçaları zaten optimal yerde |
| best-fit K=10 | 840.0mm, **-60.9%** | best-fit küçüğü öne/büyüğü sona alıyor -> felaket kötüleşme |

**Neden ölü:** İki repack politikası da kalite kazancı vermedi. largest-first occ_rest ⊆ baz-occ olduğu
için tavanı asla düşüremez (monotoniklik, K=all'da birebir 522 ile kanıtlı). best-fit ise sırayı bozup
büyük parçaları yükseğe iterek KÖTÜLEŞTİRİYOR. Tavanı düşürmek için tavan parçasının ALTINDAKİ dolu
kolonu da eject edip tüm kümeyi GLOBAL yeniden düzenlemek gerekirdi = bu artık **sıra/reorder problemi =
ZATEN ÖLÜ** (largest-first optimal, SA/ALNS 0). CGF compaction'ın sürekli-pozisyon "push/swap"
mekanizması bizim **diskret + BLB (zaten bottom-most) + greedy** dünyamızda karşılıksız — BLB her parçayı
zaten anlık-compact yerleştiriyor; geriye kalan serbestlik (sıra/oryantasyon/sürekli-rotasyon) ya doygun
ya da süper bilgisayar işi (phi-function NLP, A1).

**KARAR:** Global compaction da 6GB algoritma yolunda ÖLÜ — pitch + oryantasyon + sıra + tie-break'e
**beşinci** olarak katıldı. Magics açığı için tek kalan yol SÜPER BİLGİSAYAR (sürekli rotasyon NLP /
n=28+0.5mm fine). DERS: monotoniklik teoremini kod-öncesi kurmak, K=2/5'in neden 0 çıktığını önceden
açıkladı; tek Plan2 koşusu (en zorlu testbed) belirsiz kaldıracı net "ölü"ye taşıdı, cross-dataset gereksiz.

---

## EK — sayıların kaynağı (izlenebilirlik)
- Kalite/oryantasyon: `scripts/c3_quality_levers.py` (n=4/8/12 sweep, Plan2 @2.0mm GPU).
- Cross-dataset hız: `scripts/c3_xdataset_speed.py` (plan1/plan3 tam tablo).
- Pitch eğrisi/OOM sınırları: `scripts/c3_pitch_curve.py`.
- Tie-break kaldıracı (max-support, NO-GO): `scripts/c3_tiebreak.py` (Plan2 @2.0mm n=8, 522=522 birebir).
- Global compaction (top-K eject + best-fit repack, NO-GO): `scripts/c3_compaction.py` (Plan2 @2.0mm
  n=8; largest K=all=522 birebir, best-fit K=2/5=+0.0%, K=10=-60.9%).
- Üretim kodu: `src/nesting3d/nfv_solve.py` (n=8 default, quality=max), `src/nesting3d/instances/pitch.py`
  (`suggest_nfv_pitch`), `scripts/demo_pipeline.py` (dispatch, default heightmap).
- İlgili commit'ler: `2d8a5da` (adaptif pitch), `a26d180` (pitch cross-dataset fix/overfit gider),
  `621936c` (plaka guard), `ae306c3` (n=8 default + quality=max), `a57dbac` (pyfftw NO-GO).

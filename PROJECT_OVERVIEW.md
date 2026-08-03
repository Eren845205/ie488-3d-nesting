# PROJECT_OVERVIEW — IE 488 3D Nesting Motoru (Teknik Özet)

> **Amaç:** Dışarıdan bir danışmanın projeyi hızla ve doğru kavraması için hazırlanmış
> teknik özet. İçerik 2026-07-25 tarihinde kod tabanının doğrudan taranmasıyla
> derlenmiştir; her önemli iddiada dosya (ve çoğunlukla satır) referansı verilmiştir.
> Emin olunamayan noktalar **[DOĞRULA]** etiketiyle işaretlidir. Pazarlama dili
> kullanılmamıştır; bilinen eksikler §5'te açıkça listelenmiştir.
>
> **Not:** Repo kökündeki `README.md` projenin erken dönemini (2D nesting + ilk 3D
> denemesi) anlatır ve **bayattır**. Güncel gerçeklik bu doküman + `MOTOR/
> YONTEM_HARITASI_DATA_BASE.md` (karar veritabanı) + `STRATEJI/` klasörüdür.

---

## 1. PROBLEM FORMÜLASYONU

### 1.1 Problem tanımı

**3D, açık-boyut (open-dimension) nesting / 3D strip packing.** Düzensiz 3B parçalar
(STL) sabit tabanlı tek plakaya yerleştirilir; taban (W×D) sabittir, **yükseklik
sınırsızdır ve minimize edilen büyüklüktür** (`src/nesting3d/bin3d.py:5-8`,
`src/nesting3d/instances/format.py:88-90` — `ContainerSpec.height_mm=None` =
açık-boyut modu). Uygulama alanı: AM/SLM toz-yatağı nesting; referans rakip ticari
yazılım Magics'tir (`MOTOR/YONTEM_HARITASI_DATA_BASE.md` §1).

Bu bir **bin packing değildir** (tek plaka, plaka sayısı minimize edilmiyor);
**doluluk da birincil amaç değildir** (aşağıda).

### 1.2 Amaç fonksiyonu — "legal yükseklik"

Birincil metrik **istif yüksekliği (mm, düşük = iyi)**; yerleştirme kuralı
`(z_top, z, y, x)` leksikografik minimumu seçer (`src/nesting3d/dblf.py:8-11`).
Doluluk (`packing_density`, `mesh_fill_ratio`) ve RMS-yükseklik yalnız rapor/
tie-break metriğidir (`bin3d.py:500-540`).

Ham yükseklik tek başına kabul edilmez. Proje anayasası A2 (`STRATEJI/00_ANAYASA.md`)
gereği rapor edilen yükseklik ancak ÜÇ koşul birden sağlanırsa **legal**dir:

1. **Tam yerleşim:** yerleşen parça sayısı == toplam parça sayısı.
2. **Clearance:** parçalar arası minimum boşluk ≥ **2.0 mm** (hoca kararı 2026-07-09
   ile 1mm→2mm).
3. **Ayrılabilirlik (separability):** 5-yön sıralı söküm (±X, ±Y, +Z) ile 0 kilit;
   kilit>0 ise rot-söküm denetimi (döndürerek çıkarma, `rotation_extract.py`)
   kilitleri açabiliyorsa sonuç **"söküm-planlı legal"** sayılır (A2 güncellemesi
   2026-07-15).

Biri ihlalde sonuç **INVALID**'dir ve sebep raporlanır. Tanım iki yerde birebir
kodludur: `scripts/eval_gate.py:253-283` (`legal_of`) ve
`src/nesting3d/telemetry.py:163-187` (`append_run_v2`).

### 1.3 Kısıtlar

| Kısıt | Değer / mekanizma | Kaynak |
|---|---|---|
| Parça-parça boşluk | **2.0 mm** her yönde. Dikkat: config dosyasında değil, **kod sabiti** (`WEB_MIN_CLEARANCE_MM = 2.0`). mm→voxel dönüşümü `clearance_to_voxels`; bağımsız post-nest doğrulama cKDTree ile devoxelize mesh üzerinde (3000 örnek). | `scripts/demo_pipeline.py:73`, `coarse_to_fine.py:40-70`, `clearance.py:58-106` |
| Plaka (build volume) | **335 × 335 × 600 mm** (gerçek yazıcı; hocadan). Çözüm önceliği: `configs/plate.local.json` → env `PLATE_W/D/H_MM` → parçalardan otomatik (pay max(%2, 10mm)). | `configs/plate.local.json`, `src/runtime/plate_config.py:45-65` |
| No-go bölgesi | Recoater kolonu `[[152.5, 0.2], [185.5, 45.0]]`, tam yükseklik. Heightmap yolunda `NO_GO_SEAL` mühürü, NFV/GPU yolunda dolu-mühür; metrikler bu kolonları yok sayar. | `plate.local.json:5-14`, `plate_config.py:68-102`, `bin3d.py:43,471-493` |
| Rotasyon | **28 pozluk master set**: 8 eksen-hizalı + 4 eğik (dikten 20/25/30/35°) + 16 kalan (küpün 24 simetrisi). NFV kalite modu default **AX24** (24 eksen-hizalı; eğik pozlar greedy'de miyop bulunduğu için çıkarıldı). Hedefli tilt ayrıca §2.3'te. İnce-açı refinement ±pencere°, 1° adım. | `voxelize.py:65-133`, `nfv_solve.py:30-37`, `coarse_to_fine.py:207-236` |
| İç-içe yerleştirme | Heightmap (baseline) cavity'ye parça KOYAMAZ (kabul edilen sınır). NFV (FFT no-fit-voxel) ve Extreme-Point occupancy cavity pozisyonlarını bulur — iç-içe yerleşim hoca tarafından izinli, asıl kısıt ayrılabilirlik. | `bin3d.py:6-8`, `nfv_solve.py`, `extreme_point.py:259-290` |
| Ayrılabilirlik | Bağımsız post-check: `check_separability_5dir` (5-yön sıralı söküm, union-find kilit grupları) + rot-söküm (`kilit_rot_meshes`) + onarım (`separability_repair.py`). NFV içinde yerleşim anında `exit_guard` seçeneği. | `accessibility.py:359-418`, `continuous_settle.py:329-359`, `parallel_decode.py:54-134` |
| Sipariş-notu kısıtları | Müşteri notundan türetilen parça-bazlı kısıtlar: `orientation_lock` (poz kilidi), `pinned_orientation`, `pinned_position` (konum sabitleme). Yön→poz tablosu 28-poz setten geometrik türetilir. | `src/runtime/constraint_compiler.py:38-63,132-135` |

### 1.4 Girdi ve çıktı

**Girdi:**
- **STL dosyaları** (trimesh ile yüklenir: `format.py:411`, `models.py:98`) + adet
  listesi. Ortak iç format: `NestingInstance` JSON v1.0 (`instances/format.py:6-36`)
  — `container` + `parts[]`; parça kaynağı `box` (w/d/h) veya `stl` (yol). Parça
  künyesi: `wall_mm`, `family`, `true_fill`, `order_id`, `geo_imza` (içerik hash'i —
  kimlik dosya adına güvenmez), `kaynak_ad`.
- **Voxelizasyon çözünürlüğü (pitch) adaptif:** heightmap yolunda
  `suggest_pitch() = min_feature/2.5` ([0.5, 15] mm kelepçeli); NFV kalite modunda
  pitch = clearance = 2.0 mm (tek-voxel tam pencere, K-38 kararı)
  (`instances/pitch.py:256-297`, `demo_pipeline.py:901`).

**Çıktı:**
- Yerleşim listesi `Placement3D(part_id, name, x, y, z, orientation_idx)`
  (`bin3d.py:26-35`) + `CoarseToFineResult` sarmalayıcısı (yükseklik, doluluk,
  pitch'ler) (`coarse_to_fine.py:376-431`).
- **Birleşik STL** (trimesh concatenate; webapp'ten indirilebilir) ve **GLB**
  (three.js 3D önizleme; instancing ile 588-kopyalı sahne ~30× küçülür)
  (`export_stl.py:87-302`).
- **Multi-solid ASCII STL** (her parça kendi adıyla ayrı solid bloğu — hoca talebi)
  üretim-paketleme katmanında: `scripts/_hoca_paket.py:59-71`.
- **Söküm planı ve söküm sırası** (§3.4) + parça→sipariş kimlik defteri
  (`parca_kimlik`) + telemetri JSON.
- Tek merkezî "placement JSON şeması" dokümanı yoktur; asıl çıktı sözlüğü
  `demo_pipeline.py:1421-1481`'de kurulur. **[DOĞRULA]** — danışman resmi bir şema
  isterse buradan türetilmesi gerekir.

---

## 2. ALGORİTMA VE ML STRATEJİLERİ

### 2.1 İki çözüm hattı + otomatik mod seçimi

Üretim üç mod tanır: `auto` (default) / `heightmap` / `nfv`
(`demo_pipeline.py:733,824`).

**A) Baseline (üretim default) — heightmap coarse-to-fine:**
- Constructive taban: **DBLF** (Deepest-Bottom-Left-Fill) — hacim-azalan sıra,
  vektörize `drop_map` (kayan-maksimum) ile heightmap düşürme (`dblf.py:166-178`,
  `bin3d.py:110-142`).
- Parça sayısı > 40 (`C2F_THRESHOLD`, `demo_pipeline.py:58`) veya sipariş-kısıtı
  varsa **coarse-to-fine**: (1) kaba pitch'te voxelize + tuner tüm portföyü koşar,
  kazanan sıra+oryantasyon çıkarılır; (2) ince pitch'te tek geçiş yeniden yerleşim
  (`coarse_to_fine.py:501-915`). 40 altında düz tuner (bütçe 70 iterasyon).
- **Metaheuristik portföy:** SA (multi-start 3/5), GA, Tabu, ALNS (menü dışı) —
  `tuner.build_menu()` + monoton kabul garantisi (çıktı asla baseline DBLF'den
  kötü olamaz) (`tuner.py:12-16,82-247`, `solvers/`). SA'nın karar değişkeni
  parça sırası; tie-break RMS-yükseklik.

**B) Kalite modu (opt-in) — NFV (No-Fit Voxel, FFT-cavity):**
- Fizibilite FFT konvolüsyonuyla hesaplanır
  (`feasible = irfftn(rfftn(occ)·rfftn(grid_flip)) < 0.5`), en düşük z'de
  bottom-left-back seçilir; çıktı Bin3D'ye REPLAY edilir (drop yok → cavity
  pozisyonları korunur) (`parallel_decode.py:146-276,456-499`, `nfv_solve.py:1-11`).
- Üretim reçetesi `solve_nfv_kalite` (K-45): pitch=clearance → önce HAM koşu →
  5-yön kilit>0 ise rot-kabul dene → olmazsa `exit_guard` ile yeniden koş; kilitsiz/
  alçak olan kazanır (`nfv_solve.py:342-571`).
- Post-pass'ler: fine-settle (kuantizasyon vergisini geri alır) + **R11 sürekli
  z-kompaksiyon** (mesh düzeyinde, voxel kafesini bırakır; dört kapılı tek-taraflı —
  kazanç yoksa sonuç aynen korunur; `r11="auto"` yalnız ≤600 parçada,
  `R11_AUTO_PARCA_TAVANI`) (`continuous_settle.py:362-455`, `nfv_solve.py:325-339`).
- **GPU:** cupy varsa FFT + occupancy cihazda resident; dispatcher gpu-resident →
  CPU-thread → seri graceful fallback, hepsi birebir aynı sonuç
  (`parallel_decode.py:353-499`, `capabilities.py`). Donanım: RTX 3060 6GB + 16GB
  RAM (geliştirme makinesi).
- Bedel: NFV default'tan ~10-40× yavaş; kazanç cavity-zengin ailelerde
  (YONTEM_HARITASI §2B).

**auto modu:** `predict_nfv_benefit` (kural-tabanlı cavity-kazanç tahmini,
`adaptive_params.py`) + opsiyonel ML mod-modeli (§2.2) karar verir; şüphe/hata
durumunda güvenli düşüş heightmap'tir (`demo_pipeline.py:825-870`).

### 2.2 ML tam olarak hangi kararı veriyor?

Kritik mimari gerçek (`STRATEJI/03_SECIM_MODELI.md`): **nesting motorunun kendisi
deterministiktir, öğrenen parametre taşımaz.** ML iki ayrı, sınırlı-yetkili
seçicidir:

**(A) Solver-seçici (`AlgorithmSelector`)** — hangi metaheuristiğin kazanacağını
tahmin eder (`{dblf, sa3d, ga}`):
- **1-NN prototip sınıflandırıcı**, normalize Öklid, güven = 1/(1+d); **sklearn
  yasak, yalnız stdlib** (kara-kutu yasağı) (`selection/model.py:23,35-148`).
  Aynı dosyada alternatif olarak CART-benzeri karar ağacı, KNN ve elle-GD lojistik
  de implemente edilmiştir.
- Önünde `EasyInstancePrefilter`: "kolay" instance (kural: `max_volume_norm >
  0.259`) doğrudan DBLF'e gider; güven < 0.6 ise tüm portföy koşulur
  (`build_selection_model.py:68-89`).
- Artefakt: `data/selection_model.json` (n_train=55, **tamamı sentetik** eğitim).
- Dürüst not (projenin kendi dokümanından): bu model "en küçük etkili kararı"
  öğrenir; üretim kalitesini asıl belirleyen kararlar kural-tabanlıdır
  (`03_SECIM_MODELI.md:30-40`).

**(B) Mod-seçici (`mode_model.json`)** — `nesting_mode` routing kararı
(`{heightmap, nfv_guard@2, nfv_ham@2, nfv_kalite}`):
- **RegretWeightedLogistic + LOO-conformal kalibrasyon**; çıkarım saf stdlib
  softmax (`selection/mode_model_io.py`, `regret_logistic.py`, `conformal.py`).
- **Çift kilit sözleşmesi:** model yalnız (a) instance ailesi allowlist'te
  (şu an sadece `["long_rod", "solid_bulk"]`) VE (b) conformal prediction-set
  TEKİL ise konuşur; aksi halde `None` döner, kural devam eder
  (`mode_model_io.py:97-107`, `data/mode_model.json:230-233`).
- Artefakt: `data/mode_model.json` (schema=2, n_train=49, sürüm
  `yarisma2-2026-07-14`, insan onayı kayıtlı).

**Feature'lar:** 20 **donmuş (FROZEN)** geometrik özellik + 3 aile-farkında ek = 23
(`instances/features.py:66-97,345-352`): parça sayısı/adet oranları, konteyner-
normalize hacim dağılımı, aspect oranları, tip oranları (thin_plate/long_rod/
cube_like), fill alt sınırı, `wall_est`, `true_fill_mean`, `shell_score`.
Deterministik — yalnız geometriden türer.

**Training süreci:**
- Aile-dengeli **stratified hold-out split** (isim-bağımsız; eski "alfabetik son
  %20" hatası düzeltildi) (`selection/splits.py:51-106`).
- **LOO-CV overfit kapısı:** `cv_gap > 0.2` → overfit bayrağı (1-NN'in yapısal
  train_acc=1.0 yanlış-pozitifine karşı) (`selection/gengap.py:34-55,156-181`).
- Başarı metriği **regret (mm)**, accuracy değil (mod-modeli eğitim kanıtı:
  regret 9.66mm vs kural 17.0mm).
- **Retrain asla otomatik değil** (anayasa A6): yalnız açık komut
  `python -m scripts.retrain_selection`; aday model promote kapısından
  (hold-out'ta ≥0.1mm kazanç + temiz overfit bayrağı) geçmeden yürürlüğe giremez;
  atomik swap + arşiv (`selection/retrain.py:104-157`, `gate.py:218-254`).
- Telemetri: `data/telemetry/runs.jsonl` (460 satır v1) + `runs_v2.jsonl`
  (139 satır) + `gate_log.jsonl` (~2800 satır, append-only kapı kararları).

### 2.3 Hedefli tilt ve pinleme (K-56 zinciri)

- **Hedefli tilt:** yükseklik-sürücü parçaya x/y ekseninde 5°-85° (5'er adım) eğik
  pozlar üretilir; üç geometrik filtre (grid'e sığma, no-go'lu plakaya
  yerleşebilirlik, z-uzantısı < düz pozların min z'si)
  (`targeted_tilt.py:48-121`). Tetik geometriktir, set adına bağlı değildir
  (anayasa A11). Üretime bağlama: `demo_pipeline.py:1050-1077`.
- **`pinned_placements`:** parçayı verilen (x, y, z, rot) konumuna deterministik
  sabitler (coarse'ta danışma, fine'da otorite)
  (`coarse_to_fine.py:438-498,523`). Sipariş-notu kısıtı ("konumu değişmeyecek")
  bu mekanizmaya derlenir. Kısıtlı partide NFV otomatik c2f'e çevrilir (NFV pin
  desteklemez, `demo_pipeline.py:864-870`).

### 2.4 Veri aileleri

**Geometrik taksonomi (F1, birincil):** `thin_shell · tube · thin_plate · long_rod ·
solid_bulk · mixed_scale · unknown` (`instances/family.py`; anayasa B3). Üretim
routing (wall_aware/F5) bunu kullanır.

**Sentetik jeneratörler** (`instances/synthetic.py`, seçim modeli eğitiminin tek
kaynağı): `random_boxes`, `few_large_many_small`, `high_qty_repeat`, `thin_plates`,
`long_rods`, `shell_bells`, `hollow_tubes`, `repeat_rod_mix` (deneme5-sınıfı),
`perturb_instance` (domain randomization: qty ±%30, ölçek ±%10).

**Bilinen kapsam boşluğu (projenin kendi tespiti):** `shell_bells`/`hollow_tubes`
box-source temsil edildiğinden yalnız taksonomi/özellik testlerinde geçerlidir —
gerçek nesting benchmark'ına giremez (içi-boş geometri kaybolur,
`synthetic.py:99-104`). Yani **gerçek thin_shell/tube jeneratörü henüz YOK**
(deneme4'ün ailesi!); kabuk jeneratörü sentetik genişletme listesinin ilk sırası
(`STRATEJI/01_VERI.md:135-138`).

**Gerçek veri setleri** (tek doğruluk kaynağı `data/registry.json`):

| Set | STL tipi / toplam parça | F1 aile | Rol |
|---|---|---|---|
| plan1 | 12 / 112 | mixed | **dev** |
| plan2 | 16 / 226 | mixed (cavity-zengin, en zorlu testbed) | **dev** |
| plan3 | 15 / 109 | mixed (çubuk-ağır) | **dev** |
| deneme4 | 13 / 588 | thin_shell (çan kabukları) | **dev** |
| deneme5 | 12 / 352 | tube (ince çubuk + kutu) | **dev** (tuning'de kullanıldı → held-out ilan edilemez, A3) |
| numune | tek parça çeşidi | mixed | **held-out** (eval_gate v1'de config'i yok — koşulamaz, bilinçli) |
| boxy | sentetik kutu stres seti | solid_bulk | **held-out** (cavity'siz kontrol) |
| deneme6 | 15 / 15 (×1) | mixed | **held-out (doğuştan)** |
| plan7 | 10 / 345 | mixed (ince-plaka ağırlıklı) | **held-out (doğuştan)** |

### 2.5 Train/test ayrımı ve held-out disiplini

"5 train / 2 test" ifadesinin kod karşılığı: **5 gerçek dev seti** (plan1/2/3,
deneme4, deneme5 — tuning serbest) + sentetik jeneratörler; held-out tarafında
**4 set** (numune, boxy, deneme6, plan7) olup bunlardan **deneme6 ve plan7 ilk
kör-test sınavlarını 2026-07-21'de gördü**. Kurallar (anayasa A3 + B1):

- Held-out setler `--heldout-final` bayrağı olmadan koşulamaz; her bakış
  `registry.json`'a otomatik loglanır, loglanamıyorsa koşu da olmaz
  (`eval_gate.py:94-106,634-638`).
- Yeni gelen her gerçek sipariş **doğuştan held-out**'tur; aynı aileden ≥2
  birikince en eskisi açık kararla dev'e terfi edebilir.
- Kör-test sonucu görüldükten sonra o set için mekanizma geliştirmek = held-out'u
  dev'e çevirmek; yapılmaz (`01_VERI.md §2.2`).
- Tek-set geliştirme yasağı (A11): mekanizma tetiği geometrik yazılır (kodda set
  adı yasak), tek-set kazancı "şerhli" sayılır, ilan için 4-set kapı PASS +
  tetiksiz setlerde bit-özdeşlik (sıfır-dokunuş) kanıtı gerekir.

### 2.6 Sonuçlar (kanıt dosyalarıyla)

**Eval kapısı (`scripts/eval_gate.py`) B2 eşikleri:** herhangi bir dev-sette >%2
kötüleşme veya INVALID → FAIL; ±%0.5 gürültü bandı (voxel kuantizasyonu); hiçbiri
kötüleşmeden ≥1 set >%0.5 iyileşme → PASS; arası → insan kararı.

**Güncel dev-set baseline** (`results/eval_gate_baseline.json`, 2026-07-20,
seed=42, clearance 2mm, 335×335 + no-go):

| Set | Legal yükseklik | Kilit → rot-söküm | Süre |
|---|---|---|---|
| plan1 | **202.18 mm** | 0 | ~10 dk |
| plan2 | **529.04 mm** | 35 → 0 (söküm-planlı, 4 sertifika) | ~25 dk |
| plan3 | **601.92 mm** | 3 → 0 | ~27 dk |
| deneme4 | **220.69 mm** | 12 → 0 (söküm-planlı, 5 sertifika) | ~59 dk |

**Şampiyon kolu (R11-v4 reçetesi — üretim default'u DEĞİL, ama ölçülmüş legal
sonuçlar):** Yukarıdaki tablo üretim yolunun baseline'ıdır; agresif R11-v4
kompaksiyon reçetesiyle (pay 0.15 + doğrula-ve-rafine, K-49d) ölçülmüş daha iyi
legal sonuçlar var: **plan3 577.62** (clear 2.033, kilit 0→0, 109/109; STL
`D:\ie488\results\plan3_r11d_577.6mm.stl`; hocaya 2026-07-12 mailinde raporlandı)
ve **deneme5 214.64** (clear 2.000, kilit 0→0, 352/352; STL
`deneme5_r11v4_214.6mm.stl`) — kaynak `MOTOR/YONTEM_HARITASI_DATA_BASE.md`
§3 K-49d + `HOCA_MAIL_2026-07-12.md`. K-58 bu üretim→şampiyon makasını d4 ve
p2'de kapattı (220.69 / 529.04 rekor); **plan3'te makas hâlâ açık** (üretim
601.92 vs şampiyon 577.62). plan1'de ayrıca tilt+soft-no-go+pinleme zinciriyle
302.8 → **140.21 mm** legal ölçüldü (K-56f, `results/k56f_pinleme.json`) —
üretim kablosu (K-56g) bağlanmadığı için şerhli.

**Referansa karşı karne (7 gerçek set — dürüst tablo):** Referans yükseklikler
**Magics çıktısı değil, deneyimli operatörün MANUEL yerleşimidir** (saatler
süren elle çalışma; `HOCA_CEVAPLARI.md:128-131`). Karşılaştırma:

| Set | Bizim en iyi LEGAL | Referans (manuel) | Fark | Durum |
|---|---|---|---|---|
| plan1 | 202.18 (üretim) · 140.21 (K-56 zinciri, şerhli) | 110.41 | +%83 · +%27 | **GERİDE** |
| plan2 | 529.04 (üretim rekoru) | 492.39 | +%7.4 | **GERİDE** |
| plan3 | **577.62** (şampiyon R11-v4) · 601.92 (üretim) | 593 | **−%2.6** · +%1.5 | **ÖNDE** (şampiyon kolu) |
| deneme4 | 220.69 (üretim = şampiyon parite) | 250.24 | **−%11.8** | **ÖNDE** |
| deneme5 | 214.64 (şampiyon R11-v4) | 209 | +%2.7 | **GERİDE** (yakın) |
| deneme6 (kör test) | 68.50 | 86.32 | **−%20.6** | **ÖNDE** |
| plan7 (kör test) | 488.40 | 595 | **−%17.9** | **ÖNDE** |

Skor: **4 önde / 3 geride** (en iyi legal ölçümler esas alındığında). Dağılım
anlamlıdır: en büyük kazançlar **hiç görülmemiş kör held-out'larda** (−%17.9,
−%20.6) — genelleme kanıtı olarak tuning kazancından değerlidir. Dev tarafında
deneme4 ve plan3 (şampiyon kolu) önde; plan2 ve deneme5 yakın-geride; **plan1
açık ara geride** ve bilinen ana sorundur (K-56 zinciri 140.21'e indirdi ama
üretim kablosu + kural netlikleri bekliyor). Not: plan3/deneme5 şampiyon
değerleri üretim default'unun değil R11-v4 kolunun çıktısıdır — dışarıya sayı
verirken hangi kolun konuşulduğu belirtilmelidir. "Tüm setlerde daha iyi"
iddiası bu kayıtlarla savunulamaz.

**Kıyas-adaleti şerhi (A10 — bizim lehimize işleyen asimetri):** Bizim tüm
sonuçlar 2mm clearance + sert no-go + tam-ayrılabilirlik şartıyla ölçülmüştür.
Manuel referansların boşluk değeri **bilinmiyor** (hocaya soruldu, cevap
bekleniyor — `HOCA_MAIL_2026-07-21_TASLAK.md` soru 1) ve hoca Plan1 manuelinin
no-go'ya "hafif girişlerle" hazırlandığını doğruladı ("110.41'in sırrı bu",
`HOCA_CEVAPLARI.md:119-121`). Yani plan1'deki büyük fark kısmen kural
asimetrisinden kaynaklanıyor olabilir; cevap gelmeden set-bazlı yüzdeler dışarıya
kesin sayı olarak verilmemelidir. Hız farkı ise şerhsizdir: manuel yerleşim
saatler, bizim çözüm dakikalar mertebesindedir.

**NFV'nin heightmap'e karşı kazancı** (aynı motor içi, 3 gerçek set,
YONTEM_HARITASI §2B): plan2 **%29** · plan1 **%14** · plan3 **%20**; saf-kutu
sette (boxy) **%0** — cavity yoksa avantaj yok (yapının doğası, overfit değil).
**Şerh:** bu yüzdeler ham-yükseklik kıyasıdır; projenin kendi EVAL-1 kaydı
(YONTEM_HARITASI §3) erken NFV kazançlarının dürüst legal-metrik (clearance +
0 kilit) altında INVALID'e düştüğünü not eder — legal referans, yukarıdaki
2026-07-20 baseline tablosudur. Benzer şekilde deneme4 kabuk sıçraması
377.3 → 282.0 (−%25.3, K-19) margin=0 koşusudur; dürüst (clearance'lı) karşılığı
~329 mm olarak kayıtlıdır. **[DOĞRULA]** Geçmiş yazışmalarda geçen "plan1 ~%20 /
plan2 %17.5 / plan3 ~%28 iyileşme" üçlüsü repo içinde birebir kaynakla
bulunamadı; muhtemelen farklı bir baseline'a (ör. erken Magics kıyası) ait —
danışman bu tabloda YONTEM_HARITASI değerlerini esas almalı.

**Kör-test detayları** (ilk-koşu, out-of-the-box, `01_VERI.md §2.2`,
kanıt `results/deneme6_heldout_final.json` + `plan7_heldout_final.json`):
deneme6 68.50 mm **29 saniyede** (clearance 3.25, kilit 0); plan7 488.40 mm
103 dakikada (kilit 15 → rot-söküm 0). Şerhler: plan7 koşusunda maildeki pin
kısıtı ("konumu değişmeyecek") uygulanmadı (K-56g kablosu bekliyor);
referansların hazırlanış koşulları bilinmiyor (A10). Kör-test kuralı: ilk-koşu
açığı tarihsel karneye yazılır, sonradan kapatılan açık o tabloyu değiştirmez.

**Runtime dağılımı:** default heightmap dakikalar mertebesi (coarse-to-fine ile
104.5 dk → 9.2 dk → ~3.4 dk kabuk yolu, H-15p/H-16); NFV kalite modu set başına
~10-60 dk (yukarıdaki tablo); R11 hızlandırması (K-55/K-60) 588 parçada settle
süresini 43.5 dk → 5.1 dk'ya indirdi (commit `fd2cb23`).

---

## 3. PIPELINE MİMARİSİ

### 3.1 Mail gözcüsü

**Protokol:** IMAP (`imaplib`), Gmail API değil. SSL varsayılan port 993; SSL
kapalıysa login öncesi STARTTLS zorunlu, desteklenmiyorsa **fail-closed**
(`src/runtime/mail_ingest.py:33,310-390`). Sağlayıcı preset'leri: gmail/outlook/
hotmail (`mail_ingest.py:1319-1335`).

**Polling:** `MailPoller` daemon thread'i, varsayılan aralık **120 sn** (env
`MAIL_POLL_INTERVAL`; UI'dan min 30 sn); ilk tarama beklemeden hemen yapılır.
Otomatik başlatma yalnız env `MAIL_POLL_ENABLED` ile — aksi halde operatör
`/poll/baslat` der (`mail_poller.py:333,359-531`, `webapp/app.py:1229-1262`).
Demo modunda gömülü `FakeMailbox` (5 gerçekçi TR siparişi) kullanılır.

**Sipariş tespiti:** konu filtresi yok; "sipariş sinyali" tabanlı — gövdede adet
deseni veya `N×N×N` 3B boyut deseni (`_has_order_signal`,
`mail_ingest.py:679-693`). Yönlendirme öncelik sırası (`ingest_order`,
`mail_ingest.py:1125-1312`):

1. `.zip` eki → STL siparişi olarak işle.
2. `.xlsx/.xls/.xlsm/.csv` eki → deterministik ek-parser (LLM yok).
3. Dosya-paylaşım linki (Drive/WeTransfer/OneDrive/Dropbox allowlist) → operatör
   beklemesine düşür.
4. Ek yok + sinyal var → LLM parser (serbest metin). Injection şüphesinde
   **fail-closed karantina** — pipeline'a girmez.

Ekli mailler LLM kuyruğundan önce işlenir (`_attachment_first`).

**Adet extraction — katmanlı, önce-deterministik** (`mail_ingest.py:871-1122`):
- Katman 1+2 (birincil, regex): gövde + `.txt` eki → `parse_quantities`; STL
  adlarına toleranslı eşleme (case/TR-karakter/`-25pcs` soneki).
- Katman 3 (son çare, LLM, **topraklanmış**): yalnız deterministik katman tam
  kapsamazsa; LLM çıktısı ZIP'in gerçek dosya adlarına eşlenir, hayali adlar
  düşer; kabul için tam kapsama + `declared_total` sağlaması şart.
- Çapraz doğrulama: gövdedeki "toplam N parça" beyanı eşlenen toplamla tutmazsa
  sipariş `needs_review="quantity_conflict"` ile operatöre düşer. STL dosya
  adı/başlığındaki `-NAdet` adetleri mail gövdesi her zaman ezer; çelişki sessiz
  kabul edilmez.

**ZIP/STL işleme** (`zip_stl_extractor.py`): bellek-içi açma (diske yazmadan),
yalnız `.stl` uzantısı, zip-slip'e karşı sadece basename; zip-bomb koruması
(boyut ön-eleme + 1 MB chunk okuma + toplam 200 MB tavan); mail eki tavanı 50 MB.
STL'ler mesaj-bazlı kalıcı klasöre yazılır: `data/mail_stl/mail_stl_<sha8>/`.

**Idempotency:** SHA-256 anahtar `("imap", user, uid)` → kalıcı
`SqliteIdempotencyStore`; `mark_processed` yalnız kesin sonuç sonrası
(at-least-once semantiği) (`mail_ingest.py:426-432,550-574`).

### 3.2 Sipariş yaşam döngüsü

Açık bir state-machine enum'u **canlı yolda yoktur**; akış üç sonuçludur:
(a) tam sipariş → pipeline koşusu; (b) `needs_review` (sebepler:
`missing_quantity`, `quantity_conflict`, `share_link_dosya_bekleniyor`,
`attachment_unparseable`, `llm_bos_siparis`) → `PendingOrderStore` (dosya-tabanlı:
`data/pending_orders/<order_id>/meta.json` + STL'ler); (c) spam → işaretle geç.
Operatör `/adet-gir` ekranından adetleri tamamlar — başarı ancak gerçek nesting
çıktısı üretilirse pending silinir (`app.py:3205-3334`).

**Not→kısıt hattı (K-56g/K-61):** sipariş notu satırları önce deterministik
Kapı-0'dan geçer (`note_detector.py` — kısıt sözlüğü eşleşmesi; injection kalıbı
en önce kesilir); sonra `kisit_modu`'na göre (`configs/llm.local.json`):
- `kapali` (**şu anki default**): LLM'e sıfır dokunuş, sipariş aynen geçer.
- `golge`: analiz koşar, sonuç yalnız `not_analizi` alanına yazılır — motora
  uygulanmaz (kıyas dönemi).
- `otomatik`: yüksek güvenli kısıtlar `motor_kisitlari`'na uygulanır.

LLM kısıt rolü (`src/llm/roles/kisit.py`): self-consistency oylama (N=3,
temp 0.7) + hakem eskalasyonu (qwen2.5:7b, temp 0.0); yalnız whitelist enum tip
üretir, sayısal koordinat asla (deterministik `constraint_compiler`'ın işi);
`injection_suphesi=true` → kısıtlar kullanılmaz. Operatör onay yüzeyi:
`/kisit-onay` (`kisit_onay.html`) — hiçbir kısıt onaysız uygulanmaz.

**LLM altyapısı:** lokal Ollama (`http://localhost:11434`), bulut API'si yok.
Roller: parser/report/teklif/kisit → qwen2.5:3b; assistant → llama3.2:3b;
kisit_hakem → qwen2.5:7b-instruct. Ollama kapalıysa deterministik yol devam eder,
uygulama çökmez. Prompt şablonları `prompts/<rol>/` (system.md + schema.json +
few-shot örnekler); `prompts/lock.json` şablon SHA-256 hash kilidi — prompt'un
sessizce değişmesini engeller, değişiklik versiyon artışı + eval ister.

### 3.3 Paralel çözüm mimarisi

- **Parti-paralel süreç havuzu:** her parti ayrı süreçte
  (`ProcessPoolExecutor`, `demo_pipeline.py:1621-1660`); işçi fonksiyonu
  modül-seviyesi picklable `_process_batch` (voxelize + çözüm + fiyatlama).
- **İşçi sayısı** (`_resolve_max_workers`, `:1571-1618`):
  `min(çekirdek − 2 rezerv, parti sayısı, hard_cap)`; **RAM kapısı**
  `(boş_RAM × 0.8) / işçi_başı_GB`; env override'ları `NESTING_MAX_WORKERS`,
  `NESTING_HARD_CAP`, `NESTING_PARALLEL=0` (tam kapatma). Çekirdek tespiti
  `os.process_cpu_count()` (affinity-saygılı, Py3.13).
- Paralel tetiği (auto): ≥2 parti VE toplam parça > 40. Seed sabit → paralel ve
  sıralı sonuç **birebir**. Havuz kurulamazsa sıralıya düşer + loglar.
- **Parti-içi paralellik ayrı:** NFV oryantasyonları `ThreadPoolExecutor`
  (scipy.fft GIL bırakır); GPU varsa cupy-resident decode (§2.1B).
- `scripts/detach_run.py` runtime'ın parçası değil — uzun koşuları ayrık süreç
  olarak başlatan geliştirici yardımcısıdır (koşular `D:\ie488` ağacından).

### 3.4 Söküm planı üretimi

Baskı sonrası parça çıkarma planı üretim hattındadır (`demo_pipeline.py:1321-1462`):
- **Parça-bazlı söküm planı** rot-kabul/r11-rot yolundan gelir (hangi parça hangi
  döndürme ile çıkar — "sertifikalar").
- **Genel söküm sırası:** 5-yön sıralı söküm simülasyonu (`check_separability_5dir`
  / mesh düzeyinde `rapor_5yon_meshes`) `removable_order` üretir — operatörün
  plakadan parça çıkarma sırası.
- Sonuca `sokum_plani`, `sokum_sirasi`, `parca_kimlik` (part_id → order_id),
  `siparis_ozeti` alanları eklenir; üretilemezse alan konmaz, çözüm etkilenmez.
- Operatör yüzü: rehberli söküm konsolu
  (`webapp/static/sokum_konsol.js`, `gecmis_detay.html`).

### 3.5 Veri kalıcılığı (DB şeması)

**Postgres yoktur** (bilinçli erteleme; arayüzler arka-uç değişimine izin verecek
şekilde yazılmış — `store.py:2-4`, `pending_orders.py:15-16`). Canlı yol dört
mekanizma kullanır:

**(a) SQLite — `idempotency_keys`** (tek canlı SQL tablosu,
`idempotency.py:113-118`; üretimde `data/idempotency.db`):

```sql
CREATE TABLE idempotency_keys (
    key           TEXT PRIMARY KEY,   -- SHA-256 hex
    registered_at TEXT NOT NULL       -- ISO UTC
);
```

**(b) JSONL — iş geçmişi** `data/otonom_gecmis/gecmis.jsonl`
(`otonom_gecmis.py:35-89`). Kayıt alanları: `id, zaman, durum(bitti/kismi/hata),
hata_ozeti, kaynak(manuel/otomatik), mod, secilen_mod, auto_mode_reason,
nfv_quality, musteri, siparis_sayisi, parti_sayisi, min_yukseklik_mm, doluluk,
plate_w_mm, plate_d_mm, plate_auto, hacim_doluluk_pct, hacim_eksik_parca,
budget_exceeded, toplam_fiyat, sure_sn, asamalar[], order_ids[]` + iç alanlar
(`_dedup_key, _idem_keys, kosu_id`). Tam nesting detayı yanında:
`detay/<id>.json` + 3D önizleme `glb/<id>_<batch>.glb`.

**(c) Dosya — bekleyen siparişler** `data/pending_orders/<order_id>/`
(meta.json alanları: `order_id, customer, sender, deadline, priority_class, konu,
stl_names, container, review_reason, share_links, adet_listesi` + kısıt hattı
alanları `not_adaylari, kisit_onerileri, motor_kisitlari, onaylanan_kisitlar`).

**(d) JSON — manuel sipariş havuzu** `data/orders.json` (sipariş: `order_id,
customer, deadline, priority_class, parts[]`; parça: `name, width_mm, depth_mm,
height_mm, qty`; atomik tmp+rename yazım).

**Parça↔sipariş eşleştirmesi** tek tabloda değil, üç seviyede tutulur:
(1) instance içinde her parça `order_id` taşır → sonuçtaki `parca_kimlik` defteri
`part_id → {parca_uid, order_id, geo_imza, kaynak_ad, ad, kopya_no}`
(`demo_pipeline.py:1347-1357`); (2) `siparis_ozeti` (order_id → parça sayıları);
(3) geçmiş kaydında `order_ids[]` + siparişe-özel idempotency anahtarları
(silmede geri açılır → yeniden işlenebilirlik).

**Önemli mimari bulgu:** Tam bir state-machine'li SQL iş katmanı
(`jobs` tablosu: 12 alan, RECEIVED→…→DONE/DEAD_LETTER durumları,
`src/runtime/jobs.py:31-63` + `store.py:132-151` + `queue.py` +
`pipeline_job.py`) **yazılmış ve test edilmiş ama webapp'e BAĞLI DEĞİLDİR**
(app.py bu modülleri import etmiyor). Canlı asenkron işler bellek-içi
`OtonomJobStore` ile yürür (son 20 iş RAM'de, restart'ta kaybolur —
`otonom_jobs.py:36-151`). Ölçekleme/Postgres göçü değerlendirilirken bu ikilik
bilinmelidir.

### 3.6 Web uygulaması

Flask (application factory), `127.0.0.1:8765`, 38 route (`webapp/app.py`).
Ana ekranlar: `/` ana sayfa, `/run` demo koşusu, `/otonom` (+ asenkron
`/otonom/baslat` + `/otonom/durum/<job_id>`), `/gecmis` (+detay, GLB önizleme,
STL indirme), `/adet-gir`, `/kisit-onay`, `/siparisler` (CRUD + CSV),
`/mail-ayar`, `/plaka-ayar`, `/oncelik`, `/poll/*`, `/health`, `/sor` (LLM
asistan). Dağıtım topolojisi: fabrika-içi tek sunucu + çok tarayıcı-istemci.

---

## 4. GÜVENLİK VE HATA YÖNETİMİ

### 4.1 Credential saklama

- **Mail parolası:** `configs/mail.local.json` (operatör `/mail-ayar` ekranından
  girer; dosya `os.open(..., 0o600)` owner-only + dizin 0o700 ile yazılır,
  `app.py:3071-3086`) veya env (`MAIL_USER`/`MAIL_PASSWORD`). Kodda gömülü
  hesap/parola yok; boş parola reddedilir. Parola IMAP'e yalnız SSL (993) veya
  login-öncesi STARTTLS üstünden gider; TLS kurulamazsa **fail-closed**.
  **[DOĞRULA]** 0o600/0o700 POSIX izinleridir; sistem Windows'ta koşuyor ve bu
  bitler NTFS ACL'e birebir çevrilmez — dosya-sahibi kısıtı Windows'ta pratikte
  zayıf olabilir.
- **LLM:** lokal Ollama (`localhost:11434`, auth'suz) — bulut API anahtarı
  gerektirmez; `configs/llm.local.json` yalnız endpoint + model adları taşır
  (içinde key yok — dosya tam okundu). Opsiyonel bulut sağlayıcıları
  (openai_compat/anthropic) API key'i dosyadan değil **env'den** okur
  (`src/llm/providers/openai_compat.py:119`, `anthropic_provider.py:55`).
- **Webapp admin:** `ADMIN_PASSWORD` env'den (`app.py:587`); parola karşılaştırma
  timing-safe (`hmac.compare_digest`, bytes — unicode parola destekli).
- **.gitignore disiplini:** `configs/*.local.json`, `.env`, `data/mail_stl/`,
  `data/idempotency.db`, `data/otonom_gecmis/`, `data/pending_orders/`, `logs/`
  git-dışı (`.gitignore:15-29`). `.env`'in git geçmişine hiç girmediği iddiası
  denetim raporundan (`DENETIM_RAPORU_2026-07-01.md`); bu taramada bağımsız teyit
  edilmedi **[DOĞRULA]**.

### 4.2 Hata yönetimi (çekirdek mekanizmalar)

| Senaryo | Davranış | Kaynak |
|---|---|---|
| Aynı mail iki kez | SHA-256 `(imap, user, uid)` anahtarı kalıcı SQLite'ta; işlenmiş mail atlanır. `mark_processed` yalnız kesin sonuçtan sonra (at-least-once). | `mail_ingest.py:426-432,550-574` |
| Bozuk ZIP | Boş sonuç + log; pipeline'a girmez. | `zip_stl_extractor.py:146` |
| Zip-bomb | `ZipInfo.file_size` ön-eleme + 1 MB chunk okuma + 200 MB toplam tavan → `ValueError`. Mail eki tavanı 50 MB. | `zip_stl_extractor.py:34-45,116-146`, `mail_ingest.py:620` |
| Zip path traversal | Yalnız basename kullanılır (zip-slip önlemi); yalnız `.stl` uzantısı. | `zip_stl_extractor.py:42-90` |
| Bozuk STL | `trimesh.load` try/except → parça `None` + warning; sipariş `skipped_no_stl` listesiyle devam eder, akış çökmez. | `stl_order_loader.py:94-106,256-260` |
| Adet çelişkisi / eksiği | Sipariş `needs_review` ile operatör kuyruğuna düşer; sessiz tahmin yok. Aşırı adet `MAX_QTY=5000` ile kelepçelenir (OOM önlemi). | `mail_ingest.py:993-1011`, `parser.py:94,168-175` |
| Kalıcı-bozuk ek | Sonsuz retry yok: `attachment_unparseable` → needs_review + işaretle geç. Restart yarışına karşı `_inflight_lock` (aynı anda tek tarama). | `mail_ingest.py:1186`, `mail_poller.py:405-430` |
| Prompt injection (kısıt hattı) | Kapı-0 deterministik kalıp kesimi + LLM `injection_suphesi` → fail-closed; kısıtlar kullanılmaz. | `note_detector.py:76-80`, `kisit.py:210-217` |
| Prompt injection (sipariş parse hattı) | **Yalnız LLM beyanına dayalı** (`injection_suphesi` → karantina); deterministik regex ön-taraması YOK — açık bulgu H7 (§5). | `mail_ingest.py:1258-1268`, `parser.py:268` |
| LLM/Ollama çökük | `kisit_role=None` → deterministik yol; sipariş hattı etkilenmez. | `note_pipeline.py:72-87` |
| Paralel havuz kurulamadı | Sıralı işleme düşer + loglar (sessiz değil). | `demo_pipeline.py:1654-1660` |
| CSRF | Oturum token'ı + `hmac.compare_digest`, tüm mutasyon metotlarında (health/static hariç); başarısız → 403. | `app.py:591-617` |
| Brute-force / kaynak tüketimi | `/giris` 5/dk; ağır uçlar `/run` 3/dk, `/otonom` 2/dk; `MAX_CONTENT_LENGTH` 5 MB; session cookie HTTPONLY + SameSite=Lax; açık-yönlendirme koruması (`next` yalnız site-içi); Ollama SSRF allowlist (localhost-only). | `app.py:510-634,1335,2771` |

### 4.3 Denetim raporlarının güncel durumu

**`DENETIM_RAPORU_2026-07-01.md` (12 üretim blokeri):** kod düzeyinde bugün
doğrulanan durum — **kapalı:** C1 (adet-OOM), H1 (path traversal), H2 (zip-bomb),
H3 (brute-force), H4 (idempotency senkronu), H5 (bozuk-ek retry), H6 (restart
yarışı), H8 (jsonschema zorunlu), M2 (cookie bayrakları), M4 (`/run` rate-limit),
M5 (PollState lock). **Açık:** **H7** (deterministik injection ön-taraması yok —
tek savunma LLM beyanı), H9 (README bayat), H10 (canlı/GPU iddiaların runtime
probe ile yeniden doğrulanması), M3 (CSV import O(n²)), M6-M9, L1-L9 (düşük
öncelik; ör. L2 — ham exception string'inin istemciye dönmesi). **Kısmi:** M1 —
boş `ADMIN_PASSWORD` + ağ bind'i yalnız konsol uyarısı üretir, başlatmayı
engellemez (`app.py:3733-3746`); loopback default'ta güvenli, LAN bind'de risk.

**`DENETIM_RAPORU_2026-07-03.md` (29 bulgu, Deneme4 canlı hatalarından):** önemli
kısmı hâlâ AÇIK — özellikle **Dalga 2 (sipariş-kaybettiren format hataları):**
HTML-only mail gövdesi, ZIP içi cp437 Türkçe karakter bozulması, kardeş
.xlsx/.csv adet dosyasının okunmaması, birden çok ZIP ekinde yalnız ilkinin
işlenmesi, `;`-ayraçlı Türkçe CSV, RFC2047 kodlu ek adları; ve **Dalga 4 (motor
fiziği):** kapalı-kavite denetimi yok (#21, CRITICAL — içine toz hapsolan kapalı
boşluk tespiti), `quality=max` zaman bütçesi yok (#22), RAM guard hataları
(#23/#24).

**Rate-limiter sınırı:** `flask-limiter` `storage_uri="memory://"`
(`app.py:552`) — süreç yeniden başlayınca sayaçlar sıfırlanır; çok-process
deploy'da limitler paylaşılmaz.

---

## 5. BİLİNEN EKSİKLER VE TEKNİK BORÇ

**Borç izleme biçimi hakkında not:** proje Python kodunda hiç TODO/FIXME/HACK
işareti yok (tek eşleşme vendored üçüncü-parti `GLTFLoader.js`). Bu, borcun
olmadığı anlamına gelmez — borç bilinçli olarak **doküman tabanlı** izlenir
(YONTEM_HARITASI §5 açık yönler, DENETIM raporları, anayasa "şerh" mekanizması).
Yalnız kod tarayan bir denetim bu bağlamı ıskalar; bu doküman o köprüyü kurar.

**Mimari / kod:**
- `README.md` bayat (2D dönemini anlatıyor); güncel gerçeklik YONTEM_HARITASI +
  STRATEJI (denetim bulgusu H9, bilinçli açık).
- Clearance (2.0 mm) config'te değil **kod sabiti** (`demo_pipeline.py:73`).
- Tam state-machine'li SQL iş katmanı (`jobs.py`/`store.py`/`queue.py`/
  `pipeline_job.py`) yazılmış ama **webapp'e bağlanmamış** (atıl); canlı asenkron
  işler bellek-içi (restart'ta kaybolur).
- Adaptif oryantasyon parametresi yazıldı ama app'e bağlı değil
  (YONTEM_HARITASI §2A tablosu).
- Postgres yok (bilinçli erteleme); çok-kiracılık alanı (`tenant_id`) yalnız atıl
  katmanda.
- Rate-limiter bellek-içi (`memory://`) — restart'ta sıfırlanır, çok-process'te
  paylaşılmaz.

**Açık güvenlik/sağlamlık bulguları (denetim raporlarından, §4.3 detaylı):**
- **H7:** sipariş-parse hattında deterministik injection ön-taraması yok (tek
  savunma LLM beyanı). Kısıt hattında Kapı-0 deterministik kesim VAR; asimetri
  bilinçli kapatılmalı.
- **M1 kısmi:** boş `ADMIN_PASSWORD` + LAN bind yalnız uyarı üretir, başlatmayı
  engellemez.
- **DENETIM 07-03 Dalga 2:** sipariş-kaybettiren mail-format hataları (HTML-only
  gövde, cp437 mojibake, çoklu-ZIP, `;`-CSV, RFC2047) çoğunlukla açık.
- **DENETIM 07-03 #21 (CRITICAL, motor fiziği):** kapalı-kavite denetimi yok —
  iç-içe yerleşimde tamamen kapalı boşluğa toz hapsolması tespit edilmiyor.
  #22: `quality=max` için zaman bütçesi yok.
- M3 (CSV import O(n²)), M6-M9, L1-L9 düşük-öncelik açık.

**Test kapsamı:**
- 174 test dosyası / ~130 kaynak modülü; kritik runtime/güvenlik modülleri
  (mail_ingest, poller idempotency/race, zip extractor, note/constraint hattı,
  separability) dedike testli.
- Dedike test dosyası **görünmeyen** modüller: `targeted_tilt.py` (K-56 tilt
  yolu!), `webapp/intent_router.py`, `webapp/orders_store.py` (M3'ün yaşadığı
  yer). Dolaylı kapsam olabilir — "dedike dosya yok" ≠ "hiç test edilmiyor"
  **[DOĞRULA]**.

**Doğrulama bekleyen işler (A11 disiplini gereği "şerhli"):**
- **K-56g:** plan1 tilt+pinleme zincirinin (302.8→140.21) üretim kablosu
  bağlanmadı; 4-set kapı + baseline yenileme + commit onayı bekliyor.
- **K-58:** R11 auto-tavan 150→600 kod+test hazır; d4 (220.69) ve p2 (529.04)
  şampiyon-parite ölçüldü, **plan3'te üretim→şampiyon makası açık** (601.92 vs
  R11-v4 şampiyonu 577.62); tam 4-set kapı + commit onayı bekliyor.
- **kisit_modu = `kapali`:** not→kısıt hattı kodda + testli ama üretimde kapalı;
  gölge/otomatik geçişi onay bekliyor.
- **plan7 pin kısıtı** ("konumu değişmeyecek") ilk kör-testte uygulanmadı —
  K-56g kablosuna bağlı.
- **numune** held-out'u eval_gate v1'de koşulamıyor (config yok, bilinçli).
- Magics/manuel kıyası A10 şerhli: referans yerleşimlerin boşluk/no-go koşulları
  bilinmiyor. **Hocaya sorulmuş ama hâlâ cevapsız:** manuel yerleşimlerde
  parça-arası boşluk kaç mm (özellikle deneme5 209 koşulu) — kıyas adaleti için
  kritik (`HOCA_CEVAPLARI.md`). Soft no-go semantiği ("hafif girişler sorun
  değil") modellemesi de hoca netliği bekliyor (K-56 kalan iş).
- Anayasa B1-B5 kararları "öneri statüsünde karara bağlandı" — kesin-kilitli
  değil, kullanıcı kararıyla güncellenebilir.

**Veri boşlukları:**
- Gerçek thin_shell/tube sentetik jeneratörü yok (deneme4'ün ailesi);
  `shell_bells`/`hollow_tubes` yalnız taksonomi testinde geçerli.
- Seçim modeli eğitimi **tamamı sentetik** (69 instance); sentetik→gerçek
  genelleme garantisi yok (projenin kendi tespiti, `01_VERI.md`).
- `data/registry.json` plan7 için `Veriler/Plan7/` yolunu gösteriyor ama bu klasör
  OneDrive kopyasında yok; ZIP gerçekte `D:\ie488\data\plan7_gelen\Plan7.zip`
  konumunda **[DOĞRULA]** (koşu ağacı D:\ie488'de — büyük dosyalar bilinçli
  olarak C'ye yazılmıyor).

**Yapısal sınırlar (ölçülmüş, kanıtlı):**
- Kabuk ailesinde 264 mm = gerçek plakada yapısal tavan (K-24 kanıtlı); kalan
  kaldıraç sürekli rotasyon (A1) — mevcut 6 GB GPU'da fizibil değil, süper
  bilgisayar gerektirir.
- plan2 tilt karşılığı koşusuz NO-GO (fp_y 304 > 302); NFV plan1'de sert no-go
  (K-40).
- 16 GB RAM'de set-paralel eval orkestrasyonu hızlanmıyor (NFV çiftleri OOM →
  seri retry, K-57).

---

## 6. DOSYA YAPISI

```
IE 488 Project/
├── src/
│   ├── nesting3d/              # ÇEKİRDEK 3D NESTING MOTORU
│   │   ├── bin3d.py            # Voxel bin + heightmap drop_map + no-go mühürü
│   │   ├── dblf.py             # DBLF constructive yerleştirici
│   │   ├── coarse_to_fine.py   # İki aşamalı çözüm hattı + pinleme
│   │   ├── nfv_solve.py        # NFV kalite modu (solve_nfv_kalite, R11 tavanları)
│   │   ├── parallel_decode.py  # FFT-NFV decode + GPU/CPU dispatcher + exit_guard
│   │   ├── fft_backend.py      # scipy.fft / cupy soyutlama
│   │   ├── extreme_point.py    # 3D occupancy + cavity aday üretimi
│   │   ├── continuous_settle.py# R11 sürekli z-kompaksiyon + rot-söküm kabulü
│   │   ├── fine_settle.py      # Kuantizasyon geri-alma post-pass'i (K-17)
│   │   ├── accessibility.py    # 5-yön söküm / kilit tespiti (union-find)
│   │   ├── rotation_extract.py # Rot-söküm (döndürerek çıkarma) denetimi
│   │   ├── separability_repair.py # Kilit onarımı
│   │   ├── targeted_tilt.py    # Hedefli eğik poz havuzu (K-56)
│   │   ├── clearance.py        # Bağımsız clearance ölçümü (cKDTree)
│   │   ├── voxelize.py         # STL→voxel + 28-poz rotasyon matrisleri
│   │   ├── export_stl.py       # Birleşik STL + instanced GLB üretimi
│   │   ├── sa3d.py, tuner.py   # SA + portföy tuner (monoton kabul)
│   │   ├── adaptive_params.py  # predict_nfv_benefit (auto-mod kuralı)
│   │   ├── telemetry.py        # runs.jsonl v1/v2 telemetri
│   │   ├── solvers/            # dblf, sa, ga, tabu, alns + portföy
│   │   ├── selection/          # ML: model.py (1-NN+3 alternatif), mode_model_io,
│   │   │                       #   regret_logistic, conformal, splits, gengap,
│   │   │                       #   gate (promote kapısı), retrain (atomik swap)
│   │   └── instances/          # format.py (NestingInstance), synthetic.py
│   │                           #   (9 jeneratör), family.py (F1 taksonomi),
│   │                           #   features.py (20+3 FROZEN), pitch.py
│   ├── runtime/                # MAİL + SİPARİŞ OTOMASYONU
│   │   ├── mail_poller.py      # IMAP polling thread'i (120 sn)
│   │   ├── mail_ingest.py      # Sipariş tespiti + katmanlı adet extraction
│   │   ├── zip_stl_extractor.py# Güvenli ZIP açma (bomb/slip korumalı)
│   │   ├── pending_orders.py   # Bekleyen sipariş deposu (dosya-tabanlı)
│   │   ├── idempotency.py      # SQLite idempotency store
│   │   ├── otonom_gecmis.py    # JSONL iş geçmişi + detay/GLB persist
│   │   ├── otonom_jobs.py      # Bellek-içi asenkron iş takibi (CANLI yol)
│   │   ├── note_detector.py    # Kapı-0: deterministik not adayı tespiti
│   │   ├── note_pipeline.py    # kisit_modu orkestrasyonu (kapali/golge/otomatik)
│   │   ├── constraint_compiler.py # Sembolik kısıt → motor parametresi
│   │   ├── plate_config.py     # Plaka + no-go çözümleme
│   │   └── jobs.py, store.py, queue.py, pipeline_job.py  # ATIL SQL iş katmanı
│   ├── webapp/                 # Flask UI (38 route) + orders_store + şablonlar
│   ├── llm/                    # Provider soyutlama (Ollama) + 7 rol (kisit dahil)
│   ├── pricing/                # Fiyatlama motoru (katman maliyeti, Excel parser)
│   ├── scheduling/             # Parti/batch planlama (batcher, feasibility)
│   └── watcher/                # Eşik/sağlık kontrolleri
├── scripts/
│   ├── demo_pipeline.py        # UÇTAN UCA ÜRETİM PIPELINE'I (mod seçimi,
│   │                           #   paralel partiler, söküm planı, persist)
│   ├── eval_gate.py            # B2 eşikli eval kapısı + held-out koruması
│   ├── retrain_selection.py    # Manuel model retrain CLI
│   ├── detach_run.py           # Uzun koşular için ayrık süreç başlatıcı
│   ├── _hoca_paket.py          # Multi-solid ASCII STL çıktı paketi
│   └── c3_*.py, k*_*.py ...    # Deney scriptleri (K-xx/H-xx kayıtlarının kanıtı)
├── configs/                    # plate.local.json, llm.local.json, mail.local.json
├── prompts/                    # LLM rol şablonları + lock.json (hash kilidi)
├── data/                       # registry.json (set rolleri), selection_model.json,
│                               #   mode_model.json, telemetry/, idempotency.db,
│                               #   mail_stl/, otonom_gecmis/, pending_orders/
├── results/                    # eval_gate_baseline.json + koşu kanıtları
├── tests/                      # pytest suite (motor + runtime + webapp + LLM)
├── STRATEJI/                   # 00_ANAYASA (A1-A11), 01_VERI (registry+held-out),
│                               #   02_EVAL_KAPISI, 03_SECIM_MODELI, 04-06
├── MOTOR/                      # YONTEM_HARITASI_DATA_BASE.md — karar veritabanı
│                               #   (denenen her yöntem K-xx/H-xx, GO/NO-GO kanıtlı)
├── Veriler/                    # Gerçek setler (Plan1-3, Deneme4-6)
└── HOCA_CEVAPLARI.md           # Müşteri/danışman hoca cevaplarının kalıcı kaydı
```

**Koşu disiplini:** ölçüm koşuları `D:\ie488` ağacından `python -m
scripts.detach_run <modül>` ile yapılır (OneDrive/C'ye büyük dosya yazılmaz);
kanıt JSON+log çift kopya tutulur. Üretim logları saf ASCII'dir (Windows cp1254
konsol tuzağı).

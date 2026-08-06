# YÖNTEM HARİTASI — Nesting Motoru Karar Veritabanı (DATA BASE)

> **Bu dosya = tek doğruluk kaynağı (single source of truth).** Nesting motorunda en baştan bugüne
> denenen HER yöntem, neden işe yaradı/yaramadı, şu an üretimde ne aktif, sırada ne var — hepsi burada.
> Amaç: deneme-yanılma birikimini kalıcı bir **varlığa** çevirmek; aynı duvara iki kez toslamamak;
> her yeni oturuma yön vermek.
>
> **Kapsam:** yalnız **nesting motoru** (algoritma / kalite / hız). App/iş tarafı (mail otomasyon, LLM,
> dağıtım, IP, müşteri planı) ayrı dosyada: `APP_YOL_HARITASI.md` + ilgili memory'ler.
> **Son güncelleme:** 2026-07-03 · **Branch:** `m1-cavity-nfv` · **Rollback tag:** `checkpoint-2026-06-22-faz1-2`

---

## §0 — NASIL KULLANILIR + GÜNCELLEME KURALI

**Yeni oturum:** Önce bu dosyayı oku (§2 mevcut algoritma + §3 denenenler + §5 açık yönler). Sonra
repo kökü `RESUME_*.md` (en güncel handoff, ince-detay) + `ANALIZ_NFV.md` (NFV sayısal gelişim).

**Her DENEY sonrası (ZORUNLU):** Sonucu §3'e (kalite K-xx / hız H-xx) **standart şablonla** ekle.
Literatür araştırması olduysa §4'e işle. Açık yön kapandıysa/açıldıysa §5'i güncelle. Yeni meta-ders
çıktıysa §6'ya ekle. Üretim algoritması değiştiyse §2'yi tazele. Üst-bilgideki "Son güncelleme" tarihini at.

**Standart kayıt şablonu (kopyala):**
```
### [K-xx / H-xx] Başlık
- **Durum:** ✅ GO | ❌ NO-GO | 🟡 KISMİ/MARJİNAL   · **Tarih:** YYYY-MM-DD · **Kanıt:** script + commit + doküman
- **Ne:** tek cümle yöntem tanımı
- **Sonuç:** sayısal ölçüm (birebirlik kapısı geçti mi?)
- **NEDEN (oldu/olmadı):** kök sebep — mekanizma
- **Ders:** (varsa) gelecek için kural
- **Karne (A11):** tetik=geometrik/AD-VAR · kapı=PASS/BEKLİYOR · sıfır-dokunuş=KANITLI/BEKLİYOR · sözleşme=DEĞİL/HOCA-BEKLİYOR · held-out=BEKLİYOR
```

> **A11 KURALI (2026-07-19, Eren):** Tek-set derinleşme deneyi ŞERHLİ ön-ölçümdür;
> "kazanç" ancak 4-set kapı PASS + tetiksiz-setlerde sıfır-dokunuş kanıtıyla ilan
> edilir. Tetik kodda veri-adıyla değil geometrik koşulla yazılır. Detay:
> `STRATEJI/00_ANAYASA.md` A11.

**Durum etiketleri:** ✅ GO (ölçtü + kazandı, çoğu üretime bağlı) · ❌ NO-GO (ölçtü + kazanmadı/bozdu) ·
🟡 KISMİ (koşullu kazanç / marjinal / güvenli-modda nötr) · ⏳ AÇIK (denenmedi).

---

## §1 — PROBLEM & HEDEF

**Problem:** 3B düzensiz parçaları (STL) tek plakaya, **minimum istif yüksekliği** (mm) ile dizmek
(AM/SLM toz-yatağı nesting). Müşteri = konteyner/nesting firması; referans rakip = **Magics** (ticari).

**İki eksen:**
- **KALİTE** = istif yüksekliği (düşük = iyi). Hedef: Magics'i yakala/geç.
- **HIZ** = çözüm süresi (saniye). İkincil ama kullanılabilirlik için kritik.

**Kıyas referansları (Plan2, 226 parça, 328.74×328.19 plaka, kutuluk 0.07 = %93 boş):**
- Magics: **492mm** (0.5mm fine). · Bizim NFV n=8: **522mm** (2.0mm kaba) → açık **%6**.
- Default heightmap: 740mm. · Eski naive: 621mm (0.5mm).

**Demir kurallar:** KALİTE > HIZ · **SABİT-SAYI YASAK** (her parametre veri/donanımdan türemeli) ·
**ÖLÇ-ÖNCE** (deney→ölç→sonra üretim) · **cross-dataset** doğrulama (plan1/2/3) · birebirlik kapısı
(kaliteyi-bozmayan hız için) · reversibilite. Donanım: RTX 3060 **6GB** + 16GB RAM (Eren laptop).

---

## §2 — ŞU ANKİ ÜRETİM ALGORİTMASI (canlı snapshot, 2026-06-26)

**Üç mod (2026-06-27, K-16):** `auto` = **DEFAULT** (akıllı seçim — `predict_nfv_benefit`: cavity-zengin→NFV,
kutu/ince-plaka→heightmap; kalite-güvenli, şüphede NFV) · `nfv` (zorla cavity) · `heightmap` (zorla hızlı).
Aşağıdaki 2A (heightmap) ve 2B (NFV) o modların çekirdeği; `auto` ikisinden birini veri-odaklı seçer.

### 2A. DEFAULT — Heightmap (coarse-to-fine + DBLF + SA portföy)
| Bileşen | Nasıl | Adaptif mi? | Dosya |
|---|---|---|---|
| Boru hattı | parça>40 → coarse-to-fine otomatik (1 saat→4 dk) | ✅ otomatik tetik | `demo_pipeline.py:600 run_pipeline` |
| Pitch | `suggest_pitch` (min_feature/2.5, ince taraf) | ✅ veri-türevli | `instances/pitch.py` |
| Yerleştirme | DBLF (deepest-bottom-left) heightmap drop | sabit kural | `dblf.py`, `bin3d.py` |
| `drop_map` | sliding-window vektörize (CANLI hız, %28.5) | — | `bin3d.py _drop_map_general` |
| Oryantasyon | n=4 default (run_pipeline çağrısı) | ⚠️ adaptif YAZILDI ama app'e bağlı DEĞİL | `coarse_to_fine.py`, `adaptive_params.py` |
| Plaka | gerçek (UI/env) VEYA parçalardan otomatik; pay max(%2,10mm) | ✅ veri-türevli | `run_pipeline` |
| Metaheuristik | SA portföy + algoritma-seçim modeli | ✅ seçim modeli | `tuner.py`, `selection/` |

### 2B. OPT-IN — NFV "kalite modu" (gerçek geometrik cavity)
`scenario["nesting_mode"]="nfv"` (UI checkbox) → **`solve_nfv_kalite` (K-45, 2026-07-11)**: pitch=clearance
(K-38) + koşullu exit_guard (K-41/44; ham kilitsizse guard vergisi ödenmez) + `_instr["nfv_kalite"]` izi.
E2E-parite kanıtlı (deneme5 223.5 birebir mail-yolundan). Default BİREBİR değişmedi.
**GENEL (K-45): 2mm boşluk kuralı (`WEB_MIN_CLEARANCE_MM=2.0`, A2) + NO-GO uçtan uca
(`plate_config.resolve_no_go` → NFV/c2f/tuner-dblf üç yol + /plaka-ayar UI).**
| Bileşen | Nasıl | Adaptif mi? | Dosya |
|---|---|---|---|
| Çekirdek | FFT-NFV: `feasible = irfftn(rfftn(occ)·rfftn(grid_flip)) < 0.5`; en düşük z'de BLB | sabit (geometrik exact) | `parallel_decode.py`, `fft_backend.py` |
| Decode→üretim | NFV decode → (pid,oi,x,y,z) → `Bin3D.place` REPLAY (drop YOK, cavity korunur) | — | `nfv_solve.py` |
| Kalite reçetesi | pitch=clearance (K-38) → ham → 5-yön kilit>0 ise exit_guard (K-41/44) | ✅ kilit-koşullu | `nfv_solve.py solve_nfv_kalite` |
| Pitch (kalite modu) | = clearance (2.0; K-38 tek-voxel tam pencere); `suggest_nfv_pitch` yalnız telemetri | ✅ kural-türevli | `demo_pipeline.py` |
| Oryantasyon | n=8 default (4⊂8 küme-içerme garanti); `quality="max"`→RAM-tavanı (8→12→28) | ✅ küme-içerme + RAM | `nfv_solve.py:31` |
| Dispatcher | GPU-resident → CPU Kol A → seri (probe + graceful fallback, hepsi BİREBİR) | ✅ donanım-probe | `parallel_decode.py best_decode`, `capabilities.py` |
| Hız | xy-bbox kırpma + kademeli z-dilim + GPU-resident (3-5.5×) | — | `parallel_decode.py` |

**Kazanç (3 gerçek veri, NFV n=8 vs default heightmap):** Plan2 **%29** · Plan1 **%14** · Plan3 **%20**.
Saf-kutuda (boxy) %0 (cavity yoksa avantaj yok = doğası, overfit değil). Bedeli: NFV default'tan ~10-40× yavaş.

---

### 2C. GÜNCEL EN-İYİ (ŞAMPİYON) TABLOSU — kayıt senkronu 2026-07-25

> **Niçin bu blok:** Danışman-doküman çalışmasında (PROJECT_OVERVIEW.md) şampiyon
> değerlerinin tek bakışta bulunamadığı, registry/memory'de bayat değerler
> kaldığı görüldü (Eren: "bilgi kaybı var database'de"). Bu tablo set-başına en
> iyi LEGAL sonucu + hangi koldan geldiğini + kanıtını tek yerde tutar; her yeni
> rekor/kapı sonrası GÜNCELLENİR.

| Set | Üretim yolu (eval baseline 2026-08-04, soft sözleşme) | En iyi LEGAL (şampiyon) | Kol / kanıt |
|---|---|---|---|
| plan1 | **140.21** (K-56g pin; soft sözleşme kalıcı) | **127.20** (K-62 v20 tekil-relokasyon zinciri [z=64,8 üçlü taban + d3 TAPER relokasyonu]; **A2-LEGAL 2026-08-06**: 112/112, clear 2.447, kilit5=0 — A11 şerhi: tek-set. OTOMATİK kablo LEGAL'i: **129.00** [k62_kapi el-ayarsız, fix'li motor]. ⚠️ Eski 130.80/135.60 ÇİFT-DILATION'LI ESKİ MOTOR — yeniden-üretilemez, tarihsel) | şampiyon-reçete v20; results/k62_v20_relokasyon.json + k62_kapi.json (otomatik kol) · tarihsel: k62_v14_kilit.json |
| plan2 | **521.18** (kapı-2 REKORU — eski 529.04'ü geçti) | 521.18 (= üretim) | üretim; eval_gate_baseline 2026-08-04 |
| plan3 | 607.50 (soft bedeli +5.58 — bilinçli kabul, kapı-2) | **577.62** (K-49d R11-v4, 2026-07-13; clear 2.033, kilit 0) | şampiyon-reçete; STL plan3_r11d_577.6mm.stl (D) |
| deneme4 | **215.87** (kapı-2 YENİ ŞAMPİYON — eski 220.69'u geçti) | 215.87 (= üretim) | üretim; eval_gate_baseline 2026-08-04 |
| deneme5 | *(eval config'i yok)* | **214.64** (K-50 R11-v4, 2026-07-14) | şampiyon-reçete; STL deneme5_r11v4_214.6mm.stl (D) |
| deneme6 | **68.50** (kör-test) | 65.50 (max kolu) | held-out; deneme6_heldout_final.json |
| plan7 | **488.40** (kör-test, kısıtsız) | 488.40 (max BİREBİR) | held-out; plan7_heldout_final.json |

**Üretim R11 = v4 REÇETESİ** (`continuous_settle.uretim_r11`: pay 0.15 +
doğrula-ve-rafine + 4 kapı, tek-taraflı) + K-58 auto-tavan 600 (`ff7b055`) —
"v4'ü üretime geçirme" işi KAPALI. **Açık makas yalnız plan3** (601.92 vs
577.62, ~24mm): K-58 p3-kolu NÖTR ölçüldü (0.00) → makas R11-tavanı DEĞİL;
K-53 poz taraması da pozları eledi → kalan şüpheli, şampiyon zincirinin
başlangıç yerleşimi (596.50 ham) ile üretim tek-atış hamı (~621.5) farkı.
Teşhis adayı: şampiyon-reçete zincirini güncel sözleşmede adım-adım replay +
üretim koluyla aşama-kırılım kıyası (A4 ölç-önce).

---

## §3 — DENENEN YÖNTEMLER ENVANTERİ

### 3.1 KALİTE

### [K-56g kapı-2 + SÖZLEŞME] Soft no-go (y-üst 45→33) 4-set kapısı → KALICI SÖZLEŞME + BASELINE YENİLEME
- **Durum:** ✅ ÜRETİMDE (sözleşme kalıcı, Eren kararı 2026-08-04 sabah) · **Tarih:** kapı 2026-08-04 gece (`f615d8d`), kalıcılaştırma 2026-08-04 · **Kanıt:** `results/eval_gate_last.json` 2026-08-04T00:12 (D+C) + `scripts/k56g_kapi.log`
- **Kapı-2 sonucu (soft sözleşme 4-set, 96dk, münhasır):** p1 202.18→**140.21** (pin tetikli, kilit 0, clear 2.034) · p2 529.04→**521.18** (−7.86 REKOR; söküm-planlı cert 3) · p3 601.92→**607.50** (+5.58 BEDEL) · d4 220.69→**215.87** (−4.82 YENİ ŞAMPİYON; söküm-planlı cert 17). Net −69.1mm; B2 = İNSAN-KARARI (p3 bedeli) → **Eren KABUL**. Kapı-1 (hard sözleşme, NOOP 68dk) = çoklu-pin+NFV-pin motor değişikliklerinin 4-set sıfır-dokunuş kanıtı.
- **Kalıcılaştırma paketi (2026-08-04):** (1) `/plaka-ayar` POST **MERGE fix** (önceden config'i sıfırdan yazıp form-dışı alanları siliyordu — no_go_soft kaydedilemezdi; +4 test) · (2) `configs/plate.local.json`'a `no_go_soft` ilanı (üretim/demo_pipeline aktivasyonu; hard `no_go` fiziksel kayıt olarak kaldı) · (3) `eval_gate.py` NOGO_STD=NOGO_SOFT=(152.5,0.2)-(185.5,33.0) + NOGO_HARD tarihsel sabit + sözleşme-pin testi · (4) baseline kapı-2 koşusundan terfi (`results/eval_gate_baseline.json` C+D; eski 2026-07-20 değerleri _baseline_not'ta) · (5) bayat testler A9 ile kilitlendi (k56b tilt testleri NOGO_SOFT=None pinler; k45 _SolveSpy imzasına K-62 v8 `pinned_placements` eklendi).
- **Ders:** eval_gate soft ilanı MODÜL-ATTR ister (env değil) — ilk kapı koşusu env-only bırakınca pin dalı ölü kaldı (o koşu kazara sıfır-dokunuş replay kanıtı oldu). Sözleşme-kapılı kablo deseni (ilan yoksa ölü kod) kalıcılaştırmayı tek-config-alanı işine indirdi.
- **Karne (A11):** tetik=GEOMETRİK (duz_pin_onerisi; set adı yok) · kapı=**PASS/KABUL** (4-set ölçüldü, İNSAN-KARARI→Eren) · sıfır-dokunuş=**KANITLI** (kapı-1 NOOP + kapı-2'de p2/d4 iyileşme p3 bedel — tetiksiz set yok, hepsi ölçüldü) · sözleşme=**EVET-KARARLI** (hoca 2026-07-09 c3/9 dayanak + Eren 2026-08-04; baseline A8 gerekçeli yenilendi) · held-out=BEKLİYOR (yeni gerçek veri gelince ilk iş).

### [K-62 v9] NFV 3D pin / occupancy ön-yükleme — kanopi ÇÖZÜMÜN İÇİNDE (İLK ÖLÇÜM ŞERHLİ)
- **Durum:** 🟡 MEKANİZMA KODDA (commit `43432d3`), ilk ölçüm ŞERHLİ — pin 140,21 geçildi, v4 136,50 GEÇİLEMEDİ · **Tarih:** 2026-08-04 · **Kanıt:** `results/k62_v9_pin3d.json` (D+C) + `scripts/k62_v9_pin3d.log`
- **Mekanizma:** v8'in 2D kolon mührü (pin altı-üstü yasak) yerine pin GERÇEK 3D voxelleriyle `best_decode` occupancy'sine ön-yüklenir: `OccupancyBin3D.onyukle` (kırpmalı, çarpışma-kontrolsüz — no-go örtüşmesi meşru) + `decode/decode_gpu/best_decode occ_onyuk` + `solve_nfv(pin_3d=True)`. Pin çözücü-modelde havuz parçalarıyla AYNI clearance dilation'ını taşır (xy margin + tek-taraflı üst z-dilation) → v8-MVP'nin kuantizasyon-ihlali sınıfı yapısal kapalı. `fine_settle`/`repair` pin-farkında değil → pin_3d'de yapısal atlanır (iz bırakır). TDD 13 test (kanopi-altına istif · delikten kule · GPU parite · bit-özdeşlik · dikey clearance) + komşular 50/50.
- **İlk ölçüm (plan1, kanopi=baseplate_v2 geometrik tetikle, z-taraması, 5,4dk):** z=68 → **139,20** (en iyi) · z=70 → 141,60 · z=72/74 → 144,00; hepsi 112/112, pitch AUTO 2,4. Pin xy fizibilite ilk-poz (rot0, dy=20,5).
- **Okuma:** mekanizma ÇALIŞIYOR (kanopi pinliyken tüm set tek atışta çözüldü; v8 aynı sahnede çözümsüzdü) ama sonuç v4 suçlu-taşımanın (136,50) üstünde. Şüpheli vergiler: (a) AUTO pitch 2,4 KABA (aşama-1 105,5 pitch 0,5 ile alınmıştı), (b) settle pin_3d'de atlanıyor (kuantizasyon vergisi geri alınamıyor), (c) pin xy pozu marj-en-iyi değil ilk-uygun (delik hizası kule geçişini etkiler). İnce-pitch tek-z derinleşmesi (z=68/69, pitch 1,2) aynı gün kuyruğa alındı.
- **Şerhler:** tek-set · kilit ölçülmedi · clearance ölçüm satırı ilk koşuda hatalı (ClearanceReport.min_mm fix'i sonraki koşuda) · exit_guard pin-farkında değil (ölçüm raw).
- **TEŞHİS TURLARI (aynı gün, A4):** (1) İnce-pitch 1,2 @ z=68/69: 140,40/141,60 — kaba 2,4'ten İYİ DEĞİL → **kuantizasyon ana vergi DEĞİL**; clearance merged 2,448 ≥ 2,0 (v9 pin-clearance mekanizması SAHADA kanıtlı; v10 T4'te ikinci bağımsız doğrulama 2,603). (2) Katman telemetrisi (z=68): **kanopi üstünde 0 parça · 41 parça delikten · 70 altında** — mekanizma birebir insan-deseni; tavanı yapan **bobbin_1_v2 delik-sütunları** (alt 103,2 → üst 139,2; manuel'de sütunlar 110'da biter → bir halka TAŞIYOR). (3) Pin dy kaydırma (20,5→23,5) sonuç BİT-ÖZDEŞ — ofset kaldıraç değil; dy=32,5 pozu final-commit'te plaka-taşması hatası (margin-0 kanopi `bin3d.place` kırpma sınırı — bilinen v8 commit yolu sınırı, ölçüm etkilenmedi). **KALAN MAKAS ADRESİ: bobbin kopyalarının delik-sütunlarına DAĞITIMI (kapasite/atama) — v10 (kule-kopya seçimi × delik-atama küçük arama) veya bobbin'lerin bir kısmını kanopi-altı bölgeye yönlendirme. Kanopi z/pitch/ofset kaldıraç DEĞİL (ölçüldü).**
- **Karne (A11):** tetik=GEOMETRİK (alan-oran+doluluk+fizibilite; adayı kendisi buldu) · kapı=YOK (deney; üretim kablosu ayrı iş) · sıfır-dokunuş=YAPISAL (occ_onyuk/pin_3d default None/False = bit-özdeş; testli) · sözleşme=DEĞİL · held-out=N/A. Genelleme: GO çıkarsa k59-deseni dağılımsal (holey_frames) zorunlu.

### [K-62 v11] ÇÖZÜM-İÇİ KULE-ÖNCELİĞİ (decode sıra müdahalesi) — ✅ GO ŞERHLİ: plan1 134,40 YENİ EN-İYİ
- **Durum:** ✅ GO (şerhli tek-set; plan1 139,20→**134,40**, v4 136,50 GEÇİLDİ, clearance **2,447 ✓**) · **Tarih:** 2026-08-04 akşam · **Kanıt:** `results/k62_v11_sira.json` (D+C) + `scripts/k62_v11_sira.log`
- **Mekanizma (v10 NO-GO'nun dersiyle):** statik pin yerine çözüm-İÇİ sıra müdahalesi — `parallel_decode._sira_anahtari` opt-in `oncelik_ids` (öncelikli parçalar önce, katman-içi hacim-azalan; None=bit-özdeş, testli) + `solve_nfv(oncelik_adlari)` ad→id çevirisi. Öncelik kümesi ÇÖZÜM-GÜDÜMLÜ: referans koşuda kanopi-tepesini aşan tipler (A11: veri-adı yok). İnsan deseni "önce kuleleri dik, sonra arayı doldur" — BLB esnekliği korunur (v10'un statik-tahsis hatası yok).
- **Ölçüm (kanopi 3D-pin z-sweep × öncelik-varyantı):** A-ref 139,20 (v9 birebir) · **B-aşan z=68 → 134,40** (katman: üstünde 8'e düştü [41→18 delikten], bobbin tavanı ÇÖZÜLDÜ) · C-aile z=68 → 134,40 · z=70 kolu 136,80. Yeni tavan tipleri: pyramid_with_doors / TAPER-GAUGE (→ v11b iteratif genişletme adayı, aynı gün kuyruğa alındı).
- **Karne (A11):** tetik=çözüm-güdümlü aşan-tip (veri-adı yok) · kapı=BEKLİYOR (4-set + sıfır-dokunuş; oncelik default None=bit-özdeş YAPISAL+testli) · sözleşme=DEĞİL · held-out=BEKLİYOR. **ŞERHLER: tek-set · kilit ölçülmedi · üretim kablosu yok (deney parametresi).**
- **DEVAM ZİNCİRİ (aynı gün akşam-gece; kanıtlar results/k62_v11b/v11c/v12*/v13*):** (a) **v11b/v11c küme-arama:** kör iteratif genişletme NON-MONOTON (8'li küme 165,6'ya patlar); tekil forward-selection tekil etkiler kötü olduğundan hiçbir şey tutamaz (bobbin_1 tek 156) — **aşan-üçlü {811793-1, bobbin_1, bobbin_2} lokal optimum KANITLI** (8 ileri/geri komşusu hep kötü). (b) **v12 mikro:** 134,40 platosu z(64-69, en iyi 67-68) ve seed'e (42/7/101/2026) TAM duyarsız — BLB bu konfigde deterministik-kararlı. (c) **v12b SETTLE PİN-FARKINDALIĞI = GO:** `fine_settle_raw(onyuk_raw)` (pinler fine occ'a hareketsiz damga, kırpmalı, pid-anahtarlı; None=bit-özdeş) + nfv_solve entegrasyonu → **134,40→132,00** (2,4mm kuantizasyon vergisi geri alındı; clearance 2,447). (d) **v13 rütbeli öncelik** (dict {ad:rütbe}; motor destekli, testli): TOPLU rütbe-1 ekleme yine patlar (158,4 — whack-a-mole: MTShoe fırlar) ama **TEKİL rütbe-1 ekleme kazandırır: üçlü + TAPER-GAUGE-1@r1 = 130,80** (pyramid@r1 nötr). → (e) **v13b greedy tekil tarama SONUÇ: rütbe-1'e yalnız TAPER tutunuyor** (pyramid nötr; 811791/bobbin_3/part262835/MTShoe hepsi patlıyor 137-146) — **FİNAL 130,80 / clearance 2,447 ✓, reçete: kanopi 3D-pin z=67 + öncelik {811793-1:0, bobbin_1:0, bobbin_2:0, TAPER-GAUGE-1:1} + settle pin-farkında** (kanıt results/k62_v13b_greedy.json D+C). **ZİNCİR BUGÜN: 139,20 → 134,40 (v11) → 132,00 (v12b settle) → 130,80 (v13/v13b); manuel 110,41'e makas 20,4. Kazançlar doyumda (5,4→2,4→1,2) — öncelik ekseni tükendi.** Kalan yol (yeni seans): delik-farkındalı aşama-1 (PLAN Ç2-derin) · kanopi-altı bölge-hedefli decode · ~~kilit ölçümü~~ ✓(v14) · k59-deseni dağılımsal + 4-set kapı (A11 GO ilanı şartları) · üretim kablosu. → (f) **v14 KİLİT ÖLÇÜMÜ (2026-08-05): 130,80 A2-LEGAL** — reçete deterministik replay h=130,80 BİREBİR (112/112, 1,4dk), clearance 2,447 ✓, **5-yön kilit=0** (rot-söküm denetimine gerek kalmadı; 0,7dk) → legallik şerhi KAPandı, kalan şerh yalnız A11 (tek-set + kablo yok). Kanıt: `results/k62_v14_kilit.json` (D+C) + `scripts/k62_v14_kilit.log`. Karne: tetik=geometrik (reçete v13b'den) · kapı=BEKLİYOR · sıfır-dokunuş=YAPISAL (tüm anahtarlar default-kapalı testli) · sözleşme=DEĞİL · held-out=BEKLİYOR.

### [K-62 KABLO + DAĞILIMSAL] kanopi_zincir modülü + holey_frames ailesi + k59-deseni smoke — ✅ TETİK-DOĞRULUĞU 24/24, KAZANÇ 2W/5T/0L
- **Durum:** ✅ MEKANİZMA KODDA (src, opt-in; üretim yolu ÇAĞIRMIYOR — bit-özdeşlik yapısal+testli), dağılımsal smoke PASS · **Tarih:** 2026-08-05 · **Kanıt:** `results/k62_dagilim_smoke.json` (D+C) + `scripts/k62_dagilim_smoke.log` + `tests/test_kanopi_zincir.py` (10 test)
- **Kablo (A11 genelleme):** `src/nesting3d/kanopi_zincir.py` — v13b el-reçetesinin otomatik hali: `kanopi_adayi` (geometrik tetik: alan_oran≥0.35 + doluluk<0.6 + no-go-fizibil; veri-adı YOK) + `kanopi_zinciri_coz` (ref → 3D-pin z-adayları [ref-h oranları 0.45/0.50/0.55] → kule-önceliği rütbe-0 → opsiyonel greedy rütbe-1). **TEK-TARAFLI sözleşme: ref'ten kötü dönemez; tetik yoksa ref AYNEN döner.** `holey_frames` (synthetic.py): gerçek-STL delikli-kanopi ailesi; ızgara-ekstrüzyon mesher (kutu-birleştirme NO-GO: çakışık yüzeyler slice-voxelize paritesinde delikleri dolduruyordu — ölçülen doluluk 0.87 vs analitik 0.54; extrude_polygon da triangulation-engine bağımlılığı istiyor). Yakalanan 2. bug: stl-source PartSpec boyut alanları boş → `suggest_nfv_pitch` TypeError (üretim loader'ı bbox dolduruyor; jeneratörler aynı desene alındı).
- **Smoke sonuçları (24 tetik örneği + 8 A/B + 8 yanlış-pozitif + nokta-kontrol, 7.5dk):** (1) **TETİK 24/24 UYUM** bağımsız analitik beklentiyle (sınır-bandı 0; ateşleyen 7/24; kenar-çentiği dx-hiza fiziği dahil). (2) **KAZANÇ:** seyrek A/B (10-12 parça) 7/7 TIE — yükseklik baskısı yok, ref=en yüksek parça (DERS: kazanç ölçümü baskılı ailede yapılır); YOĞUN A/B (52-90 parça, aynı çerçeve tasarımı): **2 WIN (−%17.0, −%13.6; ikisi de pin adımından) / 5 TIE / 0 LOSS.** (3) **YANLIŞ-POZİTİF 0:** katı-plaka STL (geometrik elenme: doluluk~1.0) + random_boxes/long_rods (yapısal); nokta-kontrol tetiksizde yalnız-ref ✓.
- **Okuma:** mekanizma tetiklenen sette garanti kazanç DEĞİL — geometri uygunsa (kule+delik+istif baskısı) çift-hane, değilse 0; kayıp yapısal imkânsız. Üretim beklentisi: kanopi-sınıfı siparişlerde ~%5-15, diğer her şeyde bit-özdeş.
- **Karne (A11):** tetik=**GEOMETRİK+DAĞILIMSAL-KANITLI** (24/24 bağımsız beklenti, yanlış-pozitif 0) · kapı=**KISMEN** (aşağıdaki K-62 KAPI kaydı: plan1 otomatik LEGAL 135,60; p2/d4 etki-ölçümü BEKLİYOR) · sıfır-dokunuş=YAPISAL+testli (opt-in; üretim yolu çağırmıyor) · sözleşme=DEĞİL · held-out=BEKLİYOR (A3).

### [K-62 KAPI v1-v3] Otomatik zincir 4-set kapı paketi — ✅ plan1 OTOMATİK-LEGAL 135,60 (el-ayarsız); p2/d4 TETİKLİ sınıfa geçti
- **Durum:** ✅ KAPI KANITI (plan1 kolu) + 2 AÇIK İŞ · **Tarih:** 2026-08-05 (v1 3,9dk teşhis · v2 15,4dk · v3 21,1dk) · **Kanıt:** `results/k62_kapi.json` (D+C) + `scripts/k62_kapi.log`
- **v1 dersleri (3,9dk — A4 ucuz teşhis):** (a) pinsiz plan1 ref'i 111/112 kalıyor (kök-sebep sahada: bbox kapısı baseplate'i yerleştiremiyor) ve zincirin `ref-tam-değilse-pes` guard'ı v9'un ana bulgusuyla çelişiyordu → **fix: zincir eksik-yerleşimli ref'te de denenir; kıyas anahtarı lexicographic (n_placed → yükseklik)** (`_daha_iyi`; monkeypatch'li test kilitli, 11 test yeşil). (b) **tetik taraması: plan2 ATEŞLEDİ** (PO-TR..P282334, alan 0,363/doluluk 0,251 — seyrek-footprint) ve **deneme4 ATEŞLEDİ** (ROBT ALT v27, 0,60/0,46); plan3 sessiz. Bunlar ihlal DEĞİL — tetik geometrik koşul; bu setler "tetikli" sınıfına geçer, etkileri ayrı münhasır koşuda ölçülür (tek-taraflılık gereği yükseklik kötüleşemez; ölçülecek olan süre maliyeti + olası kazanç). Eşik oynama YOK (veri-adına eşik = A11 ihlali).
- **v2→v3 (plan1 otomatik zincir, elle z/rütbe YOK):** zincir kendi başına z=65,3 + üçlü@r0 + part262835@r1 = **132,60 (112/112)** buldu — el-reçetesine (130,80; z=67+TAPER@r1) 1,8mm mesafe, farklı konfigle: **plato geniş, mekanizma el-ayarına bağımlı değil.** AMA clearance 1,961 (39μ ihlal) → A2 INVALID (K-19 maskelenmez). **v3 GERİ-DÜŞÜŞ deseni:** kazanan geçemezse sıradaki aday tam-A2 ile denenir → öncelik-r0 135,00 da 1,967 INVALID; **yalnız-pin 135,60 → clearance 2,062 ✓ + kilit5=19 ama ROT-SÖKÜM=0 → SÖKÜM-PLANLI LEGAL** (A2 güncellemesi-2 yolu otomatik zincirde ilk saha kanıtı). Net: **otomatik+legal 135,60 = üretim pin yolundan (140,21) −4,6mm, el-müdahalesiz.**
- **Açık işler:** (1) p2/d4 zincir etki-ölçümü (münhasır, RAM uygunken; d4 ROBT ALT gerçek kanopi adayı olabilir — fırsat). (2) Öncelik konfigleri z=65,3'te sistematik 1,96-1,97 kıl-payı ihlalde (z=67'de 2,447 idi) → **z-kuantizasyon/pitch-hiza teşhisi** kablo iyileştirme adayı (öncelik yolu legal olsa 135,00 alınırdı). (3) Üretim kablosu kararı (opt-in kalite modu; geri-düşüş deseni zorunlu bileşen) — EREN KARARI.
- **Karne (A11):** tetik=geometrik+dağılımsal-kanıtlı · kapı=plan1-PASS (otomatik LEGAL 135,60), p2/p3/d4 etki-ölçümü BEKLİYOR (p3 sıfır-dokunuş: tetik sessiz + opt-in yapısal) · sıfır-dokunuş=p3 KANITLI / p2+d4 TETİKLİ-SINIF (ölçüm bekler) · sözleşme=DEĞİL · held-out=BEKLİYOR (A3).

### [K-62 v15-v16d] Teşhis zinciri: doluluk anatomisi → rip-up 2×GERİ-AL → 🔴 KÖK BULGU: PARÇA-PİN ÇİFT-DILATION
- **Durum:** 🔴 KÖK-NEDEN KANITLI (kod+davranış), fix YARINKİ SEANS İŞİ (motor değişikliği — TDD + yeniden-ölçüm zinciri) · **Tarih:** 2026-08-05 gece → 08-06 · **Kanıt:** `results/k62_v15_teshis.json` + `k62_v16_ripup.json` + `k62_v16c_tek_sokum.json` + `k62_v16d_pin_parite.json` (hepsi D+C)
- **v15 anatomi (130,80; 80s):** kanopi-altı **%65 BOŞ (4881cm³)**, 110+ tavan yükü yalnız **569cm³** (17 parça: 5 pyramid kulesi + 3 bobbin_3 + 7×811791 + MTShoe) → makas kapasite değil KOMBİNATORYAL; tavan-17 çıkarsa kalan tepe ~110 → manuel-parite bandı fiziken açık.
- **v16 rip-up (tavan sök + kalanı 3D-pin + yeniden çöz):** kaba-pitch tur-1 GERİ-AL (130,8→138,0; 17,6dk) · snap'siz varyant (settle kapalı, coarse-grid birebir) yine GERİ-AL (134,4→136,8; 0,9dk) — sökülenler eski BOŞ pozlarına dönemiyor. Yol kazaları da kayıtlı: res.fine_pitch=settle-pitch'i coarse diye geri beslemek 0,3-coarse 6,19GiB MemErr; auto pitch bol-RAM'de 0,3'e iner; detach_run env geçirmez; Ollama 2,5GB RAM'i yiyince 0,6GB'de thrashing (koşu öldürüldü, Eren onayıyla Ollama kapatıldı).
- **v16c/v16d ayırt ediciler:** tek-tepe söküm h→158,4 (anomali) · tek-alçak söküm h→132,0 (pinli pyramid 134,4'te sabitken İMKANSIZ görünümlü) · **v16d parite: 111/111 pin KONUM-BİREBİR, clearance 2,447 sağlıklı** → sahne doğru kuruluyor; "üst" farkları ölçüm-grid dilation farkı (taban dökümü dilation'lı havuz gridi vs pin commit margin-0 ham grid).
- **🔴 KÖK (kod kanıtı `nfv_solve.py:249-255`):** pin gridleri `margin=_eff_m, z_dilate=_eff_zc` ile DILATION'LI damgalanıyor; normal akışta occupancy HAM yazılır + aday dilation'lı test eder (kanıt: baseline clearance 2,447 ≈ tek-dilation). Sonuç: **parça-parça boşluk 1×, parça-pin boşluğu 2× dilation** — v9 yorumundaki "aynı garanti" iddiası yanlış. Rip-up'ın cebe dönememesi bu (cep 4,8mm ister oldu); **130,80'in içinde de kanopi çevresinde gizli çift-dilation vergisi var** — ham-pin fix'i sonrası v13b yeniden ölçümü 130,80'i de düşürebilir.
- **⚠️ DÜZELTME (v17 kod-okuma, 2026-08-06):** "occupancy normalde HAM yazılır" İFADESİ YANLIŞTI — decode HER parçayı dilated damgalar (`parallel_decode.py:291` place + GPU:476); parça-parça xy aslında **2× margin** (4,8mm @2,4 pitch), dikey tek-taraflı **1×** (2,4mm; ölçülen 2,447 min bu). Asıl asimetri: pin SABİT nesne olduğundan `_pin_hazirla` sözleşmesi "komşu kendi marjını taşır → 1× yeter" der (v8 2D-mühür ham'dı, 140,21 LEGAL saha kanıtı); v9 3D damgası pini gereksiz TAM dilation'a çıkarıp parça-pin xy'yi parça-parçayla aynı 2×'e sabitledi — rip-up'ta sökülen parçanın cebine dönmesi için gereken boşluk da 2× kaldı. İkinci bağımsız bug: v16/v16d harness'i pin koordinatını dilated-origin'den üretti (`pl.x*pt`; sözleşme margin-0 raw bbox) → parça-pinler −1 voxel kayık, kanopi-pin kaymıyor = karışık sahne + delik-hiza bozulması; v16c 158,4/132,0 "anomalileri" ise `ust` raporunun z-dilate pad'ini saymasından (rapor artefaktı).
- **SIRADAKİ (öncelik sırasıyla, yeni seans):** (1) ham-pin fix (`_vp3(margin=0, z_dilate=0)` + origin ofseti kalkar; yalnız pin_3d yolu — TDD: parça-pin boşluğu == parça-parça; v9 13 testi gözden geçir) → (2) v13b reçete yeniden-ölçüm (130,80 vergisiz kaç?) → (3) v16 rip-up yeniden (cebe dönüş açılır mı; 158,4 gizemi burada kapanır) → (4) GO ise kablo zinciri 5. adım + dağılımsal + kapı. Karne: teşhis zinciri A4-uyumlu (80s-18dk koşular); mekanizma kararı fix-sonrası ölçüme ertelendi.

### [K-62 v17] HAM-PIN fix (parça-pin çift-dilation) — ✅ KOD+TDD; v13b yeniden-ölçüm 131,40 (eski-reçete kazancı tabana karıştı)
- **Durum:** ✅ FIX KODDA + TDD (20/20 + komşu 97 test yeşil) · v13b yeniden-ölçüm TAMAM · v17 rip-up KOŞUDA · **Tarih:** 2026-08-06 · **Kanıt:** `tests/test_k62_v9_pin3d.py` (v17 bölümü, 4 yeni test; kırmızı→yeşil 4,000mm→2,0mm) + `results/k62_v13b_greedy.json` (D+C) + `scripts/k62_v13b_greedy.log`
- **Fix (`nfv_solve.py` occ_onyuk + `fine_settle.py` onyuk damgası):** pin xy'de HAM damgalanır (`margin=0`, origin ofseti kalkar); **dikey `z_dilate` KALIR** — dünkü plandaki "z_dilate=0" TUZAKTI: pin tepesi ham kalsa üstüne oturan parça 0mm'e inerdi (A2 ihlali); dikey boşluğu alttaki nesnenin üst-dilation'ı taşır. Parça-pin xy böylece 1× margin (=clearance; `_pin_hazirla` sözleşmesi, v8 saha-kanıtlı); parça-parça 2× (tarihi taban davranışı) DEĞİŞMEDİ. Pin'siz yol yapısal bit-özdeş (occ_onyuk yalnız pin_3d'de kurulur; 13 eski test yeşil).
- **TDD kanıtı:** fix öncesi parça-pin mesh boşluğu **4,000mm** ölçüldü (2× dilation, kırmızı test) → fix sonrası **2,0mm** (1×, legal ≥2,0). Dikey korunum testleri (decode + settle, pin üstü ≥ clearance) yeşil.
- **v13b yeniden-ölçüm (plan1, 18,0dk):** referans üçlü 135,00 · **taban 131,40** (eski akışta 134,40'tı — fix tabana +3,0 kazandırdı) · greedy 4 aday da GERİ-AL (TAPER-GAUGE dahil; eski reçetenin +TAPER kazancı fix'li tabana karışmış) → **en iyi 131,40, clearance 2,448 ✓**. Eski 130,80'in 0,6 ÜSTÜNDE: eski rekor çift-dilation'lı motorun arama-uzayı tesadüfüne aitti; fix'li motor aynı reçeteyle farklı (biraz yüksek) yerel tepeye indi. Şampiyon karşılaştırması v17 rip-up sonucuyla birlikte değerlendirilecek (130,80 ESKİ-MOTOR şerhli kalır).
- **v17 rip-up (dörtlü rütbe tabanı; `results/k62_v17_ripup.json`):** taban 134,40 → **tur-1 KABUL 132,00** (17 sökülen: 5 pyramid + 11×811791 + MTShoe; 95 pin; 1,4dk/tur) → tur-2 aynı sabit nokta, dur → **final 132,00 A2-LEGAL (clearance 2,447 · kilit5=0 · 112/112)**. **İLK rip-up kabulü** — v16'da (çift-dilation + harness koordinat bug'ı) her tur GERİ-AL idi; cebe dönüş fix'le AÇILDI = mekanizma kanıtı. Not: v16'nın "sökülenler dönemiyor" gözlemi İKİ bug'ın bileşimiydi (motor 2× + pin −1 voxel kayma); v17 harness'i koordinatı voxel_origin'den raw-bbox'a çevirir (kendinden-doğrulamalı) ve `ust`'u z-pad'siz raporlar.
- **v17b rip-up (üçlü rütbe, snap'sız; `results/k62_v17b_ripup_uclu.json`):** taban 132,00 (üçlü+snap'sız; v13b'nin 131,40'ı SETTLE'lıydı — fark settle kuantizasyon geri-alımı) → tur-1 GERİ-AL (132,00 sabit nokta) → **final 132,00 A2-LEGAL (clearance 2,448 · kilit5=0)**. Üçlü tabanda rip-up ek kazanç vermedi.
- **v17c rip-up (üçlü + SETTLE'lı zincir; `results/k62_v17c_ripup_settle.json`):** taban **131,40** (v13b fix'li en-iyi BİREBİR; coarse 2,4 / settle 0,6 pitch ayrımı MemErr tuzağı kapatılarak) → tur-1 GERİ-AL (131,40 sabit nokta; 10,4dk settle'lı tur) → **final 131,40 A2-LEGAL (clearance 2,448 · kilit5=0 · 112/112)** — 131,40'ın kilit ölçümü İLK KEZ yapıldı, TAM-LEGAL. **Fix'li motor plan1 LEGAL şampiyonu = 131,40.**
- **OKUMA (rip-up sabit-noktası):** üç varyantta da söküm+yeniden-çözüm 1 turda kendi tabanına döndü (v17 dörtlü kolunda tek gerçek kazanç 134,40→132,00). Cebe dönüş mekanik olarak AÇIK (v17 tur-1 kabulü kanıt) ama BLB decode sökülenleri deterministik aynı düzene götürüyor — 110-bandına inen kombinatoryal makas rip-up'ın tek başına kapatacağı şey değil (v15 anatomisiyle tutarlı: makas kapasite değil ARAMA). Sonraki aday: söküm sonrası farklı yerleştirme politikası (delik-hedefli sıra/aday üretimi) veya çok-tur perturbasyon.
- **Dağılımsal smoke YENİDEN (fix'li motor; `results/k62_dagilim_smoke.json` + log):** tetik **24/24 uyum** (7 ateşleyen, 0 sınır) · **yanlış-pozitif 0** · A/B **4W/3T/0L** — eski motorun 2W/5T/0L'sinden İYİ (ham-pin cebe erişimi sentetik ailede de kazanç çevirdi); kayıp yine yapısal sıfır.
- **🏆 KAPI YENİDEN (fix'li motor; `results/k62_kapi.json` + log):** plan1 **OTOMATİK zincir h=129,00 LEGAL** (el-ayarsız: kendi bulduğu z=65,3 + öncelik üçlü; kazanan etiket=oncelik) — eski otomatik 135,60'tan **−6,6**; eski el-reçetesi 130,80'in ve fix'li el-şampiyonu 131,40'ın da ALTINDA → **YENİ PLAN1 ŞAMPİYONU 129,00, üstelik OTOMATİK**. Mekanik açıklama: eski kapıda öncelik-konfigleri z=65,3'te sistematik 1,96-1,97 kıl-payı clearance ihlalindeydi (çift-dilation kuantizasyon artefaktı) → 135,60 geri-düşüşe kalıyordu; ham-pin fix'i tam o ihlal sınıfını çözdü (açık iş (2) z-hiza teşhisi BÖYLECE KAPANDI). Tetik taraması: ek 2/3 set (p2/d4) tetik-ateşler sınıfta (zincir etkisi ayrı münhasır koşu; tek-taraflılık gereği kötüleşme yapısal imkânsız), p3 sessiz.
- **Karne (A11):** tetik=geometrik+dağılımsal-KANITLI (fix'li motorla yeniden: 24/24 + 0 yanlış-pozitif + 4W/3T/0L) · kapı=**plan1-PASS (otomatik LEGAL 129,00)**; p2/d4 etki-ölçümü BEKLİYOR (tetikli sınıf; RAM uygunken münhasır) · sıfır-dokunuş=p3 KANITLI (tetik sessiz + opt-in yapısal) · sözleşme=DEĞİL (clearance semantiği aynı; yalnız pin damga iç-temsili) · held-out=BEKLİYOR. **ŞERH: plan1 ölçümleri tek-set.**

### [K-62 v18] z-VOXEL taraması + kademeli rip-up — 129,00 bağımsız replikasyon; iz=27 tek kazanan bölge
- **Durum:** ✅ FAZ-A+B2+A2 TAMAM (129,00 LEGAL bağımsız yeniden-üretim) · faz-B harness kusuru v18b'de düzeltildi (koşuda) · **Tarih:** 2026-08-06 akşam · **Kanıt:** `results/k62_v18_derinlestir.json` (D+C) + log
- **Faz-A z-voxel taraması (üçlü öncelik, settle'sız, 4×~1,3dk):** kanopi z değerleri voxel gridinde iz'e snap olur (65,3→27 · 67→28) — sistematik iz taraması İLK KEZ: iz=26 (62,4) → 136,80 (kanopi-altı daralır) · **iz=27 (64,8) → 129,60 KAZANAN** · iz=28 (67,2) → 132,00 · iz=29 (69,6) → 132,00. Kapının 65,3'ü ile v13b'nin 67'si FARKLI voxel seviyeleriymiş; tüm eski el-z denemeleri (67) yanlış iz'deymiş.
- **B2 settle:** 129,60 → **129,00 KABUL**; **A2: clearance 2,447 · kilit5=0 · LEGAL** — kapının 129,00'ı bağımsız zincirle REPLİKE (deterministik güven ↑).
- **Faz-B kusuru (ders):** `hedef = h − pitch` RAW-üst semantiğiyle tam tepeye denk gelir (h dilated-tepe; raw üst = h − z_pad) → sökülen listesi BOŞ, rip-up hiç koşmadı. v18b düzeltmesi: hedef sökülen bulunana dek pitch adımlarıyla iner.
- **Karne (A11):** v17 karnesiyle aynı sınıf (tek-set ön-ölçüm; fix'li motor).
- **v18b kademeli rip-up (düzeltmeli; `results/k62_v18b_ripup_kademe.json`):** taban 129,60 → k1 hedef 124,8'de tepe 5'lisi söküldü (2 pyramid + TAPER + 2 bobbin_3; 107 pin) → **4 sıra varyantı da iyileştiremedi** (V0/V1/V3 → 129,60 sabit nokta; V2-kısa 136,80 kötü) → B2 settle 129,00 (3. bağımsız replikasyon) · A2 LEGAL (2,447 · kilit5=0). **DERS: söküm+sıra-perturbasyonu ekseni TÜKENDİ** — tepe 5'lisi hangi sırayla verilirse verilsin BLB aynı düzene dönüyor; makas aday-üretimi/atama katmanında (v19 teşhisi anatomiyi ölçüyor: kanopi-altı mı, delik kapasitesi mi, yapısal mı).

### [K-62 v19] 129,00 sahnesinin doluluk anatomisi (A4 teşhis) — makas adresi: FRAGMENTASYON + istif-tepesi
- **Durum:** ✅ TEŞHİS TAMAM (4dk) · **Tarih:** 2026-08-06 akşam · **Kanıt:** `results/k62_v19_teshis_129.json` (D+C) + log
- **Bulgular (129,00 settle'lı sahne, fine 0,6 grid):** kanopi-altı **%64 BOŞ (4686cm³)** · 110+ tavan yükü yalnız **480cm³** (20 parça) · **110+ delik-kolonları %78 BOŞ (1067cm³)** · tepe sürücüleri kanopi-DIŞI bölgede istif tepelerinde (bobbin_3 93→129 · TAPER 96,6→124,8). Alt bant kanopi-dışı %76 boş.
- **Okuma:** kapasite HER bölgede bol; tepe parçalar erken-yerleşenlerin üstüne istiflenmiş (BLB aday-anı açgözlülüğü + boşluk fragmentasyonu). Toplu söküm/sıra ekseni tükendiğine göre (v17/v18b) sıradaki mekanizma **tekil relokasyon** (v20): tek parça sök → 111 pin'liyken BLB global en-alçak pozu bulur (tek-parça FFT taraması exhaustive'e yakın; ham-pin 1× boşlukla sıkı oturma mümkün) → tek-taraflı kabul.

### [K-62 v20] TAVAN-SIRALI TEKİL RELOKASYON — ✅ GO ŞERHLİ: plan1 127,20 A2-LEGAL (YENİ ŞAMPİYON)
- **Durum:** ✅ GO (şerhli tek-set) — **127,20 A2-LEGAL (clearance 2,447 · kilit5=0 · 112/112)** · **Tarih:** 2026-08-06 akşam · **Kanıt:** `results/k62_v20_relokasyon.json` (D+C) + log
- **Mekanizma (motor değişikliği YOK — v17 ham-pin altyapısı):** tavan-sıralı TEK parça sök → kalan 111 pin'liyken çöz (tek-parça problemde BLB FFT taraması global en-alçak pozu bulur) → tek-taraflı kabul; kabulde tavan yeniden değerlendirilir. Ham-pin fix'i önkoşul: relokasyon pinlere 1× boşlukla oturabiliyor (eski motorda 2× — v16'nın dönemediği cep sınıfı).
- **Ölçüm (taban z=64,8 üçlü snap'sız 129,60; 15 deneme × ~1,4dk):** d1-d2 pyramid geçildi · **d3 TAPER KABUL 129,60→127,20** · d4-d15 (pyramid/bobbin_3/TAPER/811791, üst 115-127 bandı) hepsi geçildi — tepe 5'lisi (3 pyramid + 2 bobbin_3) karşılıklı destekli, tek-parça hamleyle kırılmıyor · B2 settle nötr (tepe parçalar voxel-tabanında) · **final 127,20 LEGAL**. Kapı-129,00'dan −1,8; dünkü otomatik 135,60'tan −8,4; manuel makası 16,8.
- **Okuma:** teşhis-güdümlü (v19: fragmentasyon + istif-tepesi) tekil relokasyon İLK kez sabit-noktayı kırdı. Kalan tepe = çok-parça bağımlılığı → sıradaki eksen çift/üçlü söküm kombinasyonları (v21) veya delik-atama optimizasyonu.
- **Karne (A11):** tetik=çözüm-güdümlü (tavan-sıralı; veri-adı yok) · kapı=BEKLİYOR (mekanizma script-seviyesi; kabloya alınırsa dağılımsal+kapı zorunlu) · sıfır-dokunuş=YAPISAL (motor değişikliği yok; opt-in script zinciri) · sözleşme=DEĞİL · held-out=BEKLİYOR. **ŞERH: tek-set ön-ölçüm.**

### [K-62 v21] Tepe-bandı ÇİFT-relokasyon — ⚪ NÖTR (127,20 kırılamadı; söküm büyüdükçe BLB kalitesi düşüyor)
- **Durum:** ⚪ NÖTR (127,20 A2-LEGAL korundu) · **Tarih:** 2026-08-06 gece · **Kanıt:** `results/k62_v21_cift_relokasyon.json` (D+C) + log
- **Ölçüm:** taban+tekil replay deterministik (129,60 → d3 TAPER → 127,20 ✓) · tepe bandı 124,8+ = 7 parça (3 pyramid + 2 bobbin_3 + TAPER karışımı) · **14 çift kombinasyonu: 10'u 129,60'a ŞİŞTİ, 4'ü 127,20 eşdeğer — hiçbiri kıramadı** · settle nötr · final 127,20 LEGAL (2,447 · kilit5=0).
- **DERS (mekanizma sınırı):** tekil söküm → BLB tek parçada global-optimale yakın (v20 kazancı); İKİ parça söküm → BLB açgözlü sırası ikiliyi birlikte eski kalitede bile koyamıyor (129,60'a şişme). Relokasyon ekseni çoklu-parçada BLB'ye emanet edilemez — 110-bandı için sıradaki adaylar: (a) sökülen küçük-küme için decode-dışı ORTAK arama (2-3 parça poz×konum exhaustive/branch-bound), (b) tepe sürücülerinin poz-analizi (pyramid yatırma sınıfı — tavan yapısal mı?), (c) delik-atama optimizasyonu. Hepsi kod-geliştirme sınıfı (script-seviyesi hamleler tükendi).
- **Karne (A11):** v20 karnesiyle aynı sınıf (tek-set ön-ölçüm; NÖTR kayıt tekrar-önleme değerinde).

### [K-62 v10-MVP] Statik silo planlayıcı (kule-kopya × delik-atama, greedy raster) — ❌ NO-GO (4 tur ölçüldü)
- **Durum:** ❌ NO-GO (2026-08-04 akşam; 4 tur, hepsi ölçüldü) · **Kanıt:** `results/k62_v10_silo.json` (D+C) + `scripts/k62_v10_silo.log`
- **Ne:** v9 teşhisinin (tavan = bobbin delik-sütunları) doğrudan saldırısı: faz-A çözüm-güdümlü silo tipleri → faz-B kanopi delik-maskesinde greedy raster sütun tahsisi (katmanlı 3D pinler, tavan ≤ kanopi-tepe) → faz-C kalan set pin_3d çözümü.
- **Turlar:** T1 156,0/clear 1,77 (kısmi silo delik alanını bloke etti) · T2 136,8/clear 1,92 (margin-0 delik + aşan-önce + L≥2: tahsis tam ama İHLALLİ→geçersiz) · T3 165,6/clear 0,58 (+1 pin-dilation denemesi: kapasite çöktü, ihlal BÜYÜDÜ) · T4 **141,6/clear 2,603 LEGAL-yönlü** (kök-neden fix'li) — yine v9 139,2'nin ÜSTÜNDE.
- **KÖK-NEDEN DERSİ (ihlal serisi):** clearance ihlalleri silo mekaniğinden değil **script pin-koordinat semantiği hatasından**: planner (x,y)'yi halo'lu fp origin'inden verdi, pin sözleşmesi margin-0 bbox origin'i ister → gerçek pin modelden halo·pitch kaydı (ihlal dilation'la büyüdü = kanıt; fix sonrası 2,603). Motor +1 emniyet-dilation'ı GEREKSİZDİ (revert; pin_3d v9 bit-özdeş kaldı — sahada 2,448/2,603 iki bağımsız legal ölçüm).
- **NEDEN NO-GO:** statik ön-tahsis, BLB'nin esnekliğinden KÖTÜ — delik alanını sütunlara kilitleyince tahsis-dışı kalan kule tipleri (811793-1, bobbin_3) kanopi ÜSTÜNE kaçıyor; greedy raster + tip-sıralı atama delik-şekli/tip eşleşmesini ıskalıyor. Silo L≥2 kapasite aritmetiği +halo ile daralınca kısmî tahsis net zarar.
- **Kalan yol (sonraki seans adayları):** (a) **çözüm-İÇİ kule-önceliği** — statik pin yerine decode sıra/anahtar müdahalesi (kule tipleri delik bölgesine önce, esneklik korunur), (b) atama-OPTİMİZASYONLU planner (delik bileşeni × tip × rot eşleme, bipartite/exhaustive küçük arama), (c) v9 139,2'yi kilit ölçümüyle tamamlayıp şerhli en-iyi bandında bırakmak. Plan1 şerhli en-iyi **v4 136,50 KALIR** (v10 turu ihlalli 136,8 sayılmaz).
- **Karne (A11):** tetik=çözüm-güdümlü (faz-A; veri-adı yok) · kapı=YOK (deney) · sıfır-dokunuş=YAPISAL (motor değişikliği revert — net motor diff'i yalnız yorum) · sözleşme=DEĞİL · held-out=N/A.

### [K-62 ön-teşhis] Delikli-parça düz-poz gerçek-geometri no-go fizibilitesi (plan1 baseplate)
- **Durum:** ✅ GO (teşhis; mekanizma kodu YOK) · **Tarih:** 2026-08-03 · **Kanıt:** scratchpad `k62_delik_fizibilite.py` → `results/k62_delik_fizibilite{,_p025}.json` (repo + D) + hoca ekran görüntüleri `Veriler/hoca_ekleri_2026-08-03/`
- **Ne:** Hocanın 110,41 görüntüleri (baseplate DÜZ-KANOPİ, delikler no-go/parça geçiriyor) üzerine A4 koşusuz teşhis: baseplate_v2 footprint'i (XY projeksiyon raster, 0.5/0.25mm) no-go dikdörtgenini (30.1×45.1) tamamen boş bırakan düz yerleşim var mı?
- **Sonuç:** **VAR — bbox kapısı (`_tilt_zorunlu_parca`) YANLIŞ-POZİTİF KANITLI.** Footprint doluluk %26 (çok delikli). 0.25mm'de 4/8 poz uygun (rot0 marj 0.2 + rot180 marj **0.5mm**, ikisinin flip'leri; rot90/270 kapalı — yön-bağımlı delik); en iyi ofset (0.0, 32.8) → part alt kenarı y≈32.8 = **K-56c soft-no-go y-üst=33 bulgusuyla birebir örtüşme** (bağımsız doğrulama). Düz poz kalınlığı 40.64mm (K-56f pin değeriyle aynı); kanopi aritmetiği: 110.41 − 40.64 ≈ 69.8mm kanopi-altı istif.
- **NEDEN:** Kapı parçayı DOLU dikdörtgen sayıyor; delikli çerçevede no-go kolonu delikten/kenar-boşluğundan geçebiliyor — insan yerleşimi (110,41) tam bunu kullanmış.
- **Ders:** Bbox-konservatif fizibilite testleri delikli parçada YÖN saptırır (burada tilt zincirine zorlayıp 140,2'de bıraktı). Düşük-doluluk footprint'te gerçek-geometri testi şart. Marj 0.5mm = no-go'ya NEREDEYSE temas → hoca "ufak girişler kabul" (2026-07-09 c9) ile uyumlu ama üretim kablosunda no-go-temas toleransı sözleşme kararı ister (K-56c/soft-nogo paketiyle aynı aile).
- **Karne (A11):** tetik=geometrik-ADAY (footprint doluluk / delik-testi; kod yok) · kapı=YOK (teşhis) · sıfır-dokunuş=N/A · sözleşme=no-go-temas toleransı HOCA/EREN-BEKLİYOR · held-out=N/A. **ŞERH: tek-set (plan1) teşhisi — K-62 mekanizması kodlanırsa dağılımsal tetik-doğruluğu (k59 deseni: delikli sentetik aile) zorunlu.**
- **GÜNCELLEME 2026-08-04 (Ç2 ÖLÇÜLDÜ — GO, ŞERHLİ): NAİF-KANOPİ 148.50 → SUÇLU-TAŞIMA İTERASYONU 136.50mm (plan1 yeni en-iyi; pin 140.21 GEÇİLDİ).** Kanıt: `results/k62_kanopi_plan1{.json,.log}` + `_v3naif` arşivi (D+C). Mekanizma ölçümü: aşama-1 (111 parça, kanopi-hariç, şampiyon reçete→NFV route) 105.50/6.3dk/pitch 0.5 → replay + düz-drop kanopi z=107.5 → naif 148.50 (clear 2.000) → TELEMETRİ (dolu-altı ort 70.2 ≈ ideal 69.4, p95 105 = birkaç kule suçlu) → suçlu-taşıma (28 yerleşim çıkar → kanopi z=70.5'e indi → kuleler kanopi-sonrası drop) → **136.50, clear 2.018**. Koşu mühendisliği dersleri: (1) aşama-1 ağır nesneleri bellekteyken aşama-2 = OOM-sessiz ölüm (plan7 runner dersinin tekrarı; çözüm 2D-profil replay + gc), (2) detach stderr kaybolabiliyor → FATAL-log kalkanı scripte gömüldü, (3) NFV yolu `orientations` listesini SEYREK tutuyor (None slotlar). **Karne (A11): tetik=geometrik (alan-oran+doluluk+fizibilite; adayı kendisi buldu) · kapı=YOK (deney scripti; üretim kablosu ayrı iş) · sıfır-dokunuş=N/A (üretim yolu çağırmıyor) · sözleşme=no-go-temas + kilit ölçümü BEKLİYOR · held-out=N/A. ŞERHLER: tek-set; kilit/söküm ölçülmedi (kanopi en-üstte, +Z ilk sökülen — düşük risk ama ölçülecek); suçlu-drop taban profili düz-kabul (clearance 2.018 doğruladı); aşama-1 NFV raw height (r11'siz).** Kalan makas 136.5→110.4: taşınan kulelerin yerleşim kalitesi (greedy drop ≠ optimizasyon) + kanopi-altı istifin delik-farkındalı OLMAyışı — sonraki aday: aşama-1'i kanopi-dolu-bölge yumuşak-tavanıyla koşmak + kule-drop'a azimut/konum araması. `src/nesting3d/kanopi.py` — `duz_rot_matrisleri` (kalınlık-ekseni→Z + 4 azimut) + `duz_poz_nogo_fizibilite` (üretim voxelizer'ı `voxelize_part(margin=0)` üstünden gerçek footprint; tek voxelize + np.rot90 azimut türetimi; marj parametresi sözleşmeye açık; `no_go_bounds=None→None` bit-özdeşlik). **Üretim yolu hiçbir yerden ÇAĞIRMIYOR — kablolama ayrı adım.** TDD 9 test (`tests/test_k62_kanopi.py`): sentetik delikli-çerçeve/dolu-plaka ayrımı + marj düşürmesi + **Bin3D mekanizma pinleri: kule delikten geçer · no-go mührü dolu kolonu iter/deliği İTMEZ · `order_key` ile SON gelen çerçeve yığının ÜSTÜNE (kanopi) iner** — kanopi dekodunun üç temel taşı motorda ZATEN varmış, testle sabitlendi. **Gerçek-veri çapraz doğrulama:** çekirdek, bağımsız ön-teşhisi birebir üretti (doluluk 0.2606; rot180 dy=32.5; 10 uygun @0.5mm). SIRADAKİ: kanopi dekod ölçüm scripti (sıra-sonda + düz-kilit; sakin-makine) → dağılımsal (holey_frames) → kablolama+kapı.

> **2026-07-25 — K-56g DUZ-PINLEME URETIM KABLOSU = KOD+TDD TAMAM, SOZLESME-
> KAPILI (kosu/kapi BEKLIYOR — Eren karari "kosuyu simdilik bosver"):**
> K-56f kanitinin (p1 zinciri 302.8->140.21 LEGAL) uretim kablolamasi.
> Mekanizma: (1) `plate_config.resolve_no_go_soft` — "no_go_soft" config
> alani/env; ILAN YOKSA None -> zincir OLU KOD (bit-ozdeslik YAPISAL);
> (2) `targeted_tilt.duz_pin_onerisi` — GEOMETRIK tetik (A11: set adi yok):
> tilt-zorunlu yukseklik-surucu parcanin duz raw pozu x-ortali/y-dayali
> sigarsa + soft sinira giris <= tolerans (=clearance 2.0) ise pin dict;
> (3) demo_pipeline c2f dali + eval_gate._run_champion AYNI karar (parite
> deseni): pin varken tilt havuzu susturulur ({}), pahali tilt taramasi HIC
> kosulmaz; siparis-notu pini/acik parametreler otomatigi HER ZAMAN ezer;
> (4) soft ilan edilince efektif no-go maskesi soft dikdortgen (K-56c).
> Kanit: tests/test_k56g_duz_pin.py 12 test + komsu k56b/k56f 17 + k45/kisit
> kablo 22 = 51 yesil. Karne (A11): tetik=GEOMETRIK | kapi=BEKLIYOR (4-set +
> plan1 kazanc olcumu; sakin makine) | sifir-dokunus=YAPISAL (config'siz olu
> kod) + kapida bit-ozdeslik OLCULECEK | sozlesme=EVET-BEKLIYOR (no_go_soft
> alaninin plate.local.json'a eklenmesi = NOGO 45->33 karari; hoca 2026-07-09
> cevap 3/9 dayanagi var, baseline yenileme + Eren onayi kapida) |
> held-out=BEKLIYOR.

#### [K-25] Clearance ≥1mm üretime bağlama + GERÇEK PLAKA → Deneme4 264mm + çan-driver teşhisi
- **Durum:** ✅ ÜRETİMDE (commit `a274628`, tam suite 2577 passed) · **Tarih:** 2026-07-06 · **Kanıt:** `scripts/clearance_decompose.py`, `scripts/c3_height_driver_deneme4.py`; [[project-oturum-2026-07-06-clearance-264]], [[project-hoca-cevaplari-2026-07-06]]
- **Ne:** Hoca ≥1mm boşluk şartı web NFV-DIŞI yollara bağlandı — `clearance_mm` param (default 0.0 = bit-özdeş; NFV ayrı margin=1) + HIGH-2 post-nest `min_clearance` gate (fail-open uyarı) + M3 graceful margin-cap (kaba-pitch/dar-plaka dilation plakayı aşınca margin kısılır). Hoca mail: plaka **335×335×600 / kenar 5mm → kullanılabilir 325×325**; boşluk 1-2mm; serbest rotasyon; iç-içe izinli ama ayrılabilir (=asıl kısıt).
- **Sonuç:** Deneme4 clearance-1mm GERÇEK plakada (325) = **264mm** (baseline 245.5 +18.5, ölçülen boşluk 1.023 ✅) = Magics 250.24'ün **+%5.5'i ≈ parite**. Önceki 282/329 YANLIŞ auto-plaka (301.6) artefaktıydı. Decomposition: dikey clearance ~BEDAVA (+1mm), maliyet yatay dilation; margin=1 (260) bu plakada 1.019 ama GARANTİSİZ → margin=2 (264) güvenli. **(b) clearance-aware ödülü ≤4mm+güvensiz → DEĞMEZ; (a) dilation doğru.**
- **Height-driver teşhisi:** 264 tavanını TAMAMEN 62 ASY-0176446 çanı belirliyor (bbox 48.8×87.1×131.4, teleskop-zincir, %90 üstünde 9 çan). Düğmeler 236'da tavanlıyor, 2 ROBT plakası yatık/alçak (65/32). → **K-24 asıl kaldıraç; gerçek plakanın büyüklüğü şansını ARTIRDI** (çanları 236 altına yayma imkânı).
- **Ders:** "Daha iyi hissi" ölçüm çerçevesi eksikken YANILTICI (282/329 = config+plaka artefaktı). Kaba-pitch'te voxel-dilation clearance'ı temsil EDEMEZ (over-provision → küçük parça plakayı aşar) → M3 cap + gate şart. Gerçek plaka + clearance = dürüst metriğin temeli; her kıyastan önce plaka+clearance paritesi doğrulanmalı.

#### [EVAL-1] Eval-kapısı ilk koşusu — NFV kalite modu PLAN ailesinde de A2-İLLEGAL (ölçüldü)
- **Durum:** 🔴 BULGU (üretim değişikliği yok; NFV opt-in şampiyonluktan düşürüldü) · **Tarih:** 2026-07-06 · **Kanıt:** `scripts/eval_gate.py` ilk koşu logu
- **Ne:** STRATEJI Faz-0 kapısı dev-set'leri dürüst metrikle (legal_height: yerleşen==N ∧ clearance≥1mm ∧ 0 kilit) ilk kez ölçtü; planların şampiyonu olarak önce NFV kalite modu (üretim opt-in defaults: `solve_nfv` margin=1, adaptif pitch, fine_settle) denendi.
- **Sonuç:** plan1 **INVALID** (ham 120.7mm ama clearance **0.083mm** + **81 kilit**), plan3 **INVALID** (clearance 0.055 + **87 kilit**), plan2 NFV koşusu OOM (989MB FFT alloc). deneme4 heightmap 264.0/1.022/0 ✓ (2 bağımsız koşuda birebir).
- **NEDEN önemli:** (1) HIGH-3 (NFV margin=1'in ince pitch'te <1mm kalması) artık ölçülü gerçek; (2) K-21'in kabuk bulgusu ("NFV kazancının özü kapalı-kaviteye gömme = kilit") PLAN ailesinde de doğrulandı — ünlü ~%20-28 NFV kazançları dürüst metrikten GEÇEMİYOR (şerh: F2 +Z-çekme konservatif — kilit "sökülemez kanıtlandı" değil "sökülebilir kanıtlanamadı" demek; hoca döndürerek ayırmaya izin veriyorsa bir kısmı kurtulabilir). (3) Kapı ilk koşusunda bozuk baseline kilitlemeyi reddetti — çerçeve tasarlandığı gibi çalışıyor.
- **Aksiyon:** eval_gate şampiyonu = üretim DEFAULT'u (heightmap `clearance_mm=1.0`); NFV modu ancak legalleşme işi (F2-v2 + NFV-clearance kablosu, §5) kapıdan geçince şampiyon adayı. Plan NFV kazançlarını kurtarma işi = F2-v2'nin değer gerekçesi GÜÇLENDİ.
- **Ders:** "Dürüst metrik" tek sette değil TÜM yüzeyde uygulanınca tarihî kazançlar da yeniden yargılanır — kahraman sayılar (556, 522...) clearance+kilit şartıyla yeniden ölçülmeden kıyas tablosuna giremez (A2+A10).
- **KÖK NEDEN (aynı gece bulundu — `scripts/nfv_legal_teshis.py` + kod):** ihlal pitch- ve settle-BAĞIMSIZ (settleOFF@2.54 da 0.083; worst-pair hep iç-içe TAPER kamaları) → suçlu fine_settle DEĞİL. Mekanizma: `voxelize._dilate` bilinçli x/y-only; dikey boşluk Bin3D.z_clearance'ın işi ama **NFV yolu Bin3D drop'undan geçmiyor** — FFT fizibilitesi saf sıfır-çakışma + replay tam (x,y,z) → **NFV'de dikey clearance mekanizması HİÇ YOK**, z-bitişik voxel'lerde yüzeyler ~0mm'e iner. Kilit tablosu tutarlı: 81 parça TEK kenetli grup (=milimetre-altı boşluklu yığın); gerçek 1mm açılınca çoğu çözülebilir (hipotez, fix sonrası ölçülecek). Ayrıca margin=2 NFV `_drop_fallback` None → TypeError (fallback dilated-büyük parçayı sığdıramayınca çöküyor; fix kapsamında ele alınmalı). **FIX reçetesi:** NFV yoluna `clearance_mm` param (default 0.0 = bit-özdeş) → margin_xy=ceil(c/pitch) + grid'lere TEK-TARAFLI z-dilation (üst; taban etkilenmez) aynı voxel sayısıyla; fine_settle_raw aynı kurala uyar; plan1 probu ≥1mm + kilit yeniden ölçümü + kapı koşusu.

#### [K-24] Kasıtlı zincir-ekimi/dengeli-routing — ❌ KESİN NO-GO (Adım-2 replay ile; 264 = gerçek-plaka yapısal tavanı KANITLI)
- **Durum:** ❌ NO-GO (2026-07-06; Adım-1 teşhis + Adım-2 çift-yöntem decode-replay) · **Kanıt:** `scripts/k24_on_analiz.py` + `scripts/k24_on_analiz2.py` + `scripts/k24_adim2_prototip.py` (+logları; builder-agent, opus); yerleşimler `data/mail_stl/k24_placements_325_264.pkl` (izlenmiyor, 59MB)
- **Bulgu 1 (264 layout zincir yapısı):** 62 ASY → **13 kök** (325 plakada; 301.6'da 10'du), dağılım yine uçurum: 36-halkalı tek kule 264'ü kuruyor, 7 çan tabanda TEK (87.5), z-adım medyan **11.2mm**. 12 kök taban z=0'da → **plaka o anda 13 kök açabilmiş.**
- **Bulgu 2 (post-hoc kapasite = 0, İKİ yöntemle):** 62 ASY söküldükten sonra kalan 526 parçanın yüzeyinde ASY tabanı için yer YOK — v1 bbox-pencere-max (fazla muhafazakâr, yanal iç-içe komşuları blokaj sayar) VE v2 GERÇEK drop-semantiği (kolon-tepe + alt-profil, üretim formülü) ikisi de 0 site (min-drop 205-223mm). Mekanizma: düğmeler zincirlerin ÜSTÜNE oturmuş; ASY çıkınca kolonları "havada" kalıyor, drop altına giremiyor. **K-22 dersinin teyidi: heightmap'te post-hoc site analizi/onarımı yapısal imkânsız — kapasite ancak SIRA-İÇİ anda var.**
- **Bulgu 3 (asıl fırsat — analitik):** ASY bloğu anında (sıra 2..63, plakada yalnız 2 ROBT) 13 kök doğal açıldı; greedy dengesiz yığdı (36-kule). 13 köke dengeli dağıtım: ceil(62/13)=5 halka → ASY tavanı ~0+87.5+4×11.2 ≈ **132mm** → bin tavanı **düğme-güdümlü ~236mm**. **Ödül ~28mm (264→~236, −%10.6) = Magics 250.24 ALTI.** Spekülatif kalan: dengeli routing'de teleskop-ofset XY'si komşu köklerce bloke olabilir (greedy'nin dengesizliğinin kök sebebi bu olabilir — Adım-2 ölçer).
- **Adım-2 SONUÇ (aynı gün, 4 tam replay — üretim decode BİREBİR, yalnız ASY `_best_position` monkeypatch):**
  | konfig | tavan | clearance | kilit |
  |---|---|---|---|
  | (a) window rr13 R=±12 | **925.0** | — | — |
  | (a) window rr13 R=±25 | **637.0** | 1.019 | 0 |
  | (b) penalty λ=0.5 (tam XY + `eff=z_top+λ·z_drop`) | **264.0** | 1.023 | 0 |
  | (b) penalty λ=2.0 | **264.0** | 1.023 | 0 |
- **ÇARPICI:** (b) dengelemeyi GERÇEKTEN başardı — 36-kule kayboldu, 13 site × 4-5 halka, site-tepeleri 228-264 — ama bin tavanı **birebir 264.0** (λ'dan bağımsız aynı layout'a doyuyor). Yani dengesizlik SEBEP değil SEMPTOMDU.
- **NEDEN olmadı:** (a) sabit XY penceresi greedy'nin dayandığı yanal kavite-nesting'i (F4-A %96) öldürüyor → z-adım 11.2→~137mm, kutu-istif felaketi. (b) alçak-alan (taban + düğme-altı nest yuvaları) DOYUNCA taşan çanların ulaşabileceği minimum tepe her hâlükârda ~264 — dengeleme yalnız diğer zincirleri alçalttı, zorunlu-yüksek çanı İNDİREMEDİ. **Adım-1 Bulgu-3'ün analitik "~236, ödül ~28mm" tahmini ÇÜRÜDÜ** (11.2mm z-adımının yayılınca korunacağı varsayımı yanlıştı). K-23'ün "tavanı ASY bloğu tek başına kuruyor" hükmü artık analitik değil **decode-replay ile kanıtlı**.
- **Ders:** (1) 264 = gerçek plakada (325) drop/heightmap semantiğinin YAPISAL kabuk tavanı — 282'nin (301.6-plaka) birebir devamı; kalan ödül yalnız A1 (sürekli rotasyon/süper-bilgisayar) veya semantik değişikliği. (2) Analitik denge hesapları (su-doldurma) nesting z-adımını sabit varsayar — kabuk ailesinde bu varsayım replay'siz GÜVENİLMEZ; ölç-önce'nin sınırı: analitik teşhis YÖN verir, hüküm replay ister. (3) Süreç: riskli deneysel lane'de builder-agent + opus override + süre bütçeli eskalasyon iyi çalıştı (~2 saat, 4 legal E2E replay).
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-22 · **Kanıt:** `scripts/m1_*.py`, commit `4c85cf1`, [[project-kiyas-iyilestirme]]
- **Ne:** `OccupancyBin3D`'ye occupancy-komşu boş voxel adayları (oyuk duvar/taban tohumları) + drop fallback.
- **Sonuç:** Sentetik Π-oyukta cavity'ye soktu (5 vs bbox 7 = mekanizma çalışıyor) AMA gerçekte KÖTÜ: numune heightmap 180 / cavity 218; Plan2 740 / cavity 802.
- **NEDEN olmadı:** zarar parça-taşmasından değil — açgözlü "en-derine" seçimi YÜZEY PARÇALIYOR; gelecekteki parçaların boşluğu kullanmasını engelliyor = **greedy miyopi**. NFV-lite (occupancy-komşu) gerçek geometrik free-space değil.
- **Ders:** Greedy constructive cavity tek başına yetmez; literatür doğru (NFV + metaheuristik şart).

#### [K-02] M2-M6 — Cavity-constructive ailesi (order-SA / seçim-kuralı / beam / hibrit)
- **Durum:** ❌❌ KESİN NO-GO (5 bağımsız deney) · **Tarih:** 2026-06-22 · **Kanıt:** `scripts/m{2..6}_*.py`
- **Ne:** M2 order-SA, M3 seçim kuralı (deepest/blb/max-contact), M4 beam (B=1/3/5/8), M5 hibrit (cavity-EP∪drop), M6 gerçek Plan2 hibrit.
- **Sonuç:** M2-M4 hepsi testbed'de tam 300 (kural/sıra/lookahead fark etmedi); M5 testbed 216=heightmap; M6 Plan2 802 = heightmap'ten kötü.
- **NEDEN olmadı:** Hepsi aynı duvar — tek-geçiş/lokal-arama constructive cavity ÇIKMAZ. Miyopi GERÇEK (eksik-aday değil): cavity-dolgu anlık yükseklik artırmasa da gelecekteki boşluk kullanımını bloke ediyor.
- **Ders:** Cavity = gerçek geometrik NFV (Minkowski no-fit-voxel) + global metaheuristikten EMERGENT; ÖZEL kod değil. Aday-üretimi bbox-köşe olduğu sürece cavity emerge etmez.

#### [K-03] bbox-EP (extreme-point packer)
- **Durum:** ❌ NO-GO (üretimi geçmiyor) · **Tarih:** 2026-06-22 · **Kanıt:** `scripts/m1_bbox_validate.py`
- **Ne:** 3B-çarpışmalı extreme-point packer, bbox-köşe adayları.
- **Sonuç:** naive heightmap-DBLF'i %7-8 geçti AMA üretim (coarse-to-fine+SA, 621) zaten daha iyi. Plato 667-672 (1.07-1.08× of 621).
- **NEDEN olmadı:** aday üretimi bbox-köşe (kutu-odaklı) → gerçek oyuğu hedefleyemiyor. Tek değeri ~2sn'de hızlı seed.

#### [K-04] ⭐ C3 — Gerçek geometrik NFV (FFT korelasyon) — ANA KAZANÇ
- **Durum:** ✅ GO (ÜRETİME BAĞLI, opt-in) · **Tarih:** 2026-06-22 · **Kanıt:** `scripts/c3_*.py`, commit `c9f00fe`+`b09512e`, `ANALIZ_NFV §1`
- **Ne:** Tüm feasible uzayı FFT korelasyonuyla bul (`fftconvolve(O, P[::-1,::-1,::-1],'valid')<0.5`), en düşük z'de BLB yerleştir. Faz0 oracle %100 doğruladı.
- **Sonuç:** Plan2 TEK geçişte 556mm (heightmap 740'ı %25 geçti); katı-bbox tabanı 586'NIN ALTINDA = gerçekten oyuğa girdi (cavity'nin matematiksel kanıtı). 4 veride %9-25, regresyon yok.
- **NEDEN oldu:** Gerçek geometrik NFV TÜM feasible uzayda BLB seçtiğinden top-drop'tan yapısal güçlü (cavity üstüne EKSTRA). M1-M6'nın NFV-LİTE'ından farkı: gerçek Minkowski, occupancy-komşu değil.
- **Ders:** Doğru testbed Plan2 (cavity-zengin); numune (kutuluk 0.35) YANILTIR. Metaheuristik gereksiz (greedy 556 zaten iyi, SA 556→556).

#### [K-05] NFV oryantasyon n=8 default
- **Durum:** ✅ GO (üretimde) · **Tarih:** 2026-06-24 · **Kanıt:** `scripts/c3_quality_levers.py`, commit `ae306c3`
- **Ne:** NFV oryantasyon sayısı n=4→8 (tüm eksen-hizalı yüzler).
- **Sonuç:** Plan2 +%6.1 (556→522), Plan1 +%3.8. n=12 sadece +%1.1 ama 3× yavaş. Magics açığı %13→%6.
- **NEDEN oldu:** n=4 ⊂ n=8 küme-içerme → NFV greedy n=8'de her veride ≥ n=4 (overfit DEĞİL, set teorisi). 4→8 sweet spot.
- **Ders:** "Sabit-değil-ama-sabit": matematiksel garanti varsa sabit sayı meşru. `quality="max"` RAM-tavanı (8→12→28).

#### [K-06] NFV pitch adaptif (`suggest_nfv_pitch`)
- **Durum:** ✅ GO (üretimde) · **Tarih:** 2026-06-23 · **Kanıt:** commit `2d8a5da`+`a26d180`+`621936c`, [[project-nfv-sonraki-oturum-backlog]] #1
- **Ne:** NFV-pitch = parçayı-kaybetmeyen EN KABA güvenli pitch (güvenli oran 1.0'dan başla → bellek için adaptif kabalaştır → sığmazsa heightmap) + bellek pre-flight + plaka-oranı guard.
- **Sonuç:** Plan2 0.5mm/~5h/OOM → 2.0mm/112s/556mm. plan1/2/3/boxy hiçbiri çökmüyor.
- **NEDEN oldu:** NFV'de kalite pitch-duyarsız + maliyet kübik → kaba=hızlı+az bellek+kalite~korunur (suggest_pitch'in TERSİ yön). İlk hali (tek-oran 0.5) Plan2-overfit'ti, Plan1'i çökertiyordu → cross-dataset düzeltti.
- **Ders:** Tek-veri optimizasyonu overfit; her parametre cross-dataset doğrulanmalı.

#### [K-07] İnce-açı refinement (0.5-1° sürekli rotasyon, hocanın isteği)
- **Durum:** 🟡 KISMİ (ham NO-GO, güvenli-modda nötr) · **Tarih:** 2026-06-22 · **Kanıt:** `coarse_to_fine.py`, commit `0ac9e4b`
- **Ne:** Kazanan ayrık pozun ±window° çevresinde 1° adımlı yeniden voxelize.
- **Sonuç:** Ham greedy refinement Plan1'i BOZDU (117→136.5, 4× yavaş). Güvenli mod (açısız+açılı üret, iyiyi seç) zarar vermez ama kazanç da marjinal.
- **NEDEN olmadı (6GB'de):** Yerel z_top iyileştirme ≠ global yükseklik (döndürülen parça footprint büyütüp sonrakileri yukarı itiyor). Diskret eksen zaten doygun. → asıl sürekli rotasyon süper bilgisayar işi (bkz §5 phi-function).

#### [K-08] Sıra metaheuristiği (multi-start / SA / ALNS)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-24 · **Kanıt:** `c3_quality_levers.py`, `ANALIZ_NFV §6`
- **Ne:** Yerleştirme sırasını SA/jitter/ALNS ile ara.
- **Sonuç:** jitter sıraları birebir 556; SA 556→556. TAM SIFIR kazanç.
- **NEDEN olmadı:** largest-first (hacim-azalan) zaten optimal sıra. NFV greedy sıraya duyarsız.

#### [K-09] Adaptif DBLF-prob (oryantasyon getirisini tahmin)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-24 · **Kanıt:** commit `d835458`
- **Ne:** Heightmap-DBLF trail ile n-oryantasyon getirisini ucuz tahmin et.
- **Sonuç:** DBLF n-getiriyi TERS tahmin etti (Plan2 trail n=4<n=8 dedi ama NFV'de n=8 İYİ) + 919s yavaş.
- **NEDEN olmadı:** Heightmap-DBLF NFV-cavity davranışını temsil etmiyor.

#### [K-10] Yerleştirme tie-break (max-support / "free void fill")
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-25 · **Kanıt:** `scripts/c3_tiebreak.py`, `ANALIZ_NFV §6`, commit `c70a276`
- **Ne:** Eşit-skorlu pozisyonlar arasında köşe yerine en-çok-alttan-destekli (max-support) seç.
- **Sonuç:** Plan2 baz 522 = support 522 = **%0.0 TAM SIFIR**.
- **NEDEN olmadı:** tie-break yalnız (x,y) seçer; zstar (yükseklik) her modda sabit. Plan2 cavity-zengin → x,y dağılımı yüksekliği değiştirmiyor.

#### [K-11] Global compaction (top-K eject + best-fit repack)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_compaction.py`, `ANALIZ_NFV §7`, commit `ef45769`
- **Ne:** Layout sonrası tavan parçalarını söküp daha iyi boşluğa repack et (literatür A2/CGF).
- **Sonuç:** largest-first K=all=522 birebir (sanity); best-fit K=2/5=+0.0%, K=10=-60.9% (kötüleşme).
- **NEDEN olmadı:** **Monotoniklik teoremi** (kod-öncesi): parça yerleşince occ yalnız büyür → tek-parça eject (occ daha dolu) z+fh ASLA düşmez. Tavanı düşürmek = altındaki kolonu da eject + global reorder = ZATEN ÖLÜ (K-08). CGF'in sürekli-pozisyon push'u diskret+BLB (zaten bottom-most) dünyamızda karşılıksız.
- **Ders:** Kod-öncesi teorem kurmak K=2/5'in neden 0 çıktığını önceden açıkladı.

#### [K-12] NFV numune doğrulaması (cavity-fakir veride davranış)
- **Durum:** ❌ NO-GO (kazanç yok — beklenen) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_numune_nfv.py`
- **Ne:** Gerçek FFT-NFV'yi hocanın İLK numune verisinde (kutuluk ~0.35, cavity-fakir) çalıştır; eski eğik-plaka SA rekoru 181.5mm ile kıyas. (NFV daha önce yalnız cavity-zengin Plan2/3'te test edilmişti.)
- **Sonuç:** NFV n=8 = **180.0mm = heightmap (180.0) ile BİREBİR** (kazanç %0.0); NFV+eğik oryantasyon 186 (daha kötü). Rekor 181.5 ile "%0.8 daha iyi" görünür ama YANILTICI (180 zaten heightmap'in değeri; 181.5 farklı kurulum = ince pitch+SA+eğik plaka).
- **NEDEN olmadı:** Numune cavity-fakir → NFV'nin tek avantajı (oyuğa girme) yok. Plan2(0.07)=%29, Plan3(0.30)=%20, Plan1(0.44)=%14, numune(0.35)=%0 → kazanç kutuluk/oyukla orantılı.
- **Ders:** Meta-ders #3'ü (numune YANILTIR) gerçek FFT-NFV ile de doğruladı + NFV'nin OVERFIT OLMADIĞINI kanıtladı (cavity yoksa sahte iyileşme uydurmuyor). Eski NFV-LİTE numune'de 218 idi; gerçek NFV 180'e çekti (heightmap seviyesi).

#### [K-13] Sürekli SERBEST rotasyon (greedy menüsüne off-axis ekle)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_continuous_rot.py`, `scratch_crot_plan2*.log`
- **Ne:** n=8 baz + sürekli off-axis eğik pozlar (tilt 20/40 × azimuth × spin = 24 poz) greedy decode menüsüne eklendi; küme-içerme (set ⊇ n=8) ile "asla baz'dan kötü olamaz" beklendi.
- **Sonuç:** Plan2 C24 = **550 > baz 522 (−%5.4 KÖTÜ)**. A24 kontrol (24 eksen-hizalı) = 520 (≈baz → diskret doygun, K-05 yine doğrulandı).
- **NEDEN olmadı:** Küme-içerme garantisi greedy'de TUTMADI — greedy bir eğik pozu miyopça kapıp o parçanın z'sini düşürüyor ama footprint büyütüp sonraki parçaları yukarı itiyor (K-07 + M1-M6 miyopi tekrarı). Rotasyon parça-i için çok erken/izole kilitleniyor.
- **Ders:** Greedy decode sürekli rotasyondan FAYDALANAMAZ, zarar görür. Rotasyon ancak GLOBAL (eşzamanlı açı+pozisyon) optimizasyonla kullanılır → A1.

#### [K-14] Koordineli ortak-tilt "rack" + height-driver teşhisi
- **Durum:** ❌ NO-GO (Plan2) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_coord_tilt.py` + `scripts/c3_height_driver.py`, `scratch_coord_plan2.log`
- **Ne:** "Ekmek rafı" hipotezi — greedy serbest seçmesin diye uzun/rack-uygun parçalar (en-boy≥2 VE ≤0.6·plaka, GEOMETRİ-türevli) PAYLAŞILAN tek tilt açısına zorlandı; açı 90/75/60/45/30° tarandı. Sonra height-driver teşhisi.
- **Sonuç:** 5 açının TÜMÜ = **522.0 birebir (%0.0)**. Fallback değil (8/8 rack parça 4/4 voxelize). Teşhis: tavanı (522) **~20 BÜYÜK LEVHA** belirliyor — P282335 (77×147×**300**)×5 + kardeşler P282334/336/337 + P155308 (178×299×**356**)×1; rack-uygun küçük parçalar HİÇ tavan değil.
- **NEDEN olmadı:** Plan2 yükseklik darboğazı = düz yatamayan büyük levhalar (P282335 footprint 44.100mm², plakaya 2 sığar → ~20 levha ≈ 8 plaka-alanı → İSTİFLENMEK ZORUNDA). Bunlar rack-uygun değil (çok büyük); koordinasyon YANLIŞ parçalara uygulandı çünkü DOĞRU parçalar (büyük benzersiz levhalar) koordine-edilebilir tipte değil.
- **Ders:** Plan2'de "rotasyonla iyileştirme" = bu ~20 büyük levhayı optimal istiflemek = global sürekli-açı eşzamanlı paketleme = A1. Magics 492 (%6) tam bunu yapıyor (levhaları %6 daha sıkı). **Darboğazı ÖLÇ (height-driver) stratejiyi uygulamadan ÖNCE** — coord-tilt yanlış parçalara harcandı.

#### [K-15] Numune height-driver — rotasyonun küçük-N'de de yanlış kaldıraç olduğu
- **Durum:** ❌ NO-GO (rotasyon, teşhisle) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_height_driver_numune.py`
- **Ne:** SA-sürekli-rotasyonu numune'de (8 tip, hedef 170mm, A1 küçük-N testbed adayı) koşmadan ÖNCE meta-ders #11: tavanı (180) NE belirliyor? Baz n=8 decode + tepe-z ölçümü.
- **Sonuç:** Tavan (180) = **ince büyük plakalar** (n3 15×178×228 oran 15.2 tepe-180; n7/n6/n8 benzer ~15-19mm kalın, 180-230mm geniş). Plan2'den FARKLI darboğaz tipi ama yine rotasyon-kapalı.
- **NEDEN olmadı:** İnce plakalar düz yatıyor = **zaten minimum yükseklik** (15mm). Eğmek yüksekliği ARTIRIR (eski eğik-SA 181.5 > düz 180 = tam bunun kanıtı). Bread-rack uzun-dik parçayı yatırınca kazandırır; numune plakaları zaten yatık → rack tersine çalışır.
- **Ders:** Her iki gerçek darboğaz da rotasyona kapalı: Plan2=düz-yatamayan-büyük-levha (istif zorunlu), numune=düz-zaten-optimal-ince-plaka (eğmek uzatır). SA-sürekli-rotasyon koşulmadı çünkü ölçüm "eğik-SA tekrarı" diyor (meta-ders #11 saatlerce SA'dan korudu). Numune 170 hedefi rotasyonla DEĞİL farklı kaldıraçla (placement/interleave) — VEYA 180 ≈ düz-istif-optimal kabul.

#### [K-16] Akıllı otomatik mod seçimi (NFV/heightmap — `predict_nfv_benefit`)
- **Durum:** ✅ GO (ÜRETİMDE, **default auto**) · **Tarih:** 2026-06-27 · **Kanıt:** `src/nesting3d/adaptive_params.py::predict_nfv_benefit`, `scripts/automode_proof.py`, `tests/test_adaptive_params.py`, commit `c89041c`, `RESUME_2026-06-27`
- **Ne:** Instance'tan veri-odaklı NFV/heightmap kararı (voxelize'sız, `extract_features` bbox'tan). VARSAYILAN NFV; heightmap SADECE net-kutu (`mean_aspect_z<4`) VEYA ince-plaka-dominant (`thin_plate_ratio>0.6`). run_pipeline `nesting_mode="auto"` default; UI 3'lü radio.
- **Sonuç:** 5 veride **false-negative=0** (plan1/2/3→nfv [kazanç 14/20/29%], numune/boxy→heightmap [%0]); tam suite **2078 passed** (default heightmap→auto regresyon YOK — kutu fixture auto→heightmap birebir).
- **NEDEN oldu:** Kalite-riski ASİMETRİK: NFV yanlış-pozitif = sadece hız (NFV≥heightmap, K-12 kalite-güvenli); heightmap yanlış-negatif (cavity→heightmap) = %14-29 kalite kaybı → ŞÜPHEDE NFV → false-negative sıfır. Ayrıştırıcı `mean_aspect_z` ORTA-bant (6-13): düşük=kutu (cavity yok), çok-yüksek=ince-plaka (düz-optimal, K-14/K-15) → ikisi de kazanmaz.
- **Ders:** Açıklanabilir-kural (mekanizma-türevli eşik + geniş marj) az-veride (5) ML'den sağlam (overfit yok). "Kalite düşmesin" şartı YAPISAL karşılanır: heightmap yalnız NFV'nin zaten kazanmadığı durumda. İleride telemetri→selection/ ML hook.

#### [K-17] Pozisyon-koruyan FINE z-kompaksiyon (kuantizasyon vergisi tahsilatı)
- **Durum:** ✅ GO (**ÜRETİMDE** — `solve_nfv fine_settle=True` default-on, commit `07f697b`; kalite tek-taraflı guard'lı: iyileşmezse/bellek yetmezse coarse aynen korunur; `src/nesting3d/fine_settle.py` + 7 test, tam suite 2238) · **Tarih:** 2026-07-03 · **Kanıt:** `scripts/c1_fine_zcompact.py`
- **Ne:** NFV @2.0mm kazanan layout'un pozisyonları korunarak kullanılan (tip,oi)'ler 0.5mm'de yeniden voxelize edilir (margin mm-eşdeğer: 1 hücre@2.0 = 4 hücre@0.5); parçalar önce ORİJİNAL z'lerine konur (alçaltma YOK), sonra settle döngüsü herkes yerleşikken teması bulana kadar oturtur + sığmayana hücre-içi xy-jitter + tavana-yakına jitter-alçaltma. FFT YOK → H-11 bellek duvarına takılmaz (~500MB); H-14 sonrası fine voxelize ekonomik (sipariş başına ~1-2dk + settle saniyeler).
- **Sonuç:** Plan3 844→830.5 (**+%1.6**) · Plan2 522→516 (**+%1.1**, Magics açığı %6.1→%4.9) · Plan1 116→115.5 (+%0.4). Üçü de ≥0; kazanç cavity/istif yoğunluğuyla orantılı (mekanizma-tutarlı, overfit değil). Plan2 fine tavanı = P282335 istifi TAM TEMASTA → kalan açık levha geometrisinin kendisi (rotasyon = A1, K-14 doğrulandı).
- **NEDEN oldu:** 2.0mm hücre kuantizasyonu her istif arayüzünde (a) bir-sonraki-2mm-sınırına yuvarlama + (b) konservatif yüzey-sarmanın ~1 hücrelik şişirmesini biriktirir; fine'da oturtmak bu vergiyi geri alır. K-11 monotoniklik teoremiyle ÇELİŞMEZ (parça sökülmüyor; aynı yerleşim ince ölçekte oturtuluyor).
- **Ders:** (1) İlk sürüm min-z sırasında ANINDA alçaltıyordu → oyuk-zengin plan3'te iç-içe parçalarda (per-kolon komşuluk ≠ min-z sırası) önce işlenen parça henüz yerleşmemiş komşunun yerine düştü (-123mm!). Yerleştir-VE-oturt ayrımı şart: alçaltma yalnız herkes yerleşikken. Cross-dataset kapısı bu hatayı yakaladı (meta-ders #2'nin en sert örneği: plan1/plan2 pozititken plan3 çökmüştü). (2) Fine örnekleme coarse'un kaçırdığı yüzeyi işaretleyebilir → "fine ⊆ coarse" varsayımı mm-uzayda garantili DEĞİL; jitter-fix gerekli.

#### [K-18] n=24 eksen-hizalı oryantasyon (AX24) + K-17 settle kombinasyonu
- **Durum:** ✅ GO (**ÜRETİMDE** — `quality="max"` = AX24, commit `f44ee80`; cross-dataset 3/3) · **Tarih:** 2026-07-03 · **Kanıt:** `scripts/c1_fine_zcompact.py <ds> 0.5 n24 [prod]`
- **Ne:** NFV decode master pozların 24 eksen-hizalısıyla (0..7 + 12..27, Ry ailesi dahil; eğik 8..11 HARİÇ — K-13 miyopi) + üstüne K-17 settle. Sanity: plan2 n=24 baz 520.0 = K-13 A24 kontrolüyle BİREBİR; plan1 n=8 prod-decode (gpu-resident) 116.0 = CPU probe BİREBİR (H-04 invariant yeniden doğrulandı, decode 616→45s = 13.6×).
- **Sonuç (n8 baz → n24+settle):** plan1 **116.0→108.0 (−%6.9)** · plan2 **522.0→512.5 (−%1.8**, Magics açığı %6.1→**%4.2)** · plan3 **844.0→755.5 (−%10.5!)**. n8+settle'a karşı da 3/3 kazançlı (−7.5 / −3.5 / **−75.0**). Ayrışım veri-tipine göre değişiyor: plan2 settle-baskın (−7.5 settle), plan1 poz-baskın (−8 poz, settle 0), plan3 İKİSİ BİRDEN (−64 poz + −24.5 settle; 100/109 parça ort 14.3mm alçaldı) → iki kaldıraç TAMAMLAYICI, overfit değil.
- **NEDEN:** Küme-içerme (8⊂24) + Ry ailesi bazı parçalara (bobin, 171600003) n=8'de OLMAYAN en-basık duruşu açıyor; settle'ın kuantizasyon vergisi pozdan bağımsız tahsil ediliyor. n=24 layout'u daha sıkı istiflendiğinden settle'a daha çok vergi bırakıyor (plan3).
- **Bedel:** decode ~3-4× (yalnız opt-in quality=max; GPU-resident'ta plan1 45s / plan3 ~25dk). RAM<13GB → n=8 güvenli taban.
- **Ders:** K-05'in "8→12 sadece +%1.1" ölçümü eğik-pozlu ilk-12 setiyleydi; doğru genişletme EKSEN-HİZALI aile (Ry) imiş — poz seti seçerken "kaç poz" değil "HANGİ pozlar" sorusu belirleyici.

#### [K-19] Cidar-duyarlı ORTAK pitch (kabuk ailesinde min_feature = 2V/A)
- **Durum:** ✅ GO (probe — üretime BAĞLANMADI; bağlama = aile-genelleştirme programı F3, ayrı sprint) · **Tarih:** 2026-07-04 · **Kanıt:** `scripts/k19_cidar_pitch_olcum.py` (Deneme4 offline repro + monkeypatch, opt-in)
- **Ne:** Heightmap yolu, tek ORTAK pitch. `pitch.min_feature_mm` yaması: parça "cidar tahmini" = 2V/A (yalnız watertight + fill<0.5 kabuklarda; aksi bbox-min) → Deneme4 min_feature 7.26→0.81 → pitch 2.9 yerine **0.5mm**. **H-06 (per-part pitch) ihlali DEĞİL** — pitch yine herkes için tek; yalnız türetim kuralı cidar-duyarlı.
- **Sonuç (Deneme4, 588 parça, auto-plaka):** **282.0mm / 7865s (131 dk) / tepe RAM 0.80GB** · density 0.156. Kıyas: heightmap@2.9 377.3 (**−%25.3**) · NFV-max@kaba 386.4 (−%27.0) · **Magics 250.24 açığı ~%54 → %12.7**. Tek deneyde şimdiye dek ölçülen EN BÜYÜK kalite sıçraması.
- **NEDEN oldu:** İnce cidarlı kabuk (0.8-1.35mm) kaba voxel'de katı-blok şişer (`9d99553` boş-grid guard yan etkisi, R3 #25) → iç içe geçme/bardak-istifi imkânsızlaşır. 0.5mm'de kabuklar çözünür → çanlar birbirine oturur. Mekanizma-tutarlı: kazanç yüksekliğin kabuk-istif payıyla orantılı.
- **Bedel/risk:** 131 dk/koşu (tek sipariş!) → zaman bütçesi (#22) + F4-B identical-part fast-path ŞART; RAM 0.8GB (heightmap FFT'siz, H-11 duvarı yok). **Cross-dataset HENÜZ YOK** (yalnız Deneme4). Üretime bağlama tetiği kritik: neredeyse TÜM gerçek parçalar kabuk çıkıyor (plan1 pitch 1.02→0.61, plan3 1.00→0.55 olurdu) → tetik `family∈{thin_shell,tube}` + süre/RAM ön-kapıları + eski setlerde ≤%1 regresyon kapısı olmadan bağlanamaz (süre patlaması riski).
- **Ders:** (1) Aile-tanıma olmadan bu kaldıraç kördü — "pitch'i geometri belirlesin" ilkesi kabukta bbox-min değil CİDAR ister. (2) K-12 ("NFV≥heightmap") kabuk ailesinde kaba pitch'te kırılmıştı; kök neden pitch'miş — doğru pitch'te heightmap bile 282'ye indi. NFV@fine kombinasyonu (F3+K-18) ayrı ölçüm ister.
- **v2 TEKRAR + LEGALLİK (2026-07-04):** 282.0mm **BİREBİR** yeniden üretildi (116.4 dk — RAM rahatken; hacim-doluluk %12.9). **Erişilebilirlik: 588/588 parça +Z sökülebilir, 0 kilit** (F2 denetimi, 0.9s) — K-19 istifi TAMAMEN LEGAL/üretilebilir; NFV-max'ın 386.4'ü ise 506/588 kilitliydi (@1.25). Yani Magics kıyasında 282.0 dürüst sayı; "heightmap kapalı-kaviteye parça sokamaz → kilitsiz" mekanizma öngörüsü doğrulandı. Yerleşimler kalıcı kopyada (`data/mail_stl/k19v2_placements_B001.pkl`).
- **⚠️ CLEARANCE DÜZELTMESİ (2026-07-06) — 282 ≠ üretilebilir sayı:** K-19 heightmap yolu `margin=0` ile koşuyordu → parça-arası **min 0.084mm** (ölçüm `clearance.min_clearance`), hocanın **1mm** şartını (2026-06-11) İHLAL. "588/588 sökülebilir, 0 kilit" (F2) DOĞRU ama o **+Z erişilebilirlik/kilitlenme**; **1mm yüzey boşluğu AYRI kısıt** ve web-heightmap'te hiç kontrol edilmemişti. İç-içe-geçme YOK (voxel-doluluk tutuyor). **Kalibre formül: margin=z_clearance=max(1,ceil(clearance_mm/pitch)); pitch 0.5→(2,2).** Ölçüldü (üretim wall_aware yolu): margin=0 282mm(0.084) / margin=1 296mm(0.79-0.90, hâlâ<1) / **margin=2 329mm(1.029mm ✅≥1mm)**. **Dürüst Deneme4 = ~329mm (+%16.7), Magics 250.24 açığı %12.7→~%31.5.** AMA bu KABA dilation (parçayı şişir); clearance-AWARE yerleştirme (Magics gibi, 1mm'yi kısıt tut) 329'un altına iner = asıl kalite kaldıracı. **DERS:** benchmark (c3_generality pitch 2.0 margin=1) ve NFV (margin=1) coarse-pitch'te ≥1mm sağlıyordu (plan2 %4.2 DÜRÜST) — ama fine-pitch (0.5) NFV DE <1mm (margin=1→0.79-0.90); sistem-geneli clearance açığı. Fix kodu YAZILDI ama COMMIT EDİLMEDİ (reviewer BLOCK: HIGH-2 runtime gate + kaba-vs-aware kararı) — detay `ML_GENELLEME_STRATEJI_BULGULAR_2026-07-06.md` clearance bölümü.
- **F4-A AYRIŞIM (2026-07-04):** 95mm kazancın anatomisi (`scripts/f4a_ayrisim.py`; kapı: @0.5/n=4 yeniden-voxelize → 282.0 BİREBİR + 0 çifte-dolu voxel = orientation eşleşmesi KANITLI; 36s). Bulgular: (1) **Kazanç yanal derin iç-içelik** — 565/588 parça (%96) tabanı başka parçanın bbox z-aralığına gömülü (ort 61mm, medyan 61.5, max 131mm; 2208 iç-içe çift; çakışmasız/bbox-düzeyi) → K-20'nin "kazanç yanal karışık paketleme" hükmünün pozitif kanıtı. (2) **Ana ev sahibi ASY-0176446** (62 adet çan): içine 512× T03-düğme + 305× kendi tipi + 264× ASY-1 alıyor; 200'lük T03 ayrıca 132 kendi-içine yuvalanıyor. ROBT plakaları tabanda bitiyor (tepe 32.5/62.0mm). (3) **Tavanı 9 parça kuruyor:** yanal doluluk 0-230mm bandında ~%15-24 (tekdüze), 230mm üstü ÇÖKÜYOR (%4.8→%0.2); son 30mm'de (252-282) YALNIZ 9 adet ASY-0176446 var — diğer 12 tipin tümü ≤239.5mm'de bitiyor. → Kalan kalite kaldıracı pitch değil KUYRUK YERLEŞİMİ: o 9 ASY aşağı sokulabilirse ~240 bandına iniş potansiyeli (HİPOTEZ — kanıt K-21 NFV-fine ölçümü; tam hedefi bu).

#### [K-20] Identical-part hizalı kule şablonu (F4-B fast-path) — Deneme4
- **Durum:** ❌ NO-GO (çözücü-yerine-geçme olarak; SÜRE içgörüsü değerli) · **Tarih:** 2026-07-04 · **Kanıt:** `scripts/f4b_fastpath.py` (opt-in; reviewer düzeltmeli: kanıtlı/tahmini sınırlar ayrık)
- **Ne:** MDPI Appl.Sci 16(1):148 katman-çoğaltma fikri: tip başına TEK voxelize → optimal tek katman → hizalı dikey çoğaltma (nest_advance = Bin3D drop kuralına BİREBİR, test-kilitli) + kompozisyon bracket'i.
- **Sonuç (Deneme4 @0.5mm, 6 poz):** tahmini hizalı-kule **527.5mm** vs K-19 heightmap **282.0** — kule yaklaşımı %87 GERİDE; garantili bracket [87.5 .. 753.5] K-19'u kapsıyor (kesin hüküm gerçek yerleşim ister ama fark kapanmaz görünüyor). Telescope eden grup **2/13** — çoğu düğme hizalı istifte kabuk-oturması YAPMIYOR. Süre: **82s (96× hızlı)**, tamamı voxelize (compute 0.02s).
- **NEDEN olmadı:** K-19 kazancının mekanizması hizalı bardak-istifi DEĞİL — ince pitch'te çözünen kabukların drop_map'le YANAL KARIŞIK paketlenmesi (farklı tipler birbirinin boşluğuna). Saf dikey çoğaltma bu serbestliği atıyor.
- **Ders:** (1) "Özdeş parça = kule" sezgisi kabukta ölçümle çürüdü — kazanç yanal serbestlikte. (2) ~~SÜRE içgörüsü: 131dk'nın maliyeti drop döngüsü~~ → **H-15/H-15b DÜZELTMESİ (2026-07-05): atıf ölçümsüzdü ve YANLIŞTI — drop ~479s (%8); ara atıf "ince-açı rafinesi" de yanlıştı (üretimde hiç koşmuyor); GERÇEK maliyet coarse-tune ~5626s (%90, sentez 0.99). Bkz. H-15.** (3) Reviewer dersi: "kanıtlanabilir sınır" etiketi matematiksel kanıt ister — grid-sayımlı kule alt-sınır DEĞİLDİR (karşı-örnekli).

> **KALİTE ÖZET:** 6GB'de açığı kapatacak algoritma kaldıraçları TÜKENDİ — pitch + eksen-oryantasyon +
> sıra + tie-break + compaction + **sürekli-serbest-rotasyon (K-13) + koordineli-rack (K-14)** = **7'si de
> ölü/doygun**. Plan2 darboğazı = ~20 büyük levha (düz yatamaz, istiflenir); numune darboğazı = ince plakalar
> (düz zaten optimal, K-15) — **her ikisi de rotasyona kapalı, farklı sebeplerle**. Magics %6 açığı = fine
> pitch (0.5mm) + büyük levhaların global rotasyonu (ikisi de 6GB OOM/erişilemez) → **SÜPER BİLGİSAYAR** tek
> yol (§5 A1). NOT: A1'in küçük-N (numune) 6GB-fizibilite umudu da K-15 ile zayıfladı (numune rotasyon-kapalı).
> **GÜNCELLEME 2026-07-03 (K-17 + K-18):** "Tükendi" hükmü ALGORİTMİK kaldıraçlar içindi; H-14
> (voxelize 3×) iki yeni kaldıracı ekonomik yaptı ve İKİSİ DE ÜRETİMDE:
> **K-17 fine-settle** (NFV default-on): kuantizasyon vergisi +%0.4-1.6 (Plan2 522→516, açık %4.9).
> **K-18 AX24** (quality=max): +settle ile plan1 −%6.9 / plan2 −%1.8 (512.5, açık **%4.2**) /
> plan3 **−%10.5** (844→755.5). Yapısal açığın kalanı (levha sürekli-rotasyonu) hâlâ A1.
> **GÜNCELLEME 2026-07-04 (K-19):** "Tükendi" hükmü PLAN-aileleri içindi; yeni aile = yeni kaldıraç:
> kabuk ailesinde (Deneme4) cidar-duyarlı pitch TEK BAŞINA **−%25.3** (377.3→282.0, Magics açığı
> %54→**%12.7**) — bedeli 131 dk/koşu. Üretime bağlama = program F3 (K-19p, §5).
> **GÜNCELLEME 2026-07-04b (K-21):** Kabukta NFV-fine 262.5'e İNİYOR ama 554/588 KİLİTLİ = İLLEGAL;
> LEGAL şampiyon K-19 282.0 (0 kilit). Çarpıcı: illegal 262.5 bile Magics'in LEGAL 250.24'üne
> yetişemiyor → Magics avantajı salt kavite değil. Yeni yön: F2-v2 (sökülebilirlik-kısıtlı decode, §5).
> **GÜNCELLEME 2026-07-04c (K-22):** Kuyruk yeniden-yerleşimi NO-GO ama İKİ ALTIN BULGU: (1) 9 ASY'siz
> taban **250.5mm ≈ Magics 250.24** — açık TAMAMEN o 9 parçanın emilememesi. (2) Kuyruk cepleri
> SIRA-bağımlı: post-hoc drop 282'yi bile tekrar üretemiyor (322'ye istifledi) → kaldıraç YERLEŞTİRME
> SIRASI (K-23 adayı) veya hedefli legal-insert (F2-v2'nin ucuz hali).
> **GÜNCELLEME 2026-07-04d (K-22b + K-23 kapanışı):** Legal-insert DE (−0.5mm + 39 kilit) sıra-deneyi
> DE (teşhisle, koşusuz) NO-GO. Çarpıcı teşhis: tavanı ASY bloğu TEK BAŞINA kuruyor (64-replay'de bin
> zaten 282.0); boş çan içleri drop'a KAPALI → kule zorunluydu. **282.0 = drop/heightmap semantiğinde
> YAPISAL kabuk tavanı (6GB).** Kalan ödül (denge tavanı ~152) ancak decode değişikliği (K-24 adayı,
> spekülatif) veya A1 ile alınabilir; istif kalitemiz 9-çan kuyruğu dışında Magics PARİTE (250.5).

#### [K-23] Kuyruk-öne SIRA deneyi — TEŞHİSLE KAPANDI (koşusuz NO-GO)
- **Durum:** ❌ NO-GO (2 ucuz teşhisle; 1-2 saatlik fine koşuları HİÇ yapılmadan) · **Tarih:** 2026-07-04 · **Kanıt:** `scripts/k23_on_analiz.py` + `scripts/k23_on_analiz2.py` (35s + 52s)
- **Bulgu 1 (zincir yapısı):** 62 ASY → 10 kök; dağılım uçurum: 30-halkalı küme 282'ye tırmanmış, **6 çan tabanda TEK (87.5mm), içine hiç girilmemiş**; halka z-adımı ~10.7mm. Analitik denge tavanı **~152mm** (ceil(62/10)=7 halka/zincir) — ödül büyük GÖRÜNÜYORDU. Ayrıca sıra zaten tip-bitişik ve ASY bloğu en önde (2..63) → "kuyruğu öne al" fikri baştan boş; kuyruk 9'u = bloğun kendi son halkaları.
- **Bulgu 2 (mekanizma, teşhis-2):** ASY-bloğu anının 64-replay'inde bin **ZATEN 282.0mm** — tavanı 62 çan tek başına kuruyor, kalan 524 parça tavana dokunmuyor. O anda fazladan bir ASY için global en-iyi z_top 272.0; boş çanların pencere-minleri **272-299.5mm** (iç açık olsaydı ~98 beklenirdi) = **içler drop'a KAPALI** (rim + komşu bloke). Kule tercih değil ZORUNLULUKTU.
- **NEDEN NO-GO:** Özdeş parçada blok-içi sıra permütasyonu greedy'ye etkisiz; araya başka tip sokmak yalnız malzeme EKLER, çan içini AÇAMAZ. Drop/heightmap semantiğinde **282.0 = yapısal tavan**.
- **Ders/yeni yön:** K-22→K-23 zinciri metodolojik kazanç: 2 saatlik deney yerine dakikalık teşhis hükmü verdi (meta-ders "ölç-önce"nin teşhis-önce hali). Denge tavanı ~152 ödülü duruyor ama ancak DECODE değişikliğiyle alınabilir: çanları giriş-ofsetiyle KASITLI tohumlayan zincir-ekimi planlayıcısı (**K-24 adayı**, spekülatif — K-20 hizalı-kulenin farkı: telescope ofsetini drop değil planlayıcı seçer, yanal karışım korunur) veya A1.

#### [K-22] Kuyruk-hedefli yeniden-yerleşim (9-ASY, post-hoc drop) — Deneme4
- **Durum:** ❌ NO-GO (post-hoc drop olarak; İKİ altın bulgu doğurdu) · **Tarih:** 2026-07-04 · **Kanıt:** `scripts/k22_kuyruk_yerlesim.py` (replay kapısı 282.0 birebir; 251s)
- **Ne:** F4-A'nın işaret ettiği kuyruk (tepe > max−30mm = tam 9× ASY-0176446) K-19 v2 layout'undan söküldü; kalan 579 yerleşikken üretim `_best_position` kuralıyla (hacim-azalan) yeniden drop edildi; erişilebilirlik denetimli.
- **Sonuç:** taban 579 = **250.5mm**; yeniden-drop 9 ASY'yi ceplerine SOKAMADI — tepeler 253-282 → 281.5-322mm'e İSTİFLENDİ (282.0 → 322.0, tavan kötüleşti; hüküm NO-GO, layout atıldı; 0 kilit korunuyordu).
- **NEDEN olmadı:** Kuyruk parçalarının derin cepleri (F4-A: ort 61mm gömülme) SIRA-bağımlı — cep, ancak sahibi yerleştirme sırasının O anında düşerken var; sahibi çıkınca üstüne oturan komşu profilleri cebi "mühürlüyor" ve drop kuralı (profilin ÜSTÜNE oturur) geri giremiyor. Heightmap'te post-hoc yerel onarım yapısal olarak imkânsız.
- **ALTIN BULGU 1:** 250.5 ≈ Magics 250.24 — kabukta Magics açığının %100'ü son 9 parçanın yutulamamasında; genel istif kalitemiz Magics parite.
- **ALTIN BULGU 2 (yeni kaldıraç adayı K-23):** çare poz değil SIRA — pickle'daki placement listesi = orijinal yerleştirme sırası ELDE; 9 kuyruk ID'sini sırada öne/ev-sahibi ASY bloğuna taşıyıp `place_in_order`'ı yeniden koşmak ölçülebilir (bedel: değişen noktadan sonrası yeniden drop ≈ fine geçişin büyük kısmı ~1-2 saat/deneme). Alternatif ucuz yol: hedefli legal-insert (tam-3D çakışma + üst-kolon-boş şartı = F2-v2'nin 9-parçalık mini hali).
- **Yan bulgu (kırılganlık):** deneme4 kabuklarında n=8'in 4..7 pozlarından biri @0.5 slice-voxelize'ı düşürüyor (`trimesh repair_invalid: unable to recover polygon`) — n=4 sağlam (F4-A+bu probe kanıtı). Kabukta poz genişletme işi öncesi bilinmeli.
- **K-22b LEGAL-INSERT teşhisi (aynı gün):** drop'tan zayıf şartla (yalnız çakışmasızlık; "üstü örtülü ama söküm-sırası var" cepleri de sayar) tam-3D FFT araması (`scripts/k22b_legal_insert.py`, 25 dk): 9 ASY ancak 253-281.5 bandına dizilebildi → 282.0→**281.5 (−0.5mm)** + **39 kilit** = pratikte CEP YOK; alçak bant (~250-256) yalnız ~4 parça alıyor. **HÜKÜM: sabit geometri DOYMUŞ — kuyruk emilimi ancak yerleşimin baştan farklı kurulmasıyla (K-23 sıra deneyi) mümkün.** F2-v2'nin "hedefli mini hali" böylece ÖLÇÜLDÜ ve kapandı (tam F2-v2 = decode-içi kısıt ayrı konu).

#### [K-21] Kabukta NFV @orta-ince pitch — "cavity-packing 282'nin altına LEGAL inebilir mi?"
- **Durum:** ❌ İLLEGAL KAZANÇ (üretim yönünde NO-GO; F2-v2 gündem maddesi doğdu) · **Tarih:** 2026-07-04 · **Kanıt:** `scripts/k21_nfv_fine_kabuk.py` (yerleşimler `data/mail_stl/k21_placements_p1_n8.pkl`, izlenmiyor)
- **Ne:** Deneme4 (588, auto-plaka 301.6) → `solve_nfv(fine_pitch=1.0, time_budget_sec, fine_settle=default)` → `accessibility.check_result`. RESUME Sprint 3 §2 reçetesi.
- **Koşu 1 (quality=max, 2h):** makine 15.7GB → AX24 kapısı (eşik <13GB) frenlemedi → kural gereği 24 poz (loglanmadı — çıkarım) + RAM talebi ~11GB private → disk takası → 121 dk'da **193/588 KISMİ** (hüküm üretmez; kısmi yön sinyali 160/193 kilit). Süreç dersi: bütçe kesmesi kısmi yerleşim bırakır → probe hüküm kapısına `n_placed==beklenen` kontrolü ŞART (ilk sürüm "illegal kazanç" basmıştı — düzeltildi).
- **Koşu 2 (n=8, 3h):** **588/588, 95.1 dk**, strategy=cpu-kolA (GPU seçilmedi — @1.0 fine FFT 6GB VRAM'e sığmıyor olmalı, gözlem), settle 264.0→**262.5mm @0.5** (tepe RAM 7.97GB). K-19'un −%6.9 altı AMA **554/588 +Z kilitli (TEK dev grup)** = İLLEGAL/üretilemez.
- **HÜKÜM:** K-19 hükmü LEGALLİK boyutuyla pekişti — NFV'nin kabuk kazancının özü kapalı-kaviteye gömme; sökülebilirlik şartı konunca kazanç buharlaşıyor. Kıyas metriği "yükseklik" değil **legal-yükseklik** olmalı (K-12 "NFV≥heightmap" kabukta bu metrikle TERSİNE döner).
- **@0.8 İPTAL:** @1.0 talebi ~11GB / 15.7GB makine; @0.8 grid ~2× = bu makinede gerçekçi değil; üstelik hüküm nitel (kilit baskın) — pitch inceltmek kilidi çözmez.
- **Ders:** (1) 262.5 (illegal) > Magics 250.24 (legal): Magics farkı kavite-gömme değil, muhtemelen sürekli-rotasyon (A1) + sökülebilir yerleşimin BİRLİKTE'si. (2) quality=max'ın 13GB RAM eşiği grid-farkındalı değil — 588 parça @1.0 fine'da 15.7GB makinede takasa düşürdü; `orient_ram_brake` opt-in'i tam bu senaryo için (F0), probe'larda da kullanılmalı.

#### [F2-v2] Sökülebilirlik-farkındalı NFV decode (+Z gök-koridoru kısıtı yerleştirme anında) — plan3 prototipi
- **Durum:** ❌ KESİN NO-GO (ölçüldü) · **Tarih:** 2026-07-07 · **Kanıt:** `scripts/f2v2_prototip.py` + `scripts/f2v2_prototip.log` + `scripts/f2v2_baseline_probe.log` (C:\dev\ie488)
- **Ne:** NFV decode'a yerleştirme ANINDA +Z gök-koridoru (sky-corridor) kısıtı: parçanın üstündeki kolon boş kalmalı → her yerleşim inşaat sırasında sökülebilir (ileri-yön tümevarım garantisi; iter-2 gerekmedi, 0 kilit). Plan3 (109 parça, auto-plaka 279.7).
- **Sonuç:** sky-corridor LEGAL: settleOFF 1175.0 (117s, pitch 2.5) / settleON **1145.6mm** (259s, pitch 0.625, clearance 2.504, **0 kilit**). Kontrol baseline (İLLEGAL üretim NFV, aynı plaka): c=0.0 → 901.9 (87 kilit) / c=1.0 → 944.4 (81 kilit). **Sökülebilirlik bedeli = +201.2mm** (1145.6 − 944.4). Aynı auto-plakada heightmap default legal ≈1046 → sky-corridor onu da geçemiyor; eski-plaka heightmap şampiyonu 701 / Magics 593'e karşı +%63/+%93.
- **HÜKÜM:** NFV'nin kavite kazancı tam da gök-koridorunun YASAKLADIĞI şey (kapalı-kaviteye gömme). Legallik kısıtı decode'a konunca NFV heightmap'in gerisine düşüyor → ~%20-28'lik plan NFV kazançları legal olarak BU YÖNTEMLE kurtarılamaz. K-21 (kabuk 554 kilit) + K-22b (legal-insert NO-GO) + EVAL-1 (plan ailesi 81-87 kilit) zinciriyle tutarlı: NFV kalite modu A2-İLLEGAL kalır, şampiyon default heightmap.
- **Ders:** (1) "kilidi decode'da önle" fikri konservatif kısıtla (üst-kolon-boş) ölçüldü — kısıt kazancın tamamını + fazlasını yiyor; daha zayıf legal kısıt (söküm-sırası planlama) semantik değişikliği ister, maliyeti belirsiz. (2) Kalan gerçek kaldıraç rotasyon (A1) — Magics farkının kavite-gömme değil serbest-rotasyon+legal-yerleşim BİRLİKTE'si olduğu (K-21 dersi) bir kez daha doğrulandı.

### 3.2 HIZ (kaliteyi BOZMADAN — birebir/exact)

#### [H-01] drop_map vektörizasyon
- **Durum:** ✅ GO (üretimde CANLI) · **Tarih:** 2026-06-22 · **Kanıt:** `bin3d.py`, `tests/test_bin3d_dropmap.py`, commit `0ac9e4b`
- **Ne:** Konkav footprint Python `for` döngüsü → `sliding_window_view` tek-redüksiyon.
- **Sonuç:** Plan1 132→132 (BİREBİR), süre 77.9→55.7s = **%28.5**. drop_map tottime %72'den düştü.
- **NEDEN oldu:** Stride-trick aynı redüksiyon (max birleşmeli+tamsayı) → birebir; sadece Python döngü kalktı. (maximum_filter DENENDİ → 2.5× yavaş, generic filter tüm H'de.)

#### [H-02] Kademeli z-dilim (NFV)
- **Durum:** ✅ GO (üretimde) · **Tarih:** 2026-06-22 · **Kanıt:** `scripts/c3_speed.py`, `ANALIZ_NFV §2`
- **Ne:** FFT'yi tüm grid yerine BLB min-z'den başlayan küçük z-dilimde yap (büyüt-gerekirse).
- **Sonuç:** Plan2 985→376s = **2.6×**, 556 birebir.
- **NEDEN oldu:** Küçük dilim feasible = global min (BLB en düşüğü seçer) → birebir, daha az FFT hacmi.

#### [H-03] xy-bbox kırpma (NFV)
- **Durum:** ✅ GO (üretimde) · **Tarih:** 2026-06-23 · **Kanıt:** `scripts/c3_speed2.py`, commit `3ab5e6a`
- **Ne:** FFT yalnız dolu-bbox ± parça-ayağı bölgesinde (dışı C=0=feasible, matematiksel özdeş).
- **Sonuç:** Plan2 376→281s (1.34×); toplam 985→281 = **3.5×**, 556 birebir.
- **NEDEN oldu:** occ'un boş bölgesi her zaman feasible → FFT'ye gerek yok. Matematiksel özdeşlik.

#### [H-04] GPU-resident decode (NFV)
- **Durum:** ✅ GO (üretimde) · **Tarih:** 2026-06-23 · **Kanıt:** `scripts/c3_gpu_resident.py`, commit `d9822c4`+`b09512e`
- **Ne:** occupancy CİHAZDA resident, place in-device, host'a yalnız 3-int; cuFFT plan-cache + periyodik free.
- **Sonuç:** Plan2 51.1s = **5.5×** çapadan, RTX3060 6GB'de bile. Cross-dataset: plan1 2.7×, plan3 3.3×, plan2 5.5× (grid büyüdükçe artar). BİREBİR.
- **NEDEN oldu:** Naive transfer-tuzağı (0.65×) + plan-cache OOM aşıldı; occupancy hiç host'a inmiyor.
- **DOĞRULAMA 2026-06-30 (P3 — 596s'lik gerçek ağır cavity seti):** Canlı demoda 596s veren set = **Plan1+Plan3 birleşik** (forward'lar, nfv quality=fast, h=667.5/doluluk 0.369); o an cupy algılanmadığından CPU'ya düşmüştü. Bu makinede gerçek geometriyle (mail_stl_4F427959+CADD13C2) `solve_nfv force=gpu-resident` vs `cpu-kolA` ölçüldü — **ikisi BİREBİR aynı layout** (height eşit, H-04/H-05 invariant kanıt). Adetler ölçeklenerek seti kuşatan ölçüm (pitch 2.50, plaka 340×340, n=8): h=397→**1.67×**, h=512→**1.93×**, h=727→**2.01×** end-to-end (CPU 140/223/303s → GPU 84/116/151s). **Kazanç yükle BÜYÜR** (FFT-decode payı baskınlaşır). Ayrıştırma (h=727): voxelize **54s paylaşılan** (CPU, GPU hızlandırmaz) + decode CPU 266s → GPU 99.5s = **decode-only 2.67×**; end-to-end 2.08× voxelize'la seyrelir. → **Gerçek 596s seti (h=667.5, mult 3-4 arası) GPU'da ~2× hızlanır, kalite birebir.** Kanıt: `scripts/c3_gpu_596set.py`. NOT: decode-only hızlanma grid'le büyür (Plan2 daha büyük grid'de 5.5×, H-04 üstü); bu sette grid 11.8M olduğu için 2.67×. **Ders:** end-to-end GPU kazancının tavanı paylaşılan voxelize → §5 C1 (voxelize hızı) GPU faydasını da çoğaltır.

#### [H-05] CPU Kol A — orient-thread paralel decode
- **Durum:** ✅ GO (üretimde, GPU yoksa) · **Tarih:** 2026-06-23 · **Kanıt:** `scripts/c3_par_a.py`, `PARALLELLIK_TASARIM_2026-06-23.md`
- **Ne:** Bir parçanın oryantasyonları ThreadPool'da paralel; `oi`-sıralı reduce → seri ile birebir.
- **Sonuç:** Plan2 ~122s ~2.3×. (FFT GIL-free; `set_workers` WORKER İÇİNDE — contextvar propagate etmez.)
- **NEDEN oldu:** Greedy zincir sıralı ama oryantasyonlar bağımsız → paralel. Tavan ~2× (Amdahl).

#### [H-06] Per-part pitch / two-level grid
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-21/22 · **Kanıt:** `scripts/profile_plan1.py`, `DENEYLER_BULGULAR_2026-06-22.md`
- **Ne:** İnce parçaya az voxel (aykırı pitch'i ayır), iki-seviyeli grid.
- **Sonuç:** Tek grid'de pitch kabalaştırmak TÜM parçaları kabalaştırıp Plan1'i 106.7→129.5 (%21) BOZDU. Profil: voxelizasyon baskın değil (%14), darboğaz arama.
- **NEDEN olmadı:** Yanlış lever — voxelizasyon darboğaz değil; pitch global, ayrılamıyor. Kalite riski yüksek.

#### [H-07] bit-pack occupancy (depolama)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-23 · **Kanıt:** `scripts/c3_speed3_probe.py`, commit `8cd33f7`
- **Ne:** occupancy'yi bit-pack sakla (bellek/hız).
- **Sonuç:** FFT ~280ms vs bit-pack ~650ms = **2.3× YAVAŞ** (feasible set birebir).
- **NEDEN olmadı:** 276 solid-kolon Python döngüsü FFT'nin C/FFTW'sini geçemez (numba YOK). DEPOLAMA leveri, hesaplama değil.

#### [H-08] FastCPU backend (pyfftw)
- **Durum:** ❌ NO-GO · **Tarih:** 2026-06-23 · **Kanıt:** `scripts/c3_fastcpu_bench.py`, commit `a57dbac`
- **Ne:** scipy yerine pyfftw FFT backend.
- **Sonuç:** birebir 556 ama **5.3× YAVAŞ** (700.9s vs 132.9s).
- **NEDEN olmadı:** NFV decode binlerce küçük/değişken FFT → pyfftw her çağrıda plan kuruyor (plan-overhead); scipy pocketfft plan-cache'li üstün. (mkl_fft denenmedi — AMD makine.)

#### [H-09] occ-FFT paylaşımı (oryantasyonlar arası FFT tekrar kullanımı)
- **Durum:** ❌ NO-GO (3 varyant) · **Tarih:** 2026-06-24 · **Kanıt:** `scripts/c3_occfft_{profile,proto,batched}.py`+`c3_crop_swell.py`, commit `459e343`, [[project-nfv-sonraki-oturum-backlog]] #7
- **Ne:** occ-FFT oryantasyonlar arası sabit → 1 kez hesapla, paylaş (naif ortak-crop / maliyet-tabanlı / batched).
- **Sonuç:** BİREBİR tasarım doğru AMA kazanç GENEL DEĞİL: naif plan1 2.22×/plan3 0.96×/plan2 0.80× (sadece plan1 kazanır); maliyet-modeli gerçeği TERS tahmin; batched plan1 2.13×/plan3 OOM.
- **NEDEN olmadı:** Kök GPU mikro-mimaride (launch-overhead/plan-cache/bellek-bandı), basit N·logN modeli yakalamıyor. Üst-sınır profili (%26) gerçekte plan1'de %55 aşıldı ama plan3'te negatife döndü.
- **Ders:** Cross-dataset + test-önce 3 yanlış "üretime al"dan korudu. **mikro üst-sınır ≠ gerçek GPU kazancı.**

#### [H-10] Sparse/popcount korelasyon (binary AND, FFT'siz)
- **Durum:** ❌ NO-GO (naif form) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_popcount{,_decode}.py`, `ANALIZ_NFV §8`, commit `6627d91`
- **Ne:** Parça %93 boş → çakışmayı dolu voxeller üzerinden sparse-shift hesapla (EXACT, fp64 FFT'siz). Literatür B1.
- **Sonuç:** Mikro GO (küçük parça+geniş occ 6.67× + birebir) AMA gerçek hibrit decode 522 BİREBİR tüm THRESH iken **0.69-0.85× = baz'dan YAVAŞ**.
- **NEDEN olmadı:** Python-loop kernel-launch overhead + xy-bbox crop küçük parçada zaten küçük (FFT ucuz). Mikro üst-sınır decode'da gerçekleşmedi = H-09 dersi tekrarı.
- **Ders:** "bit-pack NO-GO"dan farklıydı (hesaplama≠depolama) ama yine NO-GO. Gerçek B1 (bit-pack popcount RawKernel) §5'te açık ama marjinal.

#### [H-11] VDB / sparse-occupancy (bellek→ince pitch→dolaylı kalite)
- **Durum:** ❌ NO-GO (ön-analiz, kurmadan) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/c3_vdb_memprofile.py`, `ANALIZ_NFV §9`, commit `c983070`
- **Ne:** VDB occupancy'yi sıkıştır → OOM gevşet → daha ince pitch (0.5mm) → dolaylı kalite. Literatür B2.
- **Sonuç:** Plan2 @2.0mm occ-array 20.5MB vs peak-GPU 8921MB = **peak/occ 434.8×**.
- **NEDEN olmadı:** Bellek darboğazı occupancy'de DEĞİL, FFT geçici array'lerinde (occ'un 435 katı). occ zaten küçük; FFT sparse edilemez (birebir kuralı). VDB ince-pitch'i açmaz.
- **Ders:** Tek ölçüm (peak/occ) VDB kurulum/debug eforuna girmeden net NO-GO = ÖLÇ-ÖNCE en temiz örneği. İnce pitch = FFT-bellek = süper bilgisayar.

#### [H-12] Voxelize OOM — `_surface_cells` mk-chunk (ÜRETİM robustluk, gerçek-veri heightmap)
- **Durum:** ✅ GO (ÜRETİMDE) · **Tarih:** 2026-06-26 · **Kanıt:** `voxelize.py::_surface_cells`, commit `36744b3`, `RESUME_2026-06-26 İş2`
- **Ne:** `_surface_cells` barycentric `pts (mk, n_bary, 3)` array'ini mk-chunk'la (tek-array yerine ~0.19GB/chunk).
- **Sonuç:** Plan2 GERÇEK veri default heightmap ÇÖKÜYORDU (356mm dev parça P155308 @0.5mm → `pts (363,559153,3)`=**4.87GB tek array** OOM → height=0 BAŞARISIZ). Chunk sonrası OOM YOK, **BİREBİR grid** (chunk==referans 194914=194914; `_mark` idempotent). 98 kritik test yeşil.
- **NEDEN gerekti:** Büyük DÜZ yüzey = az ama dev üçgen → ince pitch'te k_per_tri ~1056 → n_bary ~5.6e5; mk*n_bary tek alloc patlıyor. Pitch politikasına dokunulmadı (parça-kaybı riski yok).
- **Ders:** Bellek-bağımsız (chunk) çözüm pitch/kaliteye dokunmadan robustluk verir. **OOM (çökme) ≠ yavaşlık** — ayrı kökler.

#### [H-13] Çift-voxelize kaldırma (`_process_batch` — APP üretim hızı)
- **Durum:** ✅ GO (ÜRETİMDE) · **Tarih:** 2026-06-26 · **Kanıt:** `scripts/demo_pipeline.py::_process_batch`, commit `10b5f2e`, `RESUME_2026-06-26 İş3`
- **Ne:** Satır 610 HER ZAMAN fine voxelize ediyordu; NFV (`solve_nfv`)/coarse_to_fine KENDİ voxelize'ını yapar → o yollarda BOŞA. `voxel_parts` SADECE tuner+DBLF yolunda; C2F yol kararı voxelize'sız `estimated_n_parts = sum(qty) by distinct name` ile (to_voxel_parts semantiği birebir).
- **Sonuç:** **BİREBİR** (45-parça coarse height=36.0+density git-stash öncesi=sonrası AYNI); süre 7.0→4.4s (%37 sentetik; büyük parçada çift 159s/parça kalktığından kazanç DAHA büyük). Kalıcı regresyon testi + 175 test.
- **NEDEN oldu:** Gereksiz tekrar voxelize; yalnız tuner/DBLF voxel_parts gerektiriyor. Voxelize hata yakalama + DBLF None-guard korundu.
- **Ders:** **YARI çözüm** — coarse_to_fine FINE adımı (büyük parça 159s @0.5mm) DURUYOR; asıl kök pitch R6 = ayrı/riskli (§5).

#### [H-14] C1 — Voxelize hızlandırma: `_surface_cells` eksen-bazlı + `_slice_voxelize` bbox-kırpma
- **Durum:** ✅ GO (ÜRETİMDE) · **Tarih:** 2026-07-02 · **Kanıt:** `scripts/c1_voxprofile.py` (teşhis) + `scripts/c1_voxspeed.py` (prototip+kapı), `tests/test_voxelize_c1_exact.py`, `voxelize.py`
- **Ne:** (1) Profil (meta-ders #11): P155308 @0.5mm 150s/oryantasyonun **%84'ü `_surface_cells`** (915M barycentric nokta: pts-üretim 84s + işaretleme 41.5s), %13 `contains_xy`, %3 `section_multiplane`. (2) `_surface_cells` → eksen-bazlı hesap + `out=` buffer-reuse + int32 indeks — eleman başına AYNI çarpım/toplam sırası (IEEE deterministik) = **bit-düzeyi aynı grid**; kazanç taze dev-array tahsisleri (page-fault) + int64 trafiği + reshape kopyalarının kalkması. (3) `_slice_voxelize` → poligon bbox-kırpma (bbox dışı merkez strictly-outside → contains False, maske özdeş; H-03 xy-kırpmanın 2D analoğu).
- **Sonuç:** P155308 @0.5mm: surface 125.9→40.7s (**3.1×**), slice 25.8→8.1s (**3.2×**) → oryantasyon başına 151.6→48.8s = **3.1× uçtan uca**. Cross-dataset **9/9 birebir** (Plan2 ×2 + mail Plan1/Plan3 setleri ×4, pitch 2.0/1.0/0.5). Donmuş-referans testi kalıcı (sentetik 5 şekil × 3 pitch + chunk-sınırı + boş-grid ValueError = 33 test yeşil).
- **NEDEN oldu:** Darboğaz FLOP değil BELLEK TRAFİĞİ/tahsisti — eski kod chunk başına ~7 taze (mk,n_bary,3) float64 array üretiyordu (malloc + page-zero); buffer-reuse bunu sıfırlar, eksen-bazlı düzen aynı tavanla 3× büyük chunk açar (daha az Python-döngü turu). bbox-kırpma da test edilen nokta sayısını poligon alanına indirir (grid alanı değil).
- **Ders:** H-06'nın "voxelizasyon darboğaz değil" bulgusu HEIGHTMAP @kaba pitch içindi; fine 0.5mm + büyük parçada voxelize BASKIN hale geliyor — darboğaz pitch'e göre yer değiştirir, her rejimde yeniden profille. §5 C1 gerekçesi (voxelize = GPU kazancının tavanı) ile birleşince NFV GPU uçtan-uca kazancını da büyütür.

#### [H-15] Kabuk fine-yolu SÜRE profili — asıl maliyet COARSE-TUNE (drop da rafine de değil!)
- **Durum:** ✅✅ GO — **H-15p ÜRETİMDE (opt-in yol, commit `1cccad6`); E2E kapısı GEÇTİ: 6272s → 553s (9.2 dk, 11.3×), 282.0 BİREBİR** · **Tarih:** 2026-07-04/05 · **Kanıt:** `scripts/h15_on_analiz.py` + `scripts/h15b_coarse_profil.py` (sentez 0.99) + zincir testi v2 (telemetri: coarse 38.6s / fine 514.0s / winning=dblf_only / fine_angle 0.0)
- **Ne:** K-19/zincir-testi 104.5 dk = 6270s'nin nereye gittiği İKİ adımda ölçüldü. (1) Örneklemeli drop profili: fast-path %0 (kabuk konkav+değişken taban), fine taban geçişi **~479s (%8)** → K-20'nin "maliyet drop döngüsü" atfı YANLIŞLANDI. (2) İlk atıf denemem "%92 ince-açı rafinesi" idi — **reviewer H1 bunu da yanlışladı:** demo_pipeline C2F çağrısı `adaptive`/`fine_angle_window` GEÇMİYOR → rafine üretimde HİÇ koşmuyor (bit-özdeş-n4 kanıtı "kullanılmadı" der, "koşmadı"yı ayırt edemezdi — atıf çıkarımdı).
- **GERÇEK ATIF (h15b ölçümü): COARSE TUNE = ~5626s (%90).** `suggest_coarse_pitch(0.5)=1.5mm` (bbox-tabanlı tavan); tek dblf geçişi @1.5 = **32.1s**; `tune` = 7 konfig (baseline/sa×3/dblf/ga/tabu) × budget 25 iterasyon ≈ 7×25×32s. Sentez: 12s vox + 5626 tune + 90 fine-vox + 479 fine = **6207s vs gerçek 6270s (0.99)**.
- **Boşa gidiyor kanıtı:** K-19 v2 kazanan sırası MÜKEMMEL tip-bloklu hacim-azalan — SA/GA kazansa sıra karışık olurdu → 5626s'lik arama düz DBLF sırasını geçememiş (E2E birebir kapısıyla kesinleşecek).
- **H-15p fix (rev-2) — BAĞLANDI ve E2E-KANITLI:** (1) **Kabuk yolunda kısıtlı coarse arama** — wall_aware tetiğinde `menu={dblf_only}`: coarse 5626s → **38.6s ölçüldü**; zincir testi v2: **6272s → 553s (11.3×), 282.0 BİREBİR, kriter A+C PASS, RAM 1.11GB**. wall_aware False = birebir (menu=None). (2) `skip_fine_angle` + telemetri (`coarse_time_s/fine_time_s/winning_config/fine_angle_*` her C2F koşusunda rapor-only) bağlı; skip şimdilik defansif. (3) KALAN: dirty-region drop önbelleği — yeni darboğaz fine geçişi 514s (%93); tahmini 553s → ~100-150s bandı. (4) GPU drop — marjinal.
- **Ders:** (1) Meta-ders #11 İKİ KEZ üst üste: K-20 "drop" dedi (ölçümsüz), ben "rafine" dedim (yarı-ölçümlü) — süre atfı ancak SENTEZ ORANI ~1.0 verince kapanır; "kalan pay = şüpheli X" çıkarımı atıf DEĞİLDİR. (2) Tuner portföyü özdeş-parça-bloklu kabuk verisinde değer üretmiyor — arama uzayı (sıra permütasyonu) tip-simetrisi yüzünden çökük; portföy bütçesi aile-farkındalı olmalı. (3) Reviewer'ın "efficacy" incelemesi (kablo gerçekten çalışıyor mu) en az korelasyon incelemesi kadar değerli — H1 olmasa sahte-güvenli 8× iddiası handoff'a girecekti.

#### [H-16] Dirty-region drop_map önbelleği — kabuk fine geçişi 4.1×
- **Durum:** ✅ GO (prototip; OPT-IN, default KAPALI, üretime BAĞLI DEĞİL) · **Tarih:** 2026-07-05 · **Kanıt:** `scripts/h16_on_analiz.py`+log (ön-analiz) + `scripts/h16_kapi.py`+log (kapı) + `tests/test_bin3d_dropcache.py` (donmuş-referans)
- **Ne:** Bir yerleştirme drop_map'i yalnız yerel değiştirir hipotezi ÖNCE ölçüldü: sızıntı 0/20 (fark tam (changed-bbox+(fw-1,fh-1)) penceresi içinde), bit-özdeşlik 20/20 (tamsayı max tek-redüksiyon → yerel yeniden-hesap = full), etkilenen aday oranı ort %2.7 / p90 %7.3. Sonra `Bin3D(drop_cache=True, drop_cache_cap_mb=300)`: footprint-anahtarlı Z_prev cache (anahtar `id(orient)` + güçlü-referans pinning + `is` guard — GC/id-reuse yapısal kapalı) + place-başına DISJOINT dirty-pencere yeniden-hesabı (birleşik-bbox denendi: uzak-köşe yerleşimlerde tüm grid'e şişiyordu, 201s→119s) + LRU eviction (doğruluk-nötr: atılan anahtar tam-hesaba düşer).
- **Sonuç (Deneme4 @0.5 wall_aware fine, 588 parça):** fine **493.8s → 119.4s = 4.1×**, 282.0 BİREBİR + yerleşim listesi BİREBİR, tepe RAM +0.03GB (cache 43.6MB, 0 eviction), hit %90.3. Toplam kabuk koşusu tahmini ~9.2dk → **~2.6dk**. Atıf sentezi: ölçülen cache-siz fine 493.8s / atıf 514s = 0.96 ✓.
- **Ön-analiz tahmini İYİMSERDİ (14-38s vs ölçülen 119s):** 40 zorunlu ilk-hesap (~34s) + 17 fallback (~14s) + hit-başına birikmiş kirlilik + `_best_position` full-Z argmin sabit tabanı (~71s). Kalan optimizasyon açığı: coarse-Z warm-start + artımlı argmin (marjinal, şimdilik gerek yok).
- **ÜRETİME BAĞLAMA ÖN-ŞARTLARI (reviewer PASS, 0 CRITICAL/HIGH; wiring ayrı review turu ister):** (1) MEDIUM-2 thread-safety — cache kilitsiz; şu an güvenli (drop_map yalnız tek-thread yollardan; parallel_decode OccupancyBin3D kullanıyor) ama wiring anında per-thread Bin3D garantisi VEYA lock ŞART. (2) drop_map dönen dizi cache açıkken SALT-OKUR (docstring'de invaryant; mevcut çağıranlar doğrulandı). (3) cap_mb yalnız Z bütçesi (orient pinning + log hariç). Test boşlukları (fallback dalı + z_clearance>0 incremental) fixer'la KAPANDI.
- **Ders:** Ölç-önce üç ön-koşulu (sızıntı/bit-özdeşlik/kirlilik) ucuza doğruladı ve prototip riskini sıfırladı; ama süre TAHMİNİ yine iyimserdi — maliyet modeli sabit ek yükleri (zorunlu miss'ler, argmin tabanı) saymalı. Kazanç yönü ve kalite-nötrlük yine de doğru çıktı: ön-analiz GO/NO-GO için güvenilir, süre bandı için değil.

> **HIZ ÖZET:** Birebir/kaliteyi-bozmayan KOLAY-ORTA NFV hız kaldıraçları TÜKENDİ (NFV zaten 3-5.5×). **2026-06-26
> ÜRETİM gerçek-veri yolu:** Plan2 default heightmap ÇÖKÜYORDU → **OOM-chunk (H-12) çökme giderildi (birebir)** +
> **çift-voxelize (H-13) ~2× (birebir)**. **2026-07-02: C1 voxelize hızı (H-14) 3.1× birebir KAPANDI** —
> fine adım 159s/parça → ~50s; NFV'de paylaşılan voxelize payı küçüldüğünden GPU uçtan-uca kazancı da büyür.
> **2026-07-05: H-15/H-15p KAPANDI — kabuk fine-yolunda sürenin %90'ı COARSE-TUNE'du (sentez 0.99);
> fix menu=dblf_only (opt-in, wall_aware tetiği) E2E'de kanıtlandı: 104.5dk → 9.2dk (11.3×), 282.0 BİREBİR.**
> **F3/K-19p rollout'unun "süre patlaması" ön-şartı fiilen KARŞILANDI** (K-19 bedeli 131dk → ~9dk).
> İlk iki atıf (K-20 "drop", ara "rafine") yanlıştı — süre atfı sentez-oranı ~1.0 ister.
> **2026-07-05 (aynı gün): H-16 dirty-cache PROTOTİP GO — fine 493.8s → 119.4s (4.1×), 282.0 + yerleşim BİREBİR,
> +0.03GB RAM — ve H-16w ile AYNI GÜN ÜRETİME BAĞLANDI: wall_aware tetiğinde `drop_cache=True`, E2E zincir
> 282.0 BİREBİR + 205s (~3.4dk) = H-15p'den 2.7×, K-19 orijinal 104.5dk'dan KÜMÜLATİF 31×; thread-safety
> yapısal (cache'li Bin3D _run_fine-lokal), reviewer PASS 0 C/H/M.**
> KALAN: pitch R6 (riskli) · bit-pack/BVH (marjinal) · argmin tabanı/coarse-Z warm-start (marjinal).

> **2026-07-09 GECE TOPLU GİRİŞ (detay: RESUME_2026-07-09.md):**
> **H-17 coarse drop_cache — GO, ÜRETİMDE (commit `df37736`):** py-spy canlı kanıt (6/6 örnek):
> tam-portföy süresi coarse tune'daki CACHE'SİZ `_drop_map_general`'de; H-16 cache yalnız fine'a
> kabloluydu. Fix: aynı bayrak iki aşamayı da açar; bit-özdeşlik 2 A/B testle (no-go dahil) kanıtlı.
> Saha: p3 sıkıştırma 47.9dk/seed (n8, cache'siz) → 38.8dk/seed (n24, cache'li). DERS: darboğaz
> tahminle değil CANLI PROFİLLE bulunur (py-spy alet çantasında).
> **K-25 n24 cross-dataset — TEYİT TAMAM:** d5 −%14.8 · p1 −%14 · p2 −%22.5 · p3 −%3.7 → 4/4 kazanç;
> bedel p2'de 2× süre (61→122dk). Kablolama kararı bekliyor (öneri: kalite yolunda default n24).
> **K-26 plan3 sıkıştırma@n24 — REKOR 685** (s13; 3/3 seed <706; Magics'e +%15.5). n24+fine_angle
> eski çift-çökme kombinasyonu None.exterior fix'iyle (voxelize dejenere-poz atlama + orient_rot
> hizalama; kök neden upstream: trimesh PR #2576) sorunsuz geçti.
> **K-27 AYRILABİLİRLİK PROBLARI:** d4 K-21 yerleşimi 5-yön düz-çekmede 413/588 KİLİTLİ (NFV d4'te
> yan-çekmeyle de kurtarılamıyor; kilit=ASY+ROBT). **plan3 NFV=606.9 no-go'suz (zincir 745'e −%18.5,
> Magics 593'e +%2.3!) ve +Z 71 kilit → 5-yön 20** — plan3 kenetlenmesi çözülebilir sınıfta. NFV'nin
> kaderi hoca kriter cevabında ("yan/döndürerek çıkarma kabul mü?"). ⚠️ söküm sanity kurgu hatalı
> (dummy sahne bug'ı) — 413/20 sayıları doğrulama koşusuyla mühürlenecek. NOT: solve_nfv NO-GO
> DESTEKLEMİYOR (kriter yeşilse ilk mühendislik işi).
> **K-28 plan1 HEDEFLİ-TİLT — GO, BÜYÜK KAZANÇ (2026-07-09 gündüz):** baseplate'e Rx/Ry sürekli-açı
> taraması (5..85°) → **260 → 135.0 LEGAL** (−%48.1; Magics 110.41'e +%135→+%22.3; clear 1.120,
> 0 kilit; kule artık bobbin yığını = Magics taktiği yakalandı). İLK KOŞU TUZAĞI: poz-eşiği "grid'e
> sığan min-z" alınınca no-go yüzünden YERLEŞEMEYEN düz poz (z=41) eşiği zehirledi → tüm tilt pozları
> elendi (260=260 boşa koşu); fix = eşik "çözümün FİİLEN kullandığı pozun z'si". Kademe 3 rotasyon
> programının ilk dilimi kanıtlandı; genelleme adayı: height-driver parçaya otomatik tilt.
> **NFV NO-GO DESTEĞİ ÜRETİMDE (commit `32ff414`):** OccupancyBin3D tam-yükseklik mühür + is_feasible
> açık reddi + GPU/decode/fine_settle plumbing; 4 test + 94 regresyon. **plan3 NFV @NOGO GERÇEK
> KOŞUL = 626.2** (+Z 73 kilit → 5-yön 14/109; Magics'e +%5.6; no-go bedeli +19.3). Hoca maili
> (9 soru + kriter a/b/c) kullanıcıda — HOCA_MAIL_2026-07-09.md.
> **Süreç dersleri:** 9-SAAT DERSİ (zincir scripti kapı-sonrası duman testi + detach .err monitörü
> şart) · harness arka plan task'ları öldürülüyor → uzun koşu HEP detach_run · pytest-xdist -n4 16dk
> · zincir kapısı log-paylaşımıyla zehirlenebilir (import edilen yardımcı, eski probun loguna yazdı
> → son satır BITTI'likten çıktı; yardımcılar log'suz/parametrik olmalı).

> **2026-07-09 GECE-2 (R1/R2 zinciri; detay RESUME + STRATEJI/06):**
> **K-29 kilit-tahliye — mekanizma GO, strateji NO-GO:** tahliye kilidi 20->0 yapti AMA plan3'un
> ~470mm dev parcalari tepeye binince 618->1088 (heightmap 735'ten kotu). Ders: tamir degil ONLEME.
> Uretim kablosu solve_nfv(repair_separability=) yine de mevcut (kucuk-parca kilitlerinde ise yarar).
> **K-30/31/32 exit_guard sagasi:** v1 (bbox-slab yaklasik test) sahada 10 kilit birakti (garanti
> TUTMADI) -> K-31 A/B: settle masum, H2 -> K-32/kod-incelemesi kok neden: slab testleri bbox-ICI
> ic-ice parmaklari goremiyor (NFV'nin dogal deseni!). **v2 EXACT (_GuardScene, _blocks tek dogruluk
> kaynagi) -> plan3 @yeni-kurallar 691.9, 5-YON KILIT 0/109, clearance 2.52 — ILK A2-LEGAL NFV,
> heightmap 735'i -43mm yener. YENI SAMPIYON.** Sokulebilirlik vergisi 618->692 = 74mm; azaltma
> adaylari denendi: **K-33 coklu-aday 691.9->680.0 (-11.9); K-33b retries 2->6 = SIFIR fark,
> telemetri guard[ilk=98 retry=11 fallback=0] -> tepe-kacisi YOK, vergi = coksayida kucuk
> 'ikinci-en-iyi yuva' bedeli = (b) kriterinde ~680 yapisal tabana yakin. VIDA SONU.** Kalan
> kaldiraclar: (c) dondurme-sokum modellemesi (R10 ONE CEKILDI — 618'i legallestirir, +%4.2)
> + R3 host-Rz. META-DERS: 'garantili' iddiasi bile sahada
> dogrulanmadan yazilmaz (K-30 tek kosuyla teoriyi yanlisladi, A1/A4 calisti).

> **2026-07-10 GECE-4 — K-34 R10 DONDURME-SOKUM = GO 🏆 (plan3 sampiyon 680→618.1):**
> `rotation_extract.check_separability_rot` — 5-yon peel + "mikro-kaldir(0-3vox) + yerinde
> dondur (adaptif aci merdiveni, tunel tol 2.5vox) + duz cek" sertifikasi; cekme testinde
> +1vox dilate (NN-buzulme yalanci-serbestligi TESTTE yakalandi: 60° sahte sertifika).
> Saga: **v1** 13/20 kilit buyuk-grid muafiyetiyle hic denenmedi (0 cert — hukum degil
> metodoloji boslugu) → **v2** muafiyet kapali + fail-telemetri: tum merdivenler rung1-5
> carpisma = **dilate'li gridlerde cift-arasi bosluk ~0, sokum fizigi OLCULEMIYOR** →
> **v3** SOKUM-FIZIGI grid'leri (`_erode_clearance` = morfolojik closing superset gercek
> parca, sound; superset property-test'li): **(b+c) kilit 0/109, 618.1 LEGAL** (clear 2.501).
> Tek sertifika kilit-tasi (171600021_02 lift3+Y−1°+−Y), kalan 19 dilate'li duz peel
> kaskadi. exit_guard 680.0'i −61.9mm yener; manuel 593'e +%4.2. 7.2dk rot maliyeti.
> **META-DERSLER:** (1) yerlestirme kurali (2mm bosluk) ile ekstraksiyon fizigi AYRI
> uzaylar — kural-tasiyan dilate gridle sokum olcmek yapisal yanlis-negatif uretir;
> (2) "0 sertifika" hukum degildir: once muafiyet/butce/neden telemetrisi (A4 teshis-once
> K-34'te iki kez calisti); (3) tek kilit-tasi acilinca kaskad — kilit sayisi buyuk gorunse
> de cozum tek parcada olabilir. ACIK: (b+c) kriter etiketi hoca onayina sunulacak
> (rapor iki metrigi de tasiyor); R3 host-Rz siradaki kaldirac.

> **2026-07-10 GUNDUZ — K-35 R3 HOST-RZ (plan1) = NOTR:** dik 260 → tilt 141.0 dogrulandi →
> +16 Rz/kombo pozla hostrz 141.0 (+0.0). Neden: baseplate kulesi tilt'le ZATEN kirik; tepe
> artik bobbin yigini (141'in driver'i) ve bobbin donel-simetrik → Rz alcaltamaz. R3'un dogru
> devami "height-driver'a genelleme" ama plan1'de yapisal taban ~141 gorunumu — ek odul yok.
> Log: k35_host_rz.log; STL plan1_nogo335_hostrz_hostrz_n24_141.0mm.stl.

> **2026-07-10 GUNDUZ — K-36 DERIN ARAMA = GO 🏆🏆 (plan3 598.5 CIFT-LEGAL REKOR):**
> (1) Seed taramasi OLU: s7/s13/s99/s2025 HEPSI birebir 618.1 — NFV plan3'te tamamen
> seed-DUYARSIZ (deterministik cekim noktasi; hoca "farkli dizilim" istegi icin seed
> kaldirac DEGIL). (2) **fine_pitch=2.0 bacagi: h=598.5, (b) kilit=0 VE (b+c) kilit=0 —
> sertifikasiz, siki metrikte bile temiz, kriter serhi GEREKMEZ.** clear 2.271; 31.5dk.
> Manuel 593'e +5.5mm (+%0.9). STL plan3_nfv_derin_p2.0_s42_598.5mm.stl.
> **DERS: pitch inceltme = kavite kalitesi kaldiraci KANITLI (2.5→2.0 = −19.6mm);
> asil kaldirac seed degil COZUNURLUK.** Uretim adayi: NFV kalite modunda fine_pitch=2.0
> default (eval kapisiyla, A1 — henuz kablolanmadi).

> **2026-07-10 GECE — K-37 R4 SOFT-NOGO (plan1) ARA SONUC / K-38 PITCH-1.75 (plan3) KUYRUKTA:**
> K-37 teshis: 141 tavaninin kok nedeni HARD no-go (duz baseplate 330x302 no-go y≤45 seridine
> ~12mm girer → duz poz imkansiz → egik baseplate taban yer). Hoca cevap 9 "Plan1 baseplate
> ornegi gibi cok ufak girisler kabul" → maske y-ust 45→33 (T=12mm giris seridi, SERHLI).
> **r4_duz = 129.0 LEGAL (clear 2.000, 0 kilit; 141'den −12; manuel 110.41'e +%16.8)** — iki
> bagimsiz kosuda teyitli. **r4_btilt = 129.0 (+0.0) — bobbin ara-aci tilt ODULSUZ** (K-35
> host-Rz notruyle tutarli: bobbin donel-simetrik, tilt/Rz alcaltamiyor). HUKUM: K-37 GO
> (kok-neden teshisi dogru, hard→soft no-go −12mm) ama plan1 soft-nogo altinda ~129 YAPISAL
> TABAN gorunumu — kalan 18.6mm fark manuel operatorun no-go'ya serbest-derinlik girisi +
> surekli-aci istifinde. STL: plan1_softnogo_r4_btilt_129.0mm.stl.

> **2026-07-11 GECE-5 — K-38 PITCH-1.75 (plan3) = NO-GO, MEKANIZMA DERSLI:** h=674.2
> (598.5'ten +75.7 GERILEME; 62.7dk; (b) kilit 23, (b+c) 0). Kok neden GRID degil
> **CLEARANCE KUANTIZASYONU**: dilation voxel-tamsayi → efektif bosluk =
> ceil(2.0/pitch)×pitch. pitch=2.0'da 1 vox = tam 2.0mm; 1.75'te 2 vox = 3.5mm →
> parcalar sanal sisti, yigin buyudu (olculen clear 3.737 hipotezi DOGRULAR).
> **DERS/KURAL: 2mm kuralinda kalite-pitch'i icin tek-voxel penceresi pitch>=2.0;
> (1.0, 2.0) araligi TAMAMEN zehirli (hepsi 2 vox = asiri-dilation); pitch<=1.0
> grid butcesini patlatir (1.0 → ~179M >> 34M). Sonuc: fine_pitch=2.0 = 2mm
> kuralinin YAPISAL optimumu, pitch kaldiraci TUKENDI.** 598.5 sampiyonlugu kalici
> (kirmak icin muhendislik degisikligi gerekir: alt-voxel/asimetrik dilation — dusuk oncelik).
> **K-39 v1 (plan2 NFV, auto-pitch) = CRASH + URETIM BULGUSU:** suggest_nfv_pitch
> ince kanatlar (7.2mm) icin ~0.69 secti → (486,432,625) float64 = 1001MiB
> MemoryError. **BULGU: suggest_nfv_pitch bellek guard'i dense float64 ara-array'i
> hesaba katmiyor** (gunduz fix'i). v2 (K-39b) pitch merdiveni 2.0→1.0 ile kuyrukta
> (K-38 dersi: 2mm kuralinda TAM pitch'ler yalniz 2.0 ve 1.0).
> **K-39b SONUC (plan2 NFV v2): YUKSEKLIK GO / LEGALITE NO — 532.0 INVALID.**
> p2.0: h=532.0 (8.7dk, 226/226, clear 2.002) = heightmap 618'den **−86mm (−%13.9)**,
> Plan2.jpg beklenti bandi (520-570) DOGRULANDI — ama (b) 61 / (b+c) 29 kilit:
> R10 rot-sokum 32'sini cozdu, 29 kaldi = plan2 kanat kenetlenmesi plan3'ten derin.
> p1.0 bacagi MemoryError, v1 ile BIREBIR ayni shape (486,432,625) → alloc acik
> fine_pitch'ten BAGIMSIZ (parca-bazli voxelize/oneri katmani supheli — ayni gunduz
> debug'ina dahil). SIRADAKI: K-41 exit_guard (plan3 K-30v2 emsali: onleme vergisi
> +50-90 beklenir → 580-620 bandi, 618 alti hala mumkun).

> **2026-07-11 GECE-5 — K-41 PLAN2 EXIT-GUARD = GO 🏆🏆 (plan2 YENI SAMPIYON 544.5 CIFT-LEGAL):**
> NFV @fine_pitch=2.0 + exit_guard=True → **h=544.5, (b) VE (b+c) kilit 0/226, cert 0
> — SERHSIZ; clear 2.004; 226/226; 29.6dk.** Heightmap sampiyonu 618.0'dan **−73.5
> (−%11.9)**; manuel 492.39'a +%10.6 (onceki +%25.5). Guard vergisi yalniz **+12.5**
> (ham 532.0 29-kilit INVALID → 544.5 kilitsiz) — plan3'te ayni vergi +66 idi.
> **DERSLER:** (1) Plan2.jpg manuel-yerlesim analizi ("acik=istif zekasi, tum pozlar
> eksen-hizali = NFV sinifi; beklenti 520-570") IKI KOSUDA dogrulandi — rakip yerlesim
> GORSELI tek basina yol haritasi cikartabiliyor (anatomi-istihbarati metodu);
> (2) guard vergisi aile-bagimli: plan2'nin cok-sayida orta-boy parcasi "ikinci-en-iyi
> yuva"yi ucuza buluyor, plan3'un dev parcalari bulamiyordu; (3) NFV rotasi artik
> 2 ailede kanitli (plan3 duvar-kavite, plan2 karma-istif) / 2 ailede zararli
> (plan1 duz-plaka K-40, d4 sokum-kilitli K-27). ACIK: uretime kablolama
> (family_routing'e plan2-ailesi NFV+guard rotasi — eval kapisiyla, A1).
> STL: results/plan2_nfv_guard_544.5mm.stl.

> **2026-07-11 GUNDUZ — K-42 PLAN2 ROT-DERIN = NO-GO:** ham 532.0 deterministik
> yeniden uretildi ✓; default R10 29 kilit/8 cert birebir teyit (131dk) ✓;
> DERIN butce (Z180/X60/Y60, lift 0-6, 2400s) yalniz 6 parca daha actı:
> **kilit 29→23, cert 11 (255dk)** → 532.0 INVALID KALDI, **544.5 guard
> sampiyonlugu KALICI**. DERSLER: (1) plan2'nin kalan kilitleri aci-butcesi
> sorunu DEGIL — gercek kenetlenme (kanat ic-ice deseni); "onleme > tamir"
> (K-29 dersi) bir kez daha dogrulandi, guard'in +12.5 vergisi bu 23 kilidin
> gercek fiyati. (2) MALIYET: derin rot denetimi 226-parcali sahnede ~4.3 saat
> (default 2.2 saat) — sokum-denetimi olcek sorunu var; buyuk sahnede rot
> denetimini yalniz mühürleme (final dogrulama) icin kos, arama dongusune koyma.

> **2026-07-11 GUNDUZ — K-43 PLAN1 MULTI-START = NOTR (siralama uzayi KAPALI):**
> r4_btilt kurulumu birebir + 7 kosu: ref_vol 129.0 · vol_tilt 129.0 ·
> fp_desc 132.0 · h_desc 146.0 · shuf7 129.0 · shuf13 135.0 · shuf99 129.0
> → **EN IYI = 129.0, hicbir siralama gecemedi** (K-08 "largest-first optimal"
> plan1'de de dogrulandi; 129 coklu-baslangicta cekim noktasi).
> **PLAN1 YAPISAL TABAN ARTIK KANITLI: 129.0 serhli / 141.0 serhsiz — 5 kaldirac
> ailesi olculdu ve kapandi (tilt K-28/37 · Rz K-35 · soft-nogo K-37 · NFV K-40 ·
> siralama K-43). Manuel 110.41'e kalan +%16.8 = surekli-poz uzayi (A1) +
> operatorun serbest no-go girisi — voxel-tabanli mevcut motorla erisimsiz.**

> **2026-07-11 GUNDUZ — K-44 DENEME5 NFV = GO 🏆🏆🏆 (PROJENIN EN BUYUK TEK-SET
> SICRAMASI: 338.4 → 223.5, −%34.0):** NFV @2.0 HAM bacak = **h=223.5, (b) VE
> (b+c) kilit 0/352, cert 0 — SERHSIZ CIFT-LEGAL, guard bile GEREKMEDI**
> (clear 2.000; 352/352; 20.3dk). Manuel 209'a **+%6.9** (onceki +%61.9!).
> **DERSLER:** (1) d5 anatomisi (216x ozdes ince cubuk 11x19x147) NFV'nin ideal
> sahasi cikti — tekrarli/orgu-istif aileleri kavite-decode ile kilitsiz sikisir;
> heightmap'in 338'i tamamen istif-verimsizligiydi. (2) NFV rota haritasi
> guncellendi: kanitli 3 aile (p3 duvar-kavite · p2 karma-istif · d5 tekrarli-cubuk)
> / zararli 2 (p1 duz-plaka · d4). (3) "En buyuk goreli acik = en buyuk firsat"
> sezgisi dogrulandi (kullanici yonlendirmesi). ACIK: family_routing'e d5-ailesi
> (yuksek-tekrar ince-parca) NFV rotasi + hoca sorusu "manuel 209 hangi bosluk?"
> STL: results/deneme5_nfv_ham_223.5mm.stl. Guard bacagi TAMAM: 244.0 legal
> (kilit 0/0) — ham kilitsizken guard gereksiz +20.5 vergi; guard-vergisi
> tablosu: p2 +12.5 · d5 +20.5 · p3 +66 (aile-bagimli). KURAL ADAYI: once ham
> kos, kilit CIKARSA guard'la tekrarla (K-41/44 birlesik recetesi).

> **2026-07-12 — K-46 DENEME4 NFV = GO 🏆🏆🏆🏆 (TARIHI: MANUEL ILK KEZ GECILDI):**
> ham NFV @2.0 = **231.5, manuel 250.24'un −%7.5 ALTINDA** — projenin ilk
> manuel-alti LEGAL sonucu. clear 2.018 (6000-orneklem DURUST olcum; d4'un eski
> 288'i 1mm kablosu + 3000-ornek iyimserligiyle INVALID'di), 588/588, 32.4dk.
> (b) kilit 363 (d4 klasigi — 62 ASY cani) → **R10 rot-sokum 39 SERTIFIKAYLA
> 0/588'e indirdi** (K-34 mekanizmasi buyuk olcekte ilk kez). Hoca kriteri
> (b)+(c) KABUL oldugundan tam-legal; rapor 5-yon-tek metrikte INVALID oldugunu
> + sokum-sertifika planini tasir (A2). **DERSLER:** (1) "d4 NFV yolu kapali
> (K-27 413/588)" hukmu ROT-SOKUMSUZ dunyaya aitti — R10 + erode-clearance
> gridleri hukmu TERSINE cevirdi; NO-GO kayitlari mekanizma degisince yeniden
> denenir (A7'nin sinir kosulu). (2) "288 yapisal tavan" hukmu heightmap'e
> ozguydu — cozucu ailesi degisince tavan tasinamaz. (3) Rot-sokum buyuk
> olcekte de pratik: 363 kilit → 39 cert + kaskad, denetim dahil ~1s/parca.
> GUARD BACAGI TAMAM: **276.5 CIFT-LEGAL SERHSIZ** (kilit 0/0 cert 0, clear
> 2.019 @6000-ornek) — sertifikasiz-sokum yedegi (hoca (c)'yi cekerse bile
> eski 288'den iyi). Guard-vergi tablosu FINAL: p2 +12.5 · d5 +20.5 ·
> **d4 +45** · p3 +66. ACIK: hoca paketine sokum-plani gorseli (39 cert).

> **2026-07-11/12 — K-45 URETIM KABLOLAMASI = GO ✅ (E2E PARITE PASS):**
> Sampiyon recetesi URETIME baglandi: `solve_nfv_kalite()` (pitch=clearance
> K-38 + kosullu exit_guard K-41/44 + rot recete-disi K-42) · WEB_MIN_CLEARANCE
> 1.0→2.0 (A2) · NO-GO uctan uca (plate.local.json/env → NFV+c2f+tuner/dblf
> uc yol; /plaka-ayar UI 4 alan) · plate.local.json canli 335x335x600+no_go.
> **A1 KANITI: E2E parite PASS — deneme5 gercek mail yolundan h=223.5 BIREBIR
> (352/352; recete izi: pitch 2.0, secilen=ham, guard_kosuldu=false, kilit 0;
> 26.2dk).** Tam suite 2641/2641. YAN URUNLER: (1) bayat-mock tuzagi (A9)
> reporting_wave mock'unda yasandi+yakalandi (imza-kilidi calisti);
> (2) parse_declared_total kenar-durum fix'i ("Deneme5 parcalari" yapisik
> rakami beyan saniyordu → (?<!\\w) + 5 test; guvenli-yon dususu dogruydu,
> false-positive maliyeti kalkti). SURECDERSI: detach sonrasi duman testi
> ATLANDI ve ilk E2E gece bosa gitti — 9-saat dersi istisnasiz uygulanir.
> **K-40 (plan1 NFV, hard+soft bacak) = SERT NO-GO:** iki bacak da 333.0 (2.6dk,
> pitch auto 0.6, 112/112) — heightmap 129.0'in 2.6 KATI. Ders: plan1 "duz plaka +
> cok kucuk parca" sinifi = heightmap/DBLF sahasi; NFV kavite-decode bu ailede
> zararli (F5 family_routing'in plan1'i heightmap'e yollamasi dogru davranis).
> Piramit-ici gomme/bel-kenetleme hipotezi NFV'nin mevcut decode'uyla gerceklesmedi.
> **plan1 NIHAI: 129.0 serhli / 141.0 serhsiz — tum kaldiraclar (tilt/Rz/soft-nogo/NFV)
> denendi, kalan fark manuel operatorun serbest no-go girisi + surekli-aci istifi.**

> **2026-07-12 — H-17 FFT BELLEK TAVANI = GO ✅ (URETIMDE; K-39 MemErr kapandi):**
> KOK teshis: MemErr (486,432,625)=1001MiB float64 = scipy fftconvolve'un
> next_fast_len'li TAM-BOY ic tamponu (336x336x600 occ + 151x97x26 kernel;
> 486=2*3^5/432/625 hepsi 5-smooth — pitch'ten "bagimsiz" gorunmesi padding
> yuvarlamasiydi). OLC-ONCE bulgulari (A4, bench_oa_vs_fft/bench_zchunk):
> (1) oaconvolve COZUM DEGIL — kernel plakaya oranla buyukken bloklar ise
> yaramaz, uretim boyunda tepe 5.4GB; (2) f32 sapmasi 4.4e-03 (esik 0.5'e
> ~100x marj var AMA buyuk N'de buyur — koddaki f64-zorunlu notu hakli, f32'ye
> GECILMEDI); (3) TEK-EKSEN dilim yonu kritik: kanat kernel'inde z-dilim
> 704MB, cubuk kernel'inde z-dilim 2.5GB ama x-dilim ~1GB. FIX: eksen-adaptif
> dilimli 'valid' konvolusyon (out/ker orani en buyuk eksen; cikti dilimleri
> bagimsiz -> karar BIREBIR, f64 hata ~1e-11 << 0.5). Butce SABIT+env
> (NFV_FFT_BUDGET_MB=768 CPU / NFV_FFT_GPU_BUDGET_MB=1536 GPU) — canli
> RAM'den TURETILMEZ (determinizm). Tam-boy tahmin butceye sigarsa ESKI yol
> -> mevcut @2mm sampiyonlar bit-ozdes. Kablolar: get_backend sarmali (seri+
> paralel CPU) + gpu_conv_valid_chunked (GPU-resident _blb_xybbox_gpu).
> KANIT: tests/test_h17_fft_chunk.py 14 yesil (GPU dahil) + E2E duman
> (zorla-dilimli solve_nfv yerlesim BIREBIR) + tam suite 2654 yesil (2 fail =
> webapp-async xdist flake, seri 8/8). ACTIGI KAPI: pitch 1.0 (2mm kuralinda
> ikinci TAM pitch) artik kosulabilir -> K-47.
> **2026-07-13 — K-47a DENEME5 @1.0 = GO 🏆 (YENI SAMPIYON 218.0; H-17'nin
> ILK SAHA KANITI):** ham NFV @pitch=1.0 = **218.0 CIFT-LEGAL SERHSIZ** (kilit
> 0/0 cert 0, clear 2.000, 352/352). 223.5'ten −5.5 (−%2.5); manuel 209'a
> +%4.3 (onceki +%6.9). K-38'in ongordugu kuantizasyon-vergisi geri alimi
> DOGRULANDI (2mm kuralinda ikinci TAM pitch calisiyor). **SURE BEDELI AGIR:
> solve 344.6 dk (5.7 saat) vs @2.0'in 20.3 dk'si (~17x)** — kalite/sure
> takasi regret raporunda ayri kolon olacak (ML plani Faz B). GPU %90-100
> doluydu (VRAM 5.8/6.1GB — H-17 dilimleme sayesinde sigdi; eskiden MemErr).
> STL: results/deneme5_p1_ham_218.0mm.stl. Guard bacagi GEREKMEDI (kilit 0).
> **K-47b PLAN2 @1.0 = ALTYAPI-FAIL (kalite hukmu DEGIL):** ham bacagi
> `MemoryError: std::bad_alloc` (C++ katmani) ile oldu — muhtemel kok:
> quality=max 24-oryantasyon KANAT gridleri @1.0 (f64 flip cache ~8x buyudu,
> 6GB VRAM/host asimi; d5'in kucuk cubuk gridlerinde sorun yoktu). p2
> sampiyonu 544.5 @2.0 KALIYOR. Tekrar secenegi (dusuk oncelik): CPU-yol
> (NFV_BACKEND=fast) + n_orientations=8 ile ~6-12 saatlik kosu — karar Eren'e.
> DERS: pitch-1.0 kapisi parca-grid boyutuyla olceklenir; buyuk-parcali
> setlerde once grid-cache bellek on-tahmini yapilmali (H-18 adayi).

> **2026-07-12 — R11 SUREKLI Z-KOMPAKSIYON INSA EDILDI (K-48 PROBU KUYRUKTA):**
> fine_settle (K-17) pitch/4 kafesinde durur; R11 kafesi tamamen birakir —
> mesh-gercek mesafeler (min_clearance ile AYNI orneklem+cKDTree ailesi),
> surekli z'de asagi oturtma. KRITIK kural: dusme hicbir komsu ciftini
> min(hedef=2.0+0.1 pay, MEVCUT mesafe)-eps altina indiremez — mutlak esik
> olsaydi kafesin tam-2.0mm yan bosluklari her dusmeyi bloklardi. Yasak-bolge
> kolonu tam-yukseklik oldugundan z-dusme onu ihlal EDEMEZ (analitik).
> Tarama kaba(0.5)->ince(0.02) ilk-ihlalde-dur (binary search DEGIL: yan
> komsu mesafesi dz'de monoton olmayabilir). Deterministik (sabit tohum/sira/
> adim). src/nesting3d/continuous_settle.py + tests/test_r11 7 yesil.
> UYARI: orneklem-tabanli (konservatif DEGIL) -> pay + cagiranin 6000-ornekli
> clearance kapisi ZORUNLU; kilit yeniden-denetimi sart (z-dusme kilit
> URETEBILIR — R2 dersi). **K-48 (k47b-kapili kuyrukta): d5 223.5 replay +
> R11 + kapilar (kazanc>0.5 / clear>=2.0 / kilit(post)<=pre, margin-0 @1.0
> ayni-metrik pre-post). GO ise uretim kablolamasi eval-gate ile ayri is.**

> **2026-07-13 — ML-PLANI SPRINT 1-2 (Faz A+B+C) = TAMAM (kod katmani; onaylanan
> plan: ~/.claude/plans/vivid-snacking-wadler.md):** Karar-yuzeyi gocu altyapisi
> kuruldu — (A) kxx_telemetri + backfill_v2: 17 elle-transkribe K-olcumu
> (log-alintili) + 118 otonom kaydi -> runs_v2 136 satir; registry deneme5(dev)/
> deneme6(held-out). (B) **KURAL-REGRET ILK OLCUMU: ortalama 71.5mm / maks
> 192mm** — plan1 192mm (KURAL NFV'YE YOLLUYOR, K-40 kanitina ragmen; kutu/
> plaka esikleri yakalamiyor -> CANLI ROUTING HATASI) · d5 120.4mm (kural
> heightmap diyor; en iyi 218.0 NFV@1.0) · d4 45mm kotumser (wall_aware kolu
> 2mm kuralinda OLCUMSUZ -> K-49 olcum adayi) · p2/p3 0.0 (kural optimal).
> nfv_kalite esdegeri uretim tetigiyle (5-yon b_kilit) turetildi — d4'te
> uretim ciktisi 276.5'tir, 231.5 sampiyonu rot-sertifika otomasyonu ister
> (UI cift-aday / R10-kablolama gerekcesi). (C) dataset_v2 (mevcut TrainingRow
> uzerine mod-duzeyi adaptor — gengap/gate/loo SIFIR degisiklik) + 4 yeni model
> (argmin yukseklik-regresyonu / regret-agirlikli lojistik / LOO-conformal
> guven kumeleri / mini-bagging) + mod_yarismasi (9 aday + KURAL baseline).
> **YARISMA ILK KOSUSU (n=5): argmin_ridge 70.9 ~ kural 71.5 basabas;
> tek-ornekli aileler LOO'da yapisal ogrenilemez -> MODEL DEVREYE ALINMADI
> (dogru karar kendiliginden cikti). Kritik yol = veri birikimi: Faz D dongusu
> + sentetik kabuk/cubuk jeneratorleri (01_VERI §6).** Testler: +28 yesil
> (5+6+5+12+3 yeni dosya + regret_raporu 3). Commit'ler: fafc860 (A),
> 346362a (B+C1), 8baf53d (C2+C3). SIRADA (Sprint 3, zincir-bitti kapili):
> eval_gate sampiyon-yolu NFV guncellemesi + baseline kilidi + registry guard
> + C4 challenger parametresi (default bit-ozdes).

> **2026-07-13 — K-48 R11 SUREKLI Z-KOMPAKSIYON PROBU (d5) = NO-GO v1 /
> MEKANIZMA-GO:** replay 223.5 birebir (17.5dk; mesh-gercek h=221.50 — voxel
> raporu 2mm sarma-payi tasiyor, R11'in avlanma alani). Kompaksiyon: 283/352
> parca oturdu, toplam dusme 1245.8mm, **kazanc 7.76mm (221.50->213.74),
> KILIT 0->0 (dusme kilit URETMEDI — R2 korkusu bu probda dogrulanmadi)**.
> ENGEL: clearance(6000)=1.591 < 2.0 -> kapi REDDETTI. Kok: R11 orneklem-
> tabanli mesafe (4000 nokta) en yakin cifti kacirdi; 0.1mm pay yetmedi —
> continuous_settle.py'nin kendi risk notundaki senaryo AYNEN. **KAPILARIN
> DEGERI: 7.76mm'lik 'kahraman sayi' uretime/rapora SIZAMADI (A1/A2).**
> FIX v2 (K-48b kuyrukta): pay_mm 0.4 + samples 8000 (beklenti: kazancin
> ~%60-80'i korunur, clearance >=2.0'a doner). Sure: R11 fazi 27.6dk (352
> parca) — uretim-uyumlu.

> **2026-07-13 — K-48b R11 v2 (d5) = GO ✅🏆 (R11 KANITLANDI):** pay 0.4 +
> samples 8000 fix'i CALISTI: **kazanc 4.54mm (221.50 -> 216.96), clearance
> 2.000 TAM, kilit 0->0** — v1 kazancinin %59'u korundu (tahmin bandi icinde).
> STL: results/deneme5_r11v2_217.0mm.stl. **STRATEJIK BULGU: @2.0+R11
> (~1.5 saat) = 216.96, pitch-1.0 sampiyonundan (218.0, 5.7 saat) HEM IYI HEM
> 4x UCUZ** — R11 kalite/sure takasinda pitch-inceltmeyi geride birakti.
> METODOLOJI SERHI (A10): 216.96 MESH-GERCEK olcu; eski sampiyonlar
> VOXEL-RAPORLU (voxel >= mesh, d5'te fark ~2mm). Manuel 250.24/209/593
> zaten Magics STL olculeri (mesh-gercek) oldugundan MANUEL kiyasta
> mesh-gercek DAHA ADIL; set-ici kiyaslarda taban belirtilmeli. YAN URUN:
> kxx_telemetri kablosunun ILK CANLI kullanimi (K-48b kendi v2 satirini
> yazdi: legal=216.96, kosu_id=K-48b/r11v2). ACIK: K-50 adayi = @1.0 layout
> (218.0) + R11 kombinasyonu (beklenti 213-215 bandi); R11'in uretim
> kablolamasi (solve_nfv_kalite post-pass'i, eval-gate'li) ayri is.

> **2026-07-13 — K-49 SERISI (p3 R11) = GO 🏆🏆 (PLAN3 MANUEL GECILDI —
> PROJENIN IKINCI MANUEL-ALTI SETI):** K-49c (pay 1.2 + samples 12000):
> **596.50 -> 589.76 (kazanc 6.74mm) | clear 2.186 | kilit 0->0 | manuel
> 593.0 -> GECILDI (−3.24mm, −%0.55)**. STL: results/plan3_r11c_589.8mm.stl;
> telemetri v2 satiri otomatik. Yol haritasi: K-49a v3 (pay 0.4) kazanc
> POTANSIYELINI olctu (17.56mm, 578.94!) ama clearance 1.231'e kacti (buyuk
> yuzeyde 8000 ornek seyrek — pay yetmedi) + kilit denetimi subdivide ucgen
> patlamasiyla MemErr (52M ucgen, 3.5GB) -> fix: _kilit_5dir_meshes
> method=slice (denetim 200dk'dan 2.4dk'ya!). DERSLER: (1) R11 orneklem
> yogunlugu yuzey ALANIYLA olceklenmeli (d5 kucuk-yuzey gecti, p3 buyuk-yuzey
> kacirdi); (2) pay/kazanc takasi ailebagimli: d5'te pay 0.4 yetti (%59 koru),
> p3'te 1.2 gerekti (%38 koru); (3) subdivide voxelize yuksek-yuzlu STL'de
> yasak — slice. SUREC KAZALARI (kayit): v2 7h kosusu olduruldu (kose-bulut
> patlamasi -> VERTEX_CAP 1500 fix); k49c regex-turetme self-gate deadlock'u
> (ders: script turetme ACIK YAZIMLA). ACIK: K-49d (R11 v4 dogrula-ve-rafine,
> pay 0.15 + kesin 2.00 oturma) KOSUYOR — beklenti 582-586 bandi (pay kaybini
> geri alir); ayrica d4/d5/p2'ye R11 v4 uygulanmasi (K-50 serisi adayi).
> **K-49d SONUCU (ayni gece) = GO 🏆🏆🏆 (v4 KANITLANDI, YENI P3 SAMPIYONU):**
> agresif kompakt (pay 0.15): 596.50 -> 577.62 (kazanc 18.88) + rafine dongusu
> 5 tur / 0.8 dk'da clear'i tam 2.033'e oturttu, YUKSEKLIK HIC ARTMADI ->
> **577.62 | clear 2.033 | kilit 0->0 | manuel 593'e −15.38mm (−%2.6)**.
> STL: results/plan3_r11d_577.6mm.stl. v4 payli-v3'ten 12.14mm derin —
> "pay tamponu yerine dogrula-ve-rafine" mimarisi (Eren'in "3.2 cok, optimum
> degil" itirazi) SAHADA DOGRULANDI. Rafine ucuz (tur basina bir 6000-ornek
> olcum); sonlanma garantili (dz>=0 klamp). SIRADA: K-50 seri (d5/d4/p2'ye
> v4) -> 4-set dagilim tablosu -> eval-gate -> uretim terfi dosyasi.

> **2026-07-14 — K-50 R11-v4 COK-SET SERISI = TAMAM (A5 dagilim dosyasi;
> 3 GO / 1 NO-GO):** tek proses seri (d5->d4->p2), her sette sampiyon-recete
> replay birebir + v4 (pay 0.15 + dogrula-ve-rafine) + kapilar + otomatik
> telemetri. SONUCLAR (mesh-gercek):
> **d5: 221.50->214.64 GO 🏆 (kazanc 6.86; clear 2.000; kilit 0->0; rafine
> 0 tur — pay 0.15 bile yetti; manuel 209'a +%2.7; YENI SAMPIYON; STL
> deneme5_r11v4_214.6mm.stl)** ·
> **d4: 229.33->220.69 NO-GO (kazanc 8.64 VARDI ama kilit 11->12 — kompaksiyon
> 1 parca kilitledi, kapi REDDETTI; sampiyon 231.5 KALIR; not: pre=11, K-46'nin
> 363'u dilated-grid metrigiydi, helper margin-0 @1.0 olcer — pre/post ayni
> metrik, delta durust)** ·
> **p2: 542.20->541.44 GO (kazanc yalnizca 0.76; clear 2.003; kilit 0->0;
> guard'li kanat yerlesimi zaten sikiymis; rafine 8 tur)**.
> p3 (K-49d) ile dagilim: **+18.9 / +8.6(red) / +6.9 / +0.8 — kazanc AILE-
> BAGIMLI** (kule yuksekligi x arayuz sayisiyla olcekleniyor; alcak/genis
> istifte kirinti). DERSLER: (1) v4 rafine dongusu 4 sette de ucuz ve stabil
> (0-8 tur, <1.5dk); (2) d4 tipi kilit-hassas ailede v5 ihtiyaci = kilit-
> farkindali geri-alma (yeni kilitlenen parcanin dz'sini geri al — 8.64'un
> cogu kurtarilabilir, ADAY); (3) uretim kablolamasi TEK-TARAFLI olmali
> (fine_settle sozlesmesi gibi: kapilardan gecemezse R11 sonucu atilir,
> coarse korunur — boylece d4'te bile guvenli). SIRADA: tam suite ->
> eval-gate -> solve_nfv_kalite post-pass kablosu (insan onayiyla).

> **2026-07-14 — SENTETIK COGALTMA + YARISMA-2 = MODEL KURALI ILK KEZ YENDI 🎉:**
> (Eren talimati "sentetik cogaltmayi baslat") 01_VERI §6 uygulandi:
> repeat_rod_mix (d5-sinifi, YENI jenerator) + perturb_instance (qty +-%30 /
> olcek +-%10 jitter) + mevcut-ama-hic-kosulmamis shell_bells & hollow_tubes
> ilk kez kosuldu. **44 instance x 2 arm (heightmap=_run_champion URETIM
> PARITESI / nfv=solve_nfv_kalite) = 88 satir, 0 hata, ~1.5 saat** — egitim
> tablosu 5 -> 49 instance. **YARISMA-2 SONUCU (LOO-regret, n=49):
> regret_logistic 9.66mm (acc .837) < mini_bagging 9.81 < karar_agaci 10.0
> < ... < KURAL 17.0mm (acc .306) — kural-kanamasi %43 azaldi.** Aile
> kirilimi: kural long_rod'da 17.15 ve solid_bulk'ta 18.73 kaniyor (model
> ~0) = plan1/d5 canli-hata bulgusunun sentetik teyidi; thin_shell'de KURAL
> hala iyi (6.77 vs 8.37) -> C4 allowlist tasarimi dogrulandi (model yalniz
> kanitli ailelerde konusmali). Overfit bayragi tum adaylarda temiz.
> argmin_ridge n=49'da cokdu (19.26 — dogrusal model yetersiz, ADAY-DISI).
> Kanit: results/mod_yarismasi_v2.json. **PROMOTE = INSAN KARARI (Y-1/Y-4,
> Eren'e sunuldu):** oneri = regret_logistic + guvenli_aileler allowlist
> {long_rod, solid_bulk} ile C4 challenger'a baglamak (Sprint 3).

> **2026-07-15 — K-52 D4 ROT-KABUL = GO 🏆🏆 (YENI d4 SAMPIYONU 220.69; hoca
> 2026-07-14 sokum-toleransi kriteri ilk kez uygulandi):** K-50'nin kilit
> kapisinin reddettigi R11v4 adayi (220.69, kilit 11->12) hoca cercevesiyle
> yeniden yargilandi (scripts/k52_d4_rot_kabul.py, log scripts/
> k52_d4_rot_kabul.log): replay 588/588 (18.4dk) -> R11v4 229.33->220.69
> clear=2.006 (393dk; K-50 beklentisiyle BIREBIR — determinizm kaniti) ->
> ROT denetimi (margin-0 @1.0 re-voxelize + check_separability_rot, butce
> 1200s, erode (2,2)): **kilit=0/588, 5 rotasyon sertifikasi, 1.4dk** ->
> SOKUM-PLANLI KABUL. **Manuel 250.24 -> -%11.8** (onceki sampiyon 229.33
> -%8.4 idi; +8.64mm). STL results/deneme4_r11v4_rot_220.7mm.stl; telemetri
> v2 kosu_id=K-52/rot-kabul. DERSLER: (1) 5-yon metriginin "kilitli" dedigi
> 12 parca rot'ta TAMAMEN acildi -> 5-yon d4 ailesinde gereginden sert,
> hoca cevabinin cikarimi olculdu-dogrulandi; (2) rot denetimi korkulandan
> COK ucuz: 588p @1.0 = 1.4dk (K-42'nin 2-4 saati eski parametre setiydi;
> max_grid_vox=800 + erode (2,2) ile sertifika araması kisa) -> rot-kabul
> kapisinin uretim maliyeti ihmal edilebilir; (3) surec: ilk kosu
> erode_clearance_vox=2 (int) TypeError bombasi tasiyordu (lazy unpack —
> 6.5 saat sonra patlayacakti); statik incelemeyle yakalandi, restart
> maliyeti ~35dk; dz-sigorta (settle sonrasi npz snapshot) artik standart
> pratik. KABLO DURUMU: rot-kabul kapilari kodda hazir (`1fab9e0`, her yerde
> default KAPALI) + dz export kablosu canli (`7add014` — R11/rot kazanci
> artik musteri STL/GLB'sine yansiyor) -> **pipeline'da rot_kabul="auto"
> acilmasi EREN KARARI bekliyor.** SIRADA: tam suite -> k51b.

> **2026-07-15 — K-51b BASELINE KILIDI = KURULAMADI (exit 4, dogru guard;
> BULGU-DOLU NO-GO):** eval_gate v2 sozlesmesi (335+nogo/2mm/NFV-fast/6000)
> dev-set baseline'i kilitleyemedi cunku URETIM-DEFAULT yolu 3 sette INVALID:
> **plan1 INV (111/112 + 87 kilit; routing hala NFV'ye yolluyor — Sprint-1
> canli-hata teyidi) · plan2 INV (59 kilit, ham 706.5; rekor 544.5 quality=max
> idi) · plan3 INV (63 kilit, ham 754.5; rekor 577.6) · deneme4 287.0 LEGAL
> (kilit 0, clear 2.016; ama routing hala heightmap/wall_aware@0.5 — sampiyon
> 220.69 NFV+rot yolu DEGIL).** Kanit: results/eval_gate_last.json; log
> %TEMP%/detach_k51_baseline_kilit.out. DERSLER/ACIK KARARLAR: (1) fast-vs-max
> ucurumu buyuk (%25-30 + kilit patlamasi) — "uretim yolu fast" sozlesme
> tercihi baseline'i INVALID'e dusuruyor; (2) **eval sozlesmesi hoca-kabul
> kriterinden SERT kaldi**: 5-yon kilit=0 sarti rot-sokum kabulunu (hoca
> 2026-07-14; K-52 12/12 acildi; maliyet 1.4dk/588p) gormuyor — A2'ye
> rot-sokum katmani eklenmesi EREN KARARI (eklenirse plan2/3 kilitleri
> yeniden yargilanir, baseline kurulabilir); (3) d4 routing guncellemesi
> (heightmap->NFV+rot) ayri karar; (4) challenger kiyasi baseline olmadan
> raporlanamadi. SIRADAKI ADAY: k51c = ayni sozlesme + rot-sokum denetimli
> kilit metrigi (Eren onayiyla) veya quality=max baseline.

> **2026-07-15 — EREN KARARLARI ISLENDI: A2 ROT-SOKUM KATMANI + d4 ROUTING
> NFV+rot (kod canli, k51c bekliyor):** (a) **A2 katmani** (ANAYASA A2
> guncelleme-2): eval_gate 5-yon kilit>0'i tek basina RED saymaz —
> `kilit_rot_meshes` (K-52 tabani @1.0, butce 1200s) yeniden yargilar; rot
> kilit=0 -> SOKUM-PLANLI legal (`sokum_planli`+cert raporda); hata/butce
> konservatif eski RED; kilitsizde HIC kosmaz (K-42 maliyet dersi).
> (b) **d4 routing**: predict_nfv_benefit `rot_sokum` parametresi —
> family katmaninda thin_shell artik NFV+rot yoluna (K-46/K-52: 220.69 <
> 287.0); tube kanitsiz -> eski yol. Pipeline default ACIK
> (`rot_sokum_routing`, senaryo anahtariyla kapatilabilir); eval ayni
> routing'le kosar. (c) **rot_kabul "auto" tavani R11'den AYRISTI**:
> `ROT_KABUL_AUTO_PARCA_TAVANI=600` (rot denetimi ucuz — K-52 588p=1.4dk;
> asil sigorta sure butcesi) — R11 kompaksiyon tavani 150 kalir (K-50:
> 588p=375dk). (d) **eval uretim paritesi tamamlandi**: kapi NFV dalinda
> r11="auto"+rot_kabul="auto" kosar ve r11 uygulanirsa dz-KAYMIS sahneyi
> olcer (yukseklik r11-sonrasi, kilit dz'li meshlerde kilit_5yon_meshes;
> musteri STL paritesi `7add014`) — eski r11=False karari dz'nin height'a
> yansimadigi doneme aitti. TDD: test_eval_gate 29 / test_adaptive_params
> +5 / test_rot_kabul +3 / test_demo_pipeline +2. ACIK KALAN: fast-vs-max
> ucurumu (gozcu quality=max kosuyor, sozlesme fast — Eren karari) +
> plan1'in NFV'ye routing'i (kural canli-hatasi, model allowlist disi).
> SIRADA: A9 tam suite -> k51c (`scripts/k51c_baseline_kilit.py`).

> **2026-07-15 — K-51c: ROT-SOKUM KATMANLI SOZLESME ILK OLCUM (exit 4 —
> plan1 eski-routing INVALID'i baseline'i engelledi, kalan 3 set LEGAL):**
> plan2 **542.5 SOKUM-PLANLI** (219 kilit -> rot 0, 4 cert; 933.9s) — max
> rekoru 541.44'e +%0.2, **fast-vs-max ucurumu plan2'de rot-kabulle KAPANDI**
> (eski k51b: INVALID 59 kilit). plan3 **601.9 SOKUM-PLANLI** (3 kilit ->
> rot 0, 1 cert; 5740.6s=96dk — fast NFV plan3'te YAVAS, acik yon) — max
> 577.62'nin +%4.2 ustu ama artik LEGAL (k51b: INVALID 63 kilit). deneme4
> **276.5 SOKUM-PLANLI (338 kilit -> rot 0, 0 CERT!** — tum kilitler erode'lu
> sokum fiziginin PEEL'iyle acildi, rotasyon hic gerekmedi: 5-yon metriginin
> dilate-kaynakli asiri-sertliginin kaniti; 454.9s) — eski heightmap-fast
> 287.0'dan -10.5mm (yeni NFV+rot routing k51c'de canliydi); sampiyon 220.69
> (max+R11) ile fark %25 = d4'te fast-vs-max acik. plan1 INVALID 111/112
> (tilt-zorunlu kapi k51c BASLADIKTAN SONRA yazildi). Kanit:
> results/eval_gate_last.json; scripts/k51c_baseline_kilit.log.
> SIRADAKI: k51d = ayni sozlesme + tilt-zorunlu kapili routing (plan1 ->
> heightmap-fast) -> 4 set legal ise BASELINE ILK KEZ KURULUR.

> **2026-07-16 — K-53 POZ TARAMASI TAMAM (AILE-BAGIMLI karisik hukum; kanit
> results/k53_poz_taramasi.json + scripts/k53_poz_taramasi.log):**
> **d4 (kabuk-kavite): GO-egilimli** — n=8 276.5 / n=12 276.5 (kazanc 0!)
> / n=16 261.0 (-%5.6, 25dk) / n=24 250.0 (-%9.6, 38dk; hepsi sokum-planli
> legal, kilit 369-555 rot'la 0). **plan3 (duvar-kavite): NO-GO** — n=12
> 622.0 (+%3.3 KOTU) / n=16 627.0 (+%4.2 KOTU) vs n=8 601.9; ilk-N master
> pozlar (egikler dahil) plan3 duvar-istif dengesini BOZUYOR. DERSLER:
> (1) poz kaldiraci yalniz d4-ailesinde ve 16'dan sonra aciliyor (12 bosa);
> (2) "kac poz"dan cok "HANGI pozlar" — tarihsel kiyas: d4 AX24-max ham
> 231.5 (K-46) < ilk-24 250.0 -> AX24 eksen-hizali seti ilk-N master'dan
> ~18mm iyi; plan3'te fast n=8 601.9 zaten K-36 AX24-ham 598.5 PARITESINDE
> -> plan3'un rekor farki (577.6) POZ DEGIL R11 farki. SONUC/ADAYLAR:
> (a) d4-benzeri ailede oneri = AX24 setine gecis (fiilen quality=max poz
> seti; eval kapisiyla), plan3'te poz isi YOK; (b) 220 hedefi icin asil
> kaldirac R11'in hizlandirilmasi (K-55: settle/clearance orneklemesi saf
> CPU — paralel/GPU ile ayni matematik, bit-ozdes sonuc) + R11'li "kalite
> modu" opsiyonu; (c) genelleme aile-kosullu kalir (A5), kor-test held-out
> sinavi bekliyor.

> **2026-07-16 — K-53c: d4 @ AX24 POZ SETI = GO (Eren karari (a); kanit
> results/k53c_ax24_d4.json + scripts/k53c_ax24_d4.log):** eval sozlesmesi
> (335+nogo+2mm+rot-kabul, seed=42) altinda deneme4 n_orientations="ax24"
> -> **231.5mm SOKUM-PLANLI LEGAL** (588/588, clearance 2.018, 553 kilit
> -> rot 0, 5 cert; 1742s=29dk). Kiyas: n=8 276.5'ten **-45.0mm (-%16.3)**;
> ilk-24 250.0'dan -18.5mm — "HANGI pozlar" dersi OLCUMLE dogrulandi (AX24
> egiksiz seti, egikli ilk-N master'i ezer); K-46 max ham 231.5 ile BIREBIR
> PARITE (fast sampiyon yolunda AX24 = max kalitesi, r11 auto-tavan disi
> 588p>150). Sure de LEHTE: 1742s < ilk-24 2272s (egik pozlarin decode'u
> bosa masrafmis). Sampiyonla (220.69 = max+R11) kalan fark 10.8mm = SAF
> R11 -> K-55 hizlandirmanin degeri netlesti. MEKANIZMA: evaluate_set /
> _run_champion artik n_orientations="ax24" kabul eder (_poz_seti_cevir:
> "ax24" -> quality="max" cevirisi, NFV dali; heightmap dalinda acik red;
> int/None bit-ozdes; +5 test). SIRADAKI: aile-kosullu uretim default'u
> (d4-benzeri kabuk-kavite ailesinde AX24, digerlerinde n=8) — 4-set
> eval_gate PASS kapisiyla kablolanir; plan3'te poz isi YOK (K-53).

> **2026-07-16 — K-53d: AILE-KOSULLU AX24 DEFAULT KABLOLANDI + 4-SET EVAL
> DOGRULADI (kanit scripts/k53d_ax24_default_eval.log +
> results/eval_gate_last.json):** MEKANIZMA: `ModeDecision.nfv_quality`
> alani (default "fast" = geriye uyum) — rot-sokum thin_shell dalinda
> "max" (AX24) onerilir; demo_pipeline (payload nfv_quality=None ->
> oneri dolar, acik deger EZER) + eval_gate (_run_champion, override yoksa
> dec.nfv_quality) ayni default'u okur = uretim paritesi. 4-SET SONUC:
> **d4 231.5 SOKUM-PLANLI (553 kilit->rot 0, 5 cert; 1990s) = K-53c
> BIREBIR — fast default'u 276.5'ten -%16.3 iyilesti** · plan2 542.5
> (4. kez birebir) · plan3 601.9 (3. kez birebir; 5835s) — thin_shell
> disi aileler BIT-OZDES = kablolama regresyonsuz · plan1 INVALID (K-54
> bilinen bloker, bu isten bagimsiz) -> exit 4, baseline yine kilitlenmedi
> (K-54'e bagli). TDD: test_adaptive_params +2 / test_eval_gate +2 /
> test_demo_pipeline +2 (sarici desenle gercek solve); suitler yesil
> (28+36+58). d4 sampiyon zinciri artik: fast-default 231.5 -> +R11
> "kalite modu" 220.69 (fark 10.8mm = saf R11; K-55 hizlandirma adayi).

> **2026-07-17 — K-55: R11/CLEARANCE HIZLANDIRMA = GO (bit-ozdes, d4
> uretim-olcegi ~9x; kanit scripts/k55_d4_hiz_paritesi.log +
> scripts/k55_bench_settle.py):** MEKANIZMA (karar DEGISTIRMEZ, yalniz hiz;
> veri-tipine bakan dal YOK — Eren overfit sorusu 2026-07-16): (1) cKDTree
> .query cok-cekirdek `workers` — kesin NN mesafeleri worker'dan bagimsiz;
> OLCUM 16-cekirdek 48p@12000: w=4 30.8s / **w=6 21.0s optimum** / w=8 24.7
> / w=-1 35.9 (asiri-abonelik ZARAR) -> politika min(6, cores) + R11_WORKERS
> env, TEK KAYNAK clearance.py; (2) `_uygun` icin distance_upper_bound
> budamasi — KESIN esdeger (sonlu donen d kesin; min<esik <=> (d<esik).any();
> sinir d==esik iki yolda False; en kotu durumda tam sorgu maliyeti =
> asla yavaslatmaz); (3) en-dar-esik-once komsu siralamasi (AND
> sira-bagimsiz). SENTETIK: 97.1s -> 21.0s (4.6x), dz_md5 BIREBIR.
> URETIM KANITI (K-52 akisi birebir replay): h 229.33 -> **220.69 BIREBIR**
> · clear **2.006 BIREBIR** · rot kilit **0/588** (5 cert; 2.7dk) · settle+
> rafine **393dk -> 43.5dk (~9.0x)** — es-zamanli webapp suiti yukune ragmen;
> gercek veride budama sentetikten COK kazandirdi. NOT: replay (solve_nfv
> max) 75.3dk (K-52 18.4dk — CPU cekismesi; R11 disinda, K-55 kapsami degil).
> TDD: test_r11_continuous_settle +4 (workers esitligi / scipy sozlesme /
> min_clearance workers / env siniri). ETKI: R11 "kalite modu" opsiyonunun
> onundeki sure engeli kalkti (d4 zinciri fast 231.5 -> +R11 220.69 artik
> ~45dk); R11 auto-tavani (150) yeniden degerlendirilebilir (ADAY).
> ACIK: hizlanma CARPANI aile-bagimli olabilir (sikisiklik/bulut boyutu) —
> k55b adayi: d5/p2 R11 replay hiz+parite olcumu.
> gelistirici-lokal plate.local.json'a ACIKTI (tam suite 2841/2842'de tek
> kirmizi; K-53c+d diff'inden BAGIMSIZ — stash-bisect'le kanitli):**
> test_coarse_path_unchanged... senaryosu no_go_bounds GECIRMIYOR ->
> run_pipeline configs/plate.local.json'un no_go'sunu cozup sentetik
> 250x250 plakaya hocanin no-go kolonunu uyguluyordu; 86.4 referansi
> no-go'suz dunyadan (a274628, 2026-07-06 — plate.local'e no_go 07-11'de
> K-45 ile girdi), no-go'lu SA 79.2'ye sapiyor (ilginc: kisit ALTINDA
> daha iyi lokal optimum = 86.4 referansi zayif optimum sinyali).
> FIX: resolve_no_go teste monkeypatch'le None (test_ingest_zip_stl
> izolasyon deseninin no-go karsiligi); 86.4 izole yesil. NOT:
> test_plaka_ayar_post gercek configs/ dosyasina yazip finally'de geri
> yukluyor (mtime yeniler, icerik korunur) — xdist/paralel kosuda yaris
> riski acik yon. DERS: "deterministik referans" testleri ortam-lokal
> config'leri (plate.local.json ailesi) SIFIRLAMADAN kosulmamali.

> **2026-07-17 — K-54: GRACEFUL CLEARANCE-CAP C2F'E TASINDI = plan1 ILK KEZ
> URETIM YOLUNDAN TAM-LEGAL (302.8mm; kanit results/eval_gate_last.json +
> tests/test_coarse_to_fine.py k54 testleri):** TESHIS (tek-parca probe,
> scratchpad k54_teshis.py): suclu COARSE asamasi — baseplate_v2 330.2mm @
> coarse 3.048 + margin 1 dilation -> 111 > 109 voxel, 4 pozun 4'u de
> tasiyor -> dblf acik-hatasi (dblf.py place_in_order assert) TUM cozumu
> olduruyor; FINE @1.016 + margin 2 = 329<=329 TAM sigiyor; no-go suclu
> DEGIL (margin=0'da poz3 yerlesiyor; NOGO_STD x[152.5,185.5]xy[0.2,45]
> kose yamasi). FIX: web yolundaki M3 graceful cap (demo_pipeline
> 2026-07-06) c2f'e tasindi — `cap_margin_to_plate` formul web'le BIREBIR:
> fit=int((plate_min-max_part)/(2*pitch)), margin>fit ise fit'e kis (0'a
> kadar); `_voxelize_with_fallback` (+adaptif dal) + fine margin ayni cap'i
> uygular (plate dims verilmezse cap YOK = eski cagiranlar bit-ozdes);
> telemetri `CoarseToFineResult.clearance_capped` (tetiklenmeyince None).
> SONUC: plan1 **302.8mm LEGAL — 112/112 yerlesim, kilit 0(!), clear 2.042,
> 283.4s** — coarse cap yalniz ARAMAYI etkiledi, fine margin=2 tam korundu
> (fiziksel clearance kaybi YOK; min_clearance 2.042 kaniti). Onceki
> durumlar: k51c 111/112 INVALID -> k51d/k53d EXCEPTION crash. TDD: +6 test
> (cap birim + plaka-boyu-parca entegrasyon RED->GREEN + no-trigger
> telemetri-bos); komsu 155 + demo_pipeline/tuner 75 yesil. ETKI: 4-set
> BASELINE onundeki SON bloker kalkti -> k51e tam-baseline adayi. NOT:
> 302.8 plan1'in ILK uretim-yolu sayisi (129 serhli = ozel egik-plaka SA
> deneyi, kiyas tabani degil); tilt pozlari n=4 setinde yok — plan1 rekor
> isi ayri aday (K-43 multistart / hedefli-tilt mirasi).

> **2026-07-17 — K-51e TAMAM = BASELINE ILK KEZ KILITLENDI (exit 0; kanit
> results/eval_gate_baseline.json created 2026-07-17T17:05 + k51_baseline_kilit.log):**
> 4/4 set LEGAL — plan1 **302.8** (112/112, kilit 0, clear 2.042; 356s;
> K-54 kanit kosusuyla bit-ozdes) · plan2 **542.5** (4. kez birebir; 1188s) ·
> plan3 **601.9** (3. kez birebir; **1640s=27dk** — onceki 96-155dk YUK
> altindaydi, munhasir-kosuda 3-5x fark = K-57(a) kaniti) · deneme4 **231.5**
> (K-53d birebir; 553 kilit->rot 0, 5 cert; 2095s). Toplam ~88dk (sakin
> makine). ETKI: tune_bo exit(2) on-sarti ACILDI; bundan sonra her motor
> degisikligi B2 esikleriyle bu tabana kiyaslanir (A1/A8). Kosu C: agacindan
> (`fc63f6a` commit-temiz; D:\ie488 agaci bayat — K-53d emsali). NOT:
> baseline json results/ gitignore'unda IZLENMIYOR — degerler burada kayitli;
> dosyanin `git add -f` ile dondurulmasi Eren karari. SIRADAKI ADAYLAR:
> K-57 kapi hizlandirma (set-paralel; §5) + K-56 plan1 hedefli-tilt (§5).

> **2026-07-17 — K-57b UYGULANDI + ILK OLCUM (parite 3/4 kanitli; OOM dersi
> + seri-kurtarma eklendi):** eval_gate'e `--parallel N` (pencere-N cocuk
> surec; 0=KAPALI sirali yol BIREBIR, testli) + `--json-out` cocuk modu
> (LAST/kiyas/baseline yalniz ebeveynde — dosya yarisi yok; held-out bakisi
> ebeveynde TEK kayit A3). OLCUM (--parallel 2, kullanici makineyi aktif
> kullanirken): **plan1 302.8 + plan2 542.5 + d4 231.5 baseline'la BIT-OZDES**
> (surec-izolasyon parite tezi DOGRULANDI) · WALL 59dk (sirali 88dk, −%33) ·
> plan3 OOM ("Unable to allocate 1.19 MiB" = RAM tukenmesi; plan2||plan3 iki
> RAM-agir NFV cakisti + kullanici uygulamalari). FIX: iyimser-paralel +
> SERI KURTARMA — EXCEPTION'li set digerleri bitince tek basina 1 kez
> yeniden kosulur (duz INVALID denenMEZ — deterministik olcum); en kotu
> durum o set icin sirali maliyet, parite bozulmaz. TDD toplam +7 test
> (43/43). GPU teyidi (K-57c kismi): capabilities gpu=True/fp64=True, cocuk
> cupy yukluyor; per-decode strateji telemetrisi ACIK YON. KALAN: kurtarmali
> tam parite kosusu (4/4 + wall; sakin makinede) — sonra K-57 kapanir.
> ADAY: NFV_FFT_BUDGET_MB cap'inin paralel cocuklara gecirilmesi (H-17
> dilimli konvolusyon bit-ozdes — es-zamanli NFV RAM tepesini dusurur).
>
> **DUZELTME + TAM PARITE KOSUSU (2026-07-18, kurtarmali; kanit
> scripts/k57_parite_kosu.log):** PARITE **4/4 BIT-OZDES DOGRULANDI** —
> plan1 302.8 · plan2 542.5 · plan3 601.9 · d4 231.5 hepsi delta +0.00,
> **VERDICT NOOP** (surec-izolasyon parite tezi KESIN). Seri kurtarma CANLI
> calisti (plan3||d4 cakismasi plan3'u OOM'a dusurdu "1.89 MiB alloc fail" ->
> d4 bitince plan3 tek basina yeniden kosuldu, 601.9 kurtarildi). **HIZ
> BULGUSU (onceki −%33 IDDIASI GECERSIZ — o 59dk plan3 OOM'la FAIL vermisti,
> yani 3 seti sayiyordu):** kurtarmali tam kosu WALL **87.4dk ≈ sirali 88dk =
> hiz kazanci ~0 BU DONANIMDA.** Kok neden: plan2/plan3/d4 UCU DE RAM-agir
> NFV; 16GB'de (~2GB bos) herhangi ikisi cakisinca OOM -> seri-retry o seti
> sirali maliyete geri donduruyor + kullanici yuku sureleri sisirdi (d4
> 2372s vs baseline 2095s). SONUC: K-57b'nin (a) PARITE altyapisi + (b) OOM
> SAGLAMLIK'i URETIMDE ve kanitli; AMA (c) HIZ faydasi RAM-cap OLMADAN bu
> makinede GERCEKLESMIYOR. **GERCEK HIZ ON-SARTI = NFV_FFT_BUDGET_MB cap'ini
> cocuklara gecir** (H-17 dilimli-konvolusyon bit-ozdes; RAM tepesi duser ->
> OOM'suz gercek paralellik) VEYA daha cok RAM / plan1+d4 gibi HAFIF ciftleri
> esle. Munhasir-kosu politikasi (K-57a) hala gecerli (yuk sureleri sisiriyor).
>
> **K-57c OLCULDU = FFT-CAP OOM'u COZMEDI (kok neden RAM, FFT DEGIL; kanit
> scripts/k57_parite_kosu.log @ NFV_FFT_BUDGET_MB=350):** parite 3/4 yine
> BIT-OZDES (plan1 302.8 · plan2 542.5 [NFV seti, dusuk budget'la da birebir
> = H-17 dilim=tam-boy SAHADA dogrulandi] · d4 231.5) AMA plan3 IKI KEZ OOM —
> plan3||d4 cakismasi OOM, seri kurtarmada plan3 TEK BASINA (RAM tekelinde,
> dusuk budget) BILE OOM ("4.76 MiB alloc fail"). KESIN TESHIS: OOM hata
> boyutu ~2-5 MiB kucuk dizilerde = sistem TAMAMEN RAM'siz; suclu FFT tamponu
> DEGIL (350MB'a kapatildi) — FFT-DISI RAM (mesh dizileri, clearance
> ornekleme 6000/mesh, voxel gridleri) + genel baski (baslangic bos 2.5GB,
> kullanici aktif). WALL 62dk YANILTICI (plan3 bitmedi = 3-set; onceki 59dk
> gibi). K-57 NET DEGERI: (a) parite altyapisi + (b) OOM seri-kurtarma
> URETIMDE/kanitli (opt-in, zararsiz); (c) HIZ bu donanim+yukte
> GERCEKLESMIYOR — asil kaldirac RAM (daha cok RAM / bos-makine munhasir kosu
> / super-bilgisayar §5). Kod calisir; HIZ KANITI bos-makine kosusuna
> ERTELENDI. SONRAKI ADAY: clearance-sample paralel-cap (parite riski, d4
> 3000-iyimser dersi) veya --parallel 3 + bol RAM (3 agir seti ayirmak icin).
> plan2 542.5 (3. kez birebir — determinizm saglam) · plan3 601.9 (2. kez
> birebir; sure 9293s=155dk, k51c'de 5741s — CPU cekismesi duyarli, fast-NFV
> plan3 yavasligi K-53/K-55 konusu) · d4 276.5 (2. kez birebir; 548.8s) ·
> plan1 INVALID (heightmap-c2f voxelize EXCEPTION — K-54 graceful
> clearance-cap isi; pitch 1.016 @wall_aware=False). BASELINE kilidi K-54
> cozulunce k51e ile denenir. Kanit: results/eval_gate_last.json;
> scripts/k51d_baseline_kilit.log.

> **2026-07-18 — K-56a OLCULDU = GO (plan1 uretim-yolu 302.8 -> 202.2 LEGAL,
> −100.6mm = −%33.2; kanit D:\ie488\results\k56_plan1_uretim_tilt.json +
> scripts/k56_plan1_uretim_tilt.log):** MEKANIZMA: opt-in `extra_rot_overrides`
> zinciri (voxelize_part `extra_rot_matrices` -> expand_quantities ->
> to_voxel_parts -> solve_coarse_to_fine -> eval_gate evaluate_set; ek pozlar
> default setin SONUNA — coarse/fine indeks tutarli; NFV dalinda ValueError;
> TUM default'lar bit-ozdes, TDD tests/test_k56_extra_rot.py 10 test + komsu
> ~394 yesil + A9 fake-imza hizasi test_eval_gate._fake_eval_ortam). DENEY
> (scripts/k56_plan1_uretim_tilt.py, uretim sozlesmesi evaluate_set):
> A = uretim default **302.769 replay** (k51e bit-ozdes; 314.6s). Tarama:
> baseplate_v2'ye x/y 5..85@5 tilt @fine 1.016/margin 2; filtre = grid-sigma
> + no-go'suz-yerlesebilirlik dikdortgen testi + z<298vox (YERLESEBILEN
> default-poz esigi — 2026-07-09 "esik cozumun kullandigi poz" dersi). Kabul
> 14 poz (x20..x85); **TUM y-tilt pozlari YAPISAL OLU** (fp_y~307mm > 290mm
> no-go-otesi serit — y-tilt baseplate y-boyunu kucultmuyor). B = **202.185
> LEGAL serhsiz: 112/112, kilit 0 (rot denetimi gerekmeden), clear 2.032,
> 270.8s (A'dan HIZLI — kule kisaldi)**. Eski dblf@1.0 kaniti 141.0'a kalan
> ~61mm fark adaylari: 5-derece adim kabaligina karsi ince-aci taramasi
> (x20-x50 bandinda 1-2 derece), coarse kuantizasyon, dblf sira etkisi.
> SIRADAKI (K-56b): (1) URETIM KABLOSU — tilt-zorunlu kapi tetiklenince
> hedefli-tilt otomatik (pipeline + eval kapisi 4-set PASS + Eren onayi),
> (2) ince-aci taramasi, (3) filtre-gevsetme olcumu (dblf'e birak). SUREC
> NOTU: D:\ie488 agaci HEAD'den geriydi (onceki kosular kismi kopyayla) —
> src/scripts/tests robocopy /E ile TAM senkronlandi; ayrica Git Bash
> `kill -0` detached PID'i goremiyor -> cift-kopya tuzagi yasandi (memory
> feedback-gitbash-kill0-detached-pid; canlilik tasklist/Get-Process ile).

> **2026-07-18 — K-57d ON-TESHIS = NO-GO (voxel-cache kapiyi hizlandirmaz;
> kanit results/k57d_voxelize_pay.json + scripts/k57d_voxelize_pay_teshis.log):**
> Eren yonu "kaliteden odun vermeden hiz" -> K-57d kalici voxel-cache adayi
> once A4 olc-once teshisine sokuldu (cache TASARLANMADAN): 4 setin uretim-
> rotasi voxelize'i izole zamanlandi (heightmap: to_voxel_parts coarse+fine;
> NFV: _voxelize_nfv @p2.0 kalite-recetesi; d4 AX24 n24). SONUC: plan1 41.5s
> (%11.7) · plan2 61.9s (%5.2) · plan3 80.3s (%4.9) · d4 61.4s (%2.9) =
> **TOPLAM 245s / 5279s = %4.6** (k51e munhasir tabanina oran). MUKEMMEL
> cache bile kapiyi ~4dk kisaltir (Amdahl duvari); olcum pytest yuku altinda
> = pay sisik bile olabilir -> karar degismez. HUKUM: K-57d kapi icin
> DUSUK-ONCELIK/NO-GO; cache ancak cok-tekrarli APP kullaniminda (ayni STL
> yeniden-islenirse) ayri gerekceyle geri gelir. YAN BULGU (baseline JSON +
> teshis): kapi suresinin ~%95'i voxelize-DISI — plan3'te r11 UYGULANMIS
> (kazanc 19.58mm; 1639s icinde payi bilinmiyor), plan2 rot-denetimi 219
> kilit/226 mesh, d4 clearance 6000-ornek x 588 mesh. SIRADAKI TESHIS:
> evaluate_set'e davranis-notr sure-kirilim telemetrisi (solve/clearance/
> kilit5/rot ayri sayaclar) + tek-set anatomi kosusu -> hiz yatiriminin
> gercek adresi veriyle secilir (r11 mi decode mu olcum katmani mi).

> **2026-07-18 — K-57 ANATOMI OLCUMU (sure-kirilim telemetrisi) = KAPI
> SURESININ HARITASI CIKTI + CIFT-ROT ISRAFI YAKALANDI (kanit
> results/k57_anatomi_nfv.json + scripts/k57_anatomi_nfv.log; 3/3 BIREBIR
> replay 542.5/601.92/231.5):** Once davranis-notr telemetri kablolandi
> (solve_nfv_kalite tel: solve_ham_s/solve_guard_s/kilit5_s + r11/rot_kabul
> sure_s; evaluate_set: sure_kirilim dict — TDD tests/test_sure_kirilim.py 5
> test + komsu 100 yesil). ANATOMI (sakin makine, toplam 3862s):
> **ham decode 1926s (%50: p2 266 / p3 519 / d4 1141 [AX24 %76!])** ·
> **r11 622s (%16, yalniz plan3)** · **rot_kabul solve-ici 569s (%15,
> gerekli — guard vergisinden koruyor)** · **rot eval-katmani 609s (%16:
> p2 283 + d4 209 dz'SIZ = AYNI denetimin tekrari = 492s SAF ISRAF; p3 117
> dz'li = mesru)** · olcum (clearance+kilit) 111s (%3 — suclu degil).
> **CIFT-ROT FIX KODLANDI (TDD 3 test, 64/64 eval_gate yesil):** r11_dz
> YOK + solve tel rot_kabul.uygulandi=True & rot_kilit=0 -> eval katmani
> denetimi tekrarlamaz, solve kanitini kullanir (rot_kaynak="solve_reuse";
> dz'li vaka KONSERVATIF yeniden kosar; kanit-yokluk eski yol birebir).
> **PARITE KOSUSU 4/4 GECTI (kanit results/k57_rot_reuse_parite.json):**
> plan2 542.5 BIREBIR + cert 4 BIREBIR + rot_kaynak=solve_reuse, 878.2 ->
> **678.1s (-200s, -%23)** · d4 231.5 BIREBIR + cert 5 BIREBIR, 1506.9 ->
> **1113.3s (-394s, -%26)**. Toplam kazanc 594s ≈ 10dk — kalite-notr KANITLI
> (legal + cert sayilari k51e baseline'la birebir). FIX URETIMDE (evaluate_set
> default'u; dz'li vaka konservatif korunur). SIRADAKI HIZ ADAYLARI (anatomi-temelli,
> buyukten kucuge): (1) ham decode 1926s — d4 AX24 dominant; GPU-decode
> teyidi (K-57c acik yonu, P3 ~2x kanitli) + poz-budama; (2) r11 622s
> (plan3) — ornekleme/erken-cikis (kalite-riskli, dikkatli); (3) rot_kabul
> 569s — kilit_rot_meshes hizlandirma (K-55 R11 desenine benzer cKDTree/
> budama olabilir). Voxelize %4.6 (K-57d NO-GO) ve olcum katmani %3 KAPALI.

> **2026-07-18 — K-57 DECODE TESHISI = GPU 3/3 TEYIT (K-57(c) acik yonu
> KAPANDI; kanit results/k57_decode_teshis.json):** izole voxelize+best_decode
> (verbose) uc NFV setinde: plan2 decode 93.7s / plan3 279.9s / d4 1077.8s —
> HEPSI **STRATEJI=gpu-resident** (sessiz CPU-fallback YOK; "GPU'ya tasi"
> kaldiraci mevcut degil, zaten orada). AYRISTIRMA: anatomi 'ham' kalemi =
> voxelize + decode + settle/replay -> p2: 59+94+~113 · p3: 94+280+~146 ·
> d4: 81+1078+~0. NET: d4 AX24 decode'u (24 poz x 588 parca) GPU'DA BILE
> 1078s = kapinin en buyuk tekil kalemi; hizlandirma ancak ALGORITMIK
> (decode-ici profil ister; birebirlik riski yuksek alan — dikkat). Kalici
> telemetri: evaluate_set sure_kirilim'a decode_strateji alani eklendi
> (adaptive_reason'dan; kapida GPU/CPU izi artik her kosuda gorunur).

> **2026-07-18 — K-57 ROT-MEMO = NOTR (durust kayit; kanit
> scripts/k57_rot_ab.log):** rot profili (plan2 pickle-sahne, cProfile 240s
> kosu) nd_rotate'i %42 gosterdi -> tur-tekrari memoization hipotezi kodlandi
> (check_separability_rot rot_cache, 64MB butce, _rot_memo bayragi; 25+31
> komsu test yesil). ILK kiyas HUKUMSUZDU (ayri kosular: 240s vs 410s —
> makine-yuku degiskenligi %70, K-57a dersinin bir kaniti daha). ADIL A/B
> (tek proses, ayni sahne): A memo'suz 411.7s -> B memo'lu 394.1s =
> **-%4.3 NOTR** — rapor BIT-OZDES BIREBIR (n_locked + removable_order +
> cert detaylari). Kok: sertifikalar merdivenin ILK basamaginda bulunuyor
> (aci 1.0-1.18) -> tekrar orani dusuk, memo tavani kucukmus. KARAR: kod
> zararsiz+testli+bayrakli -> KALIR; rot hizlandirmasi buyuk-kaldirac listesinden
> DUSTU. Profil yan-bulgusu: rot suresinin kalemleri rotate 100s / voxelize
> 52s / erosion+dilation 37s / _yonlu_sahne+blocks ~50s — hicbiri tek basina
> dominant degil, 5-10x'lik yapisal kazanc bu mekanikte YOK (dagilmis maliyet).

> **2026-07-18 — K-57 FASTLEN = GO, URETIMDE (kapinin en buyuk tekil kalemi
> yarilandi; kanit results/k57_decode_profil.json + k57_decode_fastlen_ab.json
> + k57_fastlen_kapi.json):** Decode ic-profili (yeni _tel telemetrisi, d4
> 60p orneklemi): **conv-FFT %93** (bbox-sync %1 / blb %1 — sync hipotezi
> curudu). KOK: gpu_conv_valid_chunked s=full (crop+kernel-1) FFT boyutunu
> next_fast_len'e YUVARLAMIYORDU (scipy CPU yolu icerde yapar; cuFFT kotu-
> kompozit boyutlarda katlarca yavas). FIX: fast_len bayragi (scipy.fft.
> next_fast_len; sifir-padding buyur, lineer konv valid bolgesi AYNI matematik
> — karar-birebir) -> decode_gpu DEFAULT ACIK. ORNEKLEM A/B (tek proses, d4
> ilk-60p): 212.6 -> 106.6s = **-%49.9, h + TUM placements BIREBIR**. KAPI
> KANITI (3 NFV seti, rot-reuse'lu tabanlara karsi): **PARITE 3/3 BIREBIR**
> (542.5 / 601.92 / 231.5) · d4 1113.3 -> **874.0s (-239s, -%21)** · p2/p3
> kazanc gurultu bandinda (decode paylari %14/%19 — makine-yuku +-%10 ortuyor;
> d4 decode-payi %76 oldugundan sinyal net). NOT: fp32 kestirmesi TARIHI
> HUKUMLE KAPALI (fft_backend: "f32 gurultusu 0.5 esigini cevirir"); fastlen
> f64 boru hattini KORUR. KALAN decode adaylari: kernel-FFT spektrum cache
> (ayni orient + ayni fshape tekrarlari) · fshape stabilizasyonu (cache
> isabetini buyutur). Kapi tabani (fastlen+rot-reuse, sakin-makine tahmini):
> ~48-55dk (k51e 88dk'dan ~%40 asagi, kalite sayilari birebir).

> **2026-07-18 — K-57 SPEC-CACHE = NO-GO @6GB (ZARARLI olculdu; kanit
> results/k57_speccache_ab.json):** kernel-spektrum LRU'su (rfftn(grid_flip)
> tekrarlarini onbellekle; SpecLRU VRAM-butceli, decode-omurlu, OOM-graceful)
> kodlandi + A/B (tek proses, d4 60p): A cache'siz 127.8s -> B 1024MB
> **303.5s = +%137 YAVASLAMA** (bit-ozdeslik BIREBIR korunarak). MEKANIZMA:
> 1GB canli spektrum 6GB VRAM'de cuFFT calisma tamponlarini sikistiriyor ->
> tahsis-thrash (K-57c RAM dersinin VRAM karsiligi). KARAR: default KAPALI
> (spec_cache_mb=0); kod+testler kalir — YALNIZ bol-VRAM ortaminda (super-
> bilgisayar A1 kosusu) yeniden degerlendirilir. DERS: cache'in kendisi de
> bellek-butcesine dahil — "hesabi sakla" ancak saklama ALANI bos ise kazanc.

> **2026-07-18 — K-57b YENIDEN-OLCUM (fastlen sonrasi) = OOM COZULDU,
> WALL NOTR @tek-GPU (kanit scripts/k57_parite_kosu.log, WALL_S=3488.7):**
> --parallel 2 kapi: **PARITE 4/4 BIREBIR** (302.8 / 542.5 / 601.9 / 231.5;
> cert 4/1/5 birebir) ve **OOM HIC YASANMADI** (K-57b/c'nin plan3||d4 OOM'u
> fastlen'in RAM/VRAM tepe-penceresini kisaltmasiyla KAPANDI — saglamlik
> kaniti). AMA WALL 58.1dk ~= sirali ~57dk = duvar-saati kazanci SIFIR.
> KOK: darbogaz artik RAM degil PAYLASILAN GPU — iki NFV decode'u tek
> RTX3060'i serialize ediyor (p3 1640->3026s, d4 874->2263s sisti; toplam
> sabit). HUKUM: set-paralel tek-GPU makinede NOTR; deger ancak cok-GPU /
> super-bilgisayar ortaminda (A1 kosusuyla birlikte). Kapi politikasi:
> SIRALI + munhasir kosu (K-57a) kalir. NOT: cocuk verdict'i BASELINE-YOK
> gosterdi cunku D agacinda baseline json yok (k51e baseline C'de; parite
> degerleri elle dogrulandi — birebir).

> **2026-07-22 — K-60 R11 KESIN-ESDEGER SORGU-ATLAMA = SENTETIK GO, uretim
> kaniti KOSUYOR (kanit scripts/k55_bench_settle cikti + tests
> test_r11_continuous_settle 13/13):** GEREKCE: plan7 kor-test kirilimi —
> R11 sure payi %60 (49dk/81dk; ham coz um 21dk) -> R11 en buyuk hiz kalemi.
> MEKANIZMA (K-55 deseni: karar matematigi DEGISMEZ, veri-tipi dali YOK):
> (a) esik hesabi bound=req budamali (yalniz min(req,d0) gerekir; inf =>
> d0>=req kesin, esik bit-ozdes); (b) analitik AABB-bosluk alt siniri
> (bulut noktalari mesh AABB'sinde -> cift mesafesi >= kutu boslugu;
> bosluk>=esik ise sorgu gereksiz, bedava); (c) Lipschitz onbellegi
> (z-otelemede cift mesafesi en fazla |ddz| azalir; bilinen sinir - yol
> >= esik oldukca sorgusuz; sorgular esik+2mm ufkuyla alt-sinir uretir).
> _GUV=1e-9 float payi YALNIZ atlamayi azaltir (yanlis atlama imkansiz).
> `atlama=False` eski yol birebir (esdegerlik kapisi). OLCUM (sentetik
> k55_bench): 48p 9.5s -> **0.7s (13.6x), dz_md5 BIREBIR**
> (226d9237...); 96p 2.5s. Kumulatif R11 zinciri: K-55-oncesi 97s ->
> K-60 0.7s (~139x sentetik). TDD: +2 bit-ozdeslik testi (normal +
> esik-dibinde sikisik sahne), dosya 13/13.
> **URETIM KANITI GELDI (ayni gun; kanit results/k60_d4_hiz_paritesi.log
> D+OneDrive): d4 588p replay PARITE TAM — h 220.69 BIREBIR, clear 2.006
> BIREBIR, rot kilit 0/588 (5 cert), settle+rafine 43.5dk (K-55) ->
> 5.1dk (~8.5x; K-52 orijinali 393dk'ya gore 77x).**
> **Karne: tetik=geometrik (veri-adi yok; saf hiz) | kapi=PASS (d4
> uretim-olcek parite tam) | sifir-dokunus=N/A (davranis bit-ozdes,
> testli+replay-kanitli) | sozlesme=DEGIL | held-out=GEREKMEZ
> (kalite-notr).** ETKI: plan7-tipi 345p sette R11 49dk -> beklenti
> ~5-8dk (dogrudan olculmedi — held-out'a hiz olcumu icin de dokunulmaz);
> kapi/uretim koslarinda R11 artik sure engeli degil.

> **2026-07-23 — K-61 EVAL v1.3 CANLI SKOR = %85 (22/26) -> OTOMATIK-MOD
> KRITERI FAIL, MOD KAPALI KALIR (kanit D:\ie488\results\
> kisit_korpus_eval.json + detach_eval_kisit_korpus.out; korpus 26 ornek):**
> Kirilim: gercek 4/4 + negatif 6/6 (notsuz yanlis tetik YOK) + zor 3/3 —
> **z03 olumsuzluk tuzagi ("yatay YATMASIN") v1.2 yapisal savunmayla
> (olumsuz-ifade guven tavani) ARTIK GECIYOR** — varyasyon 8/10 + injection
> 1/3. FAIL detayi: (a) v05/v08 = "konum" DILINDEKI belirsiz ifadeler
> ("yeri sabit kalsin" / "konumlari onceki plandaki gibi") yuksek-guvenli
> yanlis kisit uretti (yfp=2) — v05 pinned_position uretti (compiler'da
> KALICI GOLGE oldugu icin uretime SIZMAZ) ama muhafazakarlik ihlali;
> (b) i01/i02 injection bayragi kalkmadi FAKAT kisit listesi BOS = zarar
> sizmadi, tespit metrigi dustu. Karar: kisit_modu=kapali dogrulandi;
> hakem 8 ornekte devreye girdi (oy dagilimi 3-oy:14, 2-oy:2, 1-oy:3).
> ACIK YON (backlog, ayri disiplinli is): Kapi-0 injection desen seti
> i01/i02 tipine genisletilmeli + "konum" dili muhafazakarligi (belirsiz
> konum ifadesi -> guven tavani orta) — korpusa OVERFIT riskine karsi
> duzeltme korpus GENISLETMESIYLE birlikte yapilir (yeni ornek ekle,
> mevcut ornege gore ayar yapma). Karne (A11): tetik=geometrik-degil
> (LLM kalite olcumu) | kapi=GEREKMEZ (motor yolu degismedi) |
> sifir-dokunus=YAPISAL (kisit_modu kapali, uretim birebir) |
> sozlesme=DEGIL | held-out=GEREKMEZ.

> **2026-07-22 — K-56g + K-61 NOT->KISIT HATTI = KOD+TDD TAMAM, MOD KAPALI
> (kanit tests/{test_kisit_kablo,test_note_detector,test_llm_kisit,
> test_constraint_compiler,test_note_pipeline}.py = 8+15+11+14+10 yesil +
> ingest zinciri 102/102 + webapp 79/79; plan
> ~/.claude/plans/playful-tumbling-blum.md):** IKI PARCA: (1) **K-56g
> URETIM KABLOSU**: solve_coarse_to_fine + to_voxel_parts'a per-model
> `orientation_overrides` (28-poz master set indeks kilidi; extra_rot ad
> eslesme deseni) + run_pipeline order alani `motor_kisitlari` ->
> _process_batch DAL ZORLAMASI (kisitli parti NFV/tuner'a giremez,
> koşulsuz c2f; `kisit_yonlendirme` telemetrisi). Default None/alan-yok =
> bit-ozdes (test_pin_none deseni run_pipeline seviyesine tasindi).
> (2) **K-61 NOT->KISIT HATTI** (siparis notu "dik uretilecek"/"konumu
> degismeyecek" -> yapisal kisit): Kapi-0 deterministik not tespiti
> (note_detector; LLM'siz sozluk-kapili, notsuz siparis SIFIR-dokunus
> YAPISAL — cagri-sayan FakeProvider testi call_count==0) -> KisitRole
> (prompts/kisit-v1, whitelist enum + sembolik deger, sayi/indeks uretimi
> YASAK) -> N=3 self-consistency oylama (temp 0.7; kanonik anahtar
> tip+ad+deger) + qwen2.5:7b HAKEM eskalasyonu (Eren karari: bastan;
> orta+ayni->yuksek, farkli->dusuk, dusuk YUKSELMEZ, erisilemez->yerinde)
> -> constraint_compiler (yon->poz tablosu GEOMETRIK turetim: dik={0,1,4,5}
> R.ez=+ez; yatay=yan/yuz pozlari; pinned_* HOCA-CEVABINA-DEK kalici golge)
> -> note_pipeline karar politikasi (yalniz nihai_guven=yuksek uygulanir;
> muhafazakarlik = motora yanlis-pozitif kisit SOKMAMAK) -> rapor "Not
> Analizi" bolumu + /kisit-onay operator onay yuzeyi (oneriler meta'ya,
> onay olmadan HICBIR kisit uygulanmaz; /adet-gir kablosu). Golden korpus
> 25 ornek (tests/fixtures/not_korpusu.jsonl) + canli eval
> scripts/eval_kisit_korpus.py (gecis kriteri: dogruluk>=%90 VE
> yuksek-kesim yanlis-pozitif=0). DURUM: `kisit_modu="kapali"` (uretim
> davranisi BIREBIR) — golge'ye alma = uretim default degisikligi = EREN
> ONAYI; otomatik'e gecis ayrica eval-kriter PASS ister. hoca soru-2
> (pinned semantigi) cevabina bagimli kisim yalniz compiler cevirisi.
> **Karne: tetik=geometrik (kod veri-adi icermez; not tespiti sozluk-kapili
> genel) | kapi=PASS (motor regresyon: test_k56f_pin + test_coarse_to_fine +
> test_demo_pipeline = 127/127 yesil, 50.4dk, 3 slow deselect; ingest
> 102/102 + webapp 79/79 + yeni hat 58/58) | sifir-dokunus=TESTLI
> (notsuz/kisitsiz yollar bit-ozdes, 5 test dosyasi) | sozlesme=DEGIL
> (opt-in, default kapali) | held-out=GEREKMEZ (kalite mekanizmasi degil,
> giris-kablosu; ilk gercek notlu siparis golge-kiyas verisi olacak).**

> **2026-07-20 — plan3 KURTARMA = PASS + K-58 p3-KOLU = NOTR -> K-56b KAPI
> 4/4 TAMAM (kanit D:\ie488\results\k56b_plan3_kurtarma.json + .log;
> 27.2dk, OOM YOK @2.6GB):** plan3 **601.92 BIT-OZDES** (tarihsel 3 kosuyla
> ayni; kilit 3 -> rot 0 sokum-planli, clear 2.004) -> (a) 2026-07-18
> OOM'unun CEVRESEL oldugu kesinlesti, K-56b kapi kaniti 4/4 TAMAMLANDI
> (p1 202.18 + p2/d4 birebir + p3 601.92); (b) K-58 p3-kolu NOTR: r11
> uygulandi (667s) ama net etki 0.00mm — TELEMETRI NUANSI: r11_kazanc=19.58
> R11'in IC-tabanina gore (h0 621.5 mesh-settle-oncesi), eval mesh-gercek
> olcumu o bosligu ZATEN goruyordu; p2/d4'te R11 GERCEK ek kazanc verdi
> (529.04/220.69), p3'te ayni bosluk cift-sayim. (Telemetri iyilestirme
> adayi: r11_kazanc yaninda eval-taban net-etki alani.) **K-58 4-KOL OZET:
> p2 -13.46 REKOR · d4 -10.81 SAMPIYON-PARITE · p3 0.00 NOTR (+11dk sure)
> · p1 etkisiz (heightmap). B2: hicbir set kotulesmedi, 2 set buyuk
> iyilesti -> PASS ADAYI; insan-karari maddesi: p3'un kalite-notr +11dk
> R11 maliyeti (Eren).** Kalan: tam suite + Eren commit onaylari (K-56b +
> K-58) + baseline yenileme (p1 302.8->202.2 + p2/d4 yeni degerler).
> Karne (A11): tetik=OK | kapi=4/4 OLCULDU | sifir-dokunus=4/4 KANITLI |
> sozlesme=DEGIL (hard'la kosuldu) | held-out=BEKLIYOR.

> **2026-07-20 — K-58 d4-KOLU OLCULDU = SAMPIYON-PARITE (kanit
> D:\ie488\results\k58_d4_olcum.json + .log; 58.8dk):** deneme4 uretim yolu
> (ref 231.5) K-58 tavaniyla **220.6917 LEGAL = SAMPIYON 220.69 BIREBIR**
> (clear 2.0063 sampiyonla ayni; kilit 12 -> rot 0 sokum-planli;
> r11_kazanc 8.64). K-50 HIKAYESININ KAPANISI: o donem ayni 8.64mm kazanc
> "kilit 11->12" diye KAPIDA REDDEDILMISTI — rot-kabul katmani (hoca
> kriteri 2026-07-14 + K-52) R11 kapisina baglaninca ayni kazanc simdi
> sokum-planli KABUL. Sifir-dokunus: fark tamamen r11 izi -> r11-haric
> PASS (p2 ile ayni desen). K-58 DURUM: p2 529.04 (yeni rekor) + d4 220.69
> (sampiyon-parite) olculdu; KALAN plan3-kolu (sakin RAM; NOT:
> k56b_plan3_kurtarma'nin BEKLENEN=601.92 varsayimi K-58'li agacta GECERSIZ
> — r11 uygulanirsa ~577-590 beklenir, script hukmu guncellenmeli) + p1
> replay (K-58 etkisiz beklenir: heightmap dali) + Eren commit onayi.
> Karne (A11): tetik=parametre(genel) | kapi=KISMI (p2+d4 olculdu) |
> sifir-dokunus=p2+d4 KANITLI | sozlesme=DEGIL | held-out=BEKLIYOR.

> **2026-07-19 GECE — K-59 DAGILIMSAL SMOKE = A11/B1 ILK DAGILIM KANITI
> (kanit D:\ie488\results\k59_dagilim_smoke.json + .log; 1.0dk):** Sentetik
> aileler (B1, synthetic.py): plaka-baskin 8 ornek (dev plaka 300-334 x
> 280-325, tetik sinirinin IKI yani) + kontrol random_boxes/long_rods 6.
> SONUC: (1) **TETIK DOGRULUGU 14/14** — bagimsiz geometrik beklentiyle
> birebir (sinir-alti s4/s7 dogru sonuk; kontrolde yanlis-pozitif 0/6).
> (2) **A/B kazanc dagilimi 4/4 WIN, delta ort -94.2mm (aralik -63..-118)**
> — hedefli-tilt kablosunun kazanci plan1-ozgu DEGIL, aile-geneli;
> dagilim uzerinde olculdu. (3) Kontrol nokta-kontrolleri BIT-OZDES
> (tetiksiz aileye sifir dokunus). (4) **KAPSAM BOSLUGU: 2/6 tetiklenen
> ornek (s3 308x304, s6 327x317 — iki taban boyutu da >290) HEM kablosuz
> HEM kablolu yolda cokuyor** (k51d istisna sinifi; mevcut uretimde de var
> = kablo regresyonu degil, ACIK ALT-BOLGE). K-56g pinleme-kapisi + soft
> sozlesmenin tam hedefi buras — 4 sabit setin gosteremeyecegi bosluk
> dagilimsal harness'le bulundu. SMOKE SERHI: yukseklik proxy (clearance/
> kilit tam olcumu + buyuk-N sweep sakin-makine isi). Harness bundan boyle
> her yeni mekanizmanin standart sinavi (proje CLAUDE.md'de kayitli).
> Karne (A11): tetik=GEOMETRIK dagilimsal-KANITLI 14/14 | kapi=BEKLIYOR |
> sifir-dokunus=dagilimsal OZDES + p2 canli r11-haric PASS | sozlesme=
> degisiklik yok (HARD kosuldu) | held-out=DOKUNULMADI.

> **2026-07-19 GECE — K-58 p2-KOLU OLCULDU = GO-ADAYI + A11 SIFIR-DOKUNUS
> r11-HARIC PASS (kanit D:\ie488\results\k58_p2_olcum.json + .log; 25dk):**
> Working tree'de TUM K-56 zinciri dururken plan2 uretim yolu kosuldu (ref
> 542.5, 4 bagimsiz birebir): **529.04 LEGAL = YENI p2 REKORU** (eski
> sampiyon 541.44'un 12.4mm alti; clear 2.019, kilit 35 -> rot 0
> sokum-planli; manuel farki +%10 -> +%7.5). Iz: r11_uygulandi=True (K-58
> tavan 150->600 kalkti kaniti), r11_kazanc 11.22mm + rot-sokum etkilesimi
> = -13.46 toplam; **r11-DISI fark YOK -> K-56c/d/e/f mekanizmalarinin
> p2'ye sizmadigi OLCULDU** (varsayilmadi). K-58 hala SERHLI: 4-set kapi
> tamamlanmadi (d4 gece sirada ~75dk; plan3 sakin-RAM; p1 replay).
> Karne (A11): tetik=parametre(genel) | kapi=KISMI (p2 kolu olculdu) |
> sifir-dokunus=p2 KANITLI, d4/p3 bekliyor | sozlesme=DEGIL | held-out=BEKLIYOR.

> **2026-07-19 — K-56f BUYUK-PLAKA PINLEME = GO (p1 uretim yolu 170.7 ->
> 140.21 LEGAL; kanit D:\ie488\results\k56f_pinleme.json + .log; 5.8dk):**
> MEKANIZMA KODDA+TESTLI: solve_coarse_to_fine(pinned_placements) opt-in
> zinciri — default None BIT-OZDES; pin aramadan CIKAR (SA tasiyamaz);
> coarse bin'lere danisma-commit (kuantizasyon kelepceli strict=False, hic
> sigmazsa atlanir); fine'da otorite-commit (sinir-disi ValueError, sessiz
> kirpma yasak); pin MARGIN'SIZ raw voxelize (tek-tarafli dilation
> ozdesligi: komsular kendi marjini tasir -> parca-pin boslugu >= margin
> yapisal); placements + fine_voxel_parts enjeksiyonu -> olcum katmani
> pin'i normal parca gibi gorur. eval_gate passthrough + NFV guard. TDD
> tests/test_k56f_pin.py 6 + komsu 136 yesil (A9 bayat-mock 1 fake imza
> hizalandi; A9 ayrica TAZE if/elif bug'ini yakaladi — pin satiri tilt
> elif'ini kirmisti, duzeltildi). DENEY: baseplate DUZ pin (raw 325x298,
> z=40.6mm; x-ortali, y uzak-kenar; no-go girisi 1.50mm <= 12mm tolerans;
> soft sozlesme; extra_rot_overrides={} ile oto-havuz susturuldu) ->
> **140.208 LEGAL (clear 2.034, kilit 0, 112/112, 345s)**. Projeksiyon
> (~141) TUTTU. ZINCIR: 302.8 -> 202.2 (tilt) -> 171.7 (soft) -> 170.7
> (raw) -> **140.2 (pin)** = toplam -%53.7; dblf@1.0 kaniti 141.0 GECILDI,
> K-37 129'a 11mm, manuel 110.41'e 30mm kaldi. OKUMA: 140.2-40.6=99.6mm =
> 111 parcanin plaka-ustu istifi ~ serbest-taban 101.17 — istif zaten
> dogal tabaninda; kalan makas SAF ISTIF KALITESI (manuelin ustu-istifi
> ~70mm = ~%30 daha siki). KALAN ADAYLAR: (a) **K-56g uretim kablosu** —
> "duz-pinleme kapisi" GEOMETRIK tetik (yukseklik-surucu parcanin duz pozu
> YALNIZ kuantizasyon/kenar-tasma nedeniyle oluyse otomatik pin; A11
> uyumlu, veri-adi yok) + 4-set kapi; (b) 111-parca alt-problemine kalite
> modu (K-40 NFV no-go'su PLAKALI olcumdu — plakasiz alt-problem acik
> soru; pin+NFV kompoziti gelecek isi).
> **Karne (A11):** tetik=DENEYDE-ELLE (K-56g'de geometriklesecek) |
> kapi=BEKLIYOR (4-set sakin seans) | sifir-dokunus=BEKLIYOR |
> sozlesme=SOFT Eren-onayli + no-go-giris/kenar hoca-bekliyor |
> held-out=BEKLIYOR.

> **2026-07-19 — K-56e DUSUK-POZ ZORLAMA = KOMPOZISYON-DEGISMEZLIGI KANITI
> (kanit D:\ie488\results\k56e_dusuk_poz_zorla.json + .log; ~14dk):** dar
> x8..x14 (7 poz) ve orta x8..x20 (13 poz) zorlamalari IKISI DE **170.68857
> BIT-OZDES** (serbest 43-poz menu + oto 16-poz havuzla AYNI float, AYNI
> clearance) -> SA zaten alcak pozu SECIYORMUS; 170.7'nin surucusu
> baseplate acisi DEGIL, kalan 111 parcanin daralan tabanda istifi.
> SA-miyopi hipotezi RED (kompozisyon menu-degismez; baseplate acisi 8-20
> bandinda maliyet-NOTR = cozum saglam). KALAN MAKAS (170.7 -> K-37 129 ->
> manuel 110.4) = DUZ-POZ meselesi: duz 40.6mm poz mevcut dilate-grid
> semantigiyle hicbir pitch'te acilamiyor (mm-duzeyinde 0-pay [33+302=335
> tam] + dilate grid plaka kenarindan ~2mm tasar; K-37 rig'i raw-grid
> semantigindeydi, 129 oradan). ADAY K-56f: "buyuk-plaka PINLEME"
> iki-asamali dekod — baseplate duz y=33'e DETERMINISTIK sabitlenir (arama
> yok), 111 parca on-dolu sahnede normal cozulur; projeksiyon ~40.6+101 =
> ~141 (bugunku istif verimiyle), rafineyle 110-130 bandi. HOCA NETLIGI
> GEREKEN: (a) parca no-go sinirina temas (raw semantik), (b) plaka
> kenarina temas / clearance'in plaka-duvarina uygulanmamasi.
> **Karne (A11, K-56c/d/e zinciri toplu):** tetik=GEOMETRIK (tilt-zorunlu
> kapi; kodda veri-adi yok) | kapi=BEKLIYOR (4-set sakin seans) |
> sifir-dokunus=BEKLIYOR (p2/p3/d4'te tetik yok — kapida kanitlanacak) |
> sozlesme=SOFT Eren-onayli + hoca-teyit-bekliyor, RAW hoca-bekliyor |
> held-out=BEKLIYOR (kor-test gelince ilk sinav).

> **2026-07-19 — K-56d v2 RAW-NO-GO (KAPI-HIZALI) = MARJINAL (+kapi yamasi
> KANITLI; kanit D:\ie488\results\k56d_raw_nogo_v2.json + .log; ~16dk):**
> Yama: predict_nfv_benefit sarildi (kapi karari SOFT bounds — tilt-zorunlu
> kalir), eg.NOGO_STD=ERODE (cozucu+havuz raw semantigi). Routing DOGRU
> calisti (otomatik +16 poz; NFV'ye kacis yok). SONUC: A=B **170.689
> BIT-OZDES** (clear 2.036, kilit 0) — soft 171.70'ten yalniz **-1.0mm**;
> x8-x14 pozlari (plaka z 80-110mm) MENUDE ama SA yine ~ayni dengede (168
> vox; soft'ta 169'du). OKUMA: raw semantik sinirlari actı ama SA
> KOMPOZISYONU degismedi — 111-parca tabani 101.17 iken toplam 170.7'de
> kalmak fizik degil ARAMA freni suphesi (meta-ders 12 greedy egik-poz
> miyopisi). K-56e zorlama testi ayni gun -> ayri kayit. SERH: raw semantik
> hoca netligi bekliyor ("parca no-go sinirina temas edebilir mi").

> **2026-07-19 — K-56d v1 RAW-NO-GO = OLCUM BASARISIZ ama IKI DEGERLI BULGU
> (kanit D:\ie488\results\k56d_raw_nogo.json + scripts/k56d_raw_nogo.log;
> 10.5dk):** Deney: clearance margin'inin no-go SINIRINA uygulanmamasi
> (raw semantik) — NOGO'yu margin kadar erode edip ayni boru hattina verme
> numarasi. BULGU-1 (TASARIM KISITI, uretim kablosuna gececek): erode
> ADIM -1 tilt-zorunlu kapisini SONDURDU — kapinin raw-rect testi duz pozu
> "sigar" sandi (302.0 <= 304.03) -> plan1 NFV'ye yonlendi (K-40 sert
> no-go yolu) -> A INVALID 111/112, B ValueError. 2026-07-09 "filtre
> dersi"nin sozlesme-katmani tekrari: KAPI-FEASIBILITY ile COZUCU-
> YERLESTIREBILIRLIK ayni semantikte kalmali (raw benimsenirse kapi
> erode-EDILMEMIS bounds'la karar vermeli). BULGU-2 (YAN-OLCUM): NFV
> kolunda kalan 111 parca TEK BASINA h=101.17'ye istiflendi (clear 2.024,
> kilit 0) = plan1'in baseplate-disi taban yuksekligi ~101mm — manuel
> 110.41'in erisilebilirligi ilk kez SAYIYLA gorundu (baseplate x8-x11
> alcak-tilt'le [z 80-96mm] yanlara sokulabilirse toplam ~101-110 bandi).
> v2 (kapi-yamali: kapi=SOFT, cozucu=ERODE) ayni gun kosuldu -> ayri kayit.

> **2026-07-19 — K-56c SOFT NO-GO ON-OLCUMU = GO (p1 uretim yolu 202.2 ->
> 171.70 LEGAL, -30.5mm = -%15.1; kanit D:\ie488\results\k56c_soft_nogo.json
> + scripts/k56c_soft_nogo.log; 17.4dk; Eren karari 2026-07-19 "soft
> girsin"):** Maske K-37 (y-ust 45->33 = T=12mm giris; hoca cevap 9
> dayanagi). IKI KOL BIT-OZDES 171.70457... / clear 2.036 / kilit 0:
> A_soft = DOGAL routing — K-56b kablosu soft bounds'la OTOMATIK +15 poz
> kurdu (zehirlenme YOK: duz poz fp_y-dilate 306.8 > 302 filtrede dogru
> kapali; kapi+kablo sozlesme-parametrik calisiyor KANITLI) · B_soft = acik
> 40-pozlu @1 menu (x11..x50 acildi; x11-x14 z 95.5-109.7mm MANUEL-ALTI
> pozlar dahil) — SA yine ayni dengede (dusuk aci genis fp_y ile taban
> yiyor; granulasyon K-56b(2) gibi yine etkisiz). KALAN ADAYLAR (171.7 ->
> 129-110): (a) RAW-no-go semantigi — clearance margin'inin no-go SINIRINA
> uygulanmamasi (K-37 129.0 boyle dogdu; hocanin cevap-9 ornegi bizzat DUZ
> plaka girisi = kasitla uyumlu; no-go bounds'u margin kadar erode ederek
> SIFIR solver degisikligiyle olculebilir; x5-x10 z 66-90mm + duz poz
> acilir AMA duz poz pitch-kuantizasyonda 0-pay/2-vox-tasma sinirinda) ·
> (b) ust-istif verimi (eğik rampa ustu DBLF kullanimi). SIRADAKI:
> sozlesme degisikligi paketi (eval NOGO_STD 45->33 + web plate.local.json
> + 4-set kapi + baseline yenileme; sakin-makine seansi; Eren commit onayi).

> **2026-07-19 — K-56b(2) INCE-ACI TARAMASI = NOTR OLCULDU (kanit
> D:\ie488\results\k56b_ince_aci.json + scripts/k56b_ince_aci.log; 9.2dk):**
> x16..x50 @1 (35 poz) + kaba kuyruk x55..x85 @5, K-56a filtresi birebir.
> Kabul 31+7=38 poz; B = evaluate_set(plan1, 38 poz) = **202.18468...
> BIT-OZDES (K-56a 14-pozlu sonucla ayni float, clear ayni) -> kazanc
> +0.0mm.** Ince granulasyon SA kararini DEGISTIRMEDI (deterministik
> tie-break ayni kazanani seciyor) — @5 izgara suclu DEGILMIS. ASIL BULGU:
> x16-x19 bandi (z 118.9-132.1mm = hedef 141-110 bandinin ta kendisi) HARD
> no-go'ya engelli: fp_y 291.6-295.6mm > 290mm ("otede" limiti); x19 SADECE
> 1.6mm girisle aciliyor (x16 -> z 118.9 = -83mm potansiyel). HUKUM:
> hard-sozlesmede aci-granulasyonu kaldirac DEGIL (NOTR kayit; tekrar
> denenmez); p1'in 141-110'a inis yolu = FILTRE-GEVSETME / SOFT NO-GO
> SOZLESME KARARI (hoca cevap 9 "cok ufak girisler kabul" — K-37'de -12mm
> kanitli, 129s o maskeyle bulundu; EREN + gerekirse hoca karari bekliyor).

> **2026-07-19 — p2 DEV-PARCA HEDEFLI-TILT = KOSUSUZ NO-GO (A4 teshis,
> dakikalik; bos deney onlendi):** p2 yukseklik-suphelisi PO-TR155308-17705
> (356.1x299.2x177.8; 356 hicbir eksen-hizali tabanla 335'e sigmaz -> 356
> DIK zorunlu — plan1 dik-dikilme cezasinin p2 karsiligi). Gercek-mesh
> tarama: bbox-matematiginin aksine y35-y45 bandi z'yi dusuruyor
> (346/332/318mm; voxel @2.0 uretim pitch'inde dogrulandi) AMA fp_y TUM
> bantta 304mm ve no-go'lu plakada yerlesilebilir y-araligi 290mm (soft
> no-go'da bile 302mm) -> 304 > 302 HER SOZLESMEDE YERLESEMEZ; z-rot
> transpozu da olu (fp_x 304 > 152.5/149.5 sol/sag seritleri); x-tilt
> tamamen olu (fp 404+mm). HUKUM: p2'de hedefli-tilt kaldirac DEGIL —
> p2 aciginin (+%10 manuel-ustu) kalan adresi istif zekasi (A1 surekli
> rotasyon, super-bilgisayar §5); K-14 buyuk-levha + K-41 hukumleriyle
> tutarli. NOT: eval_gate NFV dalinda extra_rot_overrides bilincli
> ValueError — kablo ihtiyaci da dogmadi.

> **2026-07-18 GECE — K-56b URETIM KABLOSU KANITLANDI (kapi 3/4 + plan3
> ortam-OOM ertelemesi; kanit scripts/k56b_kapi.log + results/):** Kablo:
> ModeDecision.tilt_parca (ADIM -1 yapisal alan) -> targeted_tilt.
> hedefli_tilt_overrides (K-56a tarama mekanigi modullestirildi; filtre:
> grid-sigma + no-go serit-testi [adaptive ile ayni formul] + yerlesebilen-
> poz z-esigi) -> eval_gate + demo_pipeline c2f extra_rot_overrides (K-53d
> parite deseni; acik override ezer, None->tilt'siz birebir, tetiksiz
> setlerde SIFIR dokunus). TDD tests/test_k56b_tilt_kablo.py 8 test + komsu
> 109+58 yesil. KAPI KOSUSU (sirali, baseline kiyasli): **plan1 202.2 LEGAL
> — K-56a olcumuyle ONDALIK-OZDES (202.18468.../clear 2.03227...; kablo
> deterministik) = baseline 302.8'e -%33.2 IYILESME** · plan2 542.5 + d4
> 231.5 BIREBIR · plan3 ORTAM-OOM ile INVALID (kablo-ILGISIZ: plan3'te
> tilt tetiklenmez, ayni gun ayni kodla 3 kez 601.92 birebir; OOM "1.06MiB
> alloc" = K-57c kucuk-alloc deseni; makine 8+ saat kosu sonrasi commit
> baskisi 33.6/42GB) -> resmi verdict FAIL exit 1 AMA sebep cevresel.
> Kurtarma 2 kez denendi (ikincisi acilista sessiz oldu) — UCUNCU KOR
> DENEME YAPILMADI (recovery kurali); plan3-tek kurtarma (k56b_plan3_
> kurtarma.py hazir) YENIDEN-BASLATMA-SONRASINA ertelendi. A1 tam-PASS +
> baseline guncellemesi (302.8 -> 202.2, A8 gerekceli) o kosuya bagli.

> **2026-07-15 — SOKUM KONSOLU P2-P6 TESLIM (Eren: "plandakini eksiksiz
> uygula, frontend-design ile"):** P2 ortak `static/viewer3d.js` (iki
> sayfanin kopya viewer'i tek modulde; instancing/agir-sahne/isik/tam-ekran
> korunur + instanceId->part_id haritasi, pick, renk/vurgu API'leri; sonuc
> sayfasi instancing+tam-ekrani bedava kazandi). P3 siparis-rengi modu
> (12'lik palet, lejant cipleri) + siparis ozet kartlari. P4 tikla-tani
> (Raycaster; kimlik karti part_id->parca_kimlik registry'den — ada asla
> guvenmez; kopya/siparis/musteri/uid/sira/talimat). P5 rehberli sokum HUD
> (sol-alt kompakt; siradaki parca turuncu vurgulu digerleri soluk; buyuk
> adim sayaci + ilerleme + klavye oklari; kutu etiketi "X kutusuna").
> P6 sonuc.html paritesi (Sokum Plani bolumu + sira rozetleri) + eski
> kayitlarda tum yeni bolumler gizli (testli). `static/sokum_konsol.js`
> XSS-hijyenik (yalniz createElement/textContent — siparis/musteri adlari
> guvensiz veri). Dogrulama: test_sokum_konsolu 4 render testi + Playwright
> canli dogrulama (renk toggle/lejant/tikla-tani/rehber adimlama ekran
> goruntuleriyle Eren'e iletildi). Estetik: NESTING.FORGE endustriyel
> kimligi (Archivo + IBM Plex Mono, amber aksan) uzerine operator HUD'u.

> **2026-07-15 — K-51d ARA BULGU: PLAN1 HEIGHTMAP YOLU DA DUSUYOR (yeni
> acik is, K-54 adayi):** tilt-zorunlu kapi plan1'i dogru sekilde
> heightmap'e yonlendirdi AMA solve_coarse_to_fine yolu voxelize'da
> EXCEPTION: "baseplate_v2 hicbir oryantasyonda plakaya sigmiyor" —
> clearance margin dilation'i (pitch'e bagli >=1 voxel) 330.2mm parcayi
> 335mm plakadan tasiriyor. demo_pipeline web yolunda GRACEFUL
> clearance-cap var (margin kisilir, 2026-07-06); c2f/eval yolunda YOK.
> Yani plan1 su an HICBIR uretim yolundan 335+nogo+2mm sozlesmesinde
> cozulmuyor (129s rekoru OZEL egik-plaka SA deneyiydi, uretim yolu degil).
> COZUM ADAYI (K-54): graceful clearance-cap'in c2f'e tasinmasi + buyuk
> parcada margin=0 istisnasi (parca-plaka temas kuralini Eren'le netlestir).
> k51d yine exit 4 verecek; plan2 542.5 DETERMINISTIK dogrulandi (k51c ile
> birebir ayni deger, ikinci kosu).

> **2026-07-15 — K-53 PLANI: FAST'I MAX'A YAKLASTIR (Eren yonu: "fastleri
> gelistirelim, olmadi max'i opsiyon sunariz"):** Teshis — quality yalniz POZ
> SAYISINI kontrol eder (fast=8, max=AX24; decode ~3-4x). Ucurum dagilimi
> poz-duyarliligi dogruluyor: plan2 +%0.2 (8 yetiyor) / plan3 +%4.2 /
> d4 +%19 (kavite aileleri; d4'te ayrica R11'in 588p'de auto-tavan disi
> kalmasi). DENEY PLANI (k51d baseline kurulduktan SONRA, kapiya karsi):
> (a) K-53a plan3 @fast n_orientations {12,16,24} taramasi — kazanc/sure
> egrisi; (b) K-53b d4 ayni tarama; (c) kazanan konfig eval_gate 4-set
> PASS ise uretim default guncelle (aile-kosullu poz seti adayi: kavite
> ailelerinde 12-16, kutu/plaka'da 8 — sure yalniz kazanan yerde artar).
> Fallback: tarama kazandirmazsa quality=max UI opsiyonu onerilir.
> NOT: evaluate_set(n_orientations=...) override zaten var (tune_bo kablosu).

> **2026-07-15 — PLAN1 ROUTING CANLI-HATASI KAPANDI: TILT-ZORUNLU FIZIBILITE
> KAPISI (Eren istegi "plan1'i hallet"):** kok mekanizma GEOMETRIK KESIN
> bulundu: baseplate_v2 330.2x302 @335x335 plaka + no-go kolonu
> (x[152.5,185.5], y<=45) -> parca x'te en fazla 4.8mm kayabilir, no-go her
> duz eksen-hizali konumda parcanin ICINDE kalir = duz poz IMKANSIZ
> ("hedefli-TILT zorunlu" dersinin geometrik kaniti). NFV tilt bilmez ->
> 111/112 eksik yerlesim (k51c) / dikse 333.0 (K-40). COZUM:
> `predict_nfv_benefit(no_go_bounds=...)` ADIM -1 kapisi — hicbir duz pozu
> (WxD, DxW dikdortgen aritmetigi, kesin test) no-go'lu plakaya sigmayan
> parca varsa HEIGHTMAP zorunlu; fizibilite kaniti model dahil her katmani
> ezer. Default None = bit-ozdes; pipeline+eval no-go'yu gecirir. Dagilim
> (A5): yalniz plan1 tetikler — plan2/3 NFV, d4 NFV+rot AYNEN (canli probe).
> TDD 5 test. NOT: k51c plan1'i ESKI routing'le olctu -> exit 4 beklenir;
> k51d yeni routing'le baseline'i yeniden dener.

> **2026-07-15 — /run(rich) ~50s YAVASLAMA KOK TESHISI (A4 ucuz teshis,
> kosusuz):** kok = C4 mode_model promote (`94283b9`): rich senaryonun 3
> partisi de aile=solid_bulk (guven 0.79) + allowlist + conformal-tekil ->
> model KURALI EZIP heightmap yerine NFV secior (kural net-kutu diyordu,
> dogruydu — rich parcalari saf kutu, cavity yok). NFV yanlis-pozitifi
> kalite-guvenli AMA hiz vergisi buyuk (K-12: kutuda kazanc 0; pitch=2.0
> kalite recetesi + r11="auto" mesh-settle de NFV dalinda biniyor).
> 3 parti x (solve_nfv_kalite fast + r11 settle) ~= 50s olcegiyle ortusuyor.
> ACIK KARAR (Eren): (a) kabul (demo endpoint'i yavas ama kalite-guvenli),
> (b) mode_model katmanina net-kutu hiz-guard'i (mean_aspect_z<4 ->
> model atlanir; modelin allowlist ailesini kismen korler — A6 geregi
> otomatik yapilmadi), (c) rich demo senaryosuna nesting_mode="heightmap"
> sabitleme (yalniz demo'yu hizlandirir, uretimi degistirmez).
> Kalan olcum: parti basina solve-vs-r11 sure dagilimi (suite bosalinca).

---

## §4 — LİTERATÜR ENVANTERİ (araştırıldı / reddedildi / koda eklendi / denendi)

3 deep-research turu + 8 önceden-var PDF. Arşiv: `MOTOR/makaleler/`. Kapı: makale→tekniği kodla→benchmark;
geçemezse MERGE YOK (makale iddiası ≠ bizim veride iyi).

### Tur 01 — Algoritma-seçim / portföy (2026-06-14, `01_ARASTIRMA_BULGULAR.md`)
| Kaynak | Konu | Durum |
|---|---|---|
| Xu 2008 SATzilla | algoritma-seçim | ✅ KODA EKLENDİ (`selection/`) |
| Kerschke 2019 | seçim survey / özellik müh. | ✅ tasarıma yansıdı |
| Renau-Hart 2024 | kolay-instance ön-filtre | ✅ KODA EKLENDİ (`selection/prefilter.py`) |
| Kostovska 2023 | portföy budama | 🟡 kavramsal |

### Tur 02 — Magics kıyas (2026-06-21, `02_magics_kiyas_literatur_2026-06-21/`, 22 kaynak)
| Kaynak | Konu | Durum |
|---|---|---|
| **Lamas-Fernandez OR 2022** | voxel + **NFV** + bottom-left-back + VNS | ✅ **KODA EKLENDİ → C3 (K-04, ana kazanç)** |
| Stoyan/Bennell/Romanova EJOR 2018 | quasi-phi NLP sürekli rotasyon | ⏳ AÇIK (süper bilgisayar, §5 A1) |
| COMPOLY compaction | O(n²)→O(n) decomposition | ⏳ AÇIK (süper bilgisayar) |
| NIST sıralı/en-büyük-önce | yerleştirme sırası | ✅ doğrulandı (largest-first optimal, K-08) |
| Ikonen GA (NFP+GLS) | cavity-aware metaheuristik | ❌ denendi (M2-M6 ailesi NO-GO) |

### Tur 03 — Bakılmamış yöntemler (2026-06-25, `03_nfv_bakilmamis_yontemler_2026-06-25/`, 45 kaynak)
| Kaynak / aile | Konu | Durum |
|---|---|---|
| **A1** Phi-function NLP + sürekli rotasyon (Romanova/Stoyan/Bennell) | Magics'in muhtemel sırrı | ⏳ AÇIK — **süper bilgisayar, en güçlü** (§5) |
| **A2** Global compaction (CGF, eject-reinsert/swap) | layout-sonrası boşluk kapatma | ❌ DENENDİ NO-GO (K-11) |
| A3 DRL/diffusion (IR-BPP, DiffPack) | öğrenme-tabanlı | ⏳ düşük öncelik (2D/online, eşleşmiyor) |
| A4 Exact/MIP/CP | tam çözüm | ⏳ düşük öncelik (226 parçada tıkanır) |
| **B1** Binary AND+popcount (Turing 1-bit, XNOR conv) | FFT'siz exact korelasyon | ❌ naif DENENDİ NO-GO (H-10); RawKernel açık |
| **B2** VDB/OpenVDB sparse occupancy | bellek→ince pitch | ❌ DENENDİ NO-GO (H-11) |
| B3 BVH/octree/OBB broad-phase | kaba-eleme | ⏳ AÇIK (sınırlı, xy-bbox zaten var) |
| B4 Sparse-FFT, RT-core continuous | yaklaşık hızlandırma | ❌ ELENDİ (birebir değil, kural ihlali) |

### Önceden-var 8 PDF (`MOTOR/makaleler/pdf/`)
AM nesting taksonomi/review 2025, irregular 3D packing dataset, voxel convex-concave similarity, 3D
placement, energy-aware nesting+scheduling (hocanın alanı), DBLF varyantları. Çoğu okuma-listesinde
(`00_OKUMA_LISTESI.md`); voxel/NFV yaklaşımımızı besledi.

---

## §5 — AÇIK / BEKLEYEN YÖNLER (öncelik + efor + beklenti)

| # | Yön | Donanım | Efor | Beklenti | Not |
|---|---|---|---|---|---|
| **A1** | **Phi-function sürekli rotasyon NLP** (quasi-phi + IPOPT + decomposition) | **Süper bilgisayar** (büyük-N) | Çok yüksek | **ORTA-YÜKSEK** (düştü) — Magics'in muhtemel sırrı (diskret→sürekli rotasyon). K-13/K-14 darboğaz=büyük-levha global rotasyonu; AMA K-15: numune (küçük-N) darboğazı da rotasyon-kapalı | Küçük-N 6GB-fizibilite umudu K-15 ile **zayıfladı** (numune ince-plaka, eğmek uzatır). A1 hâlâ Plan2 büyük-levha paketi için geçerli ama "ucuz numune kanıtı" yolu kapandı. Açılırsa: rotasyon-amenable YENİ veri bulup orada test. |
| A1b | n=28 + 0.5mm fine NFV koşusu | Süper bilgisayar (bol VRAM) | Orta | Adil Magics kıyası + gerçek NFV tavanı | Bizde OOM (FFT-bellek, H-11). |
| B1' | bit-pack popcount RawKernel (gerçek B1) | 6GB | Yüksek (CUDA) | Marjinal (Amdahl + mikro-dersi) | Naif sparse NO-GO'ydu (H-10); önermiyoruz. |
| B3 | BVH/OBB broad-phase | 6GB | Düşük | Sınırlı (xy-bbox zaten broad-phase) | |
| — | Kalite kazanımlarını (n=8/adaptif) default heightmap'e bağla | 6GB | Düşük | Adaptif şu an 6× yavaş → önce maliyet ayarı | App-bağlama işi. |
| A3 | DRL/diffusion | GPU+eğitim | Yüksek | Belirsiz | 1-2 yıl sonra tekrar bak. |
| ~~K-17p~~ | ~~K-17 üretime bağla~~ → **KAPANDI 2026-07-03** (commit `07f697b`: `fine_settle.py` + solve_nfv default-on + pitch_mm export hizası) | 6GB | — | +%0.4-1.6 ÜRETİMDE | |
| ~~K-18p~~ | ~~AX24'ü quality=max'a bağla~~ → **KAPANDI 2026-07-03** (commit `f44ee80`; cross-dataset 3/3: plan1 −%6.9 / plan2 −%1.8 / plan3 −%10.5) | 6GB | — | ÜRETİMDE (opt-in max) | |
| **K-19p/F3** | Cidar-duyarlı pitch'i üretime bağla (tetik: `family∈{thin_shell,tube}`; K-19 GO — Deneme4 377.3→**282.0**, Magics açığı %12.7) | 6GB | Orta | **YÜKSEK (kabuk ailesi)** | Ön-şart: zaman bütçesi aktif + cross-dataset ≤%1 + süre-patlaması guard'ı (131dk/koşu!). Aile-genelleştirme programı F3; F4-B fast-path ile birlikte değerlendir. |
| ~~F2-v2~~ | ~~Sökülebilirlik-farkındalı NFV decode~~ → **KESİN NO-GO 2026-07-07** (plan3 prototipi ölçüldü, §3.1 F2-v2: sky-corridor legal 1145.6 vs illegal-NFV 944.4 = sökülebilirlik bedeli +201mm; aynı plakada heightmap 1046'yı bile geçemiyor) | 6GB | — | — | NFV kavite kazancı = gök-koridorunun yasakladığı şeyin kendisi; legal kurtarma bu yöntemle İMKANSIZ ölçüldü. Kalan kaldıraç A1 (serbest rotasyon — hoca 2026-07-07 cevabıyla artık RESMİ koşul). |
| ~~K-23~~ | ~~Kuyruk-öne SIRA deneyi~~ → **TEŞHİSLE KAPANDI 2026-07-04** (koşusuz NO-GO: özdeş parçada sıra etkisiz + çan içleri drop'a kapalı + tavanı ASY bloğu tek başına kuruyor — §3.1 K-23) | 6GB | — | — | 282.0 = drop semantiğinde YAPISAL kabuk tavanı. |
| ~~K-24~~ | ~~Bilinçli zincir-ekimi/dengeli-routing dekodu~~ → **KESİN NO-GO 2026-07-06** (Adım-2 çift-yöntem replay, §3.1 K-24: window 637-925 felaket; penalty dengelemeyi başardı ama tavan BİREBİR 264.0 — dengesizlik sebep değil semptomdu) | 6GB | — | — | **264 = gerçek plakada yapısal kabuk tavanı KANITLI** (282'nin devamı). Kalan ödül yalnız A1 (sürekli rotasyon) veya semantik değişikliği; kabukta istif kalitesi 9-çan kuyruğu dışında Magics-parite (250.5 vs 250.24). |
| ~~H-15p~~ | ~~Kabuk yolunda kısıtlı coarse arama~~ → **KAPANDI 2026-07-05** (commit `1cccad6`; E2E: 104.5dk → **9.2dk (11.3×)**, 282.0 BİREBİR; telemetri üretimde) | 6GB | — | ÜRETİMDE (opt-in wall_aware yolu) | F3 rollout süre ön-şartı karşılandı. |
| ~~H-16w~~ | ~~H-16 dirty-cache üretime bağlama~~ → **KAPANDI 2026-07-05** (E2E 5/5: 282.0 BİREBİR + **205s** (H-15p 553s'den 2.7×, K-19 orijinali 6272s'den **31×**) + cache telemetri hit %90.3 + RAM 1.17GB; MEDIUM-2 thread-safety YAPISAL kapalı: cache'li Bin3D _run_fine-lokal, parallel_decode OccupancyBin3D; reviewer PASS 0 C/H/M) | 6GB | — | ÜRETİMDE (wall_aware tetiği, `drop_cache=wall_aware_pitch`) | Kabuk koşusu artık ~3.4dk. LOW notları: thread-isolation test docstring'i geniş; `drop_cache_cap_mb` operatör-ayarlanamaz (default 300, peak 43.6MB — zararsız). |
| **C1** | ~~Büyük-parça voxelize SÜRESİ~~ → **algoritma-hızı KAPANDI (H-14, 3.1× birebir, 2026-07-02)**; kalan alt-parça = pitch politikası R6 | 6GB | Yüksek/RİSKLİ (R6) | DÜŞÜK-ORTA (kalan) | `_surface_cells` eksen-bazlı + bbox-kırpma üretimde (fine 159s→~50s/parça). GPU-tavan gerekçesi de kısmen karşılandı (voxelize payı 3× küçüldü). KALAN yalnız pitch R6 (tek 1mm parça → 356mm parça da 0.5mm): parça-kaybı+**H-06 duvarı**+cross-dataset riski — ayrı karar ister. |
| **K-56** | **plan1 hedefli-tilt'i ÜRETİM yoluna öğret** — **K-56a ÖLÇÜLDÜ 2026-07-18 = GO (§3): 302.8 → 202.2 LEGAL şerhsiz (−%33.2).** K-56b: (1) üretim kablosu KODDA+kapı 3/4 (plan3 çevresel-OOM; kurtarma + baseline + commit bekliyor), (2) ince-açı ~~taraması~~ → **NÖTR ÖLÇÜLDÜ 2026-07-19 (§3: 38 poz, 202.18 bit-özdeş, +0.0mm — açı granülasyonu kaldıraç değil)**, (3) soft no-go → **K-56c GO (202.2→171.70)**; (4) raw/K-56d MARJİNAL (−1.0) + kapı-hizalama dersi; (5) **K-56f PİNLEME GO 2026-07-19 (§3): 170.7→140.21 LEGAL — zincir toplamı 302.8→140.2 (−%53.7), dblf@1.0 141 geçildi; pinned_placements altyapısı kodda+testli.** KALAN: **K-56g düz-pinleme üretim kablosu** (geometrik tetik, A11) + sözleşme paketi (NOGO_STD 45→33 + web + 4-set kapı + baseline; sakin seans) + hoca netlikleri (no-go giriş/kenar teması) + 111-parça istif kalitesi (manuel üstü-istif ~%30 sıkı — plakasız alt-problem NFV açık soru) | 6GB | Düşük (altyapı hazır) | **YÜKSEK (plan1)** — dik dikilme cezası kanıtla kırıldı; y-tilt yapısal ölü (fp_y>290) | Eren sorusu 2026-07-17 ("plan1 niye bu kadar kötü"). Max/AX24 ÇARE DEĞİL; NFV plan1'de K-40 sert no-go. Eski miras kanıtı: dblf@1.0 tilt 141.0. p2 dev-parça tilt karşılığı KOŞUSUZ NO-GO (§3 2026-07-19). |
| **K-62** | **Delikli-parça düz-poz GERÇEK-GEOMETRİ no-go kapısı + düz-KANOPİ yerleşimi** — hoca 110,41 anatomisi ÇÖZÜLDÜ (2026-08-03 ekran görüntüleri `Veriler/hoca_ekleri_2026-08-03/`): manuel yerleşimde baseplate DÜZ/yatay ve diğer parçaların ÜSTÜNDE kanopi gibi; no-go kolonu ve dik duran parçalar çerçevenin DELİKLERİNDEN geçiyor; 112 parça, 330,2×328,1, toplam 110,41 (Magics Information paneli görüntüde). Bizim K-56 ADIM -1 kapısı (`adaptive_params._tilt_zorunlu_parca`) parçayı DOLU dikdörtgen (bbox) sayıyor → "hiçbir düz poz sığmaz" hükmü delikli parçada YANLIŞ-POZİTİF; tilt zinciri bu yüzden 140,2'de kaldı. **ÖN-TEŞHİS ✅ GO 2026-08-03 (§3 K-62):** footprint doluluk %26; düz poz GERÇEK geometride MÜMKÜN — rot0/rot180 (+flip), en iyi marj 0.5mm, ofset (0, 32.8) = K-56c y-üst-33 bulgusuyla örtüşüyor; bbox kapısının yanlış-pozitifliği KANITLI. İş: (a) kapıya gerçek-geometri fizibilite testi — geometrik tetik: footprint doluluk oranı düşük / no-go'yu alan delik var (A11-uyumlu, veri-adı yok); (b) KANOPİ mekanizması: delikli büyük parçayı iki-aşamalı dekodda parçaların ÜSTÜNE düz yerleştir (K-56f `pinned_placements` altyapısı hazır; delik-hizalama araması yeni); (c) sözleşme: no-go-temas toleransı (marj 0.5mm — "ufak giriş kabul" c9 uyumlu, karar gerek). **KÖK-SEBEP ENVANTERİ TAMAM 2026-08-03 (4 paralel kod taraması): tam analiz + geniş çözüm paketi (Ç1 gerçek-geometri kapı · Ç2 düz-kanopi iki-aşamalı dekod · Ç3 ML solidity özellikleri + heightmap+kanopi ARM'ı · Ç4 _drop_fallback/dilation düzeltmeleri · Ç5 holey_frames dağılımsal doğrulama) → repo `PLAN_KOK_SEBEP_VE_KISIT_V2.md` (Eren onayında). Yan bulgular: FEATURE_NAMES'te solidity yok (ML aileyi göremiyor) · NFV sıra-sabit (kanopi permütasyonu arama uzayında yok) · /plaka-ayar POST merge bug'ı (no_go_soft'u siler).** | 6GB | Orta | **ÇOK YÜKSEK (plan1)** — hedef bandı 110-130; insan mekanizması artık BİLİNİYOR (tahmin değil, görüntü-kanıtlı) | A10: 110,41 İNSAN yerleşimi (Magics-otomatik değil) + "no-go dahil" beyanı 2026-07-07; kanıt: HOCA_CEVAPLARI 2026-08-03 + 3 görüntü. K-56g düz-pin kablosuyla birleşir. |
| **K-58** | **R11 auto-tavan 150→600** (üretim yolunu şampiyonlara eşitler) — kod+TDD HAZIR 2026-07-19 (`nfv_solve.R11_AUTO_PARCA_TAVANI`; gerekçe K-55 hız kanıtı 588p 375dk→43.5dk; testler 32+57 yeşil, tasarım-pin testleri bilinçli güncellendi). KALAN: 4-set kapı ölçümü (beklenti: d4 231.5→~220.7, p3 601.9→~577.6, p2 +~1mm nötr-pozitif) + Eren commit onayı | 6GB | Düşük | **YÜKSEK (d4+p3 dengesi)** — üretim-şampiyon makasını kapatır (Eren 2026-07-19 "dengesizliği düzelt" yönü) | Kapı süresi +~45-60dk (R11 d4). Sakin-makine seansında plan3 kurtarmayla birlikte. |
| **K-57** | **Eval-kapısı hızlandırma paketi**: (a) münhasır-koşu politikası ✅ GEÇERLİ (yük süreleri şişiriyor, kanıtlı); (b) set-paralel orkestrasyon ✅ KODDA (parite 4/4 NOOP kanıtlı) ama **hız bu RAM'de gerçekleşmiyor** (16GB'de RAM-ağır NFV çiftleri OOM→seri-retry; §3 K-57b/c); (c) GPU-teyit kısmi (capabilities OK, per-decode telemetri açık); (d) ~~kalıcı voxel önbelleği~~ → **NO-GO 2026-07-18 (§3 K-57d: voxelize payı toplam %4.6 — Amdahl duvarı; cache ancak çok-tekrarlı APP senaryosunda ayrı gerekçeyle)** | 6GB | — | Kapı hızının kalan adresi: süre-kırılım telemetrisi + r11/decode/ölçüm-katmanı anatomisi (§3 K-57d yan bulgu) + RAM/boş-makine | Kanıt: k51e + K-57b/c parite koşuları + k57d_voxelize_pay.json. |

**Net:** 6GB'de hem KALİTE (5 kaldıraç + A2) hem KOLAY/ORTA HIZ (occ-FFT/sparse/VDB) TÜKENDİ. Gerçek
ilerleme = **SÜPER BİLGİSAYAR** (A1 sürekli rotasyon + ince-pitch için bol VRAM). Erişim konteyner-app
planında var (hocayla, [[project-konteyner-app-plani]]).

---

## §6 — META-DERSLER (sürece dair birikim — tekrar tuzağa düşmemek için)

1. **ÖLÇ-ÖNCE.** Deney → ölç → SONRA üretim. Hiç üretime körü körüne uygulama. (occ-FFT 3 yanlış "üretime al"dan, VDB gereksiz kurulumdan korudu.)
2. **Cross-dataset ŞART.** Tek veri (Plan2) overfit'tir. plan1/plan2/plan3 üçü de doğrulanmalı; biri bile bozulursa NO-GO (pitch overfit Plan1'i çökertmişti).
3. **Plan2 = en zorlu cavity testbed** (kutuluk 0.07). **Numune YANILTIR** (kutuluk 0.35, cavity-dominant değil) — kalite kararı asla numunede verilmez.
4. **Mikro ≠ gerçek decode.** Mikro-benchmark üst-sınırdır, garanti değil. occ-FFT (%26→negatif) ve sparse-popcount (6.67×→0.85×) iki kez bunu gösterdi.
5. **Birebirlik kapısı** (array_equal / aynı yükseklik) kaliteyi-bozmayan hız için ZORUNLU. Geçmeyen aday merge edilmez.
6. **SABİT-SAYI YASAK** — ama matematiksel garanti (küme-içerme: 4⊂8) veya donanım-türevi (RAM-tavanı) sabit MEŞRU; veri-uydurma sabit DEĞİL.
7. **Kod-öncesi teorem kur.** Monotoniklik (K-11) ve küme-içerme (K-05) sonuçları önceden açıkladı, boş deneyden korudu.
8. **Makale → kod → benchmark kapısı.** Makale iddiası ≠ bizim veride iyi (Ikonen GA, A2 compaction). Geçemezse MERGE YOK.
9. **Cavity = gerçek geometrik NFV'den EMERGENT**, özel kod değil. Aday-üretimi bbox-köşe olduğu sürece cavity çıkmaz (M1-M6 ezici kanıt).
10. **Üretim DEFAULT'a dokunma.** Tüm deneyler `scripts/`'te; NFV opt-in; default heightmap birebir korundu (2043 test yeşil).
11. **Darboğazı ÖLÇ, stratejiyi uygulamadan ÖNCE** (height-driver teşhisi, K-14). Koordineli-rack yanlış parçalara harcandı çünkü "tavanı ne belirliyor" önce ölçülmedi; ölçülünce darboğazın rack-uygun OLMAYAN büyük levhalar olduğu çıktı. Hangi parçayı döndüreceğini bilmeden rotasyon stratejisi körlemesine.
12. **Greedy ⊕ rotasyon = miyopi (K-13).** Küme-içerme garantisi (4⊂8, K-05) eksen-hizalıda tuttu ama sürekli off-axis'te TUTMADI: greedy eğik pozu erken/izole kilitler, footprint büyütür. Rotasyon GLOBAL optimizasyon ister (eşzamanlı açı+pozisyon), greedy'ye cıvata olmaz.

---

## EK — kaynak haritası (izlenebilirlik)
- **Handoff'lar:** `RESUME_2026-06-{21..27}.md` (kronolojik, en güncel = **`RESUME_2026-06-27.md`**: akıllı
  mod seçimi K-16). Önceki: `RESUME_2026-06-26.md` (mail-fix + voxelize OOM H-12 + çift-voxelize H-13).
- **NFV sayısal:** `ANALIZ_NFV.md` (§1-5 gelişim/overfit, §6-9 NO-GO kanıtları).
- **Kıyas/M1-M6:** `MAGICS_ANALIZ.md`, `PLAN_KIYAS_IYILESTIRME.md`, memory [[project-kiyas-iyilestirme]].
- **Backlog:** memory [[project-nfv-sonraki-oturum-backlog]] (madde 1-12).
- **Literatür:** `MOTOR/makaleler/{00_OKUMA_LISTESI,01_ARASTIRMA_BULGULAR}.md` + `02_*`/`03_*` arşivleri.
- **App tarafı (kapsam dışı):** `APP_YOL_HARITASI.md`, [[project-konteyner-app-plani]].
- **Deney scriptleri:** `scripts/c3_*.py`, `scripts/m{1..6}_*.py` (hepsi negatif/pozitif kanıt, üretime dokunmadı).

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
```

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
`scenario["nesting_mode"]="nfv"` (UI checkbox) → `solve_nfv`. Default BİREBİR değişmedi (2043 test yeşil).
| Bileşen | Nasıl | Adaptif mi? | Dosya |
|---|---|---|---|
| Çekirdek | FFT-NFV: `feasible = irfftn(rfftn(occ)·rfftn(grid_flip)) < 0.5`; en düşük z'de BLB | sabit (geometrik exact) | `parallel_decode.py`, `fft_backend.py` |
| Decode→üretim | NFV decode → (pid,oi,x,y,z) → `Bin3D.place` REPLAY (drop YOK, cavity korunur) | — | `nfv_solve.py` |
| Pitch | `suggest_nfv_pitch` — parça-koruyan EN KABA + bellek pre-flight + plaka guard | ✅ veri+donanım | `instances/pitch.py` |
| Oryantasyon | n=8 default (4⊂8 küme-içerme garanti); `quality="max"`→RAM-tavanı (8→12→28) | ✅ küme-içerme + RAM | `nfv_solve.py:31` |
| Dispatcher | GPU-resident → CPU Kol A → seri (probe + graceful fallback, hepsi BİREBİR) | ✅ donanım-probe | `parallel_decode.py best_decode`, `capabilities.py` |
| Hız | xy-bbox kırpma + kademeli z-dilim + GPU-resident (3-5.5×) | — | `parallel_decode.py` |

**Kazanç (3 gerçek veri, NFV n=8 vs default heightmap):** Plan2 **%29** · Plan1 **%14** · Plan3 **%20**.
Saf-kutuda (boxy) %0 (cavity yoksa avantaj yok = doğası, overfit değil). Bedeli: NFV default'tan ~10-40× yavaş.

---

## §3 — DENENEN YÖNTEMLER ENVANTERİ

### 3.1 KALİTE

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

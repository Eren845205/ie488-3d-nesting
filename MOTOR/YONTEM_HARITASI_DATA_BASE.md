# YÖNTEM HARİTASI — Nesting Motoru Karar Veritabanı (DATA BASE)

> **Bu dosya = tek doğruluk kaynağı (single source of truth).** Nesting motorunda en baştan bugüne
> denenen HER yöntem, neden işe yaradı/yaramadı, şu an üretimde ne aktif, sırada ne var — hepsi burada.
> Amaç: deneme-yanılma birikimini kalıcı bir **varlığa** çevirmek; aynı duvara iki kez toslamamak;
> her yeni oturuma yön vermek.
>
> **Kapsam:** yalnız **nesting motoru** (algoritma / kalite / hız). App/iş tarafı (mail otomasyon, LLM,
> dağıtım, IP, müşteri planı) ayrı dosyada: `APP_YOL_HARITASI.md` + ilgili memory'ler.
> **Son güncelleme:** 2026-06-30 · **Branch:** `m1-cavity-nfv` · **Rollback tag:** `checkpoint-2026-06-22-faz1-2`

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

#### [K-01] M1 — Greedy constructive cavity (NFV-lite, yüzey-temelli aday)
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

> **KALİTE ÖZET:** 6GB'de açığı kapatacak algoritma kaldıraçları TÜKENDİ — pitch + eksen-oryantasyon +
> sıra + tie-break + compaction + **sürekli-serbest-rotasyon (K-13) + koordineli-rack (K-14)** = **7'si de
> ölü/doygun**. Plan2 darboğazı = ~20 büyük levha (düz yatamaz, istiflenir); numune darboğazı = ince plakalar
> (düz zaten optimal, K-15) — **her ikisi de rotasyona kapalı, farklı sebeplerle**. Magics %6 açığı = fine
> pitch (0.5mm) + büyük levhaların global rotasyonu (ikisi de 6GB OOM/erişilemez) → **SÜPER BİLGİSAYAR** tek
> yol (§5 A1). NOT: A1'in küçük-N (numune) 6GB-fizibilite umudu da K-15 ile zayıfladı (numune rotasyon-kapalı).

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

> **HIZ ÖZET:** Birebir/kaliteyi-bozmayan KOLAY-ORTA NFV hız kaldıraçları TÜKENDİ (NFV zaten 3-5.5×). **2026-06-26
> ÜRETİM gerçek-veri yolu:** Plan2 default heightmap ÇÖKÜYORDU → **OOM-chunk (H-12) çökme giderildi (birebir)** +
> **çift-voxelize (H-13) ~2× (birebir)**. KALAN büyük-parça darboğazı = `coarse_to_fine` FINE adımı 159s/parça
> @0.5mm pitch (**pitch R6** — tek 1mm parça → 356mm parça da 0.5mm) → AÇIK/riskli iş (§5: surface_cells hız +
> pitch politikası, H-06 duvarı + parça-kaybı + cross-dataset). Kalan başka: bit-pack popcount RawKernel / BVH.

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
| **C1** | **Büyük-parça voxelize SÜRESİ** (`_surface_cells` hızı + pitch R6, fine 0.5mm 159s/parça) | 6GB | Yüksek/RİSKLİ | **ORTA** (APP kullanılabilirlik) | H-13 sonrası AÇIK. `coarse_to_fine` FINE adımı büyük parçayı 0.5mm voxelize. pitch kabalaştırma=parça-kaybı+**H-06 duvarı**+cross-dataset kalite; `_surface_cells` algoritma-hızı daha güvenli. **YENİ GEREKÇE (2026-06-30, H-04 doğrulama):** voxelize NFV'de GPU-decode'la hızlanMAZ (CPU-bound, paylaşılan) → end-to-end GPU kazancının TAVANI = voxelize payı (596s-seti ölçümünde h=727'de 54s/320s = %17). Voxelize'ı hızlandırmak GPU faydasını da çoğaltır (decode zaten 2.67×). |

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

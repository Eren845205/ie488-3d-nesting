# PLAN_KIYAS_IYILESTIRME.md — Magics Kıyası + İyileştirme Yol Haritası

> **AMAÇ:** Yeni session'da bilgi kaybı olmadan kaldığımız yerden devam.
> Konu: bizim nesting motoru, gerçek hoca verisinde Magics'in gerisinde kalıyor
> (yükseklikte %15–26) ve tek büyük sette çok yavaş (~78 dk). İki sorunu
> **çözmek için önce MAKALE ARAŞTIRMASI** (yeni session'da), sonra plan+kod.
> Tarih: 2026-06-21. Branch: `app-demo-build`.

---

## 0. YENİ SESSION — BURADAN BAŞLA

1. Bu dosyayı + `[[project-kiyas-iyilestirme]]` memory'sini oku.
2. İlk iş: **deep-research** (aşağıda §5 sorgu listesi) — fine-angle 3B rotasyon
   packing + AM build-plate packing + voxel/octree hız.
3. Araştırma çıktısını sentezle → §6 fikirleri somut plana çevir → kullanıcıya
   önceliklendirme sun. Koda BAŞLAMADAN önce kullanıcı onayı.
4. Kıyas rakamlarını yeniden üretmek istersen: §4'teki scriptler hazır.

---

## 1. KIYAS SONUÇLARI (taze, 2026-06-20/21)

Hoca verisi: `C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan{1,2,3}\Plan{1,2,3}\*.stl`

| Plan | Parça (tip/adet) | Bizim yük. | Hoca (Magics) | **Oran** | Plaka | Doluluk | Süre |
|---|---|---|---|---|---|---|---|
| Plan1 | 12 / 112 | 106.7 mm | **YOK** (hoca yük. gelmedi) | — | oto 340×340 | %16.6 | ~5.5 dk* |
| Plan2 | 16 / 226 | **621.0 mm** | **492.39 mm** | **1.26×** | 328.74×328.19 (hoca plakası) | %8.0 | **~78 dk** |
| Plan3 | ~15 / 109 | 685 mm | 593.86 mm | 1.15× | — | ~%16 | (eski not) |

\* Plan1 süresi Plan2 ile CPU paylaşırken ölçüldü → şişkin.

**Hoca Plan2 referansı `Veriler/Plan2.jpg` Magics ekran görüntüsünden teyitli:**
Length 328.74 · Width 328.19 · **Height 492.39 mm** · "226 of 226 parts".

**Plan2 koşusu:** pitch 0.5mm, kazanan algoritma `sa_auto`, 226/226 yerleşti,
nest 4664 s. Plan1 koşusu: pitch 1.02mm, auto plaka 340.2×340.2.

### Adetler (mail görsellerinden, repoda KAYITLI — kaybolmasın)
**Plan1 (toplam 112):** ENG-500053_L-Bracket 22, 811793-1 20, TAPER-GAUGE-1 10,
bobbin_1_v2 12, bobbin_2_v2 12, bobbin_3_v2 6, 811791-1 19, pyramid_with_doors 5,
MTShoe 1, M18_toShopVac_Adapter 2, part262835 2, baseplate_v2 1.

**Plan2 (toplam 226):** P00000002586 20, part284676_06B23B8_model_r_0 15,
part282114_07D4114_model_r_0 9, PARCA_NYLON-12_KABLO_KORUMA **93**,
PO-TR154979-17747_P282334 5, _P282335 5, _P282336 5, _P282337 5,
PO-TR154989-17667_P282407 20, _P282410 12, PO-TR156122-17810_P284641 17,
part282115_07D4113 9, PO-TR155318-17709 5, PO-TR156398-17851 4,
PO-TR155890-17789 1, PO-TR155308-17705 1.

**Plan1 hoca yüksekliği YOK** — kullanıcıda yok; gelirse Plan1 oranı tamamlanır.

---

## 2. SORUN A — KALİTE (Magics'in %15–26 gerisinde)

Gap büyük ihtimalle **arama (SA/GA/Tabu) değil, YERLEŞTİRME İLKESİ.**

### Kök sebep A1 — Rotasyon çok kaba (EN BÜYÜK KALDIRAÇ, hoca da söyledi)
- Hoca açıkça dedi: **"0.5–1 dereceye kadar hassas döndürme gerekli; sizde sadece
  90° var."**
- Kod: `src/nesting3d/voxelize.py:60 rotation_matrices()` — 28 "master poz":
  - 0..7: eksen-hizalı 90° rotasyonlar
  - 8..11: **eğik pozlar** ama yalnız X ekseni + kaba {20°,25°,30°,35°}
  - 12..27: kalan eksen-hizalı (küpün 24 simetrisi)
- **Kıyas koşusu `n_orientations=4` ile çalıştı** (`scripts/demo_pipeline.py:121,261`)
  → **yalnız ilk 4 poz, HİÇ EĞİM YOK.** Yani 1.26× sonucu saf 90° ile.
- İki katman eksik: (a) mevcut eğik pozlar bile default kapalı; (b) 0.5–1°
  serbest/sürekli rotasyon hiç yok (28 sabit poz enumerasyonu ≠ sürekli açı).
- **0.5° × 3 eksen = milyonlarca poz → enumerasyon imkânsız → SÜREKLİ açı
  üzerinde ARAMA/coarse-to-fine rotasyon gerek** (bellek A14 fikri).

### Kök sebep A2 — Heightmap / üstten-düşürme istifi (doluluk %8'in nedeni)
- `src/nesting3d/dblf.py`: yerleştirme `(z_top, z, y, x)` leksikografik — parça
  yükseklik profilinin üstüne en iyi geçişmeyle oturuyor (skyline/heightmap drop).
- Sonuç: parça **çıkıntı altına sokulamıyor, büyük parçanın oyuğuna/iç boşluğuna
  gömülemiyor** (part-in-part yok). Magics gerçek 3B kilitleme yapıyor.
- %8 doluluk bunun kanıtı (çok seyrek istif).

### Kök sebep A3 — Voxel çözünürlüğü ince kilitlenmeyi kabalaştırır
- 0.5mm'de bile yüzey kilitlenmesi kaba; incelt → hız ölür (Sorun B ile gerilim).

### İkincil
- Tek konteyner/katman stratejisi; arama zayıf ilkenin üstünde çalışıyor
  (iyi ilke > iyi arama).

---

## 3. SORUN B — HIZ (Plan2 ~78 dk)

### Kök sebep B1 — Tek ince parça tüm partiyi boğuyor
- Plan2'de **1 mm kalınlık** parça var (bbox≈[6,1,19.5] — 93 adet NYLON kablo
  koruma). `src/nesting3d/instances/pitch.py suggest_pitch` = min_feature/2.5 →
  global pitch **0.5 mm**'ye iniyor.
- 328×328×492 / 0.5³ ≈ **~270 milyon voxel** → tek ince geçiş bile dakikalarca.
- **Tek parça yüzünden TÜM parçalar en ince çözünürlüğün bedelini ödüyor**
  (uniform global pitch).
- Coarse-to-fine (`src/nesting3d/coarse_to_fine.py`) tam-optimizasyonu kurtarıyor
  ama fine geçişin maliyeti bu tek parçadan ötürü patlıyor.
- Kanıt: 2.5mm denedik → o 1mm parça yok olduğu için ValueError (voxelize.py:220
  "min_dim/pitch<0.5 kaybolur"). 1.5mm denedik → kesin koşu (0.5mm) önce bitti.

---

## 4. KIYASI YENİDEN ÜRETME (hazır scriptler)

- `scripts/plan1_kiyas_kosu.py` — Plan1, adetler gömülü, auto plaka.
- `scripts/plan2_kiyas_kosu.py` — Plan2, adetler + HOCA plakası (328.74×328.19),
  oranı basar. (Bunlar throwaway analiz scripti; commit'siz olabilir.)
- Koşu: `PYTHONIOENCODING=utf-8 python -u scripts/plan2_kiyas_kosu.py`
- ⚠️ Plan2 ~78 dk sürer (0.5mm pitch). Hızlı yaklaşık için fine_pitch≥1.5mm
  (`scripts/plan2_hizli.py`) ama 1mm parça için >2mm pitch çöker.

---

## 5. ARAŞTIRILACAK — DEEP RESEARCH SORGULARI (yeni session ilk iş)

1. **3D irregular packing / nesting with free (continuous) rotation** —
   no-fit-polyhedron (NFP-3D), phi-functions, quasi-phi-functions.
2. **Additive manufacturing build-volume / build-plate packing** (tam bizim
   problem: çok parça tek hacme, yükseklik/packing optimize) — SLS/MJF nesting.
3. **Coarse-to-fine / multi-resolution rotation search** (0.5–1° hassasiyet) —
   global açı tarama + yerel iyileştirme.
4. **Voxel vs true-mesh collision; sparse voxel / octree** ile bellek+hız;
   parça-bazlı çözünürlük (ince parçanın global pitch'i belirlemesini önleme).
5. **Cavity-aware / part-in-part 3D nesting** (büyük parça oyuğuna küçük parça).
6. (Bonus) Magics "SmartNesting"/Sinter modülü akademik karşılıkları.

Çıktı: her yön için "değer/efor + bizim koda nasıl oturur" özeti.

---

## 6. FİKİR MENÜSÜ (araştırma sonrası somutlaşacak)

**Kalite:**
- **Fine-angle rotasyon (coarse-to-fine):** kaba açı tara → kazanan etrafında
  0.5–1° ince tara. EN YÜKSEK GETİRİ (hoca da bunu istedi). Önce kolay adım:
  default `n_orientations`'ı artır (eğik 8..11 pozları aç) → bedava kısmi kazanç.
- Oyuk-farkında / part-in-part yerleştirme.
- Üstten-düşürme yerine çıkıntı-altı yerleşime izin (gerçek 3B çakışma).
- Hedef fonksiyonuna doluluk ödülü.

**Hız:**
- İnce parçayı global pitch'ten ayır: kaba grid'de min-1-voxel tabanlama / 2B
  ayak-izi muamelesi → global pitch kalın parçalara göre.
- Octree / seyrek voxel (voxellerin çoğu boş).
- Tekrarlı voxelizasyon paylaşımı (93 aynı parça — `expand_quantities` şablon
  paylaşımı var mı doğrula).
- GPU voxelize/çakışma; süper bilgisayarda portföyü düğümlere dağıt.
- (Not: parti-paralel zaten VAR — 5 ayrı sipariş için; tek devasa set için
  yardım etmez. Detay: paralel env'leri `[[project-app-gercek-veri-durum]]`.)

**Kilit içgörü:** Kalite açığı = İLKE (kaba rotasyon + heightmap). Hız açığı =
tek-parça-pitch'i-belirliyor. Büyük ölçüde **bağımsız iki iş.**

---

## 7. KARAR / YAKLAŞIM
- Kullanıcı kararı: bu iyileştirmeleri eklemeden önce **makale araştırması**,
  ve onu **YENİ SESSION'da** yapacak. Bu dosya o devirin handoff'u.
- Doğrudan koda atlama YOK — önce araştır, sonra planla, sonra kullanıcı onayı.

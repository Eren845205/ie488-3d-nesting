# MAGICS ALGORİTMA ARAŞTIRMASI — Genel Yaklaşım & Karar Mantığı

> Deep-research sentezi (2026-06-22, 19 kaynak, 22 doğrulanmış iddia). Amaç:
> Magics'in GENEL nesting prensibini anlamak (tek veriye overfit etmeden), kendi
> voxel-3B motorumuzu ona göre tasarlamak. Bu-veri sayısal analizi: `MAGICS_ANALIZ.md`.

## 1. MAGICS'İN İÇ ALGORİTMASI AÇIK DEĞİL — ama davranışı/ayarları belgeli
- Magics'in **iç algoritması (çarpışma yöntemi, yerleştirme, meta-sezgisel) GİZLİ**,
  hiçbir kaynakta yok. Sadece YETENEK/PARAMETRE düzeyinde belgeli.
- **Belgeli davranış:** tam-3B hacim yerleştirme (2.5D katmanlı değil), plaka dolunca
  otomatik sonraki plakaya geçer; **yoğunluk optimizasyonu** + kullanıcı oryantasyon
  kısıtları; parça-bazlı dönüş/öteleme serbestliği ("Freedom of parts"), **varsayılan
  dönüş açısı 90°** (= bizim kaba rotasyonumuzla AYNI; daha ince adım ayarlanabilir);
  **build-height kontrolleri** (3 mod: Distribute in Height / Optimise Slice Volume /
  ikisi); **4 durdurma kriteri** (ilk çözüm / hedef yoğunluk / manuel / süre → anytime
  metaheuristic). Kaynak: materialise.com Nester + Magics Academy tutorial.
- **UYARI (yanılgı düzeltmesi):** "Magics nesting patenti" diye anılan US10921780B2
  aslında **Assembrix Ltd.'in** (Materialise değil!), PRM/RRT motion-planning kullanıyor
  → **Magics modeli olarak KULLANMA.** İlk araştırmada bunu yanlış etiketlemiştim.

## 2. ASIL ALGORİTMİK ŞABLON — akademik toz-yatağı literatürü (Magics'in muhtemel sınıfı)
Magics'i kopyalayamayız ama **alanın standart mekanizması** (Magics'in de büyük olasılıkla
kullandığı sınıf) net:

**A) Lamas-Fernandez/Bennell/Martinez-Sykora — Operations Research 2022 (EN GÜÇLÜ analog):**
- **Voxel temsili + No-Fit-Voxel (NFV) çarpışma** (2B no-fit-polygon'un 3B'si; ayrık-küp
  kesişimi → çok hızlı çakışma testi).
- **Deterministik "bottom-left-back" yerleştirme:** aday konumlar **önce en küçük z, sonra
  x, sonra y** sırasıyla değerlendirilir → ilk geçerli konum en-alt-sol-arka. (3B gravity-drop.)
- **Hedef: build-height minimizasyonu** (strip-packing) — bizim hedefle AYNI.
- **Oryantasyon SABİT;** arama değişkenleri = parça **SIRASI + köşe-kuralı** (4 köşe varyantı).
  Oryantasyon yukarı-akışta (upstream) belirleniyor.
- **Metaheuristic:** ILS / Tabu / **VNS (en iyi)** — sıra/layout üzerinde arama.

**B) OBB-tree + SVD-principal-axes + flower-pollination — IJAMT 2022:**
- Oryantasyonu **principal axes** ile seçer (en büyük print-alanı / en küçük print-yükseklik).
- **En büyük parça önce** (descending OBB area) sıralama. Min build-height birincil, origin'e
  yakınlık ikincil.
- **Voxelizasyonu REDDEDİYOR** (her oryantasyon/pozisyon yeniden voxelize → pahalı/bellek);
  OBB bir kez kurulur. → **Bizim voxel motorunun ZAYIF noktası tam bu** (per-orientation
  revoxelize maliyeti); azaltmalıyız (önbellek/coarse-to-fine/OBB-prefilter).

**C) NIST taksonomisi (genel karar mantığı):**
- **İki-adım** (önce oryantasyon, sonra konum — ucuz, lokal-optimum) vs **entegre** (birlikte —
  global, pahalı). 
- 3B nesting NP-hard → **sıralı tek-tek yerleştirme** standart (hepsini aynı anda değil).
- **Çok-parçalı nesting'de 3 rotasyon da (özellikle Z/in-plane) ŞART** — tek parçada Z önemsiz
  ama çoklu nesting'de parçaların birbirine göre dizilişini değiştirir.

## 3. EN KRİTİK İÇGÖRÜ — "cavity nesting" ÖZEL bir şey DEĞİL, EMERGENT
- **Hiçbir kaynak Magics'in özel "parça-içi-parça" mantığı olduğunu göstermiyor.** Cavity
  doldurma, **genel overlap-free 3B paketlemeden KENDİLİĞİNDEN doğuyor:** NFV ile bir parça,
  çakışmadığı HER yere konabilir — büyük parçanın oyuğunun içi dahil. Özel "cavity" kodu YOK;
  sadece **gerçek-3B çakışma testi** (heightmap-drop değil) yeterli.
- **Bizim gap'in açıklaması net:** heightmap üstten-düşürme oyuğa GİREMEZ → cavity emerge edemez.
  `extreme_point.py` 3B çarpışmaya sahip AMA aday üretimi bbox-köşe → oyuk-içi konum hiç ÖNERMİYOR
  → cavity yine emerge etmiyor (bu yüzden numune testinde heightmap'le berabere kaldı!).
- **Çözüm:** gerçek-3B + **aday konumların oyuk-içini de kapsaması** (NFV/free-space adayları).
  Cavity o zaman kendiliğinden dolar.

## 4. KENDİ MOTORUMUZ İÇİN GENEL TASARIM PRENSİPLERİ (overfit değil, alan-standardı)
1. **Hedef:** build-height min (birincil) + kompaktlık/origin-yakınlığı (ikincil). ✓ zaten var.
2. **Temsil/çarpışma:** voxel + **NFV gerçek-3B overlap** (destek yok, toz-yatağı). 3B çarpışma
   `OccupancyBin3D`'de VAR; eksik = NFV-tarzı aday üretimi.
3. **Yerleştirme:** sıralı tek-tek, **bottom-left-back (z→x→y) deterministik** kural.
4. **Sıra:** en büyük önce (print-area/OBB/hacim). ✓ zaten var.
5. **Oryantasyon:** iki-adım (upstream), low-height poz; çok-parça için **Z/in-plane rotasyon dahil**. ✓ n=8.
6. **Arama:** SIRA (+kural) üzerinde metaheuristic; **VNS-sınıfı** en iyi. (Bizde SA var.)
7. **Aday konum (ASIL İŞ):** oyuk-içi geçerli konumları da üreten NFV/free-space adayları
   (bbox-köşe DEĞİL) → cavity emerge eder.
8. **Hız:** per-orientation revoxelize maliyetini azalt (önbellek/coarse-to-fine/OBB-prefilter).

## 5. NET YOL HARİTASI (tek thread, kanıta dayalı)
- **M1 (lever):** `OccupancyBin3D`'ye **NFV/free-space aday üretimi** ekle (oyuk-içi konumlar);
  bottom-left-back kuralı; sıralı en-büyük-önce. **Test:** Plan2'de katı-bbox tabanını (586mm)
  GEÇ → Magics'e (492) yaklaş. Bu, cavity'nin emerge edip etmediğini KANITLAR (gerçek GO/NO-GO).
- **M2:** 3B constructive packer'ı **metaheuristic** (VNS/SA) ile sar (sıra araması).
- **M3:** Hızlandır (fast-path + OBB-prefilter + coarse-to-fine; süper bilgisayar).
- Oryantasyon iki-adımda kalır (n=8 + principal-axes low-height); Z-rotasyon dahil.

**Özet:** Magics'i kopyalamıyoruz (gizli) ama **genel prensibi netleştirdik:** gerçek-3B
overlap-free (NFV) paketleme → cavity kendiliğinden dolar. Bizim tek eksiğimiz oyuk-içi aday
üretimi. Bu, hem bu-veriye hem genele uyar (overfit değil).

Kaynaklar: Materialise Nester/Academy; Lamas-Fernandez OR 2022 (eprints.whiterose.ac.uk/186468,
INFORMS opre.2022.2260); OBB/FPA IJAMT 2022 (s00170-021-07954-y); NIST (tsapps.nist.gov 930053).
Tam doğrulama: deep-research raporu (101 agent).

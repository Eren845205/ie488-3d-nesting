# Araştırma Bulguları — küratörlü makale kısa listesi (2026-06-14)

> Kaynak: deep-research harness (çoklu web arama → kaynak çekme → 3-oy adversaryal
> doğrulama → sentez). Aşağıdaki künyeler **doğrulanmıştır** (her iddia 3-0 oyla
> teyit; uydurma yok). Motorumuzun 5 boşluk alanına (bkz 00_OKUMA_LISTESI) göre.

## ⚠️ Kapsam dürüstlüğü

- **Gap 1 (Algoritma Seçimi) + Gap 2 (Hyper-Heuristik): KAPSAMLI doğrulandı** (9 bulgu).
- **Gap 3 (modern 3D operatörler/ALNS), Gap 4 (extreme-point yerleştirme), Gap 5
  (voxel/SDF AM + dataset): bu turda doğrulanmış birincil kaynak ÇIKMADI** —
  araştırma bütçesi Gap 1-2'ye yoğunlaştı. Bunlar açık; ikinci araştırma turu
  gerekir. (Repodaki mevcut PDF'ler Gap 3-5'i kısmen kapsıyor — 00_OKUMA_LISTESI.)
- Aday (henüz doğrulanmamış, kaynak listesinde geçen) Gap 4 makaleleri: Martello-
  Pisinger-Vigo 3D-BPP (OR 2000), Crainic-Perboli-Tadei extreme-point (CIRRELT/
  IJOC). İkinci turda doğrulanacak.

---

## Gap 1 — ALGORİTMA SEÇİMİ / instance başı portföy (✅ doğrulandı)

> Bizim PORTFÖY şu an "hepsini koş, en iyiyi POST-HOC seç". Literatür: instance
> özelliklerinden KAZANANI TAHMİN et (önceden), pahalı tam-portföyü atla.

| # | Künye | Teknik | Motorumuza nasıl |
|---|---|---|---|
| 1 | **Xu, Hutter, Hoos, Leyton-Brown (2008). SATzilla: Portfolio-based Algorithm Selection for SAT. JAIR 32:565-606** (arXiv:1111.2249). UBC — alanın TEMEL makalesi, binlerce atıf. | Empirik zorluk modeli (regresyon): instance özelliği → çözücü-başı runtime/skor tahmini → en iyi çözücüyü ONLINE seç. | §6.3.1 algoritma-seçim modelinin omurgası. Telemetrimiz (özellik vektörü + çözücü sonuçları) zaten bunun eğitim verisi. |
| 2 | **Kerschke, Hoos, Neumann, Trautmann (2019). Automated Algorithm Selection: Survey and Perspectives. Evolutionary Computation 27(1):3-45** (arXiv:1811.11597). Kanonik survey. | Problem tanımı + "performans tamamlayıcılığı" (tek SOTA algoritma yok) + ucuz instance özellik kataloğu. | Seçim katmanımızın tasarım planı + özellik mühendisliği checklist'i; portföyümüzün tamamlayıcı çözücüleri tam da seçimin sömürdüğü ön koşul. |
| 3 | **Pulatov, Anastacio, Kotthoff, Hoos (2022). Opening the Black Box: Algorithm Selection with Algorithm Features.** (cs.uwyo.edu/~larsko). | İki paradigma: (a) kazananı doğrudan tahmin (sınıflandırma) VEYA (b) çözücü-başı performans tahmin + en iyi (regresyon = SATzilla). Zengin özellik → oracle'a (virtual-best) %26-28 yaklaşma. | Hangi modeli kuracağımızın kararı: başlangıç için karar ağacı/RF sınıflandırma (okunabilir kural). |
| 4 | **Renau & Hart (2024). Identifying Easy Instances to Improve Efficiency of ML Pipelines for Algorithm-Selection. PPSN XVIII (LNCS)** (arXiv:2406.16999). Edinburgh Napier (Emma Hart). | "Kolay" instance ön-filtresi: tek generalist çözücüyle çözülenleri ayır, pahalı özellik/seçim hesabını ATLA, bütçeyi zor instance'lara aktar. VBS/SBS/seçici üstüne kazanç. | **EN YÜKSEK değer/efor.** Bizde çok instance'ta tüm çözücüler BERABERE (kolay) — ön-filtre orada doğrudan DBLF'ye gider, portföyü zora ayırır. |
| 5 | **Kostovska, Cenikj, Vermetten et al. (2023). PS-AAS: Portfolio Selection for Automated Algorithm Selection. AutoML 2023, PMLR v224** (arXiv:2310.10685). | Algoritma davranış meta-temsili → benzerlik grafı → çeşitli/temsili portföy seçimi. **DİKKAT:** "alt-portföy her zaman tam portföyü geçer" iddiası ÇÜRÜTÜLDÜ (0-3). | Çözücü setimizi budama (SA vs Multi-Start SA gereksiz mi?) için kavramsal yön — ama tam portföy default'umuz güvende (alt-portföy garanti değil). |

## Gap 2 — HYPER-HEURİSTİK / instance-özel konfigürasyon (✅ doğrulandı)

> Bizim INSTANCE-TUNER zaten bir **seçim hyper-heuristiği** (menüden seç + monoton
> kabul). Literatür onun kanonik yapısını + packing'de kanıtını veriyor.

| # | Künye | Teknik | Motorumuza nasıl |
|---|---|---|---|
| 6 | **Burke, Gendreau, Hyde, Kendall, Ochoa, Özcan, Qu (2013). Hyper-heuristics: A Survey of the State of the Art. JORS** (+ "Revisited" 2019, Burke et al.). Nottingham ASAP — kanonik taksonomi. | İki eksen: arama uzayı (seçim vs üretim; constructive vs perturbative) × geri-besleme (no-learning/online/offline). "Domain barrier". | Tuner+portföyümüzün literatürdeki tam yeri; tasarım dili + sonraki adım haritası. |
| 7 | **Drake, Kheiri, Özcan, Burke (2020). Recent Advances in Selection Hyper-heuristics. EJOR 285(2):405-428** (S0377221719306526). Nottingham ASAP. | Seçim HH = düşük-seviye heuristik seçimi + HAREKET KABUL mekanizması; her iter heuristik uygula → kabul kararı. | Tuner'ı düzgün genelleştirme reçetesi: bizim "menü seç + monoton kabul" tam bu yapı; kabul kriterlerini (büyük-iyileşme, geç-kabul) buradan zenginleştir. |
| 8 | **López-Camacho, Terashima-Marín, Ross, Ochoa (2014). ESWA** (S0957417414002668). | GA-tabanlı seçim HH: birey = koşul-aksiyon kural seti (instance DURUMU → düşük-seviye packing heuristiği). 1D + 2D-düzenli + 2D-düzensiz (konveks/konkav) bin packing; görülmemiş instance'a genelleşir, instance-başı en iyi tek heuristiği geçer. | Packing'de DOĞRUDAN kanıt: instance özelliklerinden heuristik seçimi çalışıyor → §6.3.1'i cesaretlendirir; özellik mühendisliği örneği. |
| 9 | **Burke, Hyde, Kendall, Woodward (2010). A GP Hyper-Heuristic for Evolving 2D Strip Packing Heuristics. IEEE TEVC** (10.1109/TEVC.2010.2041061). | Genetik programlama: çözüm uzayı değil HEURİSTİK uzayı arar; yeniden-kullanılabilir CONSTRUCTIVE heuristik üretir — "hangi parça + nereye" (bizim DBLF'nin iki kararı); insan-rekabetçi (elle-tasarlanmış SOTA'yı geçer). | **Gap 4 yolu:** elle-kodlanmış DBLF'yi GP ile evrilen heuristikle DEĞİŞTİR/yarıştır (uzun vade; decoder'ın kendisini iyileştirir). |

---

## 🎯 ÖNCE ENTEGRE ET — top 3 (değer/efor)

1. **Algoritma-seçim katmanı + KOLAY-INSTANCE ön-filtresi** (#1, #2, #4 + telemetrimiz).
   *Neden ilk:* veri zaten birikiyor (telemetri = özellik+sonuç); ön-filtre (Renau&Hart)
   düşük-efor-yüksek-değer (berabere kalan kolay instance'larda portföyü atla). §6.3.1'i
   başlatır. **Efor: orta. Değer: yüksek.**
2. **Instance-Tuner'ı seçim-HH olarak yeniden çerçevele** (#7 yapısı: seçim + hareket-kabul).
   *Neden:* tuner zaten bu; literatür kabul kriterlerini (geç-kabul vb.) + temiz yapıyı verir.
   **Efor: düşük. Değer: orta (sağlamlık + genişleme).**
3. **GP ile placement heuristiği üretimi** (#9) — DBLF'yi evrilen heuristikle yarıştır.
   *Neden sonra:* decoder'ın kendisini iyileştirir (R5 overhang sınırına da dokunabilir) ama
   yüksek efor. **Efor: yüksek. Değer: yüksek ama uzun vade.**

## Adım B — Repodaki makaleler okundu (Gap 3-5, bedava tur, 2026-06-14)

> Workflow yerine elimizdeki PDF'lerin `.txt` çıkarımları tarandı. Doğrulanmış
> workflow değil, makale-içi okuma — ama temelleri netleştiriyor.

- **Review 2025 (Nesting Problems in AM — Classification & Review):**
  - Çarpışma/temsil yöntemleri: orthogonal polyhedra, **voxel (BİZİM)** — "küçük
    voxel = daha iyi fidelity ama çok daha yavaş" (tam bizim pitch takası);
    **sphere tree** (hiyerarşik, HIZLI çarpışma/yakınlık — hız için alternatif
    temsil); OCCS kodlama.
  - Algoritma manzarası: metaheuristik (GA, SA), heuristik, **ML+heuristik
    hibrit** (Industry 4.0 frontier = bizim algoritma-seçim işimiz).
- **Taxonomy/Dataset (IJPR 2019, Wäscher ekolü):**
  - **DBL (Deepest Bottom-Left) 3DIP'in BASKIN tekniği** — "çoğu çözüm DBL
    varyantı kullanır". → bizim DBLF seçimi alan STANDARDI (doğrulandı, özür
    gerektirmez); overhang sınırı (R5) alanın geneline ait, bize özel zayıflık değil.
  - D|C|B|A taksonomisi (instance sınıflandırma) — feature/selection için faydalı.
  - Yeni A2018 dataset'i (önceki <20-parça setlerinden zengin); 3DIP benchmark'ları
    KIT (R7 dürüst doğrulandı).

**Step B sonucu (dürüst):** repo makaleleri TEMELLERİMİZİ DOĞRULUYOR (voxel + DBLF
= alan standardı) ve frontier'i gösteriyor: (1) ML-hibrit = algoritma-seçim
[şu an kuruluyor], (2) sphere-tree = çarpışma hızı [drop_map/numune hız alternatifi].
AMA turnkey "daha iyi taban çözücü" VERMİYORLAR — somut yeni-çözücü teknikleri
(ALNS, extreme-point) OR literatüründe (Gap-4, henüz doğrulanmadı).

**→ Adım A kararı:** en net additive/güvenli kazanç = **ALNS** (Adaptive Large
Neighborhood Search) — plain SA/GA'yı geçen bilinen metaheuristik, `Solver`
protokolüyle YENİ çözücü olarak eklenir (motor bozulmaz), benchmark kapısı
doğrular. Extreme-point (R5) Gap-4 araştırmasına bağlı + yüksek efor → sonra.

## Sonraki araştırma turu (açık)

Gap 3 (modern ALNS/3D operatör), Gap 4 (extreme-point/maximal-space — Martello-Pisinger-Vigo
OR 2000, Crainic-Perboli-Tadei IJOC adayları), Gap 5 (voxel/SDF AM nesting + dataset) için
DAR deep-research turu (geniş değil — ilk tur 5 boşluğa yayılıp bütçe Gap 3-5'te bitti).
Her doğrulanan makale → 03_GENISLETME.md "makale→kod" kapısı.

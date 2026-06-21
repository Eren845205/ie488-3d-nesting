# FAZ 4 TASARIMI — Gerçek-3B / Cavity-Aware Yerleştirme

> Tarih: 2026-06-22. Read-only tasarım (kod yok). Amaç: kalite açığının KÖKÜNÜ
> kapatmak — heightmap-drop'un oyuğa/çıkıntı-altına yerleştirememesi (doluluk
> %8-17). Magics'in 2× yoğunluğunun karşılığı budur.

---

## 0. EN ÖNEMLİ BULGU — çekirdek ZATEN VAR

`src/nesting3d/extreme_point.py` halihazırda tam bir **3B occupancy + extreme-point
cavity-aware packer** içeriyor (R5 fix):
- **3B occupancy grid** (`OccupancyBin3D`) — heightmap yerine tam 3B doluluk.
- **3B çarpışma testi** → parça, voxelleri çakışmadığı HER yere konabilir (çıkıntı
  altı / oyuk içi dahil) — drop paradigmasının kısıtı YOK.
- **Extreme-point aday üretimi** (Crainic 2008 tarzı) — yerleşmiş parçaların
  geometrisinden konum adayları.
- **Hızlı yol** (`column_top` heightmap kısa-devresi): "üste otur" durumunda 3B-AND
  atlanır, sadece cavity adayları 3B maliyeti öder — drop_map'in fast-path mantığı.
- `place_extreme_point` — dblf'in 3B muadili constructive packer. Deterministik,
  z-ekseni auto-expand.
- **Test edilmiş** (`tests/test_extreme_point.py`), sentetik overhang senaryolarında
  heightmap'i yapısal olarak geçiyor.

**Yani Faz 4 = sıfırdan yazma DEĞİL → ENTEGRASYON + ÖLÇÜM + aday-üretimi iyileştirme.**

---

## 1. NEDEN ENTEGRE DEĞİL / AÇIK SORUN

`extreme_point.py` docstring: *"Existing heightmap Bin3D / dblf / solvers are NOT
touched. Parallel alternative."* Üç gerçek engel:

1. **Gerçek veride ÖLÇÜLMEDİ.** `compare_extreme_point.py` sadece sentetik kutular
   ("real numune STL too slow at 3D occupancy scale"). `numune_ep_oneshot.py` gerçek
   numunede koşuyor AMA sonucu kayıtlı değil — **KOŞULMASI gerek (GO/NO-GO).**
2. **Aday üretimi bbox-köşe tabanlı (kutu-odaklı).** `_update_extreme_points` parçanın
   BBOX köşelerinden aday üretir → düzensiz parçanın gerçek oyuğunu tam kullanamaz.
   Cavity fırsatının (numune'de zarfın ~%49'u çıkıntı-altı boşluk!) sadece bir kısmını alır.
3. **3B ölçek maliyeti.** Fine pitch'te 3B occupancy = ağır bellek + yavaş çarpışma.
   (440×440×1200 voxel @0.5mm ≈ 232 MB bool; bit-pack ile ~29 MB.)

---

## 2. KRİTİK ENABLER — toz yatağı = destek/yerçekimi YOK

Üretim toz yataklı ([[project memory]] + voxelize.py: "toz yataklı üretimde her
oryantasyon basılabilir"). → Parça **desteğe ihtiyaç duymaz, HAVADA durabilir.**
Bu çok önemli: parça başka parçanın oyuğuna, iç içe, çakışmayan HER 3B konuma
konabilir (gerçek 3B nesting). Drop'un "üstten düşür + yerçekimi" kısıtı tamamen
kalkar. EP packer bunu zaten destekliyor (z'yi serbest arıyor).

---

## 3. ÖNERİLEN YOL (ölç → iyileştir → entegre)

### Adım 4.0 — GO/NO-GO ÖLÇÜMÜ (en düşük efor, ÖNCE bu)
`numune_ep_oneshot.py`'yi KOŞ. Gerçek numune parçalarında EP, heightmap DBLF'yi
geçiyor mu (aynı pitch, adil)? 
- **EP belirgin kazanıyorsa** → cavity-aware bu parçalarda işe yarıyor → 4.1-4.3'e yatırım yap.
- **~eşit/kötüyse** → bbox-EP düzensiz cavity'yi kullanamıyor demektir → önce 4.1
  (aday üretimi), yoksa Faz 4'ün getirisi şüpheli → kararı revize et.
Maliyet: ~dakikalar (EP+heightmap tek pass, coarse pitch=2). **Veri-odaklı GO/NO-GO.**

### Adım 4.1 — Aday üretimini düzensiz-cavity-farkında yap (gerekirse)
bbox-köşe yerine, occupancy'nin gerçek **boş-ama-erişilebilir** voxellerinden aday
üret (yüzey-komşu boşluklar / NFV-No-Fit-Voxel, Lamas-Fernandez & Bennell INFORMS
OR 2022). Düzensiz parçanın oyuğunu hedefler. En büyük kalite kaldıracı ama en zor.

### Adım 4.2 — Tractability (3B ölçek)
- **Bit-packed occupancy** (np.packbits) → 8× bellek.
- **Coarse-EP → fine doğrulama:** cavity kararını coarse'ta ver (ucuz), fine'da yalnız
  o konumları 3B doğrula. Hibrit: çoğu parça heightmap-hızlı, cavity adayları 3B.
- Fast-path (column_top) zaten "üste otur"u bedavaya getiriyor — koru.

### Adım 4.3 — Pipeline entegrasyonu
- EP'yi portföye **constructive solver** olarak ekle (tuner zaten solver seçiyor).
- **FINE aşaması 3B konumları onurlandırmalı:** mevcut fine `place_in_order` drop ile
  z'yi belirliyor → EP'nin cavity (x,y,z) yerleşimini üretemez. Fine'da da
  OccupancyBin3D gerekir (veya coarse-EP sıra+poz+z'yi fine 3B'de tek-geçiş yerleştir).
- `coarse_to_fine` bunu yeni bir "mod" olarak alır; heightmap yolu korunur (regresyon yok).

### Adım 4.4 — Ölçüm
Plan1 (küçük) önce → EP vs heightmap yükseklik/doluluk. Kazanırsa Plan2'de COMPOLY/
parçalı ölçekle. Faz 0 harness'ına EP modu ekle.

---

## 4. RİSKLER

| Risk | Etki | Azaltma |
|---|---|---|
| Bellek (fine 3B grid) | EN BÜYÜK | bit-pack / coarse-EP / sparse |
| Hız (3B çarpışma) | Yüksek | fast-path + aday budama + Faz 1 hız ön-koşul |
| bbox-EP düzensizde zayıf | Getiriyi düşürür | 4.1 NFV aday üretimi |
| Fine 3B yeniden yazımı | Regresyon | heightmap yolu paralel korunur |
| Gerçek parçada cavity az çıkar | Faz 4 getirisi düşük | **4.0 GO/NO-GO önce ölçer** |

---

## 5. ÖZET / KARAR

- Faz 4'ün **çekirdeği yazılı** (extreme_point.py) — sıfırdan değil.
- **İlk iş = 4.0 GO/NO-GO ölçümü** (`numune_ep_oneshot.py` koş) — düşük efor, cavity-
  aware'in bu parçalarda gerçekten kazandırıp kazandırmadığını söyler. Yatırımdan ÖNCE.
- Kazanırsa: aday-üretimi (4.1) + tractability (4.2) + entegrasyon (4.3) → asıl kalite kaldıracı.
- Bu, "ölç, sonra yatır" (veri-odaklı) ilkesiyle uyumlu — kör mimari değişim yok.

İlişkili: `PLAN_IYILESTIRME_YOLHARITASI.md` (Faz 4 maddesi), `ARASTIRMA_NESTING_LITERATUR.md`
(NFV/Araujo/Ikonen), `extreme_point.py`, `numune_ep_oneshot.py`, `compare_extreme_point.py`.

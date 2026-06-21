# DENEYLER & BULGULAR — Magics Açığını Kapatma (2026-06-22)

> Hangi yöntem denendi, sonuç ne oldu, ne sonuca varıldı. Ham ölçümler:
> `results/kiyas_sonuclari.csv`. Ölçüm aracı: `scripts/kiyas_harness.py`.
> Kıyas: Plan1 (112 parça, oto plaka) ve Plan2 (226 parça, hoca plakası 328.74×328.19,
> hoca yüksekliği 492.39mm). "hızlı mod" = fine_pitch 1.5mm (yaklaşık, biraz yüksek
> tahmin); "kesin mod" = 0.5mm (resmî). Sabit tohum 42.

---

## FAZ 1 — HIZ

### ✅ drop_map vektörizasyonu (BAŞARILI, üretimde canlı)
- **Yöntem:** `bin3d.drop_map` genel yolu (konkav footprint / değişken taban) Python
  `for` döngüsünden `sliding_window_view` ile tek numpy redüksiyonuna çevrildi.
  Kayan pencere footprint maskesiyle indekslenir, taban çıkarılır, max alınır.
- **Neden güvenli:** `max` birleşmeli + tamsayı → sonuç döngüyle **birebir aynı.**
  Bellek için x-blok; devasa footprint'te döngü fallback.
- **Sonuç (Plan1 hızlı):** süre **77.9s → 55.7s (%28.5 hız)**, yükseklik **132.0 → 132.0
  (değişmedi)**, doluluk %15.5 aynı. **225/225 birebir-aynılık testi yeşil.**
- **Kök sebep neden buraydı:** cProfile — drop_map tottime %72 (gerçek STL'ler konkav,
  kutu hızlı-yoluna giremiyor, yavaş döngüye düşüyordu).

### ❌ Pitch-tabanlı "ince parçaya az voxel" (1a) — DENENDİ, GERİ ALINDI
- **Yöntem:** aykırı ince parçaya kaba pitch ver (suggest_pitch değiştir).
- **Sonuç:** tek-grid'de pitch eşitlemesi TÜM parçaları kabalaştırdı → Plan1 **106.7 →
  129.5mm (%21 BOZULDU).** → `pitch.py` HEAD'e geri alındı.
- **Ders:** tek bin grid'inde parça↔bin aynı pitch; doğru çözüm **two-level grid (1b)**
  (parça-bazlı ince alt-grid) — daha karmaşık. (Faz 1 H1 olarak sıradaki.)

---

## FAZ 2 — KALİTE

### ✅ Poz sayısı (n_orientations) süpürmesi — n=8 tatlı nokta
Önceden harness bayrağı ölüydü (`to_voxel_parts` hep n=4); `coarse_to_fine`'a baştan
sona bağlandı. **Plan1 hızlı:**

| n_orientations | Yükseklik | Doluluk | Süre |
|---|---|---|---|
| 4 (kısmi eksen-hizalı) | 132.0 mm | %15.5 | 82s |
| **8 (tüm eksen-hizalı yüzler)** | **117.0 mm** | %17.5 | 112s |
| 12 (+eğik 20-35°) | 117.0 mm | %17.5 | 151s |
| 28 (tam 24 simetri) | 117.0 mm | %17.5 | 240s |

- **Sonuç:** n=4→8 **%11.4 kalite kazancı** (parçayı tüm yüzlere yatırma). Eğik/tam
  simetri (12/28) **ek kazanç YOK**, sadece yavaşlatıyor.
- **Çıkarım:** Kalite kazancı "daha çok yüz"ten; "büyük eğim"den değil.

### ❌ İnce-açı refinement — HAM greedy BOZDU
- **Yöntem (Faz 2b, hocanın 0.5-1° isteği):** kazanan ayrık pozun ±5° çevresinde 1°
  adımlı yeniden voxelize, `_best_position` en düşük z_top'u seçer.
- **Sonuç (Plan1, ham):** **117 → 136.5mm (BOZULDU), 4× yavaş (462s).**
- **Sebep:** yerel z_top iyileştirme ≠ global yükseklik — döndürülen parça footprint'i
  büyütüp sonraki parçaları yukarı itiyor (yerel optimum tuzağı).

### ✅ Güvenli mod (ham regresyonun çözümü)
- **Yöntem:** algoritma HEM açısız HEM açılı çözümü üretir, **global yüksekliği iyi
  olanı seçer.** Baz poz daima aday (eşitlikte o kazanır).
- **Sonuç:** ince açı **kaliteyi ASLA bozamaz** (yalnız iyileştirirse kullanılır).
  Kutu parçalarda baz seçilir → 117 korunur. `fine_angle_used` şeffaflık alanı.

### ✅ Adaptif katman (sabit sayı YOK — algoritma kendi seçer)
- **Yöntem:** parçaların "kutuluk" (voxel/bbox doluluk) özelliğinden ince-açıyı seç
  (kutu→atla, düzensiz→aç); poz sayısını coarse-escalation ile seç (8→12→28, %1 altı
  kazançta dur). Karar gerekçesi `adaptive_reason`'a yazılır.
- **Sonuç (Plan1 adaptif):** **117.0mm (optimal, hardcode'suz — algoritma kendi seçti).**
  AMA **676s** (keşif maliyeti: escalation probları + ince-açıyı deneyip reddetme).
- **Çıkarım:** Kendi-karar-veren genelleşir (overfit değil) ama keşif compute MALİYETİ
  getirir. Ayarlanabilir (kutuluk eşiği, daha ucuz prob).

### Plan2 (asıl kıyas) — n=8 hızlı
- **Sonuç:** 637.5mm (hoca 492.39 → **1.295×**), %10.2 doluluk, **91 dakika.**
- **UYARI:** hızlı mod (1.5mm) — eski 621mm/1.26× **kesin** (0.5mm) ile KIYASLANAMAZ
  (farklı ölçek). n=8'in Plan2 net kazancı için n=4 hızlı baseline gerek (koşuluyor).
- **Çıkarım:** 91dk → n=8 büyük sette pahalı → **n=8'i sabit yapma**, poz da adaptif olmalı.

---

## FAZ 4 — GERÇEK-3B / CAVITY (GO/NO-GO)

### ❌ Mevcut extreme-point packer gerçek parçada kazanç vermedi
- **Bulgu:** `extreme_point.py` tam 3B occupancy + cavity-aware packer ZATEN VAR
  (test'li, sentetik overhang'de heightmap'i geçiyor).
- **Yöntem (`numune_ep_oneshot.py`, gerçek numune pitch=2):** EP vs heightmap DBLF.
- **Sonuç:** heightmap **180.0mm** = EP **180.0mm** (~EŞİT).
- **Sebep:** EP aday üretimi **bbox-köşe (kutu-odaklı)** → düzensiz parçanın gerçek
  oyuğunu hedefleyemiyor, parçaları istifliyor (heightmap'le aynı). Numune zarfının
  ~%49'u çıkıntı-altı boşluk (fırsat var) ama mevcut packer alamıyor.
- **Çıkarım:** Faz 4 ucuz entegrasyon DEĞİL. %49'u almak için **NFV (No-Fit-Voxel,
  voxel-seviyesi free-space aday üretimi)** gerek = araştırma-seviyesi efor. Detay
  `PLAN_FAZ4_TASARIM.md`.

---

## HIZ ↔ KALİTE TAKASI (kritik tablo, Plan1)

| Durum | Süre | Kalite |
|---|---|---|
| Orijinal (n=4, eski drop_map) | 77.9s | 132mm |
| **Bugün üretimde (drop_map canlı, n=4)** | **55.7s** | 132mm |
| n=8 bağlanırsa | 112s | 117mm |
| Adaptif bağlanırsa | 676s | 117mm |

- **drop_map = saf hız kazancı, üretimde CANLI.**
- **n=8/adaptif = kalite kazancı ama ZAMAN maliyeti** (n=8 bugünkünden de yavaş).
- "Hem hızlı hem kaliteli" ancak **per-part pitch (H1/1b)** ile mümkün (bütçe açar).

---

## ÜRETİM (app) DURUMU

`demo_pipeline.py:600 run_pipeline` → `solve_coarse_to_fine` varsayılanlarla
(n=4, adaptive=False) çağırıyor. Yani:
- **drop_map hız: app'te CANLI** (çekirdek, her koşu).
- **n=8 / adaptif / ince-açı: yazılı+test'li ama app'e BAĞLI DEĞİL** (uyuyor).
- **Faz 4: sadece tasarım.**

---

## KARAR (2026-06-22)
- Bu oturum commit'lendi: `0ac9e4b` (kod+test), `9c84115` (doküman).
- **Sıradaki: (C) per-part pitch (Faz 1 H1/1b)** — gerçek hız lever'ı; başarılırsa
  app dramatik hızlanır + kalite kazanımları bütçeye sığar → net hem hızlı hem kaliteli.
- **REVERSİBİLİTE:** ayrı git branch'inde yapılacak; istediğimiz gibi olmazsa branch
  atılıp `app-demo-build`'e dönülür (Ders: 1a daha önce %21 bozmuştu, risk gerçek).

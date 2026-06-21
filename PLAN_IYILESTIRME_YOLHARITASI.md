# PLAN — İyileştirme Yol Haritası (Magics açığını kapatma)

> Tarih: 2026-06-21. Branch: `app-demo-build`.
> Girdi: `ARASTIRMA_NESTING_LITERATUR.md` (22 peer-reviewed kaynak) + mevcut motor
> mimarisi (aşağıda özet). Amaç: kalite (621→~492 veya altı, doluluk %8→yukarı) +
> hız (Plan2 78dk→hedef ≤10dk) açığını faz faz kapatmak.
> İlişkili: PLAN_KIYAS_IYILESTIRME.md, project-kiyas-iyilestirme memory.

---

## 0. MEVCUT MOTOR — KRİTİK GERÇEKLER (planı bunlar şekillendiriyor)

Bu gerçekler her faz kararını belirliyor:

1. **Yerleştirme = heightmap "üstten düşürme" (drop).** `bin3d.py:54 drop_map()` her
   (x,y) sütununda parçayı en yüksek dolu kolonun üstüne oturtuyor:
   `z(x,y) = max(H[x+i,y+j] - bottom[i,j])`. → Parça **çıkıntı altına / oyuğa
   GİREMEZ.** Doluluk %8'in kök sebebi. (Gerçek-3B kilitleme yok.)
2. **Arama SADECE sıra + AYRIK oryantasyon indeksi optimize ediyor.** `sa3d.py:30`
   `Solution = List[(VoxelPart, orientation_idx)]`. Konum aranmıyor (drop deterministik).
   Yönelim, `rotation_matrices()`'in ürettiği **28 sabit pozdan** bir indeks.
3. **Enerji zaten yükseklik minimize ediyor.** `sa3d.py:44`
   `max_height_mm() + 0.1*rms_height_mm()`. → Hedef fonksiyon DOĞRU; sorun arama
   uzayı (ayrık poz) ve yerleştirme ilkesi (drop).
4. **Rotasyon kaba + kısıtlı.** `voxelize.py:60 rotation_matrices(n_orientations=4)`:
   0-7 eksen-hizalı, 8-11 eğik (Rx 55-70°, yani 20-35° eğim), 12-27 kalan simetri.
   Kıyas `n_orientations=4` ile koştu → **HİÇ eğim yok, saf 90°.** Sürekli açı yok.
5. **Pitch GLOBAL.** `instances/pitch.py:56 suggest_pitch = min_feature/2.5`, floor
   0.5mm. Tek 1mm parça → 0.5mm pitch → 270M voxel → 78dk. **Parça-bazlı pitch yok.**
6. **coarse_to_fine ZATEN VAR.** `coarse_to_fine.py`: kaba pitch'te ara → ince
   pitch'te kazanan sıra+oryantasyonu tek geçişte yerleştir. Fine-açı refinement
   için doğal kanca noktası.
7. **NLP çözücü YOK.** requirements'ta numpy/trimesh/shapely/scipy(opsiyonel) var;
   cyipopt/IPOPT yok. K1 (NLP compaction) yeni bağımlılık gerektirir.
8. **Portföy + tuner var.** SA/GA/ALNS/Tabu + `tuner.py` deterministik konfig seçimi.
   Yeni yetenekler bu portföye solver/refinement olarak eklenebilir.

---

## YOL HARİTASI — FAZ SIRASI VE GEREKÇE

**Sıralama mantığı:** Önce HIZ (Faz 1), çünkü 78dk'lık döngüde kalite deneyi
iterasyonu imkânsız — hızı düşürmeden kalite üstünde çalışılamaz. Sonra düşük-riskli
kalite kazancı (Faz 2), sonra kök kalite çözümleri (Faz 3-4). Faz 0 ölçüm altyapısı
her şeyin önünde — kazanç iddialarını doğrulayacak tek şey.

```
Faz 0  Ölçüm altyapısı (benchmark harness)        [ÖN KOŞUL, küçük]
Faz 1  HIZ: per-part çözünürlük (H1) + octree(H2) [yüksek değer/orta efor]
Faz 2  KALİTE: fine-angle rotasyon (K2)           [yüksek değer/orta efor, düşük risk]
Faz 3  KALİTE: NLP compaction post-process (K1+H3)[en yüksek değer/yüksek efor]
Faz 4  KALİTE: cavity-aware / gerçek-3B (K3)       [çok yüksek değer/en yüksek efor]
```

---

## FAZ 0 — ÖLÇÜM ALTYAPISI (ön koşul)

**Neden:** Her iyileştirmeyi "Plan1 + Plan2 hoca verisinde önce/sonra" ölçmeden
ilerlemek körlük. Caveat #1 (lokal optimum, kazanç örneğe bağlı) yüzünden HER
değişiklik gerçek veride doğrulanmalı.

**Yapılacak:**
- `scripts/kiyas_harness.py` — Plan1/Plan2/Plan3'ü sabit tohum + sabit plaka ile koşan,
  çıktı olarak (yükseklik, doluluk, süre, yerleşen/toplam) tablosu basan tek script.
  (Mevcut `scripts/plan2_kiyas_kosu.py` throwaway'i buraya konsolide et.)
- Sonuçları `kiyas_sonuclari.csv`'ye append → faz faz regresyon takibi.
- Hızlı mod: Plan2 78dk → Faz 1 öncesi bile fine_pitch=1.5mm yaklaşık koşu (kaba ama
  hızlı sinyal); kesin koşu 0.5mm.

**Kazanç:** Her faz sonunda "Magics'e göre X% yaklaştık" kanıtı.
**Efor:** Küçük (1 oturum). **Risk:** Yok.

---

## FAZ 1 — HIZ: Parça-bazlı çözünürlük (H1) + octree çakışma (H2)

**Hedef:** Plan2 78dk → ≤10dk. Kök sebep: tek 1mm parça global pitch'i 0.5mm'ye
çekiyor (270M voxel). Kaynak: Lamas-Fernandez/Bennell INFORMS OR 2022 (NFV),
Cagan CAD 1998 (octree), Araujo SFF 2015.

**Mevcut koda dokunuş:**
- `instances/pitch.py:56` — global `suggest_pitch` parça-bazlı pitch'e genişletilecek.
- `voxelize.py:283 voxelize_part` — parça başına farklı pitch ile voxelize.
- `bin3d.py:54 drop_map` — farklı-pitch parçaları tek bin grid'ine hizalama mantığı.

**Yaklaşım (en düşük riskli):** "İnce parçayı global pitch'ten ayır." Build height'i
belirleyen şey kalın parçalar; ince 1mm parça yükseklik darboğazı değil. İki seçenek:
- **(1a) İnce parça min-1-voxel tabanlama:** ince parçaları kaba grid'de en az 1 voxel
  kalınlıkta temsil et (2B ayak izi gibi) → global pitch kalın parçalara göre kalkar.
- **(1b) Two-level grid:** kaba taban grid + ince parçalar için yerel ince alt-grid.
  Daha güçlü ama daha karmaşık.
- **Başlangıç:** 1a (hızlı kazanç, düşük risk). Yetmezse 1b.

**H2 (octree, opsiyonel hızlandırma):** drop_map zaten numpy-vektörize ve hızlı; asıl
maliyet voxel SAYISI. Octree'yi yalnız 1a yetmezse ekle (önce ölç).

**Kazanç:** Süre dakikalardan dakika-altına; 270M voxel → ~10-30M.
**Efor:** Orta. **Risk:** İnce parça temsili kalite/clearance'ı bozabilir → Faz 0
harness'ı ile clearance kontrolü (`clearance.py`) şart.
**Doğrulama:** Plan2 süre + yükseklik DEĞİŞMEMELİ (sadece hız). Yükseklik bozulursa
1a yanlış uygulanmış.

---

## FAZ 2 — KALİTE: Fine-angle (coarse-to-fine) rotasyon (K2)

**Hedef:** Hocanın "0.5-1° hassas rotasyon" isteği. Kaynak: Ma/Chen/Hu/Wang CGF 2018
(sürekli yönelim optimizasyonu), EJOR 2018.

**Mevcut koda dokunuş:**
- `voxelize.py:60 rotation_matrices` — önce **eğik pozları aç** (n_orientations≥12)
  → BEDAVA kısmi kazanç (8-11 eğik pozlar zaten var ama kapalı).
- `coarse_to_fine.py:220 fine aşaması` — kazanan ayrık pozun ETRAFINDA ince açı
  taraması (örn. ±5°, 1° adım, 3 eksen) → her aday açıda yeniden voxelize → en iyi
  yüksekliği seç. Bu "coarse-to-fine rotasyon": enumerasyon yok, kazanan etrafı.
- `sa3d.py:49 _neighbour` — opsiyonel: oryantasyon-flip hamlesine küçük açı
  perturbasyonu eklenebilir (ama her perturbasyon yeniden voxelize → pahalı; önce
  Faz 1 hızı şart).

**Sıralama:** (2a) eğik pozları aç + ölç → (2b) fine-açı refinement pass → (2c) ölç.

**Kazanç:** Orta-yüksek (rotasyon kök kollardan biri). Caveat #4: rotasyon TEK kol
DEĞİL — tek başına 1.26×'i kapatmayabilir; Faz 3-4 ile birlikte.
**Efor:** Orta (mevcut coarse_to_fine'a katman). **Risk:** Düşük — mevcut motora
ekleme, mimari değişim yok. Fine-açı her parça için yeniden voxelize → Faz 1 hızı ön
koşul (yoksa süre patlar).
**Doğrulama:** Plan2 yükseklik düşmeli; süre Faz 1 sayesinde kontrol altında.

---

## FAZ 3 — KALİTE: Sürekli-rotasyon NLP compaction post-process (K1 + H3)

**Hedef:** En yüksek kalite kazancı (%16-28 literatür). Kaynak: Romanova/Bennell/
Stoyan/Pankratov EJOR 2018 (quasi-phi-function + COMPOLY), Litvinchev IFAC 2019
(AM min-height).

**Yaklaşım:** Mevcut heightmap çözümünü (Faz 1-2 sonrası) **fizibıl başlangıç noktası**
al, üstüne sürekli konum+yönelim NLP sıkıştırması ekle:
- Çakışmama + plaka-kapsama + asgari-mesafe kısıtlarını analitik (quasi-phi) yaz.
- Hedef: min build-height (IFAC 2019 formülasyonu — EJOR min-hacim DEĞİL; Caveat #3).
- **COMPOLY** ile O(n²)→O(n): 226 parçayı doğrudan çözmek imkânsız (Caveat #2,
  literatür N=15-40) → kademeli/yerel alt-problem sıkıştırması.
- Çözücü: cyipopt (IPOPT) veya scipy.optimize.minimize(SLSQP) — **yeni bağımlılık.**

**Mevcut koda dokunuş:**
- Yeni modül `src/nesting3d/compaction.py` — post-process katmanı.
- `run3d.py` / `coarse_to_fine.py` — fine yerleştirme sonrası compaction çağrısı.
- requirements.txt — cyipopt veya scipy ekleme.

**Kazanç:** En yüksek (kök çözüm). **Efor:** Yüksek (NLP model + çözücü + COMPOLY +
quasi-phi geometri). **Risk:** Yüksek — ölçek (226 parça), lokal optimum, min-height
formülasyonu yakınsama (Caveat #1-3, Açık Soru 1-2). Önce küçük alt-set (Plan1, ~12
parça) üzerinde prototip.
**Doğrulama:** Plan1'de önce kanıtla (küçük), sonra Plan2'de COMPOLY ile ölçekle.

---

## FAZ 4 — KALİTE: Cavity-aware / gerçek-3B çakışma (K3)

**Hedef:** %8 doluluğun KÖK çözümü — heightmap drop'u terk et, gerçek 3B çakışma →
çıkıntı-altı / oyuk-içi (part-in-part) yerleşim. Kaynak: Ikonen GA ICGA 1997,
Araujo SFF 2015 (NFP+GLS).

**Mevcut koda dokunuş (MİMARİ DEĞİŞİM):**
- `bin3d.py` — heightmap (2B `height[x,y]`) yerine **3B occupancy grid** + gerçek 3B
  çakışma testi. drop_map'in "üstten düşür" mantığı yerine boş-hacim arama.
- `dblf.py` — `(z_top,z,y,x)` lex-min yerine 3B konum arama (oyuk dahil).
- Bu, motorun yerleştirme çekirdeğini değiştirir → en invaziv faz.

**Kazanç:** Çok yüksek (doluluk darboğazı; Magics'in gerçek-3B kilitlemesinin
karşılığı). **Efor:** En yüksek (drop paradigmasından gerçek-3B'ye geçiş).
**Risk:** En yüksek — bellek (3B grid), hız (Faz 1 olmadan imkânsız), regresyon.
**Doğrulama:** Açık Soru 3 — cavity-aware tek başına yüksekliği ne kadar düşürür
ölçülmeli; Faz 3 ile çakışan kazanç olabilir.

**Not:** Faz 3 (NLP) gerçek-3B çakışmayı analitik kısıtlarla zaten getirebilir →
Faz 3 başarılıysa Faz 4'ün ayrı gereği azalabilir. Faz 3 sonrası yeniden değerlendir.

---

## RİSK / BAĞIMLILIK ÖZETİ

| Faz | Bağımlılık | En büyük risk | Azaltma |
|---|---|---|---|
| 0 | — | yok | — |
| 1 | Faz 0 | ince parça temsili clearance bozar | clearance.py kontrolü |
| 2 | Faz 1 (hız) | rotasyon tek başına yetmez | Faz 3-4 ile birlikte |
| 3 | Faz 1-2 | ölçek (226 parça), yeni çözücü | COMPOLY + Plan1 prototip |
| 4 | Faz 1 | mimari değişim, bellek/hız | Faz 3 sonrası yeniden değerlendir |

**Genel caveat (rapordan):** Kazançlar lokal-optimum ve örneğe bağlı; %16-28 bizim
226-set'te aynen tekrarlanmayabilir → her faz Faz 0 harness'ında doğrulanır.

---

## ÖNERİLEN BAŞLANGIÇ

**Faz 0 + Faz 1 birlikte** (ölçüm + hız): en düşük risk, sonraki tüm kalite
deneylerini mümkün kılar. Hız düştükten sonra Faz 2 (fine-açı) hızlı görünür kalite
kazancı verir. Faz 3-4 (NLP + cavity) kök çözümler, en yüksek değer/efor.

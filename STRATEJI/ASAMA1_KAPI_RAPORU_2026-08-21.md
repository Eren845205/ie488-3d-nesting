# AŞAMA-1 EĞİTİM + KAPI RAPORU (M8) — 2026-08-21

> ML planı §4 Aşama-1 / §6 M8 çıktısı. Girdiler: mod_yarismasi tur-3
> (M4-köprülü, n=79) + **tur-4 (arm-eşleme düzeltmeli, n=79 — GÜNCEL)**.
> Kanıt: `results/mod_yarismasi.json` (tur-4) + `_tur3_yedek.json` +
> `_tur2_yedek.json`, D+OneDrive.
> **GÜNCEL HÜKÜM (tur-4): kapı (c) PASS · (a) boş-test uyarılı PASS ·
> (b) yeni kazanan karar_agaci için tek ihlal mixed_scale n=1 aykırısı →
> ŞARTLI PASS. Promote adayı: karar_agaci (5,22 vs KURAL 14,65, 2,8×) —
> NİHAİ öneri tur-5'e (kafes kolları + gerçek fsm610'lu tablo, Eren
> onaylı genişleme) bağlandı; tur-5 gece koşusunda.**

## 00. TUR-5 NİHAİ HÜKÜM (2026-08-22 gece — kafes kolları + GERÇEK fsm610 dahil, n=80)

Eren onayları (2026-08-21: KARAR-1 terfi + "kafes de öğretilsin") uygulandı:
fsm610 portföy etiketi koşuldu (5 kol; **winner=kafes 400,0**; heightmap
clearance-ihlalli — AC-02'ye gerçek-veri kanıtı) ve tablo 80 instance'a
çıktı (kafes kolları dahil, atlanan kol 0).

| aday | t5 regret | kapı durumu |
|---|---|---|
| karar_agaci | 8,72 | ❌ **OVERFIT bayrağı** (cv_gap>0,2 → plan §5.4 DUR) |
| **logistic** | **8,72** | ✅ bayraksız — **PROMOTE ADAYI** |
| conformal_logistic | 8,72 | bayraksız (logistic ile özdeş tahmin) |
| mini_bagging | 9,01 | bayraksız |
| regret_logistic | 10,55 | fsm610'da kafesi SEÇEMEDİ (144,0) |
| KURAL(baseline) | 16,44 | model 1,9× önde |

**Kapı — nihai (aday: logistic):**
- **(a) fsm610-sınıfı: GERÇEK PASS** (artık boş-test değil): mass 0,44 <
  KURAL 1,56 ✓ ve **gerçek fsm610'da 0,0 < KURAL 144,0** — model kafesi
  seçmeyi öğrendi, kural seçemiyor (kafes tetiği kuralda yok — bilinen).
- **(b) diğer ailelerde bozulma: PASS (1 marjinal şerh):** t2'ye göre
  thin_shell 22,68→22,68 · tube 20,92→20,92 · long_rod/thin_plate aynı ·
  mixed_scale 192→192 (değişmedi — logistic'te İHLAL DEĞİL); tek fark
  solid_bulk 0,03→0,72 (+0,69mm, <1mm gürültü bandı — şerhle geçer).
- **(c) sıfır-dokunuş: PASS** (artefakt yok; A9 3302/0).

**ÖNERİ: logistic'i promote et** (Y-4 atomik + selection_archive
versiyonlu; M14 kablosu ayrı A6 adımı). karar_agaci ortalamada eşit ama
overfit bayraklı — plan §5.4 gereği promote EDİLEMEZ; bayrak M8-düzeltme
listesinde izlenir. mixed_scale n=1 aykırısı + aile-dengesi işi şerh
olarak devrediyor. **Promote onayı: EREN.**

---

## 0. TUR-4 GÜNCELLEMESİ (arm-eşleme sonrası, aynı gün akşam)

`nfv_fast→nfv_kalite` eşlemesi (kod-kanıtlı: üretim kalite yolu
quality=fast, demo_pipeline 890-892/1051) uygulandı, yarışma yeniden:

- **Hipotez KISMEN doğrulandı:** artefakt olan aileler düzeldi —
  high_qty_repeat 28,57→9,67 · repeat_rod_mix 19,79→4,0 · tube'daki
  sahte iyileşme (7,17) 20,92'ye geri döndü (t2 seviyesi ✓).
- **thin_shell artefakt DEĞİLMİŞ:** regret_logistic'te 22,68'de kaldı —
  o modelin tablo-büyümesiyle gerçek bir kararı bozuluyor.
- **Kazanan değişti: karar_agaci 5,22** (acc 0,722; overfit yok);
  regret_logistic 8,75'e geriledi. karar_agaci eski ailelerde t2'ye
  karşı: thin_shell 27,75→**8,37** ✓✓ · tube 20,92→**7,17** ✓✓ ·
  solid_bulk/thin_plate/long_rod değişmedi ✓ · **tek ihlal mixed_scale
  0→192 (n=1 bilinen aykırı instance — aile-dengesi işi).**
- KURAL 14,65 (m4 instance'larında artık nfv_kalite ölçülü → adil kıyas).

Kapı (b) hükmü buna göre ŞARTLI PASS'e güncellendi; mixed_scale
aykırısı ve aile-dengesi işi şerh olarak promote kararına iliştirildi.

---
*(Aşağısı tur-3 anlık raporudur — tarihçe olarak korunmuştur.)*

## 1. Bugün tamamlanan M8 hazırlığı

- **Tablo-49 kök sebebi bulundu ve kapatıldı:** M4 portföy etiketleri
  (`m4_portfoy_etiket.jsonl`) ile eğitim tablosu arasında köprü yoktu.
  `src/nesting3d/selection/m4_koprusu.py` (TDD 11/11) yazıldı; tablo
  49 → **79 instance** (+30; 1 tekrar-satır düştü).
- **fsm610-sınıfı aile (mass_plate_rod_mix, n=9) eğitim tablosuna İLK
  KEZ girdi** — kapı (a) ilk kez ölçülebilir oldu.
- Kafes kolları KATALOG §C gereği bilinçli DIŞARIDA (14 kol satırı
  sayaçla atlandı); 9 invalid kol düştü; held-out sızıntısı 0 (Y-2).

## 2. Tur-3 sonuçları (LOO regret mm; n=79)

| aday | t3 ort | t3 acc | t2 ort (n=49) | t2 acc |
|---|---|---|---|---|
| **regret_logistic** | **8,54** | 0,646 | 9,66 | 0,837 |
| karar_agaci | 8,80 | 0,785 | 10,22 | 0,714 |
| mini_bagging | 8,90 | 0,709 | 9,81 | 0,714 |
| logistic / conformal | 10,11 | 0,620 | 12,87 | 0,816 |
| **KURAL(baseline)** | **14,65** | 0,367 | 18,26 | 0,510 |

Kazanan yine **regret_logistic**; kuralı 1,7× yeniyor (Y-6: metrik
regret; acc yardımcı — acc düşüşü yeni arm'ların sınıflandırmayı
zorlaştırmasından, regret yine de iyileşti). Overfit bayrağı: 0/10.

## 3. Kapı değerlendirmesi (ML planı §4 Aşama-1 madde 3)

**(a) fsm610-sınıfında regret(model) < regret(kural): ⚠️ BOŞ-TEST
UYARILI PASS.** mass_plate_rod_mix (n=9): model 0,0 = KURAL 0,0.
Bozulma yok ama ayrışma kanıtı da yok — üretim kolları arasında bu
ailenin kararı kolay (heightmap zaten clearance-INVALID düşüyor, AC-02);
sınıfın ASIL kararı (kafes kolu) eğitim-dışı olduğundan bu kapı ancak
M14 kablo + kafes-etiket entegrasyonu sonrası gerçek anlamda ölçülür.

**(b) Diğer ailelerde bozulma yok: ❌ FAIL.** regret_logistic
t2→t3: thin_plate 0,13→0,13 ✓ · long_rod 0,0→0,0 ✓ · tube
20,92→**7,17** ✓✓ · solid_bulk 0,03→0,72 (~notr) · **thin_shell
8,37→22,68 ✗ (+14,3mm BOZULMA)** · mixed_scale 192→192 (bilinen n=1
aykırısı). Ortalama iyileşse de kapı sözü "diğer ailelerde bozulmaz"
— thin_shell bunu ihlal ediyor. Diğer adaylar da temiz geçmiyor
(mini_bagging thin_shell 8,37→27,75; karar_agaci mixed_scale 0→192).

**Kök-sebep hipotezi (güçlü):** M4 satırları tabloya YENİ arm adları
getirdi (`nfv_fast`/`nfv_max`); eski instance'ların ölçülmüş arm'ları
ise {heightmap, nfv_kalite}. Model thin_shell'de yeni arm'ı tahmin
edince kötümser-ceza konvansiyonu (ölçülmemiş arm → max−min) devreye
giriyor — yani bozulma büyük olasılıkla GERÇEK karar bozulması değil,
**arm-uzayı hizasızlığı artefaktı.** (tube'daki +13,7 iyileşme aynı
mekanizmanın ters yüzü olabilir — o da doğrulanmalı.)

**(c) Dev-set motor sıfır-dokunuş: ✅ PASS.** A9 tam suite 3302/0
(2026-08-21 gece) + yarışma hiçbir artefakt yazmadı (Y-1/Y-4), motor
koduna dokunulmadı; model yalnız rapor üretti.

## 4. HÜKÜM ve öneri

**Promote: BEKLET.** Kapı FAIL verdi — kapılar tam da bunun için var.
Promote öncesi 2 düzeltme işi (M8-düzeltme listesi):

1. **Arm-eşdeğerlik hizalaması:** M4 kollarını mevcut arm-uzayına
   anlamlı eşle (`nfv_max` ↔ `nfv_kalite` semantik kararı VEYA
   kötümser-ceza yerine arm-eşdeğerlik haritası). Karar Eren'le:
   üretim "nfv kalite" yolu quality=max koşuyorsa eşleme doğrudur.
2. **thin_shell per-instance teşhisi:** t3'te bozulan thin_shell
   instance'larında modelin tahmin ettiği arm'lar dökülür; hipotez
   doğrulanırsa (1) ile birlikte kapı yeniden koşulur (LOO ~saatler;
   münhasır pencerede).

Bu iki iş kapandığında kapı yeniden değerlendirilir; PASS gelirse
promote adayı **regret_logistic** (Y-4 atomik + `selection_archive`
versiyonlu; M14 kablosu ayrı A6 insan-onaylı adım).

## 5. Şerhler (dürüstlük tablosu)

- Kafes kolları eğitimde YOK (bilinçli, katalog §C) — kablo-sonrası 4
  maddelik entegrasyon listesi YONTEM'de (telemetri satırı + arm_of +
  KURAL tetiği + aile-dengesi).
- mixed_scale n=1 / max_regret 192 tekil aykırısı ortalamaları
  domine ediyor — aile-dengesi işi açık (M8-düzeltme ile birlikte).
- Held-out'a BAKILMADI; bu rapor kazanç ilanı DEĞİLDİR (A11).
  Aşama-3 sınavları (plan7 kör-test) promote-sonrası ayrı iş.
- KURAL'ın m4 instance'larındaki kararı RuleAdapter fallback'i
  (heightmap) — kural haritası (`regret_raporu.json`) m4 kimliklerini
  içermiyor; KURAL m4'te hafif aleyhte yarışmış olabilir (model-lehine
  yanlılık DEĞİL: kapı (b) FAIL hükmünü etkilemez, kapı (a)'da iki
  taraf da 0,0).

## A11/A6 statüsü

Eğitim yalnız LOO içinde; hiçbir artefakt yazılmadı, hiçbir model
promote edilmedi, üretim default'una dokunulmadı, held-out açılmadı.

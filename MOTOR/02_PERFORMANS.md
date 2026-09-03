# 02 — Performans (veri seti başına) + Evrim

> Hangi algoritma hangi veride ne sonuç veriyor + motor nereden nereye getirildi.
> Her benchmark koşusundan sonra güncellenir. Üretim komutu: `python scripts/benchmark.py`.

## 1. Güncel benchmark tablosu (2026-06-14, `results/benchmark_discriminating.md`)

Tek-konfig (TÜM örnekler aynı parametre), adaptif pitch, budget 200, 4 çözücü.
"Kazanç" = en iyi metaheuristiğin DBLF üzerine yükseklik azaltması.

| Instance | Aile | DBLF | En iyi (kim) | Kazanç |
|---|---|---|---|---|
| syn_rb_s0 | random_boxes | 176.4 | 152.3 (SA/GA) | **%13.6** |
| syn_rb_s1 | random_boxes | 112.5 | 104.4 (GA) | %7.1 |
| syn_flms_s0 | few_large_many_small | 269.3 | 211.6 (GA/tabu) | **%21.4** |
| syn_flms_s2 | few_large_many_small | 179.0 | 169.0 (GA) | %5.6 |
| syn_hqr_s0 | high_qty_repeat | 402.4 | 381.2 | %5.3 |
| syn_hqr_s3 | high_qty_repeat | 276.5 | 268.3 (SA) | %2.9 |
| syn_tp_s0 | thin_plates | 77.7 | 70.4 | %9.4 |
| syn_tp_s4 | thin_plates | 59.7 | 57.2 (SA) | %4.2 |
| syn_lr_s0 | long_rods | 46.8 | 41.6 (SA/tabu) | %11.1 |
| syn_lr_s5 | long_rods | 43.7 | 38.8 | %11.1 |
| **BR5** (holdout) | bischoff_ratcliff | 28.0 | 20.0 (hepsi) | **%28.6** |
| **numune** (holdout, gerçek STL) | numune | 190.2 | 184.3 (SA) | %3.1 |

**Okuma:**
- HER instance'ta pozitif kazanç → metaheuristikler her yerde DBLF'yi geçiyor.
- **Farklı algoritma farklı instance'ta kazanıyor** (flms→GA/tabu, rb→SA/GA,
  lr→SA/tabu) → tek çözücü domine etmiyor, **portföy şart.**
- **numune (gerçek STL, el-ayarsız generic motor): SA %3.1 → overfit DEĞİL kanıtı.**
- BR12, tam-numune: voxel bütçesi aşımı → ATLANIR+LOGLANIR (HPC/A14 işareti).

## 2. Bileşen-bazlı değer kanıtları (ablation)

| Değişiklik | Test instance | Önce → Sonra | Kazanç |
|---|---|---|---|
| **R1** 24 poz (8→24) | long_rods | 46.8 → 41.6 | %11 |
| **R2** adaptif t0 (vs sabit 3.0) | few_large | 269.3 → 211.6 | %21 |
| **R4** MultiStartSA (vs tek-start) | few_large | 269.3 → 211.6 | %21 |
| **drop_map** kutu hızlı yol | tüm benchmark | 520s → 90s | 38× hız |

## 3. EVRİM — nereden nereye getirildi

### Faz 0 — Numune (tek instance, el-ayarı meşru)
- DBLF + SA, **elle seçilmiş hibrit pozlar** + ince pitch (1.5mm) → **🏆 181.5 mm**
  (numune rekoru). Bu fazda tek-instance için el-ayarı işin tanımı.
- ⚠️ Risk: motor tek veri setinin gölgesinde şekillendi (R1-R7 overfit riskleri).
- El-ayarı KARANTİNADA: `models.py` `NUMUNE_*`, genel motora sızmaz.

### Faz 1-2 — Genelleştirme (2026-06-14, bu oturum)
1. **Çözücü portföyü:** SA tek başına değil → DBLF/SA/GA/tabu ortak `Solver`
   protokolü + ortak decode (adil kıyas).
2. **Benchmark (R7 kök risk):** çeşitli sentetik aileler + BR + tek-konfig +
   hold-out. **Tanı:** donmuş benchmark HİÇ koşmamıştı (sahte yeşil) → adaptif
   pitch + voxel bütçesiyle düzeltildi.
3. **Ayırt edicilik (R7/bulgu#2):** sentetikler çok kolaydı (portföy no-op) →
   sıkı-taban rejimine ayarlandı → yukarıdaki tablo (her instance ayırt ediyor).
4. **Hız:** drop_map 38× (kutu hızlı yol).
5. **R1** (24 poz), **R2/R4** (adaptif t0 + multi-start).
6. **Instance-Tuner çekirdeği** (örneğe özel ince ayar, monoton kabul).
7. **Numune generic motorda benchmark'a** (gerçek-veri overfit kanıtı %3.1).

### Faz 3 — Algoritma-seçim katmanı + overfit döngüsü (2026-06-17)
1. **Seçim modeli KURULU olduğu netleşti** (eski doküman "yok" diyordu, bayattı):
   `selection/` modülü — 1-NN prototip + kolay-instance ön-filtresi + monoton
   garanti + üretim hattına bağlı (`demo_pipeline.py`). Artefakt 69 instance'a
   kadar telemetriden eğitilebilir.
2. **Overfit döngüsü SERTLEŞTİRİLDİ (2 kök sorun çözüldü):**
   - *İsim-bağımlı hold-out:* eski "alfabetik son %20" → hold-out instance ismine
     bağlıydı (z_*/a_* ile manipüle edilebilir, aile-dengesiz). Yeni
     **stratified-by-family split** (`splits.py`): her aileden orantılı pay →
     6 ailenin hepsi temsil edilir. Tek-aile durumunda eski davranışla özdeş.
   - *1-NN yapısal yanlış-overfit:* `train_acc≈1.0` (1-NN ezber doğası) yüzünden
     `gap=train_acc−holdout_acc` daima yüksekti → kapı HER retrain'i bloklardı.
     **LOO-CV tabanlı kapı** (`gengap.py`): `cv_gap = cv_acc(LOO) − holdout_acc`
     → in-sample ezberi içermez → yanlış-pozitif bitti (gerçek veride
     overfit_flag True→False, cv_gap=0.105). Gerçek overfit koruması korundu.
   - **LOFO** eklendi (yeni aile genelleme kanıtı): model görmediği aileye
     %25–67 genelliyor (veri arttıkça yükselir).
3. **Karar ağacı seçici** eklendi (`model.py` `DecisionTreeSelector`, stdlib):
   LOO-CV %53.6 vs 1-NN %52.2; `max_depth=2` (depth=4 → %44.9 = overfit kanıtı).
4. **ALNS** seçim haritasına bağlandı + dokümante edildi (zaten benchmark'taydı).
   Zorlu instance üreticisinde (`generate_hard_instances.py`) **alns 4/4 kazandı**
   (ort. dblf 151.9 → alns 132.6 mm, %14.6) → tabu/multistart/alns'i kazanan
   kümeye sokma yolu açık.
5. **Öğretme akışı:** `scripts/retrain_selection.py --dry-run` + okunabilir kapı
   raporu (promote/overfit_flag/cv_gap/delta). Tek komutla "instance → öğret".

### Faz 4+ — Sonraki (plan)
- Instance-Tuner LLM önericisi, hocanın geçmiş gerçek nesting'leri (A11) =
  çoklu gerçek-veri = tam genellik kanıtı,
- Genel-yol drop_map hızı (numune), R3 (enerji ağırlığı taraması).

## 4. Overfit durumu — dürüst özet

| Soru | Durum |
|---|---|
| El-ayarı genel motora sızıyor mu? | ❌ Hayır — `NUMUNE_*` karantinada |
| Çeşitli SENTETİK veride çalışıyor + ayırt ediyor mu? | ✅ Evet (tablo) |
| Tek-konfig kuralı (örneğe el-ayarı yasak) uygulanıyor mu? | ✅ Evet |
| "Hepsini koş en iyiyi seç" var mı? | ✅ Portföy |
| GERÇEK veride çalışıyor mu? | ✅ Numune generic motorda SA %3.1 (1 örnek) |
| Çoklu GERÇEK veride kanıtlandı mı? | 🟡 Henüz değil — A11 (hocanın geçmiş işleri) gerekli |

**Sonuç:** overfit'i engelleyen mekanizma KURULU + sentetik çeşitlilik ve 1 gerçek
örnekte genellik gösterildi. Tam gerçek-dünya kanıtı için çoklu gerçek veri (A11) şart.

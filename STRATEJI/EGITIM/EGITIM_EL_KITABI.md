# EĞİTİM EL KİTABI — Gelen Veriyle Algoritmayı Eğitme + Test Etme (Yürütülebilir Rehber)

> **Sürüm:** v1.0 (2026-07-06, Fable 5) · **Hedef okur:** BU DOSYAYI TEK BAŞINA
> OKUYAN gelecekteki bir AI oturumu (model fark etmez) veya Eren. Amaç: başka
> hiçbir bağlam olmadan, buradaki komut ve spesifikasyonlarla eğitim/test
> döngüsünü DOĞRU ve GÜVENLİ yürütebilmek.
> Üst çerçeve: `STRATEJI/00_ANAYASA.md` (ilkeler) — önce onu oku, 2 dakika.

---

## 0. "Otomatik mi eğitilecek?" — HAYIR, ve bu bilinçli bir karar

| Otomatik OLAN | Otomatik OLMAYAN (insan tetikler) |
|---|---|
| Veri birikimi: gözcü her siparişi işler, telemetri satırı düşer | Modelin eğitilmesi (`retrain`) |
| Yeni siparişin held-out doğması (registry kaydı) | Held-out→dev terfisi |
| Advisor'ın "retrain zamanı geldi" SİNYALİ üretmesi | Eğitilen modelin yürürlüğe alınması (gate PASS şart) |
| Koşu başına legal_height/clearance/kilit telemetrisi | Motor knob değişikliği (BO sonucu bile kapıdan geçer) |

Gerekçe (`src/nesting3d/selection/retrain.py` docstring'inde kalıcı):
model kendini sessizce yanlış eğitirse risk üründe kalır. Akış her zaman:
**sistem ÖNERİR → insan KARAR verir → kapı DOĞRULAR → promote atomik.**
Bu el kitabı "otomatikleştirme" değil, **her oturumda aynı şekilde
tekrarlanabilir MANUEL süreç** sağlar.

## 1. Dosya/komut haritası (her şeyin yeri)

```
data/telemetry/runs.jsonl        # eğitim hammaddesi (JSONL; satır=instance×çözücü)
data/selection_model.json        # YÜRÜRLÜKTEKI model artefaktı
data/selection_archive/          # eski sürümler (selection_model.vN.json)
src/nesting3d/selection/         # model.py dataset.py splits.py gengap.py
                                 # gate.py retrain.py advisor.py selector.py
src/nesting3d/instances/features.py  # 20 FROZEN + 3 aile özelliği
src/nesting3d/instances/family.py    # F1 taksonomi (7 aile)
scripts/retrain_selection.py     # eğitim CLI (aşağıda birebir kullanım)
scripts/c3_generality.py         # cross-dataset benchmark (DATASETS)
STRATEJI/01_VERI.md §2.1         # instance registry (dev/held-out rolleri)
MOTOR/YONTEM_HARITASI_DATA_BASE.md   # her deneyin kayıt yeri (§3)
```

## 2. RUNBOOK-A — Bugünkü altyapıyla retrain (15 dk, hemen çalışır)

```bash
# 1) ÖNERİ (read-only; hiçbir şey yazmaz):
python -m scripts.retrain_selection --suggest
#    Çıktıda: n_total / n_new / overfit sinyali (cv_gap) / "promote eder mi"

# 2) Kapı kararını önizle (yazmaz):
python -m scripts.retrain_selection --dry-run

# 3) İnsan onayıyla GERÇEK eğitim (promote ise artefakt atomik değişir):
python -m scripts.retrain_selection
#    Seçenekler: --jsonl <yol>  --gain-mm 0.5  --artifact <yol>
```

**Kapı mantığı (gate.py + gengap.py):** aday model stratified-holdout'ta
mevcut yürürlükten `MIN_GAIN_MM`'den fazla iyi olmalı VE `gengap`
overfit_flag=False olmalı (LOO-CV doğruluğu ile holdout doğruluğu açığı
`cv_gap ≤ 0.2` ve prequential kopuş yok). Blokluysa artefakt **byte-aynı**
kalır. Promote sonrası eski model `data/selection_archive/`'a versiyonlanır.

**Held-out filtresi (ŞU AN YOK — eklenene dek elle uygula):** eğitim
tablosuna held-out instance satırları GİRMEMELİ. Bugün telemetri tamamı
sentetik olduğundan sorun yok; gerçek koşular telemetriye akmaya başlayınca
(telemetri v2) `build_training_table` çağrısına registry-rol filtresi
eklenecek (bkz §6 backlog #1). O kablo yokken gerçek-veri satırı içeren
telemetriyle retrain YAPMA.

## 3. ALGORİTMA SPESİFİKASYONLARI (uygulama seviyesi)

### 3.1 Yürürlükte: 1-NN (`AlgorithmSelector`, model.py)
- Özellik: 20-boyutlu FROZEN vektör (`FEATURE_NAMES`; n_parça, hacim
  dağılımı, en-boy, tip oranları, doluluk-LB, konteyner geometrisi...).
- Mesafe: Öklid, uzunluk uyuşmazlığında 0-pad. Güven = `1/(1+d)`.
- Determinizm: eşit mesafede alfabetik küçük `winner`.
- `n_train < 4` → en sık çözücü, güven ≤ 0.49 (LOW_CONF_CEILING).
- Selector davranışı: güven < 0.6 → tam portföye düş (yanlış tekil seçim
  yerine hepsini dene).

### 3.2 Yürürlükte: sığ karar ağacı (`DecisionTreeSelector`)
- CART-benzeri, Gini; `max_depth=2`, `min_samples_leaf=2` (LOO taramasında
  en iyi genelleme — N~69'da derin ağaç ezberler). Güven = yaprak saflığı.
- `explain()` okunabilir kural verir — müşteriye/hocaya açıklanabilirlik.

### 3.3 SIRADAKİ YÜKSELTME — k-NN (k=3-5, mesafe-ağırlıklı oy)
```
predict(x):
  D = [(dist(x, r.feature_vector), r.winner) for r in train]
  D.sort()  # eşitlikte winner alfabetik (determinizm)
  komsu = D[:k]
  oy[w] = Σ_{(d,w)∈komsu} 1/(1+d)            # ağırlıklı oy
  winner = argmax oy (eşitlikte alfabetik)
  güven  = oy[winner] / Σ oy                  # [1/k, 1] arası, kalibre DEĞİL
k seçimi: k ∈ {1,3,5} her biri için LOO-regret (aşağıda §3.5) hesapla;
          en düşük LOO-regret'li k kazanır (eşitlikte küçük k).
KABUL KRİTERİ: LOO-regret(kNN) ≤ LOO-regret(mevcut 1-NN) VE gengap temiz.
```
sklearn YASAK (çekirdek kuralı) — stdlib ile ~40 satır; `model.py`'ye
`KNNSelector` olarak, aynı `fit/predict/explain` arayüzüyle eklenir.

### 3.4 SIRADAKİ YÜKSELTME — regularize multinominal logistic + kalibrasyon
```
Model: p(sınıf c | x) = softmax(W_c · x_norm + b_c);  L2 ceza λ‖W‖²
x_norm: her özellik train-set µ/σ ile standardize (µ,σ artefakta yazılır!)
Eğitim: tam-batch gradient descent, lr=0.1, 500 iter, λ ∈ {0.01,0.1,1.0}
        λ seçimi LOO-regret ile (küçük N'de tam LOO hesaplanabilir: 69×hızlı)
Kalibrasyon: LOO tahmin-skorları üzerinde Platt (tek-parametreli sigmoid
        sıcaklık T: p' = softmax(z/T); T, LOO log-loss'u minimize eder).
Değer önerisi: kalibre p' güven-kapısının (0.6 eşiği) ANLAMLI olmasını
        sağlar — 1-NN'in 1/(1+d) güveni kalibre değildir.
KABUL: LOO-regret ≤ mevcut model VE kalibrasyon eğrisi (güven-dilimli
        doğruluk tablosu) monoton-yakın.
```

### 3.5 REGRET — başarı metriği (accuracy DEĞİL)
```
regret(instance i, model M) =
    per_solver_heights[M.predict(x_i)] − min(per_solver_heights.values())
```
`per_solver_heights` `TrainingRow`'da mevcut (dataset.py). Raporlanan:
**ortalama + maksimum regret (mm), F1-aile kırılımlı.** Accuracy yalnız
yardımcı sütun. Gerekçe: yanlış seçim bazen 0.5mm bazen 100mm'e mal olur;
accuracy ikisini aynı sayar. LOO-regret = her satır dışarıda bırakılarak
eğitilen modelin o satırdaki regret'i (gengap._loo_cv_accuracy deseni;
backlog #2 bunu model-parametrik yapar).

### 3.6 YASAKLAR (N~69 gerekçesiyle; N 3-5× artınca yeniden değerlendir)
- Gradient boosting (XGBoost/LightGBM): küçük-N'de en hızlı overfit.
- Sinir ağları, DRL yerleştirme politikası (künye A3: süper-bilgisayar sonrası).
- sklearn çekirdek `src/`'de yasak (yorumlanabilirlik + bağımlılık);
  `scripts/` katmanında dev-time Optuna/scipy KABUL (04_MOTOR_TUNING §3).
- Sessiz/otomatik retrain her katmanda yasak (§0).

## 4. RUNBOOK-B — Yeni gerçek sipariş geldiğinde (test + eğitim döngüsü)

1. **Gözcü işler** (otomatik) → koşu sonucu + telemetri.
2. **Registry kaydı:** `STRATEJI/01_VERI.md` §2.1 tablosuna satır ekle;
   rol = **held-out** (doğuştan). F1 ailesini `classify_family` ile etiketle.
3. **TEST kullanımı (held-out'ken):** tek karşılaştırma koşusu serbest —
   "üretim kuralı hangi modu seçti; tüm modlar koşulsa en iyisi hangisiydi;
   regret kaç mm?" Sonucu registry'ye bakış kaydıyla, YONTEM_HARITASI'na
   bulgu olarak yaz. **Bu sonuçla ayar YAPMA** (yaparsan set dev'e düşer).
4. **TERFİ (eğitim kullanımı):** aynı F1 ailesinden ≥2 held-out birikince
   EN ESKİSİ dev'e terfi eder (registry'de rol değişikliği + tarih + karar
   notu). Terfi eden veri: (a) seçim-modeli eğitim tablosuna girer,
   (b) `c3_generality` DATASETS'e dev-set olarak eklenir (BO objective'i
   dahil), (c) domain-randomization kaynağı olur (qty ±%30, ölçek ±%10
   perturbasyonları `source=perturb(<id>)` etiketiyle).
5. **Retrain zamanı mı?** `--suggest` koş; `n_new` anlamlıysa (≥5 yeni
   instance) ve overfit sinyali yoksa RUNBOOK-A'yı uygula.

## 5. RUNBOOK-C — Motor knob eğitimi (BO; detay `04_MOTOR_TUNING.md`)

Özet zincir: duyarlılık taraması (knob başına 3-5 değer × dev-suite) →
etkili knob'larla TPE/Optuna (`scripts/` katmanı) → objective =
**worst-case dev-set iyileşmesi** (tek-sete-overfit'i yapısal cezalandırır;
INVALID = anında red) → kazanan config `02_EVAL_KAPISI.md` §2 resmî kapı
koşusu → PASS ise commit + anchor güncelleme + YONTEM_HARITASI kaydı.
Held-out objective'e ASLA girmez; yalnız final tek-koşu doğrulama.

## 6. Backlog (bu el kitabının eksik kabloları — öncelik sırasıyla)

1. **Held-out filtresi:** `build_training_table`'a registry-rol parametresi
   (held-out satırlarını yapısal dışla). Telemetri v2'den ÖNCE şart.
2. **`gengap` model-parametrik refactor:** `_loo_cv_accuracy(table,
   model_factory)` + regret raporu → kNN/logistic adayları aynı kapıdan geçer.
3. **Telemetri v2 alanları** (`01_VERI.md` §5): mod-düzeyi etiket +
   legal_height + F1 — "karar-yüzeyi kayması"nın kapanma ön-şartı.
4. **`scripts/eval_gate.py` (Faz-0):** test tarafının tek komutu.
5. **KNNSelector + LogisticSelector** implementasyonu (§3.3-3.4 spec'e göre).
6. Kabuk-ailesi sentetik jeneratörü (aile dengesi için).

## 7. Gelecek AI oturumu için sözleşme (checklist)

- [ ] `STRATEJI/00_ANAYASA.md` okudun mu? (A1: kapısız kazanç yok; A3:
      held-out dokunulmaz; A6: sessiz öğrenme yasak)
- [ ] Yapacağın iş bir İDDİA üretiyorsa: hangi kapıdan geçecek?
      (model → §2 gate; motor → `02_EVAL_KAPISI.md` §2)
- [ ] Kullandığın veri hangi rolde? (registry kontrolü; held-out'a
      dokunacaksan bakışı logla)
- [ ] Başarıyı regret/legal_height ile mi ölçüyorsun (accuracy/ham-height
      değil)?
- [ ] Deney sonucunu (GO da NO-GO da) YONTEM_HARITASI §3'e yazdın mı?
- [ ] Model değişikliği yaptıysan: promote yalnız gate PASS + insan onayı
      ile mi oldu? Artefakt arşivlendi mi?

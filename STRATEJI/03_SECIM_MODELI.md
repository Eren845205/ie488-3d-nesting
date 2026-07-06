# 03_SECIM_MODELI — ML Mevcut Durum, Karar-Yüzeyi Kayması, Yol Haritası

> "Algoritma" iki ayrı şeydir (taslak §2, doğrulandı):
> **(A) Nesting motoru** = deterministik geometri çözücüsü — öğrenen parametre
> YOK; riski *heuristik overfitting*, savunması cross-dataset kapısı (`02_`).
> **(B) Seçim modeli** = gerçek ML (instance → hangi çözücü/mod); riski klasik
> overfitting, savunması CV + held-out. Bu dosya (B)'yi yönetir.

---

## 1. Mevcut durum (2026-07-06, koda karşı doğrulandı)

| Bileşen | Durum |
|---|---|
| Model | `AlgorithmSelector` 1-NN (normalize Öklid, güven=1/(1+d)) + `DecisionTreeSelector` (CART-benzeri, max_depth=2, min_samples_leaf=2, Gini) — sklearn'süz, yorumlanabilir, deterministik |
| Özellikler | 20 FROZEN (`FEATURE_NAMES`) + 3 aile-farkında ek (`EXTENDED_FEATURE_NAMES`, additive) |
| Overfit kapısı | `gengap.py`: LOO-CV tabanlı (`cv_gap>0.2` veya prequential kopuşu → flag), `MIN_INSTANCES=6` |
| Split | `splits.py` aile-stratified, isim-bağımsız |
| Politika | MANUEL retrain + advisor `--suggest` (otomatik tetik yapısal yasak — `retrain.py` docstring) |
| Veri | 460 satır · 69 instance · TAMAMI sentetik 6 jeneratör ailesi |
| Etiketler | `winner ∈ {dblf, sa3d, ga, tabu}` · `is_easy` (ε=0.5mm, Renau&Hart) |

Bu katman KENDİ dünyasında sağlam. Sorun dünyanın kaymış olması ↓

## 2. KARAR-YÜZEYİ KAYMASI (bu çerçevenin en önemli tespiti)

Telemetrideki 4 çözücü (`dblf/sa3d/ga/tabu`) eski metaheuristik portföyüdür.
Üretimin BUGÜN gerçek kararları:

| Karar | Bugün nasıl veriliyor | mm-etkisi (ölçülü örnek) |
|---|---|---|
| `nesting_mode`: heightmap vs NFV kalite modu | kullanıcı opt-in (`b09512e`) | Plan ailesinde NFV ~%20-28 kazanç; kabukta İLLEGAL (K-21) |
| `wall_aware` tetiği | F5 kural-tabanlı family_routing (`d408ddb`) | Deneme4 377→282 (−%25) |
| pitch tarifesi (coarse/fine, adaptif) | kural + cidar-duyarlı | K-19'un kendisi |
| metaheuristik seçimi | seçim modeli (bu dosya) | çoğu instance'ta küçük |

Yani ML'imiz en KÜÇÜK etkili kararı öğreniyor; en BÜYÜK kararlar kural-tabanlı.
Bu bir hata değil (kurallar ölçümle kondu) ama **öğrenmenin hedefi yanlış
yüzeyde.** Ayrıca modelin eğitim dünyası (kutu-sentetikler) üretim dünyasından
(kabuk/karma gerçek siparişler) ayrıştı.

**Hedef mimari (evrimsel, devrimsel değil):**
1. **Etiket uzayını genişlet:** `winner` = mod-düzeyi karar
   (`heightmap`, `heightmap+wall_aware`, `nfv`, ...) — telemetri v2 (`01_` §5)
   bunu yazmaya başlasın; eski 4-çözücü etiketi `winner_solver` olarak kalır.
2. **Kural = baseline, model = challenger:** F5 family_routing kuralları
   AÇIK ve ölçülü; model ancak kapıda (regret metriğiyle, `02_` §1) kuralı
   yendiğinde ve yalnız yüksek-güven tahminlerde default'u ezebilir
   (güven-kapılı dağıtım; düşük güvende kural/portföy).
3. **Gerçek veriden öğrenme kanalı:** gözcü koşuları telemetri v2 satırı
   üretir → gerçek instance'lar zamanla eğitim tablosuna girer (held-out
   olanlar HARİÇ — held-out satırları eğitim tablosundan yapısal dışlanır,
   registry `rol` alanına bakarak).

## 3. Yöntem envanteri (taslak verdiktleri + düzeltmeler; N~69 bağlamı)

| Yöntem | Verdikt |
|---|---|
| 1-NN + sığ ağaç (mevcut) | ✅ KORU — temel doğru |
| k-NN (k=3-5, mesafe-ağırlıklı; k LOO-CV ile) | ✅ ucuz varyans düşüşü — İLK yapılacak model işi |
| Regularize logistic (stdlib, L2, elle GD) | ✅ ekle — kalibre olasılık; güven-kapısı ancak güven anlamlıysa çalışır |
| Kalibrasyon (Platt/isotonic, LOO tahminleri üzerinde) | ✅ yüksek değer |
| Random Forest (az ağaç, sığ) | ⚠️ yalnız LOO-CV kapılı deney; sklearn yasağı sürüyor → stdlib mini-RF veya erteleme |
| Boosting (XGB/LGBM) | ❌ N 3-5× büyüyene dek hayır |
| Sinir ağı / DRL policy | ❌ (DRL = künye A3, süper-bilgisayar sonrası) |

**Düzeltme (taslağa göre):** başarı ölçüsü accuracy DEĞİL **regret** (mm) —
`02_` §1. LOO-CV döngüsü de regret raporlamalı; `gengap.py`'nin
`_loo_cv_accuracy`'si `AlgorithmSelector`'ı hardcode ediyor — model sınıfı
parametreleştirilmeli ki DT/kNN adayları aynı kapıdan geçsin (küçük refactor,
Faz-3).

## 4. Retrain protokolü (değişmedi, kayıt için)

1. Advisor sinyali (`should_retrain` = öneri, tetik değil).
2. İnsan kararı → `python -m scripts.retrain_selection`.
3. Gate: `evaluate_candidate` (MIN_GAIN_MM) + gengap flag'i temiz →
   atomik promote; aksi hâlde artifact byte-aynı kalır.
4. Held-out satırları eğitim tablosuna GİRMEZ (yüzey kayması işi §2.3 ile
   birlikte registry-farkındalı filtre eklenir).

## 5. Sıralı iş listesi (bu dosyanın backlog'u)

1. *(Faz-2 sonrası)* Telemetri v2'de mod-düzeyi etiket biriktir; ilk 10-15
   gerçek koşuda kural-vs-en-iyi regret tablosunu çıkar ("kurallar ne kadar
   iyi?" — belki model hiç gerekmiyor; bunu da kapı söyler).
2. k-NN(k>1) + LOO-regret karşılaştırması (mevcut veriyle bile yapılabilir).
3. Logistic + kalibrasyon; güven-eşiği LOO üzerinde seçilir.
4. `gengap` model-parametrik refactor.
5. Kabuk jeneratörü verisi gelince aile-dengesini yeniden kur (`01_` §6).

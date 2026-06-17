# 00 — Değişiklik Günlüğü (motor karar kaydı)

> **Amaç:** Motorda HER algoritma/bileşen değişikliğini tek bakışta izlenebilir
> kaydetmek. "Neyi denedik, neyi ekledik, neyi çıkardık, neden, benchmark'a
> etkisi ne oldu" sorusu buradan yanıtlanır. Hoca/kullanıcı "şunu beğenmedim,
> çıkar; bunu dene" derse → buraya bir satır + `03_GENISLETME.md` sözleşmesini izle.
>
> **Bu dosya ile 02_PERFORMANS farkı:** 02 = "şu an hangi veri ne sonuç veriyor"
> (durum fotoğrafı). Bu dosya = "zaman içinde ne oldu, ne reddedildi" (karar filmi).

## Nasıl yazılır (kural)

Her değişiklik EN ÜSTE eklenir (en yeni başta). Format:

```
### YYYY-AA-GG — <TİP> <kısa başlık>
- **Ne:** <algoritma/bileşen + dosya>
- **Neden:** <hoca isteği / benchmark / overfit / hata / araştırma>
- **Etki:** <benchmark/test sonucu — sayı varsa sayı>
- **Durum:** ✅ kalıcı / ⏪ geri alındı / ❌ reddedildi (merge edilmedi)
- **İz:** <commit hash / PR / test dosyası>
```

**Tip etiketleri:** ➕ EKLENDİ · ➖ ÇIKARILDI · 🔄 DEĞİŞTİRİLDİ · ⬆️ İYİLEŞTİRİLDİ ·
🧪 DENENDİ-REDDEDİLDİ (kodu merge edilmedi ama kaydı tutulur ki tekrar denenmesin) ·
📌 POLİTİKA (davranış/kural kararı)

> 🧪 **Reddedilenleri SİLME, kaydet.** "Bunu zaten denedik, işe yaramadı" bilgisi
> en az "bunu ekledik" kadar değerli — aynı çıkmaza tekrar girmeyi önler.

---

## Kayıtlar (en yeni başta)

### 2026-06-17 — 📌 POLİTİKA: öğrenme MANUEL + öneri (otomatik retrain İPTAL)
- **Ne:** Algoritma-seçim modelinin auto-retrain döngüsü; `selection/advisor.py`
  (yeni), `retrain_selection.py --suggest`, `PLAN_OGRENME.md` banner.
- **Neden:** Kullanıcı kararı — uygulama kendini sessizce yanlış eğitip (overfit)
  bozarsa risk üreticide kalır; hoca/müşteri otomatik davranışı istemeyebilir.
- **Etki:** Gerçek eğitim yalnız açık komutla; sistem read-only ÖNERİ sunar.
  Güvenlik kapısı kurulu kalır, yalnız manuel retrain anında devreye girer.
- **Durum:** ✅ kalıcı
- **İz:** commit 9985111 · `tests/test_selection_advisor.py`

### 2026-06-17 — ⬆️ İYİLEŞTİRİLDİ: overfit kapısı (stratified split + LOO-CV)
- **Ne:** `selection/splits.py` (yeni, stratified-by-family + LOFO),
  `selection/gengap.py` (LOO-CV tabanlı overfit_flag).
- **Neden:** (1) Hold-out alfabetik son %20 idi → instance ismine bağlı,
  manipüle edilebilir + aile-dengesiz. (2) 1-NN yapısal `train_acc≈1.0` →
  `gap` daima yüksek → kapı her retrain'i yanlış blokluyordu.
- **Etki:** 6 ailenin hepsi hold-out'ta temsil; overfit_flag gerçek veride
  True→False (cv_gap=0.105). 136 selection testi + 13 yeni split testi yeşil.
- **Durum:** ✅ kalıcı
- **İz:** commit 9985111 · `tests/test_selection_splits.py`

### 2026-06-17 — ➕ EKLENDİ: DecisionTreeSelector (alternatif seçici)
- **Ne:** `selection/model.py` `DecisionTreeSelector` (stdlib, yorumlanabilir).
- **Neden:** 1-NN yanına daha sağlam/yorumlanabilir seçici seçeneği.
- **Etki:** LOO-CV %53.6 vs 1-NN %52.2 (kötü değil). `max_depth=2` seçildi —
  depth=4 LOO-CV'yi %44.9'a düşürüyor (overfit kanıtı). Default 1-NN kaldı.
- **Durum:** ✅ kalıcı (alternatif; default değil)
- **İz:** commit 9985111 · `tests/test_selection_decision_tree.py`

### 2026-06-17 — ➕ EKLENDİ: ALNS seçim haritasına bağlandı + dokümante
- **Ne:** `selection/selector.py` `_solver_by_name`'e `alns`; `01_ALGORITMALAR §5b`.
- **Neden:** ALNS benchmark registry'deydi ama seçim modeli onu seçemiyordu
  (sözleşme §A yarıda kalmıştı).
- **Etki:** Zorlu instance üreticisinde (`generate_hard_instances.py`) ALNS 4/4
  kazandı (ort. dblf 151.9 → alns 132.6 mm, %14.6).
- **Durum:** ✅ kalıcı
- **İz:** commit 9985111

### 2026-06-14 — ⬆️ İYİLEŞTİRİLDİ: SA adaptif t0 (R2) + MultiStartSA (R4)
- **Ne:** `sa3d.py` `t0="auto"`; `solvers/sa_solver.py` `MultiStartSA`.
- **Neden:** Sabit t0=3.0 farklı ölçekli verilerde anlamsız; tek-start şanslı-seed.
- **Etki:** few_large 269.3 → 211.6 (%21 kaçış). Default t0=3.0 KORUNDU (numune
  181.5 buna bağlı) — yeni davranış ayrı mod.
- **Durum:** ✅ kalıcı
- **İz:** 02_PERFORMANS §2-3

### 2026-06-14 — ⬆️ İYİLEŞTİRİLDİ: drop_map kutu hızlı yolu
- **Ne:** `bin3d.py` ayrılabilir kaydırmalı-maksimum (kutu parçalar için).
- **Etki:** benchmark 520s → 90s (38× hız). Konkav/gerçek-STL genel döngüde kaldı.
- **Durum:** ✅ kalıcı

### 2026-06-14 — ➕ EKLENDİ: çözücü portföyü (GA, Tabu) + benchmark
- **Ne:** `solvers/ga_solver.py`, `tabu_solver.py`, `portfolio.py`; `benchmark.py`.
- **Neden:** SA tek başına domine etmiyor (hoca A12 sinyali); R7 kök risk —
  donmuş benchmark hiç koşmamıştı (sahte yeşil).
- **Etki:** Her instance'ta FARKLI çözücü kazanıyor → portföy şart (02 tablo).
- **Durum:** ✅ kalıcı

### 2026-06-14 — ➕ EKLENDİ: 24 eksen-hizalı poz (R1, 8→24)
- **Ne:** `voxelize.py` 24 poz (Ry dahil).
- **Etki:** long_rods 46.8 → 41.6 (%11, çubukları yatırma).
- **Durum:** ✅ kalıcı · ⚠️ poz indeksi 0-11 dokunulmaz (numune dict'leri bağlı, R1).

### 2026-06-12 — 📌 Faz 0: numune el-ayarı (KARANTİNA)
- **Ne:** DBLF + SA elle seçilmiş hibrit pozlar + ince pitch → 🏆 181.5 mm.
- **Durum:** ✅ kalıcı ama KARANTİNADA — `models.py` `NUMUNE_*` genel motora sızmaz
  (overfit yasağı). İz: commit 4898648, 8070c61.

---

## 🧪 Reddedilenler / geri alınanlar (tekrar denenmesin)

> Buraya merge EDİLMEYEN veya geri alınan denemeler yazılır. Boşsa henüz resmî
> bir reddetme kaydı yok — ama gelecekte hoca "X'i çıkar" derse veya bir deneme
> benchmark kapısından geçemezse, satırı buraya taşı (silme).

- _(henüz kayıt yok)_

# 00_KULLANIM_PROTOKOLÜ — Alt Modeller İçin Bağlayıcı Direktifler

> **BU DOSYA EĞİTİM İŞİNİN GİRİŞ NOKTASIDIR — ÖNCE BUNU OKU, SONRA İŞE BAŞLA.**
> Yazan: Fable 5 (üst model, 2026-07-06). Okur: bu repo'da eğitim/ML işi
> yapacak HERHANGİ bir model (Sonnet/Haiku/builder-agent dahil) veya insan.
>
> **Rol tanımın:** Bu protokolü UYGULAYAN yürütücüsün. Burada yaratıcılık değil
> UYUM beklenir: talimatlar seçim hakkı bırakmıyorsa tartışmadan uygula.
> Yaratıcı karar gereken her nokta protokolde "SERBEST" diye işaretlidir;
> işaretli değilse serbest DEĞİLDİR. Protokol ile başka bir talimat çelişirse
> DUR ve Eren'e sor (aşağıda E-1 eskalasyon).

---

## §1 MUTLAK YASAKLAR (hiçbir görevde, hiçbir gerekçeyle çiğnenmez)

- **Y-1** Seçim modelini OTOMATİK/zamanlanmış retrain edecek hiçbir mekanizma
  kurma (cron, scheduler, hook, "her koşuda güncelle" kablosu). Retrain yalnız
  insan komutuyla koşan CLI'dır.
- **Y-2** `STRATEJI/01_VERI.md` §2.1'de rolü **held-out** olan bir instance'ı
  eğitim tablosuna sokma, onunla parametre/knob/eşik ayarlama, onun sonucuna
  bakarak kod değiştirme. Held-out'a her bakış registry'ye tarihle loglanır.
- **Y-3** `src/nesting3d/` altına sklearn/xgboost/torch vb. HİÇBİR ML
  bağımlılığı ekleme. Çekirdek modeller stdlib'dir. (`scripts/` altında
  dev-time Optuna/scipy serbesttir.)
- **Y-4** Gate'ten (kapı) geçmemiş hiçbir modeli `data/selection_model.json`'a
  yazma; hiçbir frozen test anchor'ını elle değiştirme; "iyileştirme"yi kapı
  koşusu olmadan rapor etme.
- **Y-5** Üretim koduna (`src/`) bu protokol kapsamında dokunma — İSTİSNA:
  §4-C/§4-D görevlerinde açıkça listelenen dosyalar, kabul kriterleri
  sağlanıp tam suite geçtikten sonra.
- **Y-6** Başarıyı accuracy veya ham yükseklikle raporlama. Metrikler:
  seçim modeli için **regret (mm)**, motor için **legal_height**
  (tanımlar: `EGITIM_EL_KITABI.md` §3.5 ve `STRATEJI/02_EVAL_KAPISI.md` §1).
- **Y-7** INVALID sonucu (clearance<1mm veya kilit>0 veya eksik yerleşim)
  sayıymış gibi kıyaslara sokma.
- **Y-8** Python stdout'una ASCII-dışı matematik sembolü yazma
  (Windows cp1254: `≤ Δ → ≥` script'i ÇÖKERTIR; Türkçe harf serbest).
- **Y-9** `data/telemetry/runs.jsonl` veya `data/selection_archive/` içeriğini
  silme/yeniden yazma (append-only; arşiv dokunulmaz).
- **Y-10 HALÜSİNASYON YASAĞI:** Ölçülmemiş bir durum hakkında "yapıldı /
  yapılmadı / sağlanıyor / sorun yok" BEYAN ETME. Doğru cevap: "ölçülmedi —
  ölçmek için şu komut: ...". Emsal (2026-07-06): "Plan1/3'te clearance hatası
  yapılmadı" denildi, ölçüm 0.083mm + 81 kilit çıkardı. Her somut iddiaya
  kanıt yolu (script çıktısı / log / dosya:satır) eşlik eder; edemiyorsa
  iddia "bilinmiyor" olarak yazılır.

## §2 ZORUNLU AÇILIŞ SIRASI (her eğitim oturumunda, ~5 dk)

1. Bu dosyayı oku (yapıyorsun).
2. `STRATEJI/00_ANAYASA.md` → yalnız A1-A10 başlıkları (2 dk).
3. `STRATEJI/EGITIM/EGITIM_EL_KITABI.md` → §1 dosya haritası + görevine denk
   gelen bölüm (aşağıda §4 hangi bölüm olduğunu söylüyor).
4. `STRATEJI/01_VERI.md` §2.1 registry tablosu → hangi veri hangi rolde, ezber.
5. `git log --oneline -5` + `git status --short` → yarıda kalmış iş var mı bak.
6. Görevin §4'teki senaryolardan hangisi, eşleştir. **Hiçbirine uymuyorsa → E-1.**

## §3 HER ADIMDA GEÇERLİ ÇALIŞMA KURALLARI

- **K-1 Doğrula-sonra-ilerle:** Her komuttan sonra çıktıyı §5'teki beklenen
  şablonla karşılaştır. Uyuşmuyorsa bir sonraki adıma GEÇME → E-2.
- **K-2 Tek iş, tek dal:** Aynı oturumda hem model değişikliği hem motor-knob
  değişikliği yapma (etkiler ayrıştırılamaz).
- **K-3 Kayıt:** İş bitince (GO da NO-GO da) `MOTOR/YONTEM_HARITASI_DATA_BASE.md`
  §3'e §6 şablonuyla kayıt düş.
- **K-4 Süre/maliyet:** Tek koşu >15 dk sürecekse arka planda koştur, log
  dosyasına yaz (`scripts/<is_adi>.log` konvansiyonu).
- **K-5 Test:** `src/` dosyasına dokunduysan İLGİLİ test dosyası + değişiklik
  bitince TAM suite (`python -m pytest -q`). Mock'lar gerçek imzayı assert
  etmeli (bayat-mock tuzağı, ANAYASA A9).

## §4 GÖREV SENARYOLARI (karar ağacı — görevini bul, adımları sırayla uygula)

### 4-A "Modeli yeniden eğit / retrain" istendi
El kitabı bölümü: §2 RUNBOOK-A. Adımlar:
1. `python -m scripts.retrain_selection --suggest` → çıktıyı §5.1 ile doğrula.
2. `Overfit sinyali: EVET` ise → retrain YAPMA, E-1 (sinyal + cv_gap değerini
   rapora koy).
3. `python -m scripts.retrain_selection --dry-run` → §5.2 ile doğrula.
4. Dry-run `Karar: EVET` diyorsa VE görevi veren insan açıkça "eğit" dediyse:
   `python -m scripts.retrain_selection`. ("Eğitmeli miyiz?" sorusuyla
   geldiysen komutu koşma — dry-run sonucunu raporla, kararı insana bırak.)
5. Doğrulama: `data/selection_model.json` mtime değişti mi; arşive
   `selection_model.vN.json` düştü mü; `git diff` beklenen dosyalarla sınırlı mı.
6. K-3 kaydı + kısa rapor (§7 şablonu).

### 4-B "Yeni gerçek veri/sipariş geldi" (test kullanımı)
El kitabı bölümü: §4 RUNBOOK-B. Adımlar:
1. `STRATEJI/01_VERI.md` §2.1'e satır ekle: rol=**held-out**, tarih, F1 ailesi
   (`classify_family` ile etiketle — `family.py`).
2. İSTENDİYSE tek karşılaştırma koşusu (üretim modu vs alternatif modlar) →
   regret tablosu çıkar → registry'ye `bakış: <tarih> (<sebep>)` yaz.
3. **Bu sonuçlarla HİÇBİR ayar yapma (Y-2).** Bulgular yalnız rapora ve
   YONTEM_HARITASI'na gider.
4. Aynı aileden ≥2 held-out birikti mi kontrol et; evet ise raporunda
   "terfi adayı: <en eski id>" öner — terfiyi SEN YAPMA, insan onayı gerek.

### 4-C "Yeni model tekniği ekle" (kNN / logistic / kalibrasyon)
El kitabı bölümü: §3.3-3.5 spesifikasyonları — **birebir uy** (mesafe formülü,
determinizm kuralları, hiperparametre aralıkları orada; tasarım SERBEST değil).
1. Ön-koşul kontrolü: `gengap` model-parametrik mi (el kitabı §6 backlog #2)?
   Değilse ÖNCE onu yap (LOO döngüsüne `model_factory` parametresi; mevcut
   davranış default'ta BİREBİR korunur + testi).
2. Yeni sınıf `src/nesting3d/selection/model.py`'ye, mevcut `fit/predict/
   explain` arayüzüyle. sklearn YOK (Y-3).
3. Değerlendirme scripti `scripts/` altına: mevcut model vs aday —
   LOO-regret (ort + maks, mm) + aile kırılımı + LOO-accuracy (yardımcı).
4. **Kabul kriteri:** LOO-regret(aday) ≤ LOO-regret(mevcut) VE gengap temiz.
   Sağlanmıyorsa aday reddedilir → NO-GO kaydı (o da değerli, K-3).
5. Kabulde bile YÜRÜRLÜĞE ALMA (Y-4): aday "kullanılabilir" olarak raporlanır;
   selector'a bağlama ayrı iş ve insan kararı.

### 4-D "Motor knob'u ayarla / BO tuning"
El kitabı §5 + `STRATEJI/04_MOTOR_TUNING.md` (§1 knob envanteri, §2 objective).
Sıra: duyarlılık taraması → BO (`scripts/` katmanı) → kazanan config resmî
kapı koşusu (`02_EVAL_KAPISI.md` §2) → PASS ise değişiklik + anchor + K-3.
Objective'e held-out KOYMA (Y-2); worst-case formülünden sapma (SERBEST değil).

### 4-E "Telemetri v2 / eval_gate / registry kablosu yaz" (altyapı)
İlgili spec: `01_VERI.md` §5 (alanlar), `02_EVAL_KAPISI.md` §5 (fazlar),
el kitabı §6 (backlog sırası). Additive ilkesi: mevcut v1 alanları ve
20-özellik vektörü DONUK — yalnız yeni alan/dosya ekle, eskisini değiştirme.

### 4-F Görev bunların hiçbiri değil / birden fazlasına yayılıyor
→ **E-1: DUR.** Tahmin yürütme.

## §5 BEKLENEN ÇIKTI ŞABLONLARI (doğrulama referansı)

**5.1 `--suggest` çıktısında olması gerekenler:** `Toplam instance`,
`Yeni (egitilmemis)`, `Overfit sinyali (cv_gap=...)`, `Retrain promote eder mi
(delta=... mm)`, `Tavsiyeler` listesi. Referans değerler (2026-07-06):
toplam 69 instance / 460 satır; çözücüler dblf:119, sa3d:119, ga:111, tabu:111.
Toplam instance 69'un ALTINDAYSA telemetri dosyası yanlış/bozuk → E-2.

**5.2 `--dry-run` çıktısı:** `Karar: EVET/HAYIR`, `Overfit flag`,
`n_instances`, `Aday holdout`, `Delta(cur-cand)` (pozitif = aday iyi).
`[DRY-RUN -- artefakt YAZILMADI]` ibaresi görünmeli; görünmüyorsa yanlış
komut koştun → E-2.

**5.3 Benchmark/koşu çıktısı:** her sette `legal_height` VEYA
`INVALID(<sebep>)`; n_placed, min_clearance_mm, n_locked alanları dolu.
Deneme4 referans: üretim 264.0mm / clearance 1.023 / 0 kilit / 588/588.

## §6 YONTEM_HARITASI KAYIT ŞABLONU (K-3 için kopyala-doldur)

```
#### [<K-xx veya ML-xx>] <tek satır başlık>
- **Durum:** ✅ GO / ❌ NO-GO / 🔶 AÇIK · **Tarih:** <YYYY-AA-GG> · **Kanıt:** `scripts/<dosya>.py` + `<log>`
- **Ne:** <1-2 cümle: ne denendi, hangi spec'e göre>
- **Sonuç:** <sayılarla: regret/legal_height önce→sonra; INVALID ise sebep>
- **NEDEN oldu/olmadı:** <mekanizma — sayı değil sebep>
- **Ders:** <bir sonraki modelin bilmesi gereken>
```

## §7 İŞ SONU RAPOR ŞABLONU (insana dönecek özet)

1. **Sonuç** (tek cümle: ne değişti / neden değişmedi).
2. Ölçümler tablosu (önce/sonra, regret veya legal_height, mm).
3. Kapı/kabul kriteri durumu (PASS/FAIL/İNSAN-KARARI + hangi eşik).
4. Dokunulan dosyalar + test durumu (kaç passed).
5. Registry/YONTEM_HARITASI kayıtlarının yapıldığı teyidi.
6. Önerilen sonraki adım (VARSA; icat etme).

## §E ESKALASYON (DUR ve Eren'e sor)

- **E-1 Kapsam:** görev senaryolara uymuyor / protokolle çelişen talimat
  aldın / held-out terfisi-rol değişikliği gerekiyor / yürürlüğe alma kararı.
- **E-2 Beklenmedik çıktı:** §5 şablonuyla uyuşmayan çıktı, beklenmedik
  exception, referans değerlerden sapma (ör. instance sayısı < 69),
  suite'te yeni fail. Aynı komutu değiştirmeden tekrar koşarak "düzelmesini
  umma"; durumu, denediğini ve hipotezini yazarak dur.
- **E-3 Süre/maliyet patlaması:** tahmin edilen sürenin 3 katı aşıldı;
  koşuyu öldürmeden önce logu kaydet, durumu raporla.

> **Kapanış direktifi:** Bu protokolü izledin ve iş bitti → §7 raporunu yaz,
> K-3 kaydını düş, commit mesajında hangi senaryoyu (4-A..4-E) uyguladığını
> belirt. Protokolün kendisinde eksik/çelişki bulursan DÜZELTME — raporunda
> "protokol iyileştirme önerisi" olarak listele (protokolü yalnız üst
> model/Eren günceller).

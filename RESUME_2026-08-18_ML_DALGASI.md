# RESUME 2026-08-18 — ML Dalgası: Bugün Yapılanlar + TÜM Bekleyenler

> Eren uçağa yetişiyor; devam bu dosyadan. Kardeş dosyalar:
> `STRATEJI/RAPOR_FSM610_SINIF_VE_ML_DENETIMI_2026-08-18.md` (analiz) ·
> `STRATEJI/ML_YENIDEN_YAPILANMA_PLANI_2026-08-18.md` (plan + M-serisi).

---

## A. BUGÜN YENİ EKLENENLER (hepsi COMMIT'SİZ)

### Kod (testli; entegrasyon süpürmesi 249/249 + webapp 40/40)
1. **Kısıt-onay "Sil"**: `/kisit-onay/<id>/sil` — YALNIZ onay beklemesini
   kaldırır (sipariş+STL+onaylı kısıtlar durur); UI butonu + 4 test.
   App RESTART sonrası aktif.
2. **M1 telemetri**: `append_run_v2`'ye `pitch_coarse`, `nfv_quality`,
   `peak_ram_mb` (yaklaşık-peak) + demo_pipeline uçtan uca kablo + 5 test.
3. **M2 gengap**: sözleşme testleri (5) — model_factory ZATEN kodda çıktı
   (7aa4d60); yeni olan test güvencesi. TODO: regret_mm → GenGapReport.
4. **M3 jeneratör**: `mass_plate_rod_mix` (fsm610-sınıfı: yüksek-adet
   ince-plaka + plaka-aşan çubuk; konteynerden türetilen garanti) + 7 test.
5. **M5 özellikler**: `plaka_asan_ratio` + `log_n_total` + `solidity_proxy`
   (=true_fill; K-62 "ML delikli parçayı göremiyor" kapandı). 20 FROZEN
   korunur; FULL_FEATURE_NAMES=26.

### Doküman / karar (bugün)
- fsm610 kök-sebep + ML denetim RAPORU (D-1..D-7 bulguları).
- ML YENİDEN-YAPILANMA PLANI (veri rolleri, Aşama-1/2/3, M1-M10).
- **KARAR-1..3 UYGULANDI**: fsm610 DEV'E TERFİ + deneme5 registry kaydı
  (01_VERI) + eval kapısı boşluk eşiği **2mm** (02_EVAL; D-4 drift kapandı).
- Hoca maili v2 HAZIR: `HOCA_MAIL_2026-08-18_GOVDE.txt` (ben-özneli;
  6 soru: rotasyon kapsamı, çok-plaka, plaka/boşluk, yerleşim pratiği,
  iş karışımı, farklı-tip veri ricası).
- HOCA_CEVAPLARI: "iç-içe geçmesin" beyanı ÇELİŞKİ kaydıyla işlendi
  (2026-07-06 "iç-içe izinli+ayrılabilirlik" ile çelişiyor; motor
  davranışı DEĞİŞMEDİ — söküm-kanıtlı iç-içe legal, teyit bekliyor).
- `docs/EULA_TASLAK.md` v0.1 (FSEK eser sahibi Eren Kutlu; sihirbazda
  zorunlu I-agree + kabul logu; AVUKAT şerhli) + lisans planına sihirbaz
  kabul adımı.
- BUSINESS_PLAN: güncelleme = PAKETLİ SÜRÜM + updater (git pull ELENDİ);
  Tailscale SİHİRBAZA GÖMÜLÜR (açık onay kutusu + tek-kullanımlık
  pre-auth key + ACL + AnyDesk B planı).
- Global CLAUDE.md: planner + architect → **fable** (agent dosyaları
  güncellendi).

### Halihazırda VARDI (bugün keşfedildi, yeni değil)
KNNSelector · LogisticSelector+kalibrasyon · RegretWeightedLogistic ·
ConformalSelector ("emin değilsen sus") · MiniBagging · ArgminMode ·
build_training_table_v2 (held-out dışlamalı, mod-düzeyi arm) ·
loo_regret (model-parametrik) · mod_yarismasi.py · retrain_mod.py.
→ Model envanteri HAZIR; eksik olan YAKIT (etiket) + zarf + kablo.

---

## B. YAPILACAKLAR (öncelik sırasıyla)

### Hemen (Eren dönünce)
1. **Maili gönder** (`HOCA_MAIL_2026-08-18_GOVDE.txt` — Eren eliyle).
2. **COMMIT PAKETİ ONAYI**: bugünün tümü commit'siz (kod §A.1-5 +
   dokümanlar). Ayrıca eski bekleyen commit'siz işler: K-65 kablosu,
   kanopi v28, fsm610 app-fix'leri (RAR/kalıp/altçizgi/park-nfv), P6
   ilerleme baloncuğu, gözcü sayaç düzeltmesi, geçmiş-sil idem yolu.
3. App RESTART (fsm610 kısıtlı+NFV koşusu bittiyse) — sil butonu + sayaç
   aktifleşir. Koşu sonucu geldiyse 3-yönlü kıyas raporu yaz.

### ML dalgası devamı (mail'den BAĞIMSIZ)
4. **M4 portföy koşu scripti**: her eğitim instance × {heightmap,
   nfv-fast, nfv-max} → winner_mode + regret etiketi; ÖNCE sentetikler
   (ucuz), dev-set kolları GECE koşusu (D:\ie488, K-57a münhasır).
5. **M7 destek-zarfı**: özellik-uzayı P1-P99 kutusu + kNN-mesafe eşiği →
   zarf-dışı=abstain; EL KURALINA da uygulanır (automode_proof zarfı).
6. **M6 kalan**: mod_yarismasi koşusu (adaylar aile-kırılımlı LOO-regret
   yarışır) + güven-kapısı eşiği LOO'da seçilir; regret_mm→GenGapReport.
7. **Aşama-1 eğitim** (fsm610-odaklı): kapı = kendi sınıfında kuralı yen
   + diğer ailelerde bozulma yok + sıfır-dokunuş. Sonra **Aşama-2** tam
   retrain (aile-dengeli) → promote EREN ONAYI. Sonra **Aşama-3**:
   plan7 kör-test (sınıf-genelleme sınavı — plan7 eğitime GİRMEZ!).
8. **Kapı 2mm BASELINE YENİLEME** (A8): tüm dev-set anchor'ları 2mm ile
   yeniden koşulmadan yeni kazanç ilanı YOK (sakin-makine gece işi).
9. **Heightmap clearance zafiyeti teşhisi** (Faz A1 — korrektlik;
   dev-setlerde, K-45 kuantizasyon bağlantısı şüphesi).
10. **K-65 resmî 4-set kapı koşusu** (şu an şerhli-GO).
11. Gerçek peak-RAM izleme (M1'de yaklaşık-peak bırakıldı — küçük iş).

### Mail CEVABI gelince
12. Kısıt semantiği düzeltme (S1: duruş-koru kapsamı) → not→kısıt
    derleyici + fsm610 kısıtlı kolunun etiketi.
13. fsm610 kıyası yeniden kur (S2: 284 tek-plaka mı? çubuk yatık mı?)
    → gerçek motor açığı sayısı → v27 global yeniden-istif hedefi +
    tekrar-sömürüsü (K-66 adayı) kararı.
14. U1 çok-parti yükseklik bölme önceliği (referans pratiğine göre).
15. Gelen yeni işler (6b ricası) → OTOMATİK HELD-OUT kaydı (yeni stok).

### Business / pilot hattı
16. EULA avukat incelemesi → sihirbaza EULA ekranı + kabul logu
    implementasyonu (P4 Faz-1) + Nuitka/Cython paket hattı (Faz-2).
17. Sihirbaza Tailscale gömme implementasyonu (onay kutusu + pre-auth
    key + ACL) + paketli-sürüm updater.
18. Hoca ile İÇ-İÇE/SÖKÜM teyidi (rehberli söküm HTML göstererek —
    çelişki kaydı HOCA_CEVAPLARI 2026-08-18(2)).
19. Eski bekleyenler: A9 tam suite + p2/d4 süre ölçümü + PUSH kararı +
    K-63 (eksen-kanonik) / K-64 (simetri budama) hoca istekleri.

---
*Not: Bu oturumda held-out'a YENİ bakış yapılmadı; eğitim/koşu başlatılmadı
(M-serisi yalnız kod+test). Tüm eğitim adımları A6 insan-onaylı.*

# AŞAMA-2 KAPI RAPORU (M9 — TASLAK, promote KARARI EREN'DE) — 2026-08-31

> ML planı §4 Aşama-2 / §6 M9 çıktısı. Girdiler: 5/5 dev-set karşı-olgusal
> etiketi (kampanya v2-v7, 2026-08-30/31 gecesi; rot-söküm hükümlü + ham
> sidecar'lı) + `mod_yarismasi --kafes` (tablo n=85).
> Kanıt: `results/m4_portfoy_etiket.jsonl` (39 satır) ·
> `results/mod_yarismasi_asama2_20260831.json` + `.log` ·
> `results/m4_kollar/` sidecar'ları · kampanya logları `..._v5/v6/v7.log`
> (hepsi D + OneDrive çift kopya).

## 1. Dev-set etiket bilançosu (üretim-semantiği: A2 rot-söküm dahil)

| set | n | kazanan | h (mm) | diğer kollar (regret mm) | not |
|---|---|---|---|---|---|
| plan1 | 112 | **nfv_fast 136,20** (12 kilit→rot 0, 7 cert) | 136,20 | heightmap +35,5 · AX24 +54,0 | kafes tetik YOK ×2 (sıfır-dokunuş) |
| plan2 | 226 | **kafes_duruskoru 529,0** (44→rot 0, 6 cert) | 529,0 | kafes +44,0 · heightmap INVALID (0,001) · NFV×2 **AC-08 hata** | kafes tetiği GERÇEK-POZİTİF |
| plan3 | 109 | **heightmap 811,0** (tek legal) | 811,0 | NFV×2 **AC-08 hata** · kafes tetik YOK ×2 | 811 > 600 plaka tavanı — çok-plaka (U1) gerçeği |
| deneme4 | 588 | **nfv_max 230,0** (368→rot 0) | 230,0 | nfv_fast +39,0 · heightmap +173,4 | kafes YOK ×2; **bomba YOK** |
| deneme5 | 352 | **nfv_max 227,5** | 227,5 | nfv_fast +7,0 · heightmap +116,3 | kafes YOK ×2; DATASETS girişi bu gece eklendi |

Beş sette dört FARKLI kazanan → mod-seçiminin instance-bağımlılığı gerçek
veride doğrulandı ("hep NFV-max" veya "hep heightmap" politikası 35-173 mm
bırakır ya da INVALID üretir).

## 2. 🔴→🟡 AC-08 — kanopi zinciri bellek bombası (GÜNCEL DURUM 2026-08-31 akşam)

**Fix zinciri uygulandı (Eren onaylı plan):** A1 GPU/host hijyeni (suite 3361)
· A2 zincir pitch=clearance (K-38'e dönüş; suite 3363) · F4 cuFFT plan-cache
bayt tavanı (py-spy kök kanıtı: pinli solve'da 4×~1,5 GB plan work-area).
**Sonuçlar:** plan1 v28 üretim 136,20→**133,20 LEGAL** (−3,0; baseline kararı
Eren'e) · **plan3 zinciri İLK KEZ uçtan uca LEGAL** (tepe 10,7 GB, takas yok)
· plan2 F4-doğrulaması KOŞUDA (F4 öncesi bekçi 12,6 GB'da kesiyordu).
Aşağıdaki orijinal teşhis metni tarihsel kayıt olarak korunur.

### (tarihsel) 2.0 🔴 AC-08 — kanopi zinciri bellek bombası (ÜRETİM-KRİTİK, kapı DIŞI bulgu)

`kanopi_zinciri_uretim → kanopi_zinciri_coz → solve_nfv → GPU FFT` plan2 ve
plan3'te süreç belleğini 12,3-14,9 GB'a şişirip takasa sokuyor (py-spy yığını
+ bekçi kayıtları; plan2'de ham çözüm ~1300 s SAĞLIKLI → kanopi girişinde
patlama; deterministik). eval_gate yolu (kanopi zincirsiz) plan2'yi 521,18
LEGAL / tepe 5,3 GB koşuyor. deneme4/5'te bomba YOK. **Sonuç: uygulama
plan2/plan3 tipi bir siparişi NFV yolunda bugün üretemez.** Teşhis+fix
(src işi; TDD + P-11 yedeği + tam suite ile) promote'tan bağımsız ama hoca
testine ÇIKMADAN önce kapatılmalı. Katalog: AC-08.

## 3. Yarışma — M9-fix-1 SONRASI (gerçek KURAL kararlarıyla; n=85, kafes dahil)

KURAL artefaktı gece kapatıldı (`m9_kural_devset`: 5 dev-set için
`predict_nfv_benefit(family_routing, rot_sokum=True, no-go'suz, modelsiz)`
kararları `regret_raporu.json`'a `devset_<set>@gercek` anahtarıyla eklendi;
yarışma tekrarı: `results/mod_yarismasi_asama2_20260831_fix1.json`).

| aday | regret ort (mm) | acc | gengap bayrak |
|---|---|---|---|
| karar_agaci | 9,36 | 0,729 | **1 -> plan §5.4 PROMOTE EDİLEMEZ** |
| mini_bagging | 12,96 | 0,624 | 0 |
| **logistic (üretimdeki)** | **14,37** | 0,588 | 0 |
| conformal_logistic | 14,37 | 0,588 | 0 |
| **KURAL (gerçek)** | **17,36** | 0,365 | — |

**Dev-set kırılımı (asıl hikâye):** KURAL dev-setlerde MODELDEN İYİ —
kural: plan1 **0** (nfv_kalite dogru) · d4 **0** (nfv_max dogru; kabuk+rot
kuralı) · plan3 0 (not-1) · p2 44 (not-2) · d5 **116,3 YANLIS**;
logistic: 35,5 / 173,4 / 0 / 44 / 116,3. Toplam dev-set: kural 160,3 vs
model 369,2 — model yalnız sentetik ailelerde önde. Üretim davranışıyla
tutarlı: allowlist dev-set ailelerini zaten dışlıyor → gerçek siparişte
karar fiilen kuralın.

- not-1: plan3 tek-legal-kol (heightmap) → kötümser ceza max-min=0; bu satır
  hiçbir adayı ayırt etmez (bilgi içermez).
- not-2: p2'de kuralın seçtiği nfv_kalite AC-08 nedeniyle ölçülemedi →
  ceza 44 (kafes ikilisi farkı); AC-08 fix'i sonrası yeniden ölçülmeli.
- **YENİ KURAL ZAFİYETİ (gerçek bulgu):** d5'te kural "ince-plaka 0,62>0,6 →
  heightmap" diyor; kazanan nfv_max (−116,3 mm). `thin_plate_thr` eşiği
  tekrarlı-örgü ailesinde yanlış taraf seçiyor — tam da retrain'in
  öğrenmesi gereken yüzey.

## 4. Kapı değerlendirmesi (plan §4 Aşama-2)

- (a) model-vs-kural: sentetiklerde model önde (14,37 vs 17,36); **dev-set
  gerçek verilerinde KURAL önde** — mevcut logistic dev-set ailelerinde değer
  katmıyor (LOO'da n=1/aile: hiç görmediği aile ölçülüyor; beklenen ama artık
  ölçülmüş gerçek). Dev-set etiketleri EĞİTİME girince modelin bu yüzeyleri
  öğrenmesi retrain ile test edilir; LOO n=1/aile iken genelleme
  KANITLANAMAZ → kanıt Aşama-3 plan7 kör-testinden gelir.
- (b) diğer ailelerde bozulma yok (tur-5 ile uyumlu; mixed_scale n=1
  aykırısı 192 aynı).
- (c) motor sıfır-dokunuş: PASS (yalnız etiket + ölçüm-altyapısı değişti;
  30/30 harness testi; motor/model artefaktı değişmedi).
- **Retrain ÖN-İZLEME (dry-run, artefakt YAZILMADI):** tablo 85 instance,
  7 sınıf (kafes kolları dahil), mevcut 8-aile allowlist ile kurulum
  sorunsuz.

**HÜKÜM:** Aşama-2 verisi ve altyapısı HAZIR; retrain+promote bilinçli olarak
Eren kararına bırakıldı (aşağıda önerilen sıra ile).

## 5. Karar listesi (Eren) — güncel (KARAR-A ✅ gece kapatıldı: m9_kural_devset)

- **KARAR-B (önerilen İLK iş):** AC-08 kanopi bellek bombası teşhis+fix
  (src işi; TDD + P-11 yedeği + tam suite). Uygulama plan2/plan3 tipi
  siparişi bugün NFV yolunda üretemiyor — "test aşamasına hazır" ön-koşulu.
  Fix sonrası p2/p3 NFV kolları yeniden ölçülüp etiketler güncellenir.
- **KARAR-C:** Aşama-2 TAM RETRAIN + promote. Sorular: (1) allowlist'e
  dev-set aileleri eklensin mi (eklenmezse retrain üretim davranışını
  DEĞİŞTİRMEZ — model o ailelerde çekimser), (2) aile-dengeli ağırlık
  (plan §4.4) bu turda mı. ÖNERİM: retrain'i AC-08 fix + p2/p3
  yeniden-etiketleme SONRASINA almak (yarım/hatalı kollu veriyle
  öğretmemek); d5 kural-zafiyeti için bu bekleme üretimde risk yaratmıyor
  (bugünkü davranış zaten kural).
- **KARAR-D:** plan3 811>600 → çok-plaka (U1) hoca ajandası önceliği.
- **KARAR-F ✅ ONAYLI (Eren 2026-09-01) + TASARIM GÜNCELLEMESİ:** kampanya
  KARŞI-OLGUSAL kalır (Eren şartı: "hangisi iyiyse o — nfv-max iyiyse o,
  heightmap'se o"; her sette TÜM kollar ölçülür, kazanan etiketlenir).
  Düzeltilmiş bilgi: harness meğer no-go'yu config'ten ZATEN alıyormuş
  (soft-ilan); "no-go taşınmaz" şerhi yanlıştı. Kampanya v8: fix-sonrası
  kodla, A2_REUSE_SIDECAR=0 (her kol taze), etiketlerde yeni `kosul_imzasi`
  alanı; baseline-yenileme bitince sıralı başlar; kampanyanın ardından
  **fsm610 etiketi de fix-sonrası kodla tazelenir** (`m4_portfoy_kosu`
  M4_FAMILIES=fsm610_gercek koşusu — kafes 400,0 teyidi + KARAR-G'li nfv
  kolları). Eski KARAR-F metni aşağıda.
- **(eski) KARAR-F (2026-08-31 akşam, Eren'in plan3 itirazı üzerine):** etiket
  kampanyası kolları bugüne dek NO-GO'SUZ koştu ("kollar iç-tutarlı" şerhi) —
  ama no-go'suz kanopi zinciri HİÇ ateşleyemiyor ve sonuçlar üretim
  kalitesini temsil etmiyor (p3: harness 629 vs üretim kapısı 607,5 vs
  şampiyon 577,62). Paket E yeniden-ölçümünde kolların ÜRETİM koşullarıyla
  (NOGO_STD dahil) koşulması önerilir; eski etiketlerle karşılaştırma
  kırılımı raporlanır. ÖNERİ: EVET.
- **KARAR-G ✅ ONAYLANDI (Eren, 2026-09-01 00:55: "bundan sonra her şey
  max'la yapılacak"):** flip **UYGULANDI (01:40)** — testler yeşil, suite koşuda; detay YONTEM [KARAR-G FLIP] (tek kaynak
  `NFV_QUALITY_DEFAULT="max"`; kapsam: demo_pipeline karar/solve/kanopi +
  webapp manuel form + eval_gate fallback; kafes zinciri BİLEREK dışarıda —
  fast-reçete kanıtlı, ayrı ölçüm). Baseline'lar MAX ile yenilenecek
  (4set-max gece + kapı). Kanıt-1: G-probe plan3 577,0 LEGAL.
- **KARAR-G (2026-08-31 gece, Eren beyanı "en iyi algoritmayı vereceğiz,
  nfv fast saçmalığı ne"):** üretim default kalite = **MAX (AX24) — kalite-önce**;
  "fast" yalnız açık etiketli hızlı-önizleme opsiyonu. Bu, KARAR-6/M11
  polarite yönergesinin tamamlanmasıdır. Bağlama kanıtı: 4-set quality=MAX
  kapı koşusu (yükseklik + süre + tepe-RAM tablosu; g_probe_4set_max) →
  Eren onayıyla default flip + A9 + baseline güncellemeleri. **plan3 G-probe SONUÇ (00:45): 577,0 LEGAL** (üretim koşulları+MAX; fast 607,5'ten −30,5 mm; Magics 593'ü geçer) — KARAR-G kanıtı-1.
- **KARAR-E (bilgi):** karar_agaci yine overfit-bayraklı; üretimde logistic
  değişmeden kalıyor.

## A11 statüsü
Etiketler tek-seed (42), kol koşulları iç-tutarlı (no-go/pin taşınmadı —
ŞERH); kazanç İLANI YOK. **Ölçmeden bıraktıklarım:** AC-08 kök mekanizması (grid boyutu × pin sayısı ölçümü);
plan2'de nfv-kanopisiz kol (eval_gate 521,18 var ama no-go'lu — koşul farkı).

## 6. Şampiyon→Üretim Denetimi (2026-08-31 gece — Eren "neden düzeltilmedi" talimatı)
Tam envanter YONTEM §3 "[ŞAMPİYON→ÜRETİM DENETİMİ]" kaydında + oturum
denetim raporunda. Özet: kayıp kalite algoritma boşluğu değil; (1) karar
katmanı quality=max'a tek dar daldan ulaşabiliyordu (H8/H9 fix'leri bugün
girdi; KARAR-G default-MAX bekliyor), (2) mod-modelinin üretim çevirisi ve
allowlist'i bozuktu (H8 ✅; H7 Paket D'de), (3) süreçte KABLO KAPISI yoktu
("GO" ölçümle kapanıp bağlama 30+ kez backloga düştü → RUNBOOK P-3.8),
(4) §2C "üretim" sütunu eval_gate/fast koşuluydu (3 farklı üretim politikası;
koşul-imzası geriye uygulanacak), (5) D↔OneDrive kopya ayrışması (kapatıldı;
P-5'e senkron-denetimi eklenecek). Bağlanmamış şampiyonlar: K-62 v20 (plan1
127,20) · K-66-d duruş-koru (fsm610 400,0 — S3 mail bağımlı) · K-67 şindil —
her biri P-3.8 kablo-kapısıyla ayrı iş olarak sahiplenilecek.


---

## EK — 2026-09-02 GECE GÜNCELLEMESİ (kampanya v12 + yarışma-3)

- **Etiket seti YENİLENDİ (v12, tam-saflık imzası):** p2 winner=nfv_max 519,5
  (n_legal=4, İLK temiz) · d4 nfv_max 230 · d5 nfv_max 227,5 · p1 nfv_fast ·
  p3 KARANTİNALI (max kolu R11-örnekleme belleğine takıldı; taze koşu
  R11-diyet fix'i sonrası). fsm610 tazelendi: n_legal=5, kafes 400,0
  OTOMATİK yeniden-üretim.
- **Koruma katmanı:** eksik-ana-kol satırları artık doğuştan karantinalı +
  köprü savunması (m4_n_eksik_ana_kol) — çarpık winner eğitime giremez.
- **Yarışma-3 (kafes dahil, n=85):** karar_agaci 8,88 (overfit-flag) ·
  mini_bagging 10,73 · regret_logistic 14,12 · KURAL 25,06. fsm610/d5'te
  model 0,0. Kanıt: results/mod_yarismasi_20260902.json.
- **Retrain dry-run A/B alındı, artefakt YAZILMADI** — promote önerisi
  Eren'de (detay: MOTOR/YONTEM §3.1 2026-09-02 04:30 kaydı).
- **p3-max tekil (09-02 12:20):** R11-diyet kararlı sızıntıyı kesti (60 dk
  4,6-5,8GB) ama 3600→3720 s'de 5,8→16,8GB ani balon → bekçi iptali; satır
  OTOMATİK karantinalı (koruma canlı kanıt). Faz teşhisi: bekçi py-spy dump
  ile tekrar koşu (PID 39300, ETA ~13:25). Retrain allowlist'i devset_plan3'süz.
- **AC-09 KÖK SEBEP (13:15):** balon = kapalı-kavite TELEMETRİSİ (label
  @0,5 mm, 540M voxel, 16,9 GB) — py-spy bekçi-dump kanıtı. Fix: voxel
  bütçesi + any-havuz kaba pitch (çözüm bit-özdeş, 27 test). 3. koşu PID
  6108, ETA ~14:10; başarılıysa p3 allowlist'e geri girer.
- **p3 KAPANDI (14:11):** 3. koşu nfv_max **577,0 LEGAL** (cl 2,033, rot-söküm
  0 kilit/2 cert), balon yok; satır 54 winner=nfv_max regret{hm 234, fast 52},
  n_legal=3, karantina YOK. §1 tablosundaki plan3 satırı (811 heightmap) artık
  TARİHSEL; güncel: **plan3 nfv_max 577,0** (Magics 593 geçildi). Retrain
  allowlist'e devset_plan3 dahil. AC-09 KAPALI-İZLEMEDE.

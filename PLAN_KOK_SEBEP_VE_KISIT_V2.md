# PLAN — Plan1 Kök-Sebep + Kısıt-v2 Motor Boşlukları (2026-08-03)

> Kaynak: hoca 2026-08-03 cevabı + 3 ekran görüntüsü; 4 paralel kod envanteri
> (poz/kısıt zinciri · bbox-konservatizm · plaka/eksen · mail hattı) + K-62
> ön-teşhisi (`results/k62_delik_fizibilite*.json`). Eren yönergesi: "plan1'i
> düzeltecek şekilde değil, plan1'i YAŞAMAMIZIN kök sebebi tespit edilsin;
> ML algoritmamızı kullanarak kök sebebi düzeltecek GENİŞ çözümler."
> Bu doküman KARAR dokümanıdır — kod işleri Eren onayıyla başlar.

---

## BÖLÜM A — Plan1'i yaşamamızın KÖK SEBEBİ

**Tek cümle:** Motorun çarpışma matematiği gerçek geometriyi doğru görüyor;
ama onun ÜSTÜNDEKİ her karar katmanı (fizibilite kapıları, yerleştirme
sırası, mod/parametre seçimi, ML özellikleri) parçayı **dolu bbox/dikdörtgen**
sayıyor ve **büyük-önce-alta** istif varsayımı yapıyor — insan ise boşluğu
(delikleri) kaynak olarak kullanıp büyük parçayı **en sona, en üste** koyuyor.

Plan1 bu sınıfın ilk örneği; aynı kök sebep delikli/çerçeve/kafes içeren HER
gelecekte gelecek sette tekrar yaşanır (A11: çözüm plan1'e değil, aileye).

### KS-1 — Bbox fizibilite kapıları her katmanı eziyor
- `adaptive_params._tilt_zorunlu_parca` (117-147) + birebir kopyası
  `targeted_tilt._yerlesebilir` (27-45): parça = dolu W×D dikdörtgen, no-go
  kaçışı = 4 şerit testi. K-62 teşhisi: baseplate_v2'de YANLIŞ-POZİTİF
  (gerçek geometri düz pozu 0,5mm marjla alıyor).
- Bu kapı "fizibilite kanıtı" statüsünde → mode_model + aile katmanı + kural
  katmanının HEPSİNİ ezer (adaptive_params 231-241). Tek bbox yanılgısı düz
  dalı komple kapatıp motoru tilt/pin'e sürükledi (140,2'de kalmamızın nedeni).
- Aynı sınıf: `pitch.suggest_nfv_pitch` plaka kapısı (max bbox boyutu ≥ plaka
  → NFV infeasible) · `cap_margin_to_plate` (bbox 330 → clearance dilation
  sıfırlanıyor) · `duz_pin_onerisi` no-go giriş ölçümü (bbox kenarıyla).

### KS-2 — Sıralama: büyük-önce + tek-geçiş greedy ⇒ kanopi permütasyonu arama uzayında YOK
- Sıra metriği `-volume_voxels` (gerçek voxel — iyi) AMA dilation SONRASI
  sayılıyor (voxelize 481-499): delikli çerçevenin iç çevresi uzun olduğundan
  margin ona orantısız hacim ekler → yapay öne çıkar.
- İlk yerleşen daima z=0 (dblf._best_position / NFV blb) → 330×302 çerçeve
  ilk gelirse plakayı z=0'da işgal eder.
- NFV'de sıra SABİT (parallel_decode 186/402, tek geçiş) → "çerçeve en sona"
  permütasyonu NFV'de asla üretilemez. Heightmap+SA'da sıra arama değişkeni
  → kanopi TEORİK erişilebilir ama oraya KS-1 yüzünden yanlış gerekçeyle
  geliniyor.

### KS-3 — Kanopi yerleşince ALTI mühürleniyor
- `Bin3D.place`: sütun bottom..top arası dolu sayılır → kanopinin altındaki
  boşluğa sonradan parça sokulamaz (bilinen §2.4 sınırı). Delikler ise DOĞRU
  işleniyor (drop_map gerçek filled+bottom; delik kolonları çarpışmaz, delikten
  yukarı taşan kule serbest). Sonuç: kanopi ancak **EN SON yerleşen parça**
  olursa değer üretir → çözüm KS-2'deki sıraya bağlanır.

### KS-4 — Yardımcı yollarda dolu-kutu hâlâ diri
- `extreme_point._drop_fallback` (397-424): bbox penceresinde max, filled/
  bottom YOK → NFV-BLB tıkandığında delikli parça olduğundan yükseğe atılır.
- `_update_extreme_points`: yalnız bbox-köşe adayları (cavity=True opt-in).
- `voxelize._dilate`: dar delikleri (< 2·margin·pitch) KAPATIR → parça voxel
  uzayında gerçekten dolu tuğlaya döner (baseplate delikleri büyük — bugün
  etkilenmiyor ama aile-geneli risk).

### KS-5 — ML/parametre katmanının TÜM girdileri bbox türevli
- `features._vol = w·d·h` (bbox) → `fill_lb`, `large_part_ratio`,
  `thin_plate_ratio`, `max_part_fill_xy`... hepsi bbox'tan.
- `telemetry.FEATURE_NAMES` (20 özellik): **solidity/delik özelliği YOK** —
  %26 doluluklu çerçeve ML'in gözünde dolu plakayla AYNI.
- `instance_boxiness` dilated-voxel/bbox oranı → delikli çerçeve "kutu"
  ölçülüp ince-açı refinement'i kapanabiliyor.
- Yani: ML yönlendirici bu aileyi GÖREMİYOR; görse de önerecek strateji
  (kanopi) envanterde yok.

### İyi haber (değişmeyecekler)
- FFT çarpışma (`fft_backend.blb*`) ve `drop_map` gerçek geometri — motorun
  dürüst katmanı. Heightmap kanopi MEKANİĞİNİ zaten destekliyor: parça
  yığının üstüne inebilir, delik kolonları serbest, settle kanopiyi ezmez
  (yalnız z-aşağı + clearance'ta durur, r11 kapı-3 koruması var).

---

## BÖLÜM B — Kök sebebi düzelten GENİŞ çözüm paketi (K-62 şemsiyesi)

> İlke: hiçbir düzeltme "plan1 için" yazılmaz; tetikler geometrik (A11),
> doğrulama dağılımsal (k59 deseni) + 4-set kapı + held-out.

### Ç1 — Gerçek-geometri fizibilite (kapı düzeltmesi) — DÜŞÜK efor, YÜKSEK getiri
`_tilt_zorunlu_parca` + `_yerlesebilir` şerit testleri → parçanın
`orient.filled` maskesi ile no-go maskesinin gerçek kesişim taraması
(`extreme_point.is_feasible:180`'deki DOĞRU test zaten var — tek kaynak
fonksiyona çıkarılır). `duz_pin_onerisi` giriş ölçümü de filled-farkındalı
olur. Tetik değişmez; yalnız yanlış-pozitif kalkar. Bit-özdeşlik: dolu
parçalarda sonuç birebir (şerit testi geçen her şey gerçek testte de geçer —
konservatiflik tek yönlüydü).

### Ç2 — DÜZ-KANOPİ mekanizması (insan hamlesinin motora öğretilmesi) — ORTA efor
İki-aşamalı dekod (K-56f `pinned_placements` altyapısı üstüne):
1. Geometrik tetik: en-büyük parça + footprint doluluk < eşik (ör. 0.5) +
   plaka-ölçekli (bbox ≥ plakanın ~%80'i) → "kanopi adayı".
2. Aday sıradan ÇIKARILIR, kalan parçalar normal çözülür (KS-2 çözümü).
3. Kanopi düz pozla EN SON drop edilir (KS-3 ile uyumlu — altı zaten dolu);
   x/y ofset taraması: no-go deliğe hizalanır (K-62 teşhis kodu çekirdek olur)
   + delikten-taşan kuleler drop_map'te zaten serbest.
4. Karşılaştırma: kanopi kolu vs normal kol — iyisi kazanır (portföy deseni,
   tek-konfig ilkesi bozulmaz).
NFV dalına kanopi ÖĞRETİLMEZ (sıra sabit — dokunmak riskli); bu bir
heightmap-kolu stratejisidir.

### Ç3 — ML entegrasyonu (Eren yönergesinin karşılığı) — ORTA efor
1. `FEATURE_NAMES`'e delik/doluluk özellikleri: `min_footprint_solidity`,
   `frame_part_present` (kanopi-tetik bayrağı), `mean_true_fill` (dilation
   ÖNCESİ ham voxel/bbox). Additive → eski modeller feature-eksik satırları
   zaten sayıyor (dataset_v2 n_featuresiz_satir).
2. Kanopi kolu selection çerçevesine YENİ ARM olarak girer
   (`heightmap+kanopi`) → regret-LOO + gate ile yarışır; A6 gereği retrain
   MANUEL (`python -m scripts.retrain_selection`), otomatik promote yok.
3. `features._vol` için gerçek-hacim opsiyonu (mesh hacmi mevcut —
   `mesh_fill_ratio` altyapısı) — mode_model yeniden eğitimiyle birlikte
   değerlendirilir; tek başına anchor kaydırır, kapı şart.

### Ç4 — Yardımcı yol düzeltmeleri — DÜŞÜK-ORTA efor, ayrı kapılar
- `_drop_fallback`'e filled/bottom farkındalığı (NFV kuyruğu düzelir).
- Sıralama metriği için ham (dilation-öncesi) voxel_count opsiyonu — DİKKAT:
  mevcut şampiyonların sırası değişebilir → 4-set kapı + baseline etkisi,
  ayrı karar.
- `_dilate` dar-delik kapatma telemetrisi (delik kapandıysa raporla) —
  karar değil, görünürlük.

### Ç5 — Doğrulama zinciri (A11)
1. B1 sentetiklere `holey_frames` jeneratörü (delikli çerçeve ailesi;
   parametrik delik oranı/sayısı).
2. k59 deseni dağılımsal ölçüm: tetik doğruluğu + kanopi kazanç dağılımı +
   tetiksiz ailelerde sıfır-dokunuş.
3. 4-set kapı (B2) + kör-test karnesine dokunmadan held-out disiplini.
4. Plan1 beklentisi: 202,18 üretim → hedef bandı **110-130** (insan 110,41;
   kanopi-altı bütçe 69,8mm ölçülü).

**Önerilen faz sırası:** Ç1 → Ç2 → Ç5(dağılımsal) → 4-set kapı → Ç3(ML arm +
özellikler) → Ç4. Ç1+Ç2+Ç5 tek sakin-makine seansına sığar (tahmin: kod 1
gün + koşular).

### Ç2-DERİN YOL PLANI (2026-08-04 akşam — v4/v5/v6 ölçümleri sonrası revize)

Ölçülmüş gerçekler: v4 suçlu-taşıma 136,50 (GO) · v5 azimut/sıra NO-GO ·
v6 kule-pinleme NO-GO (pin→heightmap zorlaması NFV taban kalitesini yedi:
105,5→125). Sonuç: kanopi-altı çözüm NFV'DE KALMALI; kule sorunu NFV'nin
İÇİNDE çözülmeli. Yol, ucuzdan pahalıya üç adım:

**v7 — Suçlu tiplere YATAY poz-kilidi (SIRADAKİ; motor değişikliği YOK):**
`orientation_overrides` NFV dalında ZATEN destekli (v6'yı düşüren guard
yalnız pinned/extra_rot içindi). Faz-A suçlu sayımı → o tiplerin poz
menüsü YATAY pozlarla sınırlanır (yon_poz_tablosu "yatay" kümesi) → NFV
yeniden çözer (kule diye bir şey kalmaz, her şey ≤~69 bütçesine yatar) →
kanopi ~70'e oturur. Beklenti: toplam 105-120 bandı. Risk: yatık bobbinler
taban alanını büyütür — alan yetmezse yükseklik başka yerden artar
(ölçüm söyler). Maliyet: script-içi ~20 satır + ~15 dk koşu.

**v8 — NFV'ye gerçek pin desteği (v7 yetmezse; ORTA motor işi):**
occupancy ön-yükleme + parça düşme; kuleler dik kalır (alan tasarrufu) ama
konumu delikte sabitlenir. Kapılı üretim-motor değişikliği.

**Kablolama + doğrulama (her GO'dan sonra):** Ç5 holey_frames dağılımsal +
4-set sıfır-dokunuş kapısı + üretim kablosu (kanopi kolu portföy dalı
olarak; K-56g deseni) + baseline etkisi — hepsi ayrı Eren onaylı seans.

---

## BÖLÜM C — Kısıt-v2: 4 yeni tür için motor boşlukları ve plan

### C1 — Kopya-grubu bölme (15 yatay/15 dikey/15 45°) — KISA YOL VAR
**Kritik keşif:** motor grubu `(name, imza)` anahtarıyla kuruyor
(format.py:333) → aynı STL'yi **farklı adlarla** N PartSpec'e bölmek
(`kupon#yatay`, `kupon#dikey`, `kupon#45`) motor DEĞİŞİKLİĞİ GEREKTİRMEDEN
çalışır; her sanal ada ayrı `orientation_overrides` verilir.
- **Faz-1 (ucuz):** ingest/kısıt katmanında "sipariş ön-bölme" — derleyici
  `{ad: [{"adet":15,"pozlar":[...]}]}` yerine sanal-ad bölmesi üretir +
  Σgrup=qty doğrulaması + rapor/söküm künyesinde kaynak_ad korunur.
- **Faz-2 (yapısal, gerekirse):** gruplama anahtarına kisit_grubu bileşeni +
  kopya-deterministik atama (parca_uid) + operatör kısmi-onay yüzeyi.
- Eksiklerin tam listesi: poz/kısıt envanteri (12 madde) — şema adet alanı,
  kanonik-oy tutarlılığı (Σ=45), kesişim→partition mantığı, 15/15/15
  post-check telemetrisi.

### C2 — 45° ara açı — ORTA efor (sanıldığı kadar ucuz DEĞİL)
- Master 28 pozda 45° YOK (eğikler 20/25/30/35°); Z-45° in-plane üretimde
  kapalı (fine_angle_window=0).
- `extra_rot_overrides` EKLER ama ZORLAMAZ ("45 de denensin" ≠ "yalnız 45");
  "yalnız 45" için model-başına matris-ezici yol gerekiyor —
  `to_voxel_parts/expand_quantities` `rot_matrices`'i dışarı AÇMIYOR
  (bilinen boşluk, c3_continuous_rot.py:97).
- İş listesi: şema tipi (`orientation_angle` {eksen, aci_deg}) + whitelist +
  derleyicide matris üreten kol + taşıma anahtarı + hedefli-tilt'le öncelik
  politikası (extra_rot slotu bugün tilt'in) + NFV kolu kararı (kısıtlı parti
  zaten heightmap'e zorlanıyor — kabul edilebilir ilk sürüm).

### C3 — Recoater/gaz-akış eksenine hizalama — ORTA efor + HOCA BİLGİSİ ŞART
- Motorda eksen semantiği SIFIR (doğrulandı); no-go zaten "recoater kolonu"
  ama yön olarak değil dikdörtgen olarak modelli.
- Poz havuzu azimut-AYRIMLI (X-hizalı ve Y-hizalı pozlar ayrı indeksler —
  ham malzeme VAR); tek eksik: `yon_poz_tablosu` yalnız (R@ez).z'ye bakıyor,
  eksen ayrımı türetmiyor + parça-bağımlı "uzun eksen" kavramı yok.
- İş listesi (15 madde envanterde): `resolve_recoater_axis` (plate_config
  deseni, ~20 satır, None→bit-özdeş) + poz→eksen türetimi + şema/prompt +
  `fine_angle_axes="z"` rafinemanının kısıt-farkındalığı.
- **ÖN KOŞUL: recoater plaka X'i mi Y'si mi — hiçbir yerde yazılı değil;
  hocaya sorulacak (FSM gündemi).**
- **YOL ÜSTÜ BUG (bugün bulundu):** `/plaka-ayar` POST config'i SIFIRDAN
  yazıyor → mevcut `no_go_soft`/`min_clearance_mm` alanları kaydetmede
  SİLİNİR (app.py:3245-3261). Yeni alan eklemeden önce merge fix'i şart.
  (Ayrı küçük iş — onaya sunuldu.)

### C4 — Tek-plaka tercihi — DÜŞÜK-ORTA efor + SÖZLEŞME kararı
- Tek sipariş ZATEN bölünmüyor (batcher atomik); çok-plaka yalnız çok-sipariş
  çizelgesinde. Webapp üretim yolu fiilen hep tek parti — ama İLAN EDİLMİŞ
  değil, tesadüfi.
- Asıl boşluk: şema SİPARİŞ-seviyesi kısıt taşıyamıyor (parca_adi zorunlu) +
  derleyicide çizelge-kanalı yok + `allow_mixing`/kapasite sabit kodlu.
- Sözleşme sorusu: "mümkünse tek seferde" YUMUŞAK tercih — hard mı soft mu?
  (Hoca dili soft diyor; ilk sürüm: rapor bayrağı "tek-plaka talebi
  karşılandı/karşılanamadı" + kapasite uyarısı = davranış değişikliği YOK.)

**Kısıt-v2 önerilen sırası:** C1-Faz1 (kısa yol) → C2 → C3 (hoca cevabı
gelince) → C4 (rapor-bayrağı sürümü erken alınabilir). Hepsinde korpus+eval
genişlemesi eşlik eder; `kisit_modu` KAPALI kalır, geçiş ayrı karar.

---

## BÖLÜM D — Bugün UYGULANAN mail-hattı işleri (2026-08-03, testli)

| İş | Dosya | Test |
|---|---|---|
| **Kayıp-veri FIX:** share-link alanları (review_reason/share_links/adet_listesi) poller+webapp'ten store'a akıyor (önceden meta.json boş kalıyordu) | mail_poller.py · app.py | `test_poller_link_alanlarini_stora_gecirir` |
| Kapı-0 sözlük genişlemesi: ureti(m) · öncelik/acil/basil · tek sefer/parti/plaka · ayni plaka/tabla · birlikte · bolun · recoater · gaz akis · transvers | note_detector.py | +5 test (kupon gerçek satırı dahil) |
| RawMail `in_reply_to`/`references` (iki-mail eşleştirme ÖN KOŞULU; eşleştirme mantığı bilerek YOK — otomatik birleştirme riskli, tasarım C-envanterinde) | mail_ingest.py | `test_rawmail_thread_basliklari_default_bos` |
| Share-link allowlist: sharepoint.com · box.com · mega.nz | mail_ingest.py | +2 test |

Doğrulama: mail-hattı komşu süpürmesi **135/135 yeşil** (note_detector +
share_link + mail_poller + mail_ingest + wave2 + H7 + llm_kisit).
`kisit_modu=kapali` → davranış garantisi değişmedi (yapısal sınır).

---

## BÖLÜM E — EREN ONAYI BEKLEYEN KARARLAR

1. **Ç1+Ç2+Ç5 (kanopi paketi) kodlamaya başla?** — kök-sebep düzeltmesinin
   çekirdeği; plan1 beklentisi 110-130.
2. Ç3 ML adımları (özellik ekleme + yeni arm + manuel retrain) — Ç2 kapı
   PASS sonrası mı, paralel mi?
3. Kısıt-v2 sırası onayı (C1-Faz1 önce?) + C4-rapor-bayrağı erken alınsın mı?
4. `/plaka-ayar` POST merge fix'i (no_go_soft silme bug'ı) — küçük, ayrı iş.
5. Bugünkü mail-hattı değişiklikleri commit paketine girsin mi (mevcut
   commit'siz working tree ile birlikte; öncesi A9 tam suite).
6. FSM gündemine eklenecekler: recoater ekseni · no-go temas toleransı ·
   örnek iş emirleri · S1 eski-boşluk.

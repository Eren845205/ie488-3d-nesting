# ML / Genelleme Stratejisi — BULGULAR + FİKİRLER (2026-07-06)

> ## ⛔ YERİNİ ALDI → **`STRATEJI/`** (2026-07-06, Fable 5)
> Bu taslak koda-karşı doğrulandı, düzeltildi ve **`STRATEJI/` klasörüne**
> (README + 00_ANAYASA + 01_VERI + 02_EVAL_KAPISI + 03_SECIM_MODELI +
> 04_MOTOR_TUNING + 05_TRANSFER_PLAYBOOK) yükseltildi. Çelişkide STRATEJI/
> kazanır; bu dosya tarihsel referanstır. Neyin doğrulandığı/bayatladığı/yeni
> eklendiği: `STRATEJI/README.md` "Opus taslağına göre ne değişti".

> **Bu doküman PLAN DEĞİL.** Bugünkü (2026-07-06, Opus 4.8 oturumu) bulguları ve
> fikirleri toplar. Tasarım/plan yarın **Fable 5** ile bundan yapılacak.
> Kaynak: clearance bulgusundan doğan overfitting/genelleme tartışması.
> Sahibi: Eren. Durum: tartışma tamam, tasarım bekliyor.

---

## ⚠️ ÖN-ANALİZ UYARISI (önce bunu oku)

Bu doküman **Opus 4.8 tarafından** (bu oturumun modeli) üretildi ve **yalnızca bir
ön-analiz / ön-bulgudur.** Konuya yeterince derin bakılmadı — hızlı bir kod
okuması + kavramsal tartışma sonucu çıktı, tam bir mühendislik analizi değil.

**Amaç:** bu, bir **fikir tohumu / başlangıç noktası** olarak okunmalı; kesin
doğru kabul edilmemeli. Buradaki her bulgu, öneri ve rakam **daha güçlü / üst bir
model tarafından baştan gözden geçirilmeli.** O gözden geçirmede:
- **bazı bulgular reddedilebilir** (yanlış ya da yüzeysel olabilir),
- **bazıları düzeltilebilir**, ve
- **yeni bulgular/yönler eklenebilir.**

**Üst modelin asıl, derinlemesine analizi bizim için bu dokümandan daha
önemlidir.** Buradaki hiçbir şeyi "karar" gibi değil, "üzerine düşünülecek ilk
taslak" gibi ele al. Somut sayılar (69 instance, 0.083mm, ~10-15 gerçek veri
hedefi vb.) doğrulandığı ölçüde güvenilir; ama stratejik yargılar (hangi ML
yöntemi, ne kadar veri, hangi çerçeve) tartışmaya ve daha derin değerlendirmeye
açık öneri niteliğindedir.

---

## CLEARANCE FIX — DURUM + KARAR NOKTASI (2026-07-06 gece, güncel)

**Ölçüldü, üretim yolu (wall_aware/H-16w, builder+reviewer):**
| config | Deneme4 yükseklik | min boşluk | durum |
|---|---|---|---|
| margin=0 (MEVCUT üretim) | 282.0mm | 0.084mm | ❌ 1mm ihlal (üretilemez) |
| margin=1, zc=2 | 296mm | 0.79-0.90mm | ❌ hâlâ <1mm |
| **margin=2, zc=2 (`clearance_mm=1.0`)** | **329mm** | 1.029mm | ✅ ≥1mm |

**Dürüst maliyet: 282 → 329mm (+%16.7)** — ama bu KABA yöntem (her parçayı 2 voxel şişir).
Formül (ölçüm-kalibreli): `margin = z_clearance = max(1, ceil(clearance_mm/pitch))`;
pitch≥1 → (1,1) = NFV/benchmark konvansiyonu; pitch 0.5 → (2,2).

**KOD DURUMU:** clearance_mm mekanizması (coarse_to_fine + demo_pipeline) YAZILDI ama
**COMMIT EDİLMEDİ** — reviewer BLOCK verdi, karar bekliyor. Bayat-mock (HIGH-1)
düzeltildi (aynı `_fake_c2f` tuzağı). Değişiklikler working tree'de.

**Reviewer bulguları (opus):**
- HIGH-1 ✅ düzeltildi: `test_reporting_wave_f0` bayat mock `clearance_mm` kabul etmiyordu → broad-except sessiz DBLF-fallback'e yutuyordu. Mock imzası + `assert clearance_mm==1.0` kablo kilidi eklendi.
- HIGH-2 ⏳ AÇIK: 1.029mm eşiğe YAKIN + `min_clearance` örneklem ÜST-sınır (gerçek min <1.0 olabilir) + üretimde runtime clearance kapısı YOK. Hard üretim kısıtı → post-nest doğrulama/uyarı gerekir.
- HIGH-3 ⏳ TAKİP: NFV yolu da (margin=1) fine pitch 0.5'te <1mm (0.79-0.90mm) → Plan1/3 gibi fine-pitch NFV sonuçları da sub-1mm. Sistem-geneli clearance NFV'ye de uygulanmalı.
- M1 broad-except programlama hatalarını maskeliyor · M3 kaba-pitch'te over-provisioning (sentetik 36→86.4 +%140 bunun) · L1 bit-identity testi zayıf.

**KARAR NOKTASI (Eren + Fable 5):** İki yol —
- **(a) Kaba dilation'ı bitir:** HIGH-2 runtime uyarı kapısı ekle + commit → gözcü dürüst 329 üretir (üretilebilir ama kaba/yüksek).
- **(b) Clearance-FARKINDA yerleştirme:** dilation yerine 1mm'yi optimizasyon KISITI olarak tut (Magics böyle yapar) → 329'un ALTINA, gerçek üretilebilir + tıkiz. Asıl kalite kaldıracı. Daha çok iş.
- **Öneri:** mekanizma dürüst ÖLÇÜM için değerli (eval çerçevesinin temeli) — ama 329'u canlı-default yapmadan önce (b)'yi araştır; en azından benchmark'ı clearance-dürüst tut. Eren'in kararı (329 kalite sayısı onu rahatsız ediyor).

**MORAL — dürüst çerçeve (Eren 329'a "useless" dedi):** 329 çöküş DEĞİL:
- plan2 **Magics'in %4.2 yakınında, DOĞRU clearance ile** (pitch 2.0 margin=1 = ≥1mm) — algoritma gerçek veride gerçekten rakip. Bu tek başına "useless" iddiasını çürütür.
- Hız 31× (104.5dk→3.4dk) clearance'tan bağımsız, gerçek.
- plan1/2/3 iyileşmeleri (~%20/17.5/28) margin=1 = dürüst clearance = geçerli.
- Yalnız Deneme4 fine-pitch sayısı (282→329) düzeldi. Bir sayı ≠ tüm iş.
- 329 KABA dilation'ın tabanı; clearance-aware placement (b) + süper bilgisayar (A1) denenmemiş gerçek kaldıraçlar.
- **AÇIK SORU (hocaya):** Magics 250 kendi 1mm clearance'ıyla mı ölçüldü? Değilse 329-vs-250 hâlâ elma-armut.

---

## VİZYON — niçin ayrı bir "strateji klasörü" (kuzey yıldızı)

**Eren'in hedefi (2026-07-06):** ML/eval kısmı olgunlaştığında **ayrı bir klasör**
olsun — bundan sonra algoritmayı geliştirirken/eğitirken **oradaki sabit
stratejileri kullanalım**. Böylece her seferinde **stabil, tekrarlanabilir** bir
şekilde geliştiririz.

**Bu vizyonun keskin hâli (asıl değer buradadır):** Klasör, algoritma
geliştirmeyi **o anki yapay zekânın (model/oturum) anlık tercihlerinden bağımsız**
kılar. Bugün en kritik ders buydu — clearance bulgusu gösterdi ki "bu sonuç daha
iyi" hissi, ölçüm çerçevesi eksikken **yanıltıcı** olabiliyor (282mm bir config
artefaktıydı). Ayrı strateji klasörü şunu değiştirir:

- **Önce (bugünkü hâl):** değişiklik önerilir → "güven bana daha iyi" → o oturumun
  modelinin yargısına bağımlı, tekrarlanamaz, overfitting'e açık.
- **Sonra (hedef):** değişiklik önerilir → **sabit, repoda-checkli değerlendirme
  kapısından geçer** (tüm setler + held-out + clearance-dürüst metrik). Kabul
  kriteri objektif ve deterministik. Hangi model/oturum olduğu **fark etmez.**

Yani deterministik/stabil olan şey **kabul kriteri ve değerlendirme** — yaratıcı
"ne deneyelim" adımı hâlâ yargı ister, ama artık hiçbir iddia gate'i geçmeden
"kazanç" sayılmaz. Bu, geliştirmeyi **güvenilir ve tekrarlanabilir** yapar; tam da
Eren'in istediği "her seferinde güvenebileceğimiz sabit harita/yöntem/strateji."
(fable B1 "tek doğruluk kaynağı" + B6 "repoda-yaşayan durum, bellek değil" ile
birebir örtüşür.)

---

## 0. Neden bu doküman

Bugün clearance (parça-arası boşluk) bulgusu, projenin kronik endişesini
tetikledi: **overfitting.** Biz motoru elimizdeki birkaç veri setinde ayarlıyoruz;
yeni/görülmemiş veride aynı başarı oranı gelecek mi? Bu doküman, "algoritmayı
nasıl dürüstçe eğitir/değerlendirir, overfitting riskini nasıl minimize ederiz"
sorusuna dair bugün netleşen her şeyi kaydeder.

---

## 1. TETİKLEYEN BULGU: clearance (dürüst-metrik dersi)

**Ölçüldü (doğrulanmış):** Deneme4 web-heightmap sonucu (pitch 0.5, K-19 yolu)
parçalar arası **minimum 0.083 mm** boşluğa iniyor — hocanın **1 mm** şartını
(2026-06-11, `clearance.py` docstring'inde belgeli) **İHLAL EDİYOR**. AABB'si
1.5mm'den yakın 2884 çift var (sistematik). **İç-içe-geçme YOK** (voxel-doluluk
garantisi tutuyor; parçalar binmiyor, sadece çok yakın).

**Kök neden — tek dalda kablo eksiği:**
| Yol | margin | Durum |
|---|---|---|
| Kıyas/benchmark (`c3_generality`, MARGIN=1) | 1 | ✅ 1mm var |
| NFV kalite yolu (`nfv_solve`, default margin=1) | 1 | ✅ 1mm var |
| CLI/numune (`run3d`, numune margin=1) | 1 | ✅ 1mm var |
| **Web heightmap/tuner/fallback (`demo_pipeline`+`coarse_to_fine`)** | **0** | ❌ **ihlal** |

Ayrıca web yolunda `z_clearance=1` her yerde → pitch 0.5'te dikey boşluk 0.5mm
(<1mm).

**Neden bu ML dokümanının başında:** 282mm "kahraman sayımız" kısmen bir **config
artefaktıydı**, gerçek algoritmik kazanç değil. Yani **yanlış şeyi ölçtük ve
sonuç şişti.** Bu, "daha titiz, dürüst değerlendirme çerçevesi lazım"
argümanının somut kanıtı. İyi bir eval çerçevesi bunu baştan yakalardı (clearance
dürüst metriğin parçası olurdu).

**Ayrım — iki farklı üretilebilirlik kısıtı (karıştırma):**
- **Sökülebilirlik/erişilebilirlik** (F2): parça +Z'de çekilebilir mi (kilit).
  K-19 için "588/588 sökülebilir" DENDİ — bu doğru.
- **Yüzey boşluğu (1mm)**: parçalar baskıda kaynaşmayacak kadar uzak mı. Web
  heightmap'te ÖLÇÜLMEMİŞTİ → 0.083mm ihlal. Biri tuttu diye diğeri tutmuyor.

**AÇIK (bu oturumda bitmedi):** Düzeltilmiş z-height ölçümü (margin=1/zc=2 vs
margin=2/zc=2 ile Deneme4 kaç mm olur + 1mm gerçekten tutuyor mu) — ölçüm
kaynak-çakışmasıyla iki kez yarıda kaldı, yeniden koşuluyor. **Beklenti: z-height
YUKARI çıkar** (boşluk paketlemeyi gevşetir, yanal iç-içe/telescoping azalır).
Magics kıyası da eşit clearance kuralıyla yenilenmeli (bizim sayı 282'den yukarı,
Magics'e fark açılabilir). → clearance FIX ayrı iş (web heightmap dalına margin +
pitch-türevli z_clearance bağla; donmuş benchmark testlerini gerçek üretilebilir
sayılara güncelle; reviewer + suite).

---

## 2. KAVRAMSAL AYRIM: "algoritma" aslında İKİ ayrı şey

Overfitting ikisinde farklı anlama gelir, farklı savunma ister:

**(A) Nesting motoru** (DBLF, NFV, tuner, pitch/oryantasyon/clearance seçimi):
**deterministik geometri çözücüsü** — ML anlamında öğrenen parametresi YOK. Biz
"cidar-pitch", "AX24", "clearance" eklerken **kod mantığı** değiştiriyoruz, veriye
parametre uydurmuyoruz. Burada "training data" yanlış kelime → bu bir **benchmark
seti**.
- Buradaki risk = **heurstik overfitting**: bizim setlerde iyi, görülmemişte
  işe yaramayan kaldıraç (künye örneği: "K-05 +%1.1 eğik-pozlu ilk-12'ydi,
  genelleşmedi").
- Savunma = **cross-validation DEĞİL** → **cross-dataset regresyon kapısı**
  (her değişiklik TÜM setlerde ölçülür, birinde iyileştirip diğerinde bozan
  reddedilir + aile-bazlı raporlama).

**(B) Seçim modeli** (`src/nesting3d/selection/`): **GERÇEK ML burada** — hangi
instance için hangi çözücü/config kullanılacağını tahmin eder.
- Buradaki risk = klasik overfitting.
- Savunma = CV / held-out (zaten kurulu, bkz. §3).

---

## 3. MEVCUT ML ALTYAPISI (kod okundu, doğrulanmış gerçekler)

**Model:** `AlgorithmSelector` = **1-NN** (öklid, eğitim noktalarını saklar) +
`DecisionTreeSelector` = **CART-benzeri, max_depth=2, min_samples_leaf=2** (sığ,
bilinçli — küçük-N için doğru). Her instance için kazanan-çözücüyü + güven tahmin
eder.

**Overfit/genelleme kapısı** (`selection/gengap.py`, sertleştirme 2026-06-17):
- `OVERFIT_GAP_THRESHOLD = 0.2`, `MIN_INSTANCES = 6`.
- **LOO-CV** tabanlı: 1-NN'de in-sample train_acc yapısal ~1.0 olduğundan (her
  nokta kendine en yakın) eski "train−holdout" kapısı sürekli yanlış-pozitif
  veriyordu → artık **leave-one-out CV doğruluğu (cv_acc) vs holdout_acc** açığı
  (cv_gap) ile hesaplanır.
- **Prequential** (rolling test-then-train) doğruluk = veri sızıntısı + zaman
  kayması sentineli.

**Split** (`selection/splits.py`): **aile-stratified, isimden bağımsız holdout** —
her aile hem train'de hem holdout'ta temsil edilir (eski alfabetik-son-%20 split
isimle manipüle edilebiliyordu; "z_yeni" hep holdout'a düşerdi).

**Öğrenme politikası:** **MANUEL + öneri** (sessiz retrain YOK) — `--suggest`;
öğret `python -m scripts.retrain_selection`. Sessiz overfit'i engellemek için
bilinçli.

**VERİ (kritik rakam):**
- `data/telemetry/runs.jsonl` = **460 satır** (satır = instance×çözücü değerlendirmesi).
- **69 farklı instance**, **6 aile**. Ağırlıkla **SENTETİK**: `br*`=bischoff_ratcliff
  (literatür), `enr_*`=enriched jeneratör aileleri.
- Ham satır/aile: random_boxes 120, few_large_many_small 88, high_qty_repeat 80,
  thin_plates 72, long_rods 72, bischoff_ratcliff 28.
- **Yani model 6 gerçek veriye değil ~69 sentetik instance'a bakıyor** → korkulan
  kadar kötü değil.

**Dosyalar:** `selection/{model,dataset,splits,gate,gengap,advisor,selector,
retrain,persistence,prefilter}.py`.

**⚠️ TAKSONOMİ ÇELİŞKİSİ:** İki ayrı aile sistemi var:
- Seçim modeli (eski): random_boxes / few_large_many_small / high_qty_repeat /
  thin_plates / long_rods / bischoff_ratcliff.
- F1 aile taksonomisi (yeni, `instances/family.py`, K-19/wall_aware kullanıyor):
  thin_shell / hollow_tubes / solid_bulk / mixed_scale / ...
- "Aile-stratified" iki farklı şey demek → çerçevede **birine indirgenmeli.**

---

## 4. İŞİN ÖZÜ: İKİ VERİ REJİMİ, ZIT EKONOMİLER

**Sentetik veri (seçim modelini eğitmek):**
- Sınırsız + bedava (jeneratörler var). Şu an 69.
- Aile-CV kararlılığı için ~20-30/aile (toplam ~150-180) ideal; şu an ort ~11/aile.
- **Azalan getiri:** jeneratörün ürettiği şekli öğretir; üretmediği gerçek-dünya
  şeklini asla.

**Gerçek veri (genellemeyi DOĞRULAMAK):**
- Kıt + değerli (~6: plan1/2/3, deneme4, numune, boxy).
- **Tek dürüst genelleme testi bu.** Sentetik→sentetik CV skoru, sentetik→gerçek
  genellemeyi GARANTİ ETMEZ. Modelin gerçekte tuttuğunu ancak gerçek held-out
  kanıtlar.
- **Hocadan gelen her mail altın** → held-out'a dokunulmadan girmeli.

---

## 5. "NE KADAR VERİ LAZIM?" — net cevap

- **Sentetik:** istersek jeneratörle ~150-180'e çıkarırız (düşük öncelik, ucuz,
  aile-CV stabilize). **Darboğaz DEĞİL.**
- **Gerçek (asıl darboğaz):** üretimde görülen aileler (kabuk/kavite/karma) için
  **aile başına en az 2-3 held-out gerçek instance** → savunulabilir genelleme
  iddiası için toplam **~10-15 gerçek instance**, aile-dengeli. Şu an ~6 → kabaca
  **2x daha fazla gerçek veri.**
- **Somut:** hocadan **her tipten 2-3 farklı sipariş** iste (zaten veri talebi
  bekliyor — bu listeye ekle). Özellikle thin_shell, cavity, mixed_scale. Gelen
  gerçek veri **asla ayar için kullanılmaz**, yalnız held-out.

---

## 6. ML YÖNTEM ENVANTERİ — hangileri İŞE YARAR, hangileri YARAMAZ

> Bağlam: N~69 sentetik + ~6 gerçek, 6 aile. Öğrenen kısım = seçim modeli
> (sınıflandırma: instance→kazanan çözücü). Motor deterministik.

### (A) Seçim modeli için (gerçek ML görevi)
| Yöntem | Verdikt (küçük-N gerekçesiyle) |
|---|---|
| **1-NN + sığ karar ağacı** (mevcut) | ✅ Doğru temel. Yorumlanabilir. KORU. |
| **k-NN, k=3-5 + mesafe-ağırlık** | ✅ **Ucuz robustluk kazancı** — 1-NN'in varyansını düşürür; k'yi LOO-CV ile seç. |
| **Regularize logistic regression** | ✅ **Ekle** — çok az parametre, overfit zor, KALİBRE olasılık verir (güven-kapısı için değerli). |
| **Kalibrasyon (Platt/isotonic)** | ✅ **Yüksek değer** — is_easy/güven kapısı ancak güven anlamlıysa güvenilir. |
| **Random Forest (güçlü regularize: az ağaç, sığ)** | ⚠️ **Temkinli, YALNIZ LOO-CV kapılı deney** — ensembling ufak varyans kazancı verebilir ama N~69'da kolay overfit. |
| **Gradient Boosting (XGBoost/LightGBM)** | ❌ **Şimdilik HAYIR** — sert-fit tasarımı küçük-N'de en hızlı overfit eder; N 3-5x büyüyünce tekrar bak. |
| **Sinir ağı / derin model** | ❌ HAYIR — N çok küçük. |

### (B) Motoru (deterministik) iyileştirmek — klasik-ML DEĞİL
| Yöntem | Verdikt |
|---|---|
| **Bayesian optimization (GP / TPE) ile config-tuning** | ✅✅ **EN YÜKSEK DEĞER** — motorun sürekli knob'larını (pitch tarifeleri, tuner budget, oryantasyon sayısı) cross-dataset benchmark'a karşı optimize et. Az-örneklemli/pahalı-değerlendirme için tasarlanmış → knob'ları TEK sete elle overfit etmeye karşı korur. "Bizim config için AutoML". |
| **Domain randomization / instance perturbation** | ✅ **Faydalı orta yol** — gerçek instance'ları oynat (adet/ölçek/oryantasyon-karışım jitter) → gerçeğe yakın sentetik varyantlar; gerçek verinin etrafındaki dağılımı genişletir. |
| **Sentetik augmentation (mevcut jeneratörler)** | ✅ Ucuz, yap — az temsil edilen aileler için. Ama sentetik→gerçek açığını unutma. |
| **Aktif öğrenme** | ⚠️ Kavramsal evet ama hocanın verisini seçemeyiz → pratik kaldıraç düşük. |
| **RL / DRL placement policy** | ❌ HAYIR — künye A3 (1-2 yıl ertelendi); çok veri + eğitim altyapısı + GPU; 6GB'de fizibıl değil; overfit riski. Süper bilgisayar gelince bak. |

### Öncelik sırası (dürüst, "algoritmayı daha iyi yap")
1. **Bayesian optimization ile motor-config tuning** (veri-verimli, knob-overfitting'e karşı) — en yüksek kaldıraç.
2. **Kalibrasyon + k-NN(k>1) + regularize logistic** (ucuz, overfit düşür, güveni anlamlı yap).
3. **RF temkinli, CV-kapılı** (küçük kazanç).
4. **Sentetik augmentation + domain randomization** (veri kıtlığını ucuza aç).
5. **YAPMA:** boosting (N büyüyene dek), DRL/diffusion (erken).

**Meta-nokta:** "Algoritmayı daha iyi yapmak" için en yüksek kaldıraç daha süslü
bir sınıflandırıcı DEĞİL → (a) deterministik motorun knob'larını dürüst
cross-dataset benchmark'a karşı **Bayesian optimization** ile ayarlamak, ve (b)
daha çok **gerçek held-out veri**. N~69'da daha fazla model karmaşıklığı marjinal.

---

## 7. GENELLEME / EVAL ÇERÇEVESİ — fikirler (PLAN DEĞİL)

Yarın Fable 5 tasarlayacak. Bugünkü fikirler:

- **`eval/` (veya mevcutları toplayan) çerçeve:** held-out disiplini + cross-dataset
  + aile-bazlı regresyon kapısı + **dürüst (clearance-zorunlu) metrikler** + Magics
  eşit-clearance kıyası.
- **Held-out disiplini = tek en önemli ekleme.** Hocanın yeni verisi → held-out,
  asla tune'lanmaz. Headline metrik: **gerçek-held-out aile-başına doğruluk/kalite.**
- İyileşmenin **dağılımını** raporla (en iyi durumu değil): bir sette +%10, iki
  sette −%5 = net kayıp, kazanç kılığında.
- **Model basit kalsın** (RF/NN çekmesine dayan, §6).
- **Taksonomiyi birleştir** (§3 çelişkisi).
- Prequential drift sentineli + manuel retrain kapısı görünür yap.
- Güven-kapılı dağıtım: model yalnız yüksek güvende default'u ezsin.

---

## 8. ZATEN VAR OLANLAR (reinvent ETME — konsolide et)

- `scripts/c3_generality.py` DATASETS (cross-dataset benchmark, MARGIN=1).
- `MOTOR/YONTEM_HARITASI_DATA_BASE.md` (karar veritabanı, cross-dataset kapıları).
- `src/nesting3d/selection/` (CV + stratified split + drift sentinel + manuel retrain).
- Donmuş benchmark testleri (`tests/test_regression_numune.py`, `test_devox.py`
  clearance, frozen anchor'lar).
- `src/nesting3d/clearance.py` (bağımsız 1mm doğrulama — min_clearance).
- Jeneratörler (`instances/` — bischoff_ratcliff, enriched aileler).

Öneri = bunları **tek kasıtlı çerçevede birleştir + eksik held-out disiplinini
ekle**, sıfırdan inşa değil.

---

## 9. AÇIK KARARLAR (Eren'e — yarın Fable 5 soracak)

1. Hangi setler "dokunulmaz held-out" ilan edilecek? (Öneri: hocadan gelecek her
   yeni gerçek veri otomatik held-out.)
2. Regresyon kapısı eşikleri (set başına kaç % gerileme kabul).
3. Hangi aile taksonomisi kalacak (seçim-modeli eski mi, F1 yeni mi, birleşik mi).
4. Ne kadar yatırım (minimal eval-gate mı, tam framework mü).
5. Clearance FIX önce mi (dürüst metrik temeli) — evet, öneri: eval çerçevesinden
   ÖNCE clearance'ı bağla.

---

## 10. SIRADAKİ (bu doküman kapsamı)

- **Clearance FIX** (ayrı iş, §1 sonu): web heightmap dalına margin + pitch-türevli
  z_clearance; donmuş testleri güncelle; reviewer + suite. Düzeltilmiş z-height
  ölçümü tamamlanacak (yeniden koşuluyor).
- **Eval/genelleme çerçevesi tasarımı:** yarın Fable 5, bu dokümandan, planner ile.
- **Veri talebi:** hocadan aile-dağılımlı ~6-9 gerçek sipariş (held-out).

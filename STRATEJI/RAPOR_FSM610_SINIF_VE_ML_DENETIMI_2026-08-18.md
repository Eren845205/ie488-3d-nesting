# RAPOR — fsm610 Kök-Sebep Analizi + ML/Genelleme Stratejisi Denetimi

> Tarih: 2026-08-18 · Yazan: Fable 5 (Eren talebi: "bu verinin algoritmaya
> hangi açıdan ters olduğunu analiz et; ML stratejilerimizi denetle —
> yeterli mi, değilse ne değil, nasıl geliştirilir")
>
> Kaynaklar: STRATEJI/01_VERI.md §2.1 fsm610 satırı (3 bakış kaydı),
> YONTEM §5 K-65/U1 + §3 K-65 kaydı, adaptive_params.py, 00-05 strateji
> dosyaları, EGITIM protokolü. **Bu rapor için YENİ KOŞU YAPILMADI** —
> yalnız mevcut ölçüm kayıtları okundu (fsm610'a yeni bakış yok).

---

## BÖLÜM 1 — fsm610 motorumuza hangi açıdan ters? (katmanlı kök-sebep)

### 1.0 Setin anatomisi ve neden "bilinmeyen sınıf" olduğu

fsm610 = 4 model / **610 adet** (520 + 36 + 27 + 27); thin_plate oranı
0,94; içinde 95×10×**399,6** mm çubuklar (düz yatışta 325'lik plakaya
SIĞMAZ). Referans (Netfabb, mühendis): ~284 mm @ 2 mm boşluk (A10 şerhli).

Bu set TEK bir bilinmeyen değil, **üç varsayımın aynı anda kırıldığı bir
kombinasyon**:

1. **"thin_plate-dominant → düz istif optimal"** varsayımı: homojen küçük
   setlerde (numune 0,92) doğruydu; burada 0,94'e rağmen yanlış — çünkü
   karışımda plaka-aşan çubuk var VE 610-parça yoğunlukta etkileşimli
   yerleşim (NFV) kazanıyor.
2. **"Kısıt notu = gönderilen duruşta kilit"** yorumu: referansın 284'ü
   çubuklar yatırılmadan İMKÂNSIZ → bizim yorum referansla tutarsız
   (mail sorusu S1).
3. **"Tek parti tek plakaya sığar"** varsayımı: batching'de yükseklik
   fizibilite kapısı yok (U1) ve referansın tek/çok-plaka olduğu belirsiz
   (mail sorusu S2).

**Sınıf tanımı (A11-uyumlu, veri-adsız):** *yüksek-adet tekrarlı homojen
ince-plaka kitlesi + az sayıda plaka-aşan dik-çubuk karışımı, yoğun
doluluk.* Kritik tespit: bu sınıf ÖLÇÜM katmanında görünürdü —
`FEATURE_NAMES` içinde `repeat_part_ratio`, `n_total_parts`, `fill_lb`,
`long_rod_ratio` zaten hesaplanıyor — ama **KARAR katmanı (mod
yönlendirici) bu sinyallerin hiçbirine bakmıyor** (yalnız `mean_aspect_z`
+ `thin_plate_ratio`). Sınıfı görmemiz için yeni sensör gerekmedi;
sensör vardı, karar mekanizması bağlı değildi.

### 1.1 Açığın sayısal ayrıştırması (mevcut 3 bakışın kaydından)

| Katman | Kanıt | mm etkisi | Statü |
|---|---|---|---|
| **Kısıt yorumu** (duruş-koru) | 691,2 (kısıtlı) − 652,8 (kısıtsız) | **~38 mm** | Mail S1 cevabı bekler — algoritma sorunu DEĞİL, kanal semantiği |
| **Mod yönlendirme** (K-65) | 652,8 (heightmap) − 516,0 (NFV-max) | **136,8 mm (%21)** | Fix KODDA (şerhli-GO; 80/80 dağılımsal + sıfır-dokunuş) |
| **Clearance uygulaması** | heightmap yolu 1,004 / 0,131 < 2,0 İHLAL; NFV yolu 2,002 TEMİZ | legallik (mm değil) | AÇIK — ayrı korrektlik teşhisi (K-45 kuantizasyon dersi bağlantılı olabilir) |
| **İstif kalitesi (kalan açık)** | 516,0 vs referans ~284 | **~232 mm (%45)** | EN BÜYÜK BİLİNMEYEN — aday açıklamalar aşağıda |

### 1.2 Kalan %45'in aday açıklamaları (önem sırasıyla)

1. **Çok-plaka şüphesi:** referans 610'un tamamı tek plakada olmayabilir
   (mail S2). Cevap "bölünmüş" çıkarsa gerçek motor açığı %45'ten çok
   daha küçük — kıyas baştan kurulur.
2. **Çubuk duruşu:** referans çubukları yatırmışsa (S1), bizim 516 dik-çubuklu
   NFV'si elmayla armut; yatık-çubuk serbestisiyle koşu hiç yapılmadı.
3. **Tekrar-sömürüsü eksikliği (gerçek mekanizma adayı):** 520 özdeş ince
   plaka insan elinde düzenli/kafes istife girer; bizim greedy sıralı decode
   tekrar yapısını sömürmüyor. v27 alan-bütçesi bulgusuyla akraba ama farklı
   mekanizma: kanopi-altı yeniden-istif değil, **kitlesel özdeş-parça
   periyodik istif**. (K-44 d5 dersi "216× özdeş çubuk NFV'nin ideal sahası"
   bunun erken sinyaliydi.)
4. **Arama bütçesi/ölçek:** 610 parçada NFV-max 55 dk CPU'da (cupy
   CUDA-path'siz) koştu — parça başına arama bütçesi dev-setlerden düşük.
   GPU'lu makinede (hoca lab) bütçe artar.

**Sonuç (Bölüm 1):** fsm610 "algoritma her yerde kötü" demiyor; ölçülen
kaybın %21'i tek bir YANLIŞ KARARdan (yönlendirici), ~38 mm'si kısıt
YORUMUndan geliyor, legallik kaybı bir UYGULAMA hatasından (clearance)
geliyor ve kalan %45'in en az yarısı kıyas-şartı belirsizliği (S1+S2).
Motorun gerçekten bilmediği şey muhtemelen **tekrar-sömürüsü** — ama bunun
payı ancak mail cevabıyla sayısallaşır.

---

## BÖLÜM 2 — ML/genelleme stratejilerimizin DENETİMİ

### 2.1 Ne ÇALIŞTI (fsm610 bu disiplinin başarı kanıtıdır)

- **A3 held-out dokunulmazlığı:** fsm610 doğuştan held-out'tu; ilk bakış
  gerçek out-of-box açığını ölçtü. Sistem kendine iyi not vermedi.
- **A2 dürüst metrik:** 691,2 ve 652,8 "sonuç" diye rapor edilmedi —
  INVALID sebepleriyle yakalandı. Clearance zafiyeti maskelenmedi,
  keşfedildi.
- **A11 + k59 dağılımsal desen:** K-65 istisnası 24 saat içinde
  geometrik-kesin tetik + 80/80 dağılımsal + 0 yanlış-pozitif + dev-set
  sıfır-dokunuş kanıtıyla kodlandı. Yeni-sınıf tepki süreci İŞLİYOR.
- **Kör-test karnesi (01_VERI §2.2):** ilk-koşu açığı trend metriği
  zaten kurulu; fsm610 satırı bu tabloya girecek.

### 2.2 Ne YETMEDİ (denetim bulguları, önem sırasıyla)

**D-1 · ML yanlış yüzeyde — kendi teşhisimiz uygulanmamış (EN KRİTİK).**
`03_SECIM_MODELI.md` §2 daha 2026-07-06'da yazmış: "ML'imiz en KÜÇÜK
etkili kararı öğreniyor (metaheuristik seçimi); en BÜYÜK kararlar
kural-tabanlı." fsm610 bunun faturasını kesti: −136,8 mm'lik mod kararı
2-özellikli el kuralındaydı. §5.1 backlog maddesi (telemetri v2'de
mod-düzeyi etiket + kural-vs-en-iyi regret tablosu) hâlâ koşulmamış.
→ *Öğrenen katman, mm-etkisi en büyük karara hiç bağlanmadı.*

**D-2 · Karşı-olgusal ölçüm boşluğu — yapısal kör nokta.** Yönlendirici
yanlış-negatifi ancak biri ÖBÜR yolu elle koşarsa görülür (fsm610'da NFV
ancak Eren talimatıyla, bakış #3'te koşuldu). Runbook'lar held-out'ta "tek
koşu" diyor; alternatif-mod karşılaştırması opsiyonel. Seçilmeyen yol
ölçülmediği için **mod-kararının regret'i sistematik olarak GÖRÜNMEZ** —
karar-yüzeyi kayması çerçevemiz var ama onu besleyecek veri akmıyor.

**D-3 · El kuralları geçerlilik-zarfsız extrapolasyon yapıyor.** Mod
eşikleri (thin_plate 0,6 / aspect 4,0) 5-veri kanıtıyla (küçük setler
dünyası) kondu. fsm610 (610 parça, karışım) o kanıtın kapsadığı özellik
bölgesinin DIŞINDA — kural orada aslında hiç doğrulanmamıştı ama tam
güvenle karar verdi. Kural da bir modeldir ve destek-dışında (out of
support) düşük-güven sayılmalıydı. 03 §2.2'deki güven-kapısı fikri yalnız
öğrenen modele değil KURALLARA da uygulanmalı: destek-dışı → konservatif
yol (NFV / çift-yol / operatöre sor).

**D-4 · Eval kapısında clearance eşiği DRIFT'i (belgeler çelişiyor).**
ANAYASA A2 güncellemesi (2026-07-09, hoca teyitli): boşluk eşiği **2 mm**.
Ama `02_EVAL_KAPISI.md` §1 hâlâ "min_clearance >= 1.0mm", §2 kapı
sabitleri "clearance=1.0mm". Sonuç: heightmap'in ~1,0 mm'lik çıktısı
dev-set kapılarında LEGAL görünür, gerçek işte (2 mm şartı) INVALID düşer.
**Heightmap clearance zafiyetinin dev-setlerde bugüne dek görünmez
kalmasının muhtemel sebebi bu.** Kapı eşiği 2 mm'ye çekilmeli (KARAR işi:
baseline'lar yenilenir, A8 anchor gerekçeli güncellenir).

**D-5 · Eğitim verisi hâlâ %100 sentetik.** Seçim-modeli tablosu 460
satır / 69 instance, tamamı 6 sentetik jeneratör ailesi (03 §1). Gerçek
sipariş koşuları (artık her mail bir instance üretiyor — altın kanal)
eğitim tablosuna hiç akmadı; telemetri v2 kablosu var ama mod-düzeyi
etiket birikimi başlamadı. "Gerçek veriyle eğitim" hedefi için önce bu
kablo, sonra model.

**D-6 · Held-out sınıf keşfi → jeneratör aileye kalıcı ekleme adımı
protokolde resmî değil.** Üç kez aynı ders: d5 → repeat_rod_mix, plan1 →
holey_frames, fsm610 → k65 smoke'taki 4 aile (şu an scripts'te, kalıcı
jeneratörde DEĞİL). Desen çalışıyor ama her seferinde "hatırlanarak"
yapılıyor; 02 §4 runbook'una zorunlu adım olarak yazılmalı.

**D-7 · Ölçek stres-testi eksik değil ama kombinasyon testi eksik.**
610 parça tek başına yeni değil (d4 588, p3 577); yeni olan
"ölçek × thin_plate-dominant × karışım". Sentetik ailelerde boyutlar tek
tek var, KOMBİNASYONLAR taranmıyor. Dağılımsal smoke'lara 2-faktör
kombinasyon aileleri eklenmeli (ucuz: jeneratörler parametrik).

### 2.3 Yeterlilik hükmü (dürüst özet)

**Overfit-ÖNLEME tarafı: YETERLİ ve kanıtlı çalışıyor.** Held-out
disiplini, dürüst metrik, dağılımsal kapı, sessiz-öğrenme yasağı fsm610
krizinde tam da tasarlandığı gibi davrandı: açığı gizlemedi, ölçtü,
tek-vaka yamasını dağılımsal kanıta zorladı. Büyük müşteri/fabrika
çeşitliliğine giderken bu çekirdek KORUNMALI, gevşetilmemeli.

**Öğrenmeyi-doğru-yüzeye-taşıma tarafı: YETERSİZ.** Mevcut "ML" en küçük
kararı öğreniyor; en pahalı karar (mod yönlendirme) 2-özellikli, destek
beyansız el kuralı; karşı-olgusal veri toplanmadığı için bu kuralın
hata oranını ölçen bir döngü YOK; eğitim tablosuna tek bir gerçek sipariş
girmedi. fsm610 bu boşluğun ilk büyük faturası — ve fabrika verisi
çeşitlendikçe fatura büyür.

---

## BÖLÜM 3 — GELİŞTİRME PLANI (öncelik sıralı)

### Faz A — Mail dönüşünden BAĞIMSIZ, hemen başlanabilir

| # | İş | Sınıf | Kapı |
|---|---|---|---|
| A1 | **Heightmap clearance-uygulama teşhisi** (dev-setlerde; fsm610'a dokunmadan) — 2 mm şartında heightmap yolunun min_clearance dağılımını ölç, kök-sebep (kuantizasyon?) bul | Korrektlik | A2-legallik, dev-set |
| A2 | **Eval kapısı eşiğini 2 mm'ye çek** (D-4 drift'i kapat) — 02_EVAL §1-2 güncelle + baseline yenileme | Sözleşme/KARAR | Eren onayı + A8 anchor |
| A3 | **Karşı-olgusal çift-kol runbook'u**: her yeni held-out sınavında üretim kararı + karşı-mod KOŞULUR (ikisi de bakış olarak loglanır); regret tablosu birikir. Ayar YAPILMAZ (Y-2 aynen) — yalnız karar-katmanı karnesi dolar | Süreç | 02 §4 revizyonu |
| A4 | **Telemetri v2 mod-düzeyi etiket kablosu** (03 §5.1) — her koşuda mode + legal_height + clearance + aile satırı; A3'ün çıktısı buraya akar | Altyapı | mevcut Faz-2 üstüne |
| A5 | **fsm610-sınıfı kalıcı sentetik aile** (yüksek-adet thin_plate kitle + plaka-aşan çubuk karışımı; k65 smoke prototipi synthetic.py'ye taşınır) + 2-faktör kombinasyon aileleri | Veri | k59 deseni |
| A6 | **K-65 kalıcılaştırma**: 4-set resmî kapı koşusu + commit (şu an şerhli-GO) | Motor | B2 eşikleri |
| A7 | **Yönlendirici geçerlilik-zarfı (D-3)**: karar katmanına destek-dışı tespiti (n_total_parts / repeat_part_ratio / fill_lb kanıt kümesinin zarfı dışında → konservatif NFV veya çift-yol) — kural değişikliği dağılımsal kapıyla | Motor/karar | k59 + sıfır-dokunuş |

### Faz B — Mail dönüşü GEREKTİRENLER

| # | İş | Bağımlılık |
|---|---|---|
| B1 | Kısıt semantiği düzeltme (duruş-koru kapsamı: eksen mi, tam kilit mi, hangi parçalar) → not→kısıt derleyicisine yansıt | Mail S1 |
| B2 | fsm610 kıyasının yeniden kurulması (284 tek-plaka mı? çubuklar yatık mı?) → gerçek motor açığı sayısı | Mail S1+S2 |
| B3 | U1 çok-parti yükseklik bölme önceliklendirmesi | Mail S2 (referans pratiği) |
| B4 | Tekrar-sömürüsü mekanizması (kitlesel özdeş-parça istifi) — B2'den sonra payı netleşirse K-66 adayı olarak açılır | B2 |

### Faz C — fsm610 ile "eğitim" (overfit-korumalı mekanik)

1. **Rol kararı (E-1, Eren onayı gerekir):** fsm610 üzerinde mekanizma
   geliştirilecekse set resmen **dev'e terfi eder** (01_VERI §2.1 kayıt;
   §2.2 kuralı gereği held-out'luğu düşer). Eren'in "bu veriyi eğitimde
   kullanacağız" talimatı fiilen bu karardır — registry'ye işlenmesi onay
   sonrası yapılır.
2. **Held-out stoku yenilenir:** bundan sonra gelen her yeni sipariş
   otomatik held-out (B1 kuralı zaten böyle) + mail ricası 5b (1-2 geçmiş
   gerçek iş) yeni held-out stoğunun kaynağı. **Terfi, yeni held-out
   gelmeden "genel kazanç" ilanını İMKÂNSIZ kılar — bu bilerek böyle.**
3. **Eğitim = üç kanal, hepsi kapılı:**
   (a) *Karar katmanı:* fsm610 satırı (+A3 çift-kol verisi) mod-düzeyi
   eğitim tablosuna girer; model kural-baseline'a karşı challenger,
   metrik REGRET, LOO-CV + gengap, promote insan kararıyla (A6/Y-1);
   (b) *Motor mekanizması:* tetikler geometrik (A11), kanıt dağılımsal
   (A5-jeneratör aileleri) + dev-set sıfır-dokunuş + 4-set kapı;
   (c) *Kısıt kanalı:* B1 semantiği not→kısıt derleyici testlerine
   golden-case olarak girer (veri-adı değil, kalıp olarak).
4. **"Kazanç" ilanı** ancak: 4-set+fsm610 kapısı PASS + tetiksiz sıfır-
   dokunuş + YENİ held-out'ta (sonraki gerçek sipariş) ilk-koşu açığının
   körtest karnesinde düşmesiyle. Öncesinde her rapor ŞERHLİ.

---

## A11 statüsü (bu raporun kendisi)
Koşu yapılmadı; fsm610'a yeni bakış YOK (mevcut 3 bakışın kayıtları
kullanıldı). Bu bir analiz/denetim raporudur; hiçbir kazanç ilanı yoktur.
KARAR bekleyenler: (1) fsm610 dev'e terfi onayı, (2) eval-kapısı 2 mm
eşiği, (3) Faz A iş sırası onayı, (4) hoca maili gönderimi.

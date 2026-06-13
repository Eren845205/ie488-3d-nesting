# APP_YOL_HARITASI.md — Konteyner Nesting Uygulaması: Olası Güzergâh + Motor Riskleri

> Kaynak: 2026-06-11/12 gece oturumu konuşmaları (hoca görüşmesi sonrası).
> Amaç: numune fazı kapandıktan sonra uygulama işine başlarken bu dosya tek
> başına yol göstersin. İlişkili dosyalar: `APP_SORULAR.md` (hocaya sorular),
> `ILERLEME_2026-06-11_hoca_feedback.md` (numune fazı durumu).

---

## 0. Bağlam — iş fırsatı (2026-06-11 hoca görüşmesi)

- Algoritma iyi çalışırsa **uygulamaya çevrilip satılacak**; numune sonucuyla
  hocayı etkilemek = işi doğrudan almak.
- Hocanın vizyonu — **tam otomatik pipeline**:
  1. Mail gelir → parça verileri maillerden/eklerden çekilir
  2. Sistem hangi parçaların öncelikli paketleneceğini belirler
  3. Algoritma parçaları konteyner(ler)e optimize yerleştirir
  4. Sistem **fiyat önerisi** üretir
- Fizibilite kararı: çekirdek algoritma (motor) elimizde; kalan iş araştırma
  değil standart yazılım mühendisliği. Demo-MVP ~1-2 hafta, tam otomasyon
  kademeli ~4-8 hafta.

---

## 0.1 Hoca görüşmesi #2 (2026-06-12) — demo yönü kesinleşti

Sorular (`APP_SORULAR.md`) + bu yol haritası hocaya iletildi; yazılı cevaplar
bekleniyor. Görüşmede netleşenler:

1. **İlk demo = ALGORİTMA demosu.** Vitrin/arayüz değil; nesting'i "en iyi
   şekilde" yapan çekirdek. Faz 1 tanımı buna göre revize edildi (§4).
2. **Çoklu algoritma portföyü (A6 kısmi cevap):** hoca sadece SA değil,
   diğer algoritmaların da kullanılmasını istiyor. Yani motor tek
   metaheuristik değil, bir **algoritma portföyü** olacak (örn. constructive
   GRASP/BLF varyantları, GA, tabu, gerekirse MILP küçük instance'larda) —
   "bu algoritmaları yazılıma öğretmemiz gerekiyor". Hangi ailelerin
   bekleneceği hocanın yazılı cevabıyla kesinleşecek.
3. **Geçmiş nesting'lerden öğrenme:** hocanın geçmişte yaptığı gerçek
   yerleşimler veri olarak alınıp sisteme öğretilebilir (data-driven
   warm-start / imitation: sıralama-poz önceliklerini geçmiş çözümlerden
   çıkarma). Bu aynı zamanda gerçek-veri benchmark seti demek — §5'teki
   R7 (benchmark yok) riskinin en değerli panzehiri.
4. **Agent vizyonu onaylandı ve genişledi:** kullanıcı iki-ajan fikrini (§6)
   sundu; hocanın isteği bütün süreci otomatize eden agent / çoklu-agent
   sistemi — §6 mimarisiyle uyumlu, kapsamı Faz 2 pipeline'ının tamamını
   (mail → parse → önceliklendir → nest → fiyat) agent'lara bölmeye doğru
   genişliyor.
5. **Süper bilgisayar erişimi var (hoca):** "elimizde süper bilgisayarlar
   var, kullanabiliriz" — 1° hatta 0.5° oryantasyon hassasiyetli, çok
   detaylı algoritma tasarımı mümkün. Etkileri: R1 (poz seti) tavanı
   kalkar — eksen-hizalı 24 poz yerine ince-rotasyon araması düşünülebilir;
   multi-start SA / portföy / benchmark koşuları masifçe paralelleşir;
   daha küçük pitch (yüksek çözünürlük voxel) karşılanabilir. Dikkat:
   0.5° hassasiyet kaba kuvvetle taranamaz (arama uzayı kombinatorik
   patlar) — doğru tasarım **kaba-ince (coarse-to-fine)** rotasyon araması
   (§3 madde 7). Erişim detayları + ürün runtime'ında kullanılabilirlik
   netleşmeli (APP_SORULAR A14).

---

## 1. Motor / senaryo ayrımı — bugünkü durum

**Motor (genel, taşınabilir):** voxelization + konservatif yüzey sarması,
yatay dilation + `z_clearance` boşluk şeması, DBLF çözücü (z_top kuralı),
SA çerçevesi (sıra + poz hamleleri, best-so-far garantisi), clearance
doğrulayıcı (`clearance.py`), devoxelization/STL export, render.

**Numune'ye özel (karantinada — `models.py` senaryo verisi):**
`NUMUNE_ORIENTATIONS`, `NUMUNE_ORIENTATIONS_HYBRID`, `NUMUNE_PLATES`,
senaryo default'ları (335 taban, pitch, margin). Uygulamada bu dict'ler
OLMAYACAK; yerlerini §4'teki genel kurallar alacak.

Kanıtlanmış motor kazanımları (taşınır): çift dilation → yatay+z_clearance
(265.0 → 217.5 mm sıçraması bu şemadandı), konservatif grid (0.77 mm ihlal
yakalandı/düzeltildi), SA araması (214.5 → 198.0).

---

## 2. ⚠️ MOTOR OVERFITTING RİSKLERİ — somut liste (bakılacak)

> İlke: bu maddeler "motor kötü" demek değil; "tek veri setinin gölgesinde
> şekillendi, genelliği DOĞRULANMADI" demek. App motorunda her biri ya
> genelleştirilecek ya benchmark'la aklanacak.

| # | Risk | Neden riskli | Yapılacak |
|---|---|---|---|
| R1 | **8-poz master sette Ry rotasyonu yok** (`voxelize.rotation_matrices`) | n5 yatamıyor — "bu instance'ta gerekmedi" diye kabullenildi; başka veri setinde ciddi kalite kaybı yaratır | 24 eksen-hizalı poza (en az Ry eklenerek) genişlet |
| R2 | **SA `t0=3` tek senaryoda kalibre** (2026-06-09; 8 "çok sıcak" bulunmuştu) | Farklı ölçek/parça sayısında delta dağılımı değişir; 3 mm sabiti anlamsızlaşabilir | Adaptif t0: ilk N iterasyon delta istatistiğinden türet |
| R3 | **Enerji ağırlığı `0.1·RMS` bu veride seçildi** (`sa3d._energy`) | Çok geniş tabanlı/yayvan setlerde RMS terimi max-height'ı domine edebilir veya etkisizleşebilir | Benchmark'ta ağırlık taraması; gerekirse normalize RMS |
| R4 | **Seed alışverişi** (5 seed'den en iyi sonucu rapora koyduk) | Tek instance'a şans uydurma; app'te kullanıcıya "tipik" değil "şanslı" kalite vaat eder | Multi-start SA'yı resmî bileşen yap (N seed paralel, en iyi otomatik alınır — bütçesi tanımlı) |
| R5 | **Heightmap modeli overhang altına parça SOKAMAZ** (`bin3d.py` bilinen sınır) | Numune setinde kabul edilebilirdi; konsol/kavisli büyük parçalı setlerde sistematik hacim kaybı | App fazında ölç: benchmark'ta heightmap kaybı > %X ise tam-3D serbest yerleştirme değerlendir |
| R6 | **Pitch/margin/taban default'ları senaryo-eksenli** | 2.5/1.5/1.25 mm değerleri bu parça ölçeğine göre seçildi | Parça ölçeğinden otomatik pitch önerisi (örn. min duvar kalınlığı / hedef çözünürlük oranı) |
| R7 | **Benchmark YOK — asıl kök risk** | Yukarıdakilerin hiçbiri tek veriyle aklanamaz; testler doğruluğu kanıtlıyor, optimizasyon kalitesini kanıtlamıyor | §5 benchmark düzenini kur; "genel" iddiası o zamana dek inanç statüsünde |

---

## 3. Motor geliştirme listesi (genel — app motoru hedefleri)

1. **Ry dahil 24 eksen-hizalı poz** (R1).
2. **Adaptif poz budama** — elle "plakaya dik yasak" yerine kural: *pozun
   tek-başına yüksekliği mevcut en-iyi tavanı aşıyorsa o pozu buda*
   (hibrit içgörüsünün genelleşmiş hâli; dinamik, parça-adı bilmez).
3. **Multi-start SA + adaptif t0** (R2, R4).
4. **Sabit-boyut çoklu-bin sarmalayıcı** — open-dimension (yükseklik
   minimize) yerine konteyner sabit; amaç: konteyner sayısı min / doluluk
   max (APP_SORULAR A2-A3 cevabına göre kesinleşir).
5. **Fiziksel kısıt kancaları** — ağırlık limiti, istif kuralı, this-side-up
   (APP_SORULAR A4); feasibility katmanı baştan tasarlanır, sonradan eklenmez.
6. Performans: SA decode maliyeti ~pitch⁻²; app'te süre vaadi için iterasyon
   bütçesi + erken durdurma (yakınsama eğrisi düzleşince kes).
7. **İnce-rotasyon araması (HPC kozu — §0.1 madde 5):** 0.5-1° hassasiyet
   hedefi kaba kuvvetle değil kaba-ince stratejiyle: önce eksen-hizalı /
   kaba ızgara (örn. 15°) tarama, umut vadeden pozların komşuluğunda lokal
   rafine (1° → 0.5°). Her ince açı = yeniden voxelization — maliyet HPC'de
   paralelleştirilir (açı-başı bağımsız iş). Eğik plaka deneyindeki tilt
   altyapısı (`--orient tilt`) bunun embriyosu; genelleştirilecek.

---

## 4. Uygulama yol haritası — fazlar

### Faz 0 — Numune kapanışı (şimdi)
- Gece koşuları → en iyi sonuç → `compare_numune.py` raporu → hocaya sunum.
- Bu fazda elle kısıt/seed seçimi MEŞRU (tek instance için en iyi sonuç işin
  tanımı); hiçbir şey frenlenmez.

### Faz 1 — Demo-MVP: ALGORİTMA demosu (~1-2 hafta) *(revize 2026-06-12, §0.1)*
- **Odak: nesting kalitesi.** Hoca ilk demoda arayüz değil "en iyi şekilde
  nesting yapan" çekirdeği görmek istiyor.
- **Algoritma portföyü:** SA tek başına değil — en az 1-2 ek aile
  (constructive + ikinci metaheuristik; seçim hocanın A6 cevabıyla
  kesinleşir). Portföy aynı instance'ı koşar, en iyi sonuç raporlanır;
  bu yapı §6 Instance-Tuner menüsünün de altyapısı olur.
- **Geçmiş nesting verisi:** hocadan geçmiş yerleşim örnekleri iste —
  hem benchmark instance'ı (§5, R7) hem öğrenme verisi (§0.1 madde 3).
- Görselleştirme minimumda tutulur (mevcut render yeterli); 3D web önizleme
  + fiyat ekranı Faz 2'ye kayar. Mail YOK, otomasyon YOK.
- Motor: mevcut çekirdek + sabit konteyner boyutu + çoklu-bin sarmalayıcı.

### Faz 2 — Tam otomasyon (~4-8 hafta, kademeli)
- Mail ingest (Gmail API/IMAP) → ek parser (Excel/CSV/STL; serbest metinse
  LLM-parse katmanı).
- Önceliklendirme kuralları (hocadan — APP_SORULAR A10).
- Fiyatlama motoru (A8 netleşti: şirket stratejisi Excel ile gelecek →
  müşteri-özel kural modülü + manuel müdahale; tasarım §6.2).
- Başta **insan-onaylı** (sistem önerir, kullanıcı onaylar) → güven oturunca
  otomatik yanıt maili.

### Faz 3 — İki-ajan mimarisi (MVP+1; §6)

---

## 5. Benchmark + tek-konfig kuralı (overfit panzehiri)

- **Set:** numune + sentetik aileler (rastgele kutular; az-büyük/çok-küçük
  karışımı; yüksek-adetli tekrar parça; ince plaka; uzun çubuk) + literatür
  (kutu-tabanlı konteyner: Bischoff-Ratcliff BR1-BR15; serbest geometri:
  STL havuzu, örn. Thingiverse derlemesi).
- **Tek-konfig kuralı:** aynı parametre setiyle TÜM instance'lar koşulur;
  instance-başı el ayarı YASAK. Skor = ortalama doluluk/yükseklik + süre.
- **Regresyon koşucusu:** `scripts/benchmark.py` (tek komut, tablo basar).
  **Kabul kriteri: benchmark ortalamasını iyileştirmeyen motor değişikliği
  merge edilmez** — numune'yi 2 mm iyileştirip ortalamayı bozan değişiklik RED.
- **Hold-out:** parametre ayarı setin yarısında, doğrulama görülmemiş yarıda.
- **Çıplak-motor satırı:** her instance'ta hiç elle kısıtsız motor skoru ayrı
  raporlanır — elle hile bağımlılığı oluşursa anında görünür.

---

## 5.1 Geçmiş nesting'lerden öğrenme hattı (2026-06-12 — "eğitme"nin gerçek mekaniği)

> "Eğitme" üç ayrı mekanizma; hiçbiri "dosyayı modele yükle" değil:
> (1) makale → KOD (Claude okur, çözücü modülü yazar, benchmark'tan geçer);
> (2) geçmiş nesting → aşağıdaki istatistiksel hat; (3) LLM → few-shot (§6.1).

Geçmiş nesting verisi işleme hattı (6 adım):
1. **Toplama** — her geçmiş iş için girdi (parça listesi/boyut/adet) + çıktı
   (nihai yerleşim: konum + oryantasyon). Format: A11 cevabı.
2. **Sayısallaştırma** — ortak instance formatına (JSON/CSV) çevir;
   fotoğraf/tecrübe ise elle rekonstrüksiyon (muhtemel darboğaz).
3. **İkiye bölme** — benchmark seti (motor vs hocanın gerçek çözümü kıyası)
   + öğrenme seti. Hold-out şart (§5) — öğrendiğin veride sınanmaz.
4. **Örüntü çıkarımı** — düz istatistik: sıralama tercihleri, poz
   tercihleri, bölge/komşuluk alışkanlıkları. Sinir ağı DEĞİL.
5. **Kurala dönüştürme** — sıralama skoru ağırlıkları + poz öncelik listesi
   + yerleşim sezgileri olarak motora yazılır (okunabilir, debug edilebilir).
6. **Doğrulama kapısı** — öğrenilmiş-kurallı motor benchmark'ta çıplak
   motoru geçemiyorsa kural MERGE EDİLMEZ (usta alışkanlığı ≠ optimal).

Darboğaz teknik değil tedarik: A11 (veri + format) ve A12 (makale listesi)
hocadan gelmeden hat kurulamaz.

## 6. İki-ajan mimarisi (Faz 3 — kullanıcı fikri, 2026-06-12)

> Bu gece elle yaptığımız döngünün (probe → analiz → poz kısıtı → tekrar koş
> → kötüyse geri al) otomasyonu. Literatürdeki adı: instance-specific
> algorithm configuration / hyper-heuristic. Çözüm anında instance'a
> özelleşmek ML-overfit DEĞİLDİR; risk yalnız özelleşme motorun kalıcı
> koduna sızarsa doğar — bu mimari onu yapısal olarak yasaklar.

- **Ajan 1 — Analiz + Fiyat:** instance istatistiklerini okur (parça boyut
  dağılımı, adetler, konteyner oranları), yapı analizi raporu + fiyat önerisi
  üretir. LLM, düşük risk, ayrı modül.
- **Ajan 2 — Instance-Tuner:** motorun KODUNU DEĞİŞTİRMEZ; sadece **sabit
  menüden** konfigürasyon önerir: poz kısıtı, sıralama stratejisi,
  seed/iterasyon bütçesi. Yerleşim asla LLM'den çıkmaz, hep motordan.
- **Deterministik hakem:** clearance/ağırlık doğrulaması ve metrik kıyası
  kod'dur, LLM değil.
- **Monoton kabul (güvenlik şartı):** ajan önerisi deney olarak koşar;
  metriği İYİLEŞTİRMEZSE genel motor sonucu kalır. Kötüleşme riski yapısal
  sıfır (SA'nın best-so-far garantisinin ajan katmanına taşınmışı).
- **Kalan gerçek riskler:** (a) koşu maliyeti/süresi — her öneri tam bir SA
  koşusu; iterasyon bütçesi + müşteri süre vaadi buna göre; (b) LLM
  değişkenliği — menü kısıtı + hakem zararsızlaştırır (en kötü: boşa koşu);
  (c) orkestrasyon karmaşıklığı — motor saf kaldığı için test edilebilirlik
  bozulmaz.
- **Efor:** deney sarmalayıcısı ~günler (konfig kapıları hazır: `--orient`,
  `--start`, `--rotations`); LLM katmanı +birkaç gün + prompt iterasyonu.

### 6.1 LLM katmanı tasarım ilkesi — on-prem hazırlığı (2026-06-12)

> Tetikleyici: müşteri profili savunma sanayi (ASELSAN yan kuruluşu, Baykar
> tedarikçisi) — verinin bulut LLM API'sine çıkmasına büyük ihtimalle izin
> YOK (APP_SORULAR A13). Kullanıcı beklentisi de bu yönde.

- **İnce ve değiştirilebilir katman:** tüm LLM çağrıları tek arayüz
  arkasında (`parse(mail) → JSON`, `suggest_config(stats) → menü seçimi`,
  `write_report(result) → metin`). Arka uç: bulut API **veya** lokal
  açık-ağırlıklı model (Qwen/Llama, Ollama/vLLM) — geçiş birkaç günlük iş.
- **Lokal model yeterlilik merdiveni (eğitim SON basamak):**
  1. Görevi daralt — LLM'e sadece dar, yapılandırılmış işler (çıkarım,
     menü seçimi, metin); yerleşim/fiyat hesabı asla LLM'de değil.
  2. Few-shot prompt — 3-5 çözülmüş örnek prompt'a gömülür ("nasıl
     çalışacağını göstermek" budur, ağırlık eğitimi değil).
  3. JSON şema zorlaması + deterministik doğrulayıcı — geçemeyen çıktı
     insana düşer (Faz 2 insan-onaylı dönem zaten bunu kapsıyor).
  4. LoRA fine-tune — ANCAK insan-onaylı dönemde biriken düzeltilmiş
     örnekler (bedava etiketli veri) yeterli hacme ulaşır ve hata oranı
     hâlâ yüksekse. Baştan eğitim YOK (veri yok, gerek yok).
- **Güvenlik ağı zaten mimaride:** Instance-Tuner'da deterministik hakem +
  monoton kabul → zayıf modelin en kötü etkisi boşa koşu; parser'da şema
  doğrulaması → en kötü etki insan-onaya düşen satır. Zayıf LLM kaliteyi
  değil yalnız otomasyon oranını düşürür.
- **Ticari yansıma:** on-prem GPU (kuantize 7-14B yeterli) müşteri
  maliyetidir; "veriniz dışarı çıkmıyor" satış argümanı — on-prem paket
  §7'de daha yüksek bantta fiyatlanır.

---

### 6.2 Fiyatlama motoru — müşteri-özel kural modülü (2026-06-12, hoca şartı)

> A8 cevabının şekli: şirket kendi fiyat stratejisini **Excel** olarak
> verecek; sistem ona göre fiyatlayacak; gerektiğinde **manuel müdahale**
> mümkün olacak. Bu, ayrı bir uygulama modülüdür (Faz 2 kapsamı).

- **İlke: fiyat hesabı DETERMİNİSTİK.** "Öğrenme" = Excel'i normalize kural
  setine çevirmek (parse), ML değil. Aynı girdi → her zaman aynı fiyat;
  her fiyat satır satır izlenebilir ("bu fiyat nereden çıktı" sorusuna
  cevap verilebilir). LLM en fazla dağınık Excel'in İLK çevriminde yardım
  eder; sonuç insan onayından geçip deterministik kurala döner.
- **Dört katman:**
  1. *Strateji ingest* — Excel yükle → parser → normalize kural şeması
     (girdi alanları: hacim/ağırlık/konteyner/mesafe...; çıktı: fiyat).
  2. *Hesap motoru* — nesting sonucu (konteyner sayısı, doluluk, ağırlık)
     + kural seti → fiyat önerisi. Saf kod, birim-testli.
  3. *Manuel müdahale (hoca şartı), iki seviye* — (a) kural düzeyi: yeni
     Excel / arayüzden parametre düzenleme; (b) teklif düzeyi: operatör
     tek teklifin fiyatını göndermeden elle değiştirir. Ayrı yetki + ekran.
  4. *Versiyonlama + iz kaydı* — teklif ↔ strateji versiyonu eşlemesi;
     elle değişiklik logu. Override'lar birikir → operatör örüntüsü
     raporlanabilir (ileride istenirse "öğrenme" verisi bedavaya hazır —
     mail-parse düzeltmeleriyle aynı desen, §6.1 basamak 4).
- **SaaS yan etkisi:** müşteri-başına kural seti = çok-kiracılı SaaS'ın
  zorunlu altyapısı. İlk müşteride doğru tasarlanırsa (konfigürasyon
  olarak, kodda sabit DEĞİL) SaaS geçişinde sıfır ek iş.
- **Bağımlılık:** örnek Excel hocadan/şirketten İSTENECEK — iç yapısı
  (tablo mu formül mü, istisnalar) görülmeden parser yazılmaz (A8).

### 6.3 Kullanıldıkça akıllanan sistem — öğrenme döngüsü (2026-06-12, kullanıcı fikri)

> Üç seviye; zorlukları çok farklı. Seviye 1 zaten kuruldu, Seviye 2 demo
> sonrası ~1-2 hafta, Seviye 3'ün güvenli hâli öz-teşhis (kod değişikliği
> insan kapısından).

- **Seviye 1 — veri birikimi (HAZIR):** Faz 7 override logu (fiyat
  düzeltmeleri), benchmark tabloları (çözücü × instance sonuçları),
  insan-onay düzeltmeleri (mail-parse). Sistem her şeyi not alarak doğuyor.
- **Seviye 2 — birikimden otomatik ayar (orta; demo sonrası):**
  1. Her koşu telemetri bırakır: instance profili + çözücü sonuçları +
     operatör düzeltmeleri.
  2. Periyodik öğrenme işi öneri türetir: algoritma seçim haritası
     ("bu profilde GA kazanıyor"), parametre önerileri.
  3. **Güvenlik kapısı:** aday öneri benchmark'ta mevcut varsayılanla
     yarışır; kazanırsa yeni varsayılan, kaybederse log. Sistem
     KÖTÜLEŞEMEZ (best-so-far garantisinin sistem seviyesi).
  - Bu telemetri aynı zamanda Instance-Tuner ajanının (§6) kanıt tabanı.
- **Seviye 3 — "kendini geliştirme" SINIRI:** sistem kendi KODUNU
  değiştirmez (üretim ürününde riskli + gereksiz). Güvenli karşılık:
  **öz-teşhis** — "şu ailede sistematik zayıfım" raporunu kendisi üretir →
  backlog kendiliğinden oluşur → kod değişikliği insan + benchmark
  kapısından. Ajan yalnız konfigürasyon değiştirir (Instance-Tuner ilkesi).
- **Veri hacmi gerçeği:** öğrenme yakıtı iş hacmi; tek müşteride aylar,
  SaaS çoklu müşteride hızlanır. **Tasarım kararı şimdiden:** öğrenme
  müşteri-başına (per-tenant) tutulur — on-prem kurulumda (A13) veri
  merkezde toplanamaz; birleşik öğrenme ancak izinli müşterilerde.

### 6.3.1 Algoritma seçim modeli — "hangi veri tipine hangi algoritma, ve NEDEN" (2026-06-12, kullanıcı fikri)

> Literatür adı: algorithm selection problem / per-instance algorithm
> portfolios (SATzilla deseni). Kullanıcının tarif ettiği döngü:
> sınıflandır → kazananı eşle → nedenini anla → kendini geliştir.

1. **Instance profilleme (binlerce kombinasyon sorununun cevabı):** veri
   setleri elle kategorilere AYRILMAZ; her instance sayısal **özellik
   vektörüne** indirgenir (parça sayısı, boyut dağılımı istatistikleri,
   en-boy-yükseklik oranları, hacim varyansı, tekrar-parça oranı,
   ince-plaka/uzun-çubuk oranı, teorik doluluk alt sınırı...). Sonsuz
   kombinasyon, ~15-25 boyutlu sürekli uzaya iner — sınıflandırma orada.
2. **Telemetri eşlemesi:** her koşu = (özellik vektörü, algoritma, skor,
   süre) satırı. Kaynak: benchmark + portföy koşuları + müşteri işleri.
3. **Seçim modeli:** özellik → kazanan algoritma tahmini. Model tercihi
   **karar ağacı / random forest** — siyah kutu DEĞİL: dallar okunabilir
   kural üretir ("tekrar-parça oranı > %40 VE parça sayısı > 100 → GA").
   "Neden" sorusunun istatistiksel cevabı (feature importance) bedava.
4. **"Neden"in mekanistik seviyesi (LLM ajanı — Ajan 1 rolüne eklenir):**
   ajan, seçim modelinin kurallarını + koşu geçmişini okuyup hipotez
   raporu yazar ("GA yüksek-adetli tekrarda kazanıyor çünkü sıra
   permütasyon çeşitliliği..."). Hipotez TEST EDİLEBİLİR: sentetik
   üreticiyle hedefli karşı-deney (o özelliği değiştir → kazanan değişiyor
   mu?). Gözlem → hipotez → deney → doğrulanmış kural döngüsü = "kendini
   geliştirme"nin bilimsel ve güvenli hâli.
5. **Veri kıtlığı YOK (kritik avantaj):** seçim modelinin eğitim verisi
   müşteri beklemez — sentetik instance üreticisi (Faz 2.2) sınırsız
   instance üretir; HPC'de (A14) binlerce portföy koşusu = hazır eğitim
   seti. Müşteri verisi geldikçe model rafine edilir.
6. **Güvenlik kapısı aynı:** seçim modeli yanlış algoritma önerirse en
   kötü sonuç "o instance'ta portföyün tamamı koşmamış" olur; şüpheli
   durumda fallback = tam portföy. Yerleşim kalitesi asla model tahminine
   emanet edilmez.

### 6.4 Sipariş havuzu + termin-bazlı çizelgeleme — hoca vizyonunun işleyiş şeması (2026-06-13)

> Hocanın somut tarifi: çok müşteri (örn. Ford 5 gün terminli set, Baykar
> 30 gün terminli set) → sistem öncelikli olanları termine/veriye göre
> KENDİSİ seçer, sıraya koyar, nesting'i yapar, fiyatlar — baştan aşağı
> agent tabanlı otomasyon. Literatür karşılığı: **nesting and scheduling**
> (repo'daki energy-aware SLM nesting+scheduling makalesi tam bu aile —
> hocanın kendi araştırma alanı).

İşleyiş zinciri (her adım bir agent sorumluluğu):
1. **Sipariş alımı** — portal/mail → sipariş havuzu (müşteri, parça listesi,
   termin, öncelik ipuçları). Mail-ingest (A9) bunun giriş kapısı.
2. **Çizelgeleme katmanı (YENİ netleşen):** havuzdan iki karar birden —
   (a) hangi siparişler önce (termin yakınlığı, kapasite, iş büyüklüğü,
   müşteri önceliği = A10'un somut hâli); (b) hangi siparişler aynı
   partiye/batch'e girer. Nesting'den ÖNCE çalışan üretim planlama zekâsı;
   knapsack + makine çizelgeleme melezi.
3. **Nesting motoru** — seçilen partinin yerleşimi (Demo-1 çekirdeği).
4. **Fiyatlama + yanıt** — §6.2 motoru + onay akışı (önce insan-onaylı).
5. **Orkestrasyon** — agent zinciri; deterministik hakem + monoton kabul
   ilkeleri (§6) her katmanda geçerli.

Yeni kritik sorular (APP_SORULAR A15): farklı müşterilerin parçaları aynı
partide KARIŞABİLİR Mİ (savunma sanayinde muhtemelen hayır — batch kararını
kökten değiştirir); kapasite verisi (makine/konteyner sayısı, parti süresi,
vardiya) — termin taahhüdünün fizibilitesi buna bağlı.

Kapsam notu: bu katman Faz 2+ (tam otomasyon) işi; Demo-1'i DEĞİŞTİRMEZ —
Demo-1 motoru bu zincirin 3. halkasının dişlisidir, çizelgeleme üstüne oturur.

### 6.5 Görsel barkod-kimlik katmanı (2026-06-13 — hoca çıtlattı; ayrı modül)

> Mevcut süreç (hoca tarifi): konteynere parçalar karışık girer; içeride/
> pakette barkodlar var; bugün İNSAN, kamera fotoğraflarına bakıp hangi
> parçanın kime ait olduğunu gözle belirliyor. Hoca sorusu: "sistem
> yapabilir mi?" — Cevap: evet, ve iki seviyenin ilki düşük riskli.

- **Seviye 1 — barkod okuma (olgun teknoloji, kolay):** fotoğraf → barkod
  tespit + çözme (ZBar/ZXing sınıfı kütüphaneler; modern CV bile
  gerekmiyor) → sipariş DB eşleşmesi → etiketli görsel + sahiplik listesi.
  Gerçek zorluklar mühendislik detayı: ışık/açı/hasarlı etiket/gömülü
  parça → çok-açılı çekim + çözülemeyeni insana düşüren onay ekranı
  (sistem genelindeki insan-fallback deseniyle aynı).
- **Seviye 2 — barkodsuz görsel parça tanıma (orta-zor, AYRI proje):**
  parça kataloğuyla geometri/siluet eşleme; ilk sürümde VAAT EDİLMEZ.
- **Sinerji (kritik):** konteyneri BİZİM sistem yerleştirdiyse yerleşim
  planı elimizde → görsel katman kimlik tespiti değil DOĞRULAMA yapar
  (plan ↔ barkod çift kaynaklı teyit) + boşaltma/teslim listesi otomatik.
  Karışık gelen yabancı konteynerde salt barkod-okuma modu.
- **A15(a) ipucu:** karışım fiilen YAŞANIYOR ve sahiplik sonradan barkodla
  çözülüyor — yine de savunma sanayi müşterisinde karışım iznini yazılı
  teyit ettir (A15 güncellendi).
- **Ticari konum:** çekirdek ürün DEĞİL; donanımlı (kamera istasyonu) ayrı
  satılabilir ek modül — ürün ailesi genişlemesi, en erken Faz 4.

### 6.6 LLM rol haritası — konsolide (2026-06-13; asistan rolü eklendi)

> Dağınık LLM referanslarının (§6 Ajan 1-2, §6.1 katman ilkesi, §6.3.1
> hipotez ajanı, A9 parser) tek tablosu + YENİ asistan rolü (kullanıcı
> fikri). Hepsi §6.1 gateway ilkesine tabi: ince katman, API ↔ lokal
> takas edilebilir, few-shot, şema zorlaması, insan-fallback.

| # | Rol | Nerede | Görev | Risk | Koruma |
|---|---|---|---|---|---|
| 1 | Parser | Sipariş alımı (Faz 2) | Mail/ek → yapılandırılmış sipariş | Yanlış çıkarım | JSON şema + zorunlu alan hatası + insan onayı |
| 2 | Instance-Tuner | Nesting öncesi (§6 Ajan 2) | Sabit menüden konfig önerisi | Kötü öneri | Deney + monoton kabul; en kötü boşa koşu |
| 3 | Analiz/Hipotez | Öğrenme döngüsü (§6.3.1) | Telemetri yorumu, neden-hipotezi | Yanlış hipotez | Sentetik karşı-deney doğrulamadan kural olamaz |
| 4 | **Asistan (YENİ)** | Kullanıcı arayüzü | Sonuç açıklama, soru-cevap, öneri | Halüsinasyon | 3 kural (aşağıda) |
| 5 | Rapor yazıcı | Teklif/yanıt | Teklif metni, mail taslağı | Düşük | İnsan onayı |

**Asistan 3 kuralı:** (1) TOPRAKLAMA — yalnız sistem çıktılarından konuşur
(yerleşim planı, fiyat dökümü, termin uyarıları, telemetri); kaynak
gösterir. (2) HESAPLAMAZ, AÇIKLAR — her rakam deterministik motorlardan;
asistan dökümü dile çevirir ("fiyatın %40'ı mesafe kademesinden").
(3) ÖNERİR, UYGULAMAZ — aksiyonlar kullanıcı onay kapısından.

**Ortak altyapı (gateway — ŞİMDİ yapılabilir, PLAN_DEMO1 Faz 9):**
sağlayıcı soyutlaması (bulut/lokal/sahte), prompt şablon kayıt defteri
(few-shot yuvalı), yapılandırılmış çıktı zorlaması (şema + retry),
çağrı iz kaydı (maliyet/süre), insan-fallback politikası. Testler sahte
sağlayıcıyla — API anahtarı gerekmez. Roller bu gövdeye prompt + şema
olarak takılır; A13 cevabı (bulut/on-prem) tek konfigürasyon satırı olur.

## 7. Fiyatlama stratejisi (2026-06-12 — pazar verisi: çalışmayan
## algoritma-app'i 20.000 $'a satılmış; rakip az ve pahalı)

> Konum: fiyatla değil **"çalıştığını kanıtlayarak para alma"** ile ayrış —
> alıcı taraf bir kez yanmış, kabul-testli ödeme en güçlü satış kozu.

**Ağrı noktası — hocanın ağzından (2026-06-13):** mevcut sistem manuel,
yavaş, hataya meyilli; bu yüzden **İHALELERE GİREMİYORLAR** — teklif
süresine yetişemedikleri için para kazanma fırsatı kaçıyor. Sonuçları:
- **Değer önerisi netleşti:** "optimizasyon yazılımı" değil, **"teklif
  süresini günlerden dakikalara indiren sistem"** — parça listesi →
  dakikalar içinde yerleşim + kapasite + maliyet + fiyat → ihaleye yetişir.
- **ROI çerçevesi:** kazanılan TEK ihale muhtemelen yıllık sistem
  maliyetini öder → pazarlıkta "maliyet" değil "yatırım" dili.
- **Resmî ürün metriği: time-to-quote** (teklif süresi) — demoda vurgulanır
  ("bu sonuç X dakikada üretildi — mevcut sürecinizde kaç gün?"), kabul
  testlerine ölçülebilir kriter olarak girer.
- **İkinci acı — manuel hata:** deterministik doğrulayıcılar (clearance,
  fiyat dökümü, iz kaydı) insan hatası sınıfını yapısal kapatır; ayrı
  satış cümlesi.
- Hoca gözlemi "bu yazılımı yapan kimse yok" — uçtan uca akış (sipariş →
  çizelge → nesting → fiyat → teklif) için muhtemelen doğru; yine de ilk
  sözleşme öncesi hafif rakip taraması yapılacak (Magics tek modül,
  uçtan-uca değil).

**Fiyat çapası #2 (2026-06-12, hoca):** "Magic" — neredeyse kesin
**Materialise Magics** (AM yazılım standardı) — SADECE nesting modülünü
~20.000 $'a fiyatlıyor. Doğrulanacak: gerçekten Magics mi + kalıcı lisans
mı yıllık mı (SaaS kıyasını değiştirir). Sonuç: bandımız çapayla doğrulandı,
Faz 2 yukarı revize edildi; ilk müşteride çapanın ÜSTÜNE ÇIKMA (sıfır
referans — fiyat alıcı riskini de fiyatlar). Konumlandırma: **"Magics'in
tek modül fiyatına komple otomasyon + kabul-testli ödeme."**

| Kalem | Fiyat | Ödeme koşulu |
|---|---|---|
| Faz 1 Demo/Pilot | 3.000-5.000 $ | Çalışan demo tesliminde |
| Faz 2 Tam pipeline | 15.000-20.000 $ *(revize 2026-06-12 — Magics çapası; eski 12-15k)* | Yazılı kabul testleri geçince (doluluk %, süre, ihlalsizlik ölçülebilir) |
| Bakım+barındırma+destek | 3.000-4.000 $/yıl | İlk yıl Faz 2'ye dahil edilebilir (pazarlık tavizi kartı) |

İlk yıl toplam ~20-28k $ = "rakibin tek nesting modülü parasına çalışan
komple sistem" hikâyesi. SaaS bandı da çapayla güncellendi: 20k kalıcı
lisans ≈ 550-850 $/ay (3 yıl amorti) → 2.+ müşteride **750-1.000 $/ay +
kurulum** üst banttan açılabilir. İlkeler: (1) düşük girişli pilot güven inşa eder, Faz 2'yi
satar; (2) 5-8k'ya komple sistem VERME — kalite sinyali düşer, gelecek
müşteri tavanı iner; (3) tekrarlayan gelir şart (LLM API + sunucu sürekli
maliyet); (4) "çalışıyor" tanımı sözleşmede ölçülebilir olacak.

Netleşmesi gereken üçlü: alıcı tek şirket mi / hoca üzerinden çoklu müşteri
mi (çokluysa SaaS: müşteri başına 500-1.000 $/ay); hocanın paydaşlık /
komisyon beklentisi (ERKEN netleştir); alıcı hacmi (günlük konteyner sayısı
→ destek yükü).

**Güncelleme (2026-06-12, görüşme #2): SaaS + ortaklık sinyali.** Hoca SaaS
yörüngesini KENDİSİ teyit etti ("sonrasında SaaS yapmamızı planlıyor") ve
ifadesi ortak iş okuması veriyor — kendine rol biçiyor (doğal: müşteri
bağlantıları + alan bilgisi ondan, teknoloji kullanıcıdan). Üçlünün ilk
maddesi böylece cevaplandı (çoklu müşteri + SaaS), ikincisi "beklenti var
mı?"dan "yapı ne olacak?"a evrildi. **Zamanlama:** ortaklık pazarlığı demo
BAŞARISINDAN SONRA, ilk müşteri sözleşmesinden ÖNCE açılır (şimdi erken).
O masada netleşecek üç soru:
1. **Yapı:** gelir paylaşımı/komisyon mu, şirkette hisse mi, danışmanlık mı?
2. **IP:** kod kullanıcının — netleşmeden hiçbir yapıya girilmez. Dikkat:
   iş IE 488 ders projesi zemininden doğuyor; üniversitenin ders/araştırma
   çıktısı IP politikası kontrol edilmeli; motor kodunun ders tesliminden
   ayrışması (motor/senaryo karantina ayrımı zaten var) ticarileşme öncesi
   tamamlanmalı.
3. **Roller + destek yükü:** satış/müşteri ilişkisi hoca, ürün/geliştirme
   kullanıcı — ama SaaS'ta sürekli destek (sunucu, hata, telefon) kimin
   maliyeti?
Taktik not: hoca paydaş olursa fiyat müzakeresinde satıcı tarafında oturur
(Magics çapasını kendisinin getirmesi bu yönde işaret) — §7 riski azaldı.

**Güncelleme (2026-06-12):** Hoca çoklu müşteri bağlantısı + sonrasında
şirketleşme önerdi; bağlantıları ciddi (ASELSAN yan kuruluşlarından birinin
YK başkanı; Baykar'a parça satan firma). Yani yörünge: ilk müşteri faz-bazlı
özel proje fiyatı (yukarıdaki tablo) → memnuniyet referansıyla 2.+ müşteride
SaaS'a geçiş (kurulum ücreti 2-4k $ + 500-1.000 $/ay) → hacim oluşursa
şirketleşme. İlk müşteriyi referans-vitrini olarak fiyatla (gerekirse alt
banttan), sözleşmeye logo/referans kullanım izni eklet. Kullanıcı yaklaşımı
doğru: önce ürün + demo + tek müşteri memnuniyeti, hayal sonra.

## 8. Hocadan alınacak bilgiler (teknik olmayan kritik bağımlılıklar)

`APP_SORULAR.md` A bölümü — özellikle yeni eklenenler:
- **A8 — fiyat formülü** (girdiler: hacim/ağırlık/konteyner sayısı/mesafe?)
- **A9 — mail/ek formatları** (sabit şablon mu, serbest metin mi?)
- **A10 — önceliklendirme kuralları** (termin/müşteri/değer?)
- A4 — fiziksel kısıtlar (ağırlık, istif, this-side-up) → motor feasibility
  katmanını belirler, sonradan eklenmesi pahalı.

Cevaplar geldikçe `APP_SORULAR.md` C tablosuna işlenecek.

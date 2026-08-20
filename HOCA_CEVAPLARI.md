# HOCA CEVAPLARI VE VERİLERİ — Kalıcı Kayıt

> Hocadan gelen TÜM cevaplar, kısıtlar, referans sayıları ve veri setleri tek yerde.
> Repo = tek doğruluk kaynağı; her yeni hoca cevabı buraya tarihiyle eklenir, silinmez.
> (Oluşturma: 2026-07-07, Eren talebi: "bütün cevapları kalıcı bir yere kaydet".)

## 1. KESİN KOŞULLAR (güncel — kıyas zemini)

| Kısıt | Değer | Kaynak (tarih) |
|---|---|---|
| Yapı platformu | **335 × 335 × 600 mm** (X×Y×Z) | 2026-07-06 mail |
| Kenar payı | 5 mm (→ kullanılabilir 325×325; ama Magics kıyası 335 taban + NO-GO ile) | 2026-07-06 mail |
| Yasak bölge (NO-GO) | x[185.1, 215.2] × y[0.2, 45.3], TAM yükseklik kolonu; STL: `data/mail_stl/deneme5/_nogo_area.stl` | 2026-07-07 mail (tüm setlerde geçerli) |
| Parça arası boşluk | doluluğa göre **1-2 mm** (yoğun=2; sebep ısı-birikimi/kaynaşma) | 2026-07-06 mail; ilk 1mm şartı 2026-06-11 |
| Rotasyon | **SERBEST** (yalnız 90° değil — açılı/sürekli rotasyon meşru ve Magics'in ana silahı) | 2026-07-06 + 2026-07-07 teyit |
| İç-içe geçme | **İZİNLİ** (halka içine çubuk); asıl kısıt üretim sonrası **AYRILABİLİRLİK** | 2026-07-06 mail |
| Yükseklik sınırı | 600 mm (pratikte bağlamıyor) | 2026-07-06 mail |

**Kritik ayrım (hoca onaylı mimari):** üretilebilirlik = (a) yüzey boşluğu ≥1mm
(kaynaşma) + (b) ayrılabilirlik — İKİ AYRI kısıt; 1mm gerekli ama yeterli değil
(zincir baklaları ≥1mm olup ayrılamaz olabilir).

**AÇIK SORULAR (hocaya sorulacak/soruldu):**
- Magics sonuçları kendi 1-2mm boşluk kuralıyla mı ölçülüyor? (clearance paritesi)
- Ayrılabilirlik kriteri tam nedir: düz çekme mi, döndürerek çıkarma da kabul mü?
  *(cevaplandı 2026-07-09: b+c kabul)*
- Plan1 baseplate'i Magics plakaya açıyla mı basıyor? (110.41'in anatomisi)
  *(cevaplandı 2026-08-03: büyük taban parçası YATAY yerleştiriliyor; tamamen
  insan yerleşimi; ekran görüntüleri mailde — no-go uyumu görüntüden
  doğrulanacak, bizim geometrik kanıt "düz poz no-go'lu plakaya sığmaz" diyordu)*
- Magics yerleşim STL'leri / ekran görüntüleri paylaşılabilir mi? (dizilim istihbaratı)
  *(cevaplandı 2026-07-09: STL'ler mevcut değil)*
- **Manuel yerleşimlerde parça-arası boşluk kaç mm — özellikle Deneme5 209'un
  koşulu?** *(2026-07-14'ten beri CEVAPSIZ; 2026-07-22 S1'de plan7 için "2mm ile
  devam" mutabakatı alındı, eski setler için hâlâ açık)*
- **KAPALI KAVİTE / TOZ HAPSİ (2026-07-25 eklendi):** İç-içe yerleşimde tamamen
  kapalı boşluk oluşursa (tozun hiçbir açıklıktan tahliye edilemeyeceği hacim)
  kabul kriteriniz nedir — yasak mı, tolere edilebilir mi? Eşik var mı (hacim /
  minimum açıklık)? *(Motora kapalı-kavite denetimi ekleniyor — DENETIM 07-03
  #21; denetimin legal tanımına bağlanması bu cevaba bakıyor.)*
  *(cevaplandı 2026-08-03: "zincir olmadığı sürece sorun değil"; eşik YOK;
  sıkışan toz ufak müdahaleyle açılıyor → cavity denetimi TELEMETRİ-ONLY kalır,
  legal karara BAĞLANMAZ; detay FSM ziyaretinde)*

## 2. MAGICS REFERANS SAYILARI (hoca ölçümü; hepsi 335×335 + NO-GO DAHİL)

| Set | Magics (mm) | Kaynak |
|---|---|---|
| Plan1 | **110.41** | 2026-07-07 mail |
| Plan2 | **492.39** | 2026-07-03 dönemi (ilk kıyas noktası) |
| Plan3 | **593** | 2026-07-07 gece (Eren aktarımı) |
| Deneme4 | **250.24** | 2026-07-03 mail |
| Deneme5 | **209** | 2026-07-07 mail |

**ÖNEMLİ (2026-07-07 cevap 7):** Hocanın TÜM plan+deneme sonuçları NO-GO dahil
yapılmış → bizim tüm kıyas koşularımız da 335+NO-GO olmalı. (Deneme4'ün eski
264 sonucu 325+no-go'suzdu → GEÇERSİZ kıyas, 2026-07-07'de 288.5 ile yeniden koşuldu.)

## 3. KRONOLOJİK CEVAP/VERİ GÜNLÜĞÜ

### 2026-06-11 — Boşluk şartı (ilk)
Parçalar arası **en az 1 mm** boşluk istendi (0.084 mm'lik yerleşimler ihlaldi;
clearance düzeltme işinin kaynağı).

### 2026-07-03 — Deneme4 seti + Magics 250.24
- İlk dış-müşteri seti (FSM): ince-cidarlı kabuk ailesi, 12 tip / 588 parça
  (`data/mail_stl/mail_stl_AD786DF3`). Magics referansı 250.24 mm.
- **Kanıtlı tuzak:** `"-25pcs"` dosya adı YANLIŞTI (gerçek adet 26; mail+checksum
  doğruladı) → STL/ad kaynaklı adet asla sessiz kabul edilmez.
- WhatsApp veri talebimize karşılık: veriler "mail ekinde tek ZIP + adet listesi"
  formatında gelmeye başladı (otomasyon canlı testinin zemini).

### 2026-07-06 (gündüz maili) — 3 kritik cevap
1. **Platform 335×335×600, kenar payı 5mm** (auto-plaka 301.6 varsayımımız yanlıştı
   → o güne kadarki sayılarımız kötümserdi).
2. **Boşluk 1-2 mm** (doluluğa göre; clearance işimizi doğruladı).
3. **Serbest rotasyon + iç-içe İZİNLİ; asıl kısıt AYRILABİLİRLİK** (mimarimizdeki
   clearance ∥ F2 ayrımını doğruladı).

### 2026-07-06 (akşam, WhatsApp notu 23:25) — 2 ürün isteği
1. **"Her seferinde farklı dizmesi lazım algoritmanın"** → alternatif dizilim
   üretimi (seed rotasyonu / buton; eval determinizmi seed loglanarak korunur).
2. **"STL dosyasının içerisinde yazabiliyor adet sayıları"** → İKİ YÖNLÜ:
   GİRİŞ (bazı müşteriler adedi maile hiç yazmıyor, STL adına/içine yazıyor →
   gözcü STL-içi adet okumalı) + ÇIKIŞ (bizim STL'imiz adlandırılmış-solid yazmalı).
   YAPILACAKLAR #2 ve #4'te spec'li.

### 2026-07-07 (mail 14:17) — 7 cevap (kıyas zemini tamamlandı)
1. Plan1/2/3 plakası: hepsi **335×335**.
2. Deneme5: 335×335 ✓.
3. **Deneme5 Magics = 209 mm.**
4. **Plan1 Magics = 110.41 mm.**
5. **ROTASYON SERBEST** (kesin teyit — A1 yönü resmî gerekçeli).
6. **STL-içi adet gerçek örneği ekte:** `YP2425-Arm-2mm-2Adet.STL` — parça adı
   sonuna "-2Adet" yazılıyor. DİKKAT: dosya adı `-2Adet` AMA binary header solid
   adı `-4Adet` (ÇELİŞKİLİ!) → parser test fikstürü oldu (çelişkide operatör onayı).
7. **Tüm setler NO-GO dahil** (yasak bölge: deneme5 `_nogo_area.stl`) →
   tüm kıyaslar 335+NO-GO'da yapılır.

### 2026-07-07 — Deneme5 seti
12 tip / 352 parça (PO siparişleri + bending test parçaları),
`data/mail_stl/deneme5/` + `_adet_listesi.txt` + `_nogo_area.stl`.
Registry'de DOĞUŞTAN held-out.

## 4. HOCADAN GELEN VERİ SETLERİ ENVANTERİ

| Set | İçerik | Konum | Registry rolü |
|---|---|---|---|
| numune | ilk örnek set | (2026-05) | held-out |
| plan1 | 112 parça, mixed (baseplate 330.2mm dahil) | `VERILER/Plan1` yolu, `scripts/c3_generality.py` DATASETS | dev |
| plan2 | 226 parça, mixed/cavity-zengin | DATASETS | dev |
| plan3 | 109 parça, çubuk-ağır | DATASETS | dev |
| deneme4 | 588 parça, ince-cidar kabuk (62+126 ASY çan + 2 ROBT plaka + düğmeler) | `data/mail_stl/mail_stl_AD786DF3` | dev |
| deneme5 | 352 parça, 12 tip (PO + bending testleri) | `data/mail_stl/deneme5` | held-out |
| YP2425-Arm | STL-içi adet ÖRNEĞİ (tek dosya, çelişkili ad/header) | repo kökü `YP2425-Arm-2mm-2Adet.STL` + test fikstürü | (fikstür) |

## 5. HOCA GERİ BİLDİRİM TEMALARI (ürün yönü)

- Kıyas ölçütü her zaman **Magics yüksekliği** (doluluk yüzdesi değil).
- Operatör iş akışı önemli: alternatif dizilimler + parça takibi (STL-içi adlar).
- Veri kanalı: mail eki ZIP + adet listesi (gözcü otomasyonunun canlı test zemini).
- SaaS/ortaklık sinyali var (iş fırsatı bağlamı — APP_YOL_HARITASI).

---

## 2026-07-09 — 8 SORULUK MAİLİN CEVAPLARI (OYUN DEĞİŞTİREN SET)

1. **AYRILABİLİRLİK KRİTERİ: (b) VE (c) KABUL.** "Parçalar üstten aşağıya
   kademeli çıkarılıyor; operatöre bağlı ve manuel — kenara çekip veya
   döndürerek olabiliyor." → +Z-tek kilit metriğimiz FAZLA SERTTİ; yana
   kaydırma + döndürme kabul. **NFV kalite modu YEŞİL IŞIK.**
2. **Yerleşim dosyaları:** STL'ler mevcut değil (düzeltme 2026-07-09 akşam:
   Plan1 dahil hiçbiri gelmedi/gelemiyor); elimizdeki tek anatomi kaynağı
   baseplate FOTOĞRAFI (`Plan 1Base plate.jpg` — analizi STRATEJI/06 §2).
3. **Plan1 baseplate: DÜZ YATAK olarak yerleştiriliyor** (resim ekte) ve
   **"yasak bölgeye çok hafif girişler genelde sorun yaratmıyor"** →
   no-go YUMUŞAK kısıt (hafif ihlal tolere edilir). 110.41'in sırrı bu.
4. **YASAK BÖLGE DÜZELTMESİ: x 152,5–185,5 / y 0,2–45 mm** (bizim
   kullandığımız x 185,1–215,2 YANLIŞTI — tüm 2026-07-08/09 ölçümleri eski
   koordinatla). Tam yükseklik. **Kenar payı: üretim/geometriye bağlı 5'er mm
   boşluk bırakma durumları olabiliyor** (koşullu — güvenli taraf 5mm pay).
5. **BOŞLUK: 2 mm daha güvenli; TÜM boşluklar için geçerli** (yatay+dikey).
   (Bizim tüm ölçümler ≥1mm ile — 2mm'ye geçişte sayılar yükselir.)
6. **KIYAS BOMBASI: gönderilen yükseklikler MAGICS DEĞİL, MANUEL yerleşim!**
   "Veriler manuel hazırlanmıştır... yüksekliğe/adede/geometriye göre SAATLER
   sürebilmektedir." → 593/492/250/209/110.41 = deneyimli operatör, saatlerce.
   Bizim dakikalar mertebesi başlı başına değer önerisi.
7. **Alternatif dizilim teyit + YENİ KISIT:** bazı parçalar yalnız dikey veya
   yatay üretilir (silindir yatayda ELİPTİK çıkar) → parça-bazlı oryantasyon
   kısıtı özelliği gerekiyor (voxelize allowed_orientations altyapısı mevcut).
8. **DENEME6 GELDİ (yeni veri, ek): referans yükseklik 86,32 mm (manuel).**
   → A3 gereği HELD-OUT doğar; tuning'e sokulmayacak.
9. (Tekrar) "Yasak bölgeye Plan1'deki baseplate örneği gibi çok ufak girişler
   kabul edilebilir."

**Doğrudan sonuçlar:** kilit metriği yeniden tanımlanacak (≥5-yön söküm; c için
rotasyon-söküm) · NOGO sabiti tüm scriptlerde düzeltilecek · 2mm clearance
politika kararı (tablo yeniden ölçülür) · soft no-go modellemesi (hafif giriş
penaltılı/toleranslı) · Deneme6 held-out kaydı · Plan1 manuel-yerleşim STL
anatomi analizi.


---

## 2026-07-14 — Hoca cevabı (HOCA_PAKETI_2026-07-14 mailine; "çalışmaların çok iyi yönde devam ediyor")

**Bağlam:** İki manuel-altı sonuç (Deneme4 229.3 −%8.4, Plan3 577.6 −%2.6) +
söküm planı görseli + 4 soru gönderilmişti (Mert abi üzerinden).

1. **Söküm toleransı (soru 2 cevabı):** "Bazı parçaların çıkartılmasında
   zorlansak bile bu İHMAL EDİLEBİLECEK kadar az seviyede. Parçaların
   birbiriyle yapışması (yeterli mesafe bırakmama) ve birbirinin içine geçip
   ÇIKARILAMAYAN durumlar haricinde hepsi kolay çıkabilmektedir. **Tamamı
   kolay söküm seçeneği daha yakın geliyor.**"
   → SONUÇLAR: (a) UI çift-aday özelliğinde DEFAULT = tamamı-kolay-söküm
   (bizim tasarımla birebir örtüştü); riskli-alçak aday opsiyonel kalır.
   (b) Az sayıda zor-söküm TOLERE edilebilir → K-46 tarzı sertifikalı
   çözümler meşru. (c) "Yapışma = yetersiz mesafe" → 2mm clearance kuralının
   dolaylı teyidi.
2. **Deneme4 229.3 kabulü (soru 3 cevabı):** **"Herhangi bir sorun
   görünmemektedir."** → d4 REKORU (231.5 voxel / 229.3 mesh, söküm-planlı
   (b+c) legalite) HOCA-ONAYLI. Projenin ilk resmî manuel-altı kabulü.
3. **Yeni veri (soru 4 cevabı):** "Yeni verileri en kısa zamanda
   göndereceğim." → kör-test seti geliyor; geldiğinde A3 gereği HELD-OUT
   doğar (registry kaydı + tuning'e girmez).

**CEVAPSIZ KALAN: Soru 1 (manuel yerleşimlerde parça-arası boşluk kaç mm —
özellikle Deneme5 209'un koşulu).** Kıyas-adaleti için kritik; bir sonraki
temasta nazikçe tekrar sorulmalı.

**Doğrudan işler:** UI çift-aday default'u kesinleşti (tamamı-kolay) ·
d4 kabul notu YONTEM/RESUME'ye · yeni veri gelince held-out protokolü hazır
(gözcü + registry + kxx_telemetri kablosu bekliyor).

---

## 2026-07-20 — Plan7 verisi geldi ("verileri hazırlayabildiniz mi?" sorusuna cevap)

**Bağlam:** Eren 2026-07-20 13:45 "verileri hazırlayabildiniz mi?" diye sordu;
Mert Bey aynı gün 16:18'de cevapladı (thread: "RE: Plan1 ve Plan 3 Nesting",
Gmail mesaj id `19f7fad84ee93dbb`).

> "Merhaba Eren, Plan7'yi ekte paylaşıyorum. **Üretim yüksekliği 595 mm'dir.**
> Plan7. İyi çalışmalar, Saygılarımla."

**Doğrudan sonuçlar:**
- **Plan7 = yeni gerçek sipariş → A3/B1 gereği HELD-OUT doğar** (01_VERI §2.1
  registry'ye kaydedildi). Tuning'e GİRMEZ; ilk iş kör-test (üretim koşusu).
- Referans: **595 mm üretim yüksekliği** — hazırlanış yöntemi (manuel mi,
  Magics mi) ve boşluk/kenar koşulları MAİLDE YOK → **A10 şerhli** kıyas;
  soru listesine eklendi (2026-07-14'ten beri cevapsız clearance sorusuyla
  birlikte sorulmalı).
- Veri kanalı notu: ek + Google Drive paylaşım maili birlikte geldi
  (büyük dosya Drive üzerinden olabilir).
- 2026-07-20 canlı test: Plan7 maili gözcü/otonom hattına işletildi
  (mail→parse→nesting uçtan uca; H10 canlı doğrulaması).

---

## 2026-07-22 — 5 sorunun cevabı (Plan7 sonuç maili dönüşü)

**Bağlam:** Eren'in 2026-07-21/22 sonuç+soru mailine (kör-test tablosu +
söküm planı tanıtımı + 5 soru) Mert Bey'in cevabı. Ayrıca: "Elinize sağlık,
gayet güzel gelişmeler var" + **söküm planı ve HER İKİ yerleşimin (Plan7 +
Deneme6) STL dosyalarını istedi** ("cihazın programında kontrol etmek
verimli olur").

**S1 — Plan7 referans koşulları:**
> "Magics ile manuel hazırlandı. Yerleşim planı firmadan direkt iletildiği
> için boşluk değerini bilememekteyim. Ancak **2 mm olarak devam
> edebiliriz**. **Yasak bölge dikkate alınmıştır.**"
- Sonuç: 595 referansı Magics-manuel karışık kaynak; boşluk bilinmiyor ama
  **2 mm üzerinde ANLAŞILDI** + no-go dahil → A10 şerhi büyük ölçüde
  kalkar ("boşluk firmaca bilinmiyor, 2mm mutabakatlı" notuyla kıyas
  kesinleşir). Bizim 488,4 zaten 2mm+no-go ile koşuldu = adil kıyas.

**S2 — "Konumu değişmeyecek" SEMANTİĞİ (KRİTİK):**
> "STL verilerini Magics yazılımdan çekmekteyim. Konumu değişmeyecek
> ibaresi aslında parçanın **açısıyla (duruş açısı/yönelimi)** ilgili bir
> durum, yani **yatay imal edilmesi** talep edilmektedir. Ancak imalat
> içinde **herhangi bir yükseklikte veya X-Y koordinatında olabilir**."
- Sonuç: "konumu değişmeyecek" = KONUM DEĞİL **ORYANTASYON KİLİDİ**
  (STL'in Magics'ten geldiği duruş korunur; z/x-y tamamen serbest).
  → not→kısıt hattında bu ibare `orientation_lock {"yon": "durus_koru"}`
  (geldiği duruşu koruyan poz kümesi {0,1,4,5}; Rz düzlem-içi dönüş
  serbest — duruş açısını değiştirmez). pinned_position şeması yedekte
  kalır ama bilinen gerçek ihtiyaç ORYANTASYON. K-56f pinleme motor-içi
  optimizasyon aracı olarak ayrı yaşar.

**S3 — Plan7 yön kısıtları:**
> "Bu plan için herhangi bir kısıtımız bulunmamaktadır. Konumu
> değişmeyecek parça dışında serbest modda devam edilebilir."
- Sonuç: Plan7 yeniden-çözüm görevi: YALNIZ 288101642-a2 (6 kopya)
  duruş-kilitli, kalan 339 parça serbest. (Held-out bakışı registry'ye
  loglanacak; koşu sakin-makine seansında.)

**S4 — Yeni veri / aile talebi:**
> "Yeni veriler geldikçe iletmeye çalışıyorum. Ancak **eski üretim
> verilerinden de belirttiğiniz şekilde parçalar bulup yeni planlar
> iletmeye çalışacağım.**"
- Sonuç: eksik-aile listesi (kabuk/boru/çubuk/dev-parça/yüksek-adet)
  kabul gördü; arşivden aile-hedefli plan derleyecek.

**S5 — Gönderim biçimi:**
> "Dosya boyutları büyük olabildiği için Google Drive linki ile
> iletiyorum. Firmalardan drive, ZIP veya .stl dosyaları tek tek eklenerek
> bir maille iletilebiliyor. **İsterseniz ikimizin kullanabileceği bir
> Drive klasörü açıp** dosyaları oraya da yükleyebiliriz. İkisi de uygun."
- Sonuç: birincil kanal Drive linki (mevcut share-link ingest doğru
  yatırımmış); ORTAK KLASÖR önerisi masada — kabul edilirse tek-kanal
  otomasyon (klasör-izleme) mümkün. Karar Eren'de.

**Doğrudan işler:** (1) Plan7+Deneme6 STL + söküm planı paketi hocaya
gönderilecek; (2) Plan7, a2-duruş-kilidiyle yeniden çözülecek (üretim
kablosu K-56g hazır — orientation_overrides); (3) not→kısıt hattında
"durus_koru" çevirisi + prompt/korpus güncellemesi; (4) Drive ortak
klasör kararı.

## 2026-08-03 — 7-soruluk paket mailinin cevabı + FSM DAVETİ

**Bağlam:** Eren'in hoca-paketi maili (`HOCA_MAIL_2026-07-26_GOVDE.txt`;
Drive paket + 7 soru) sonrası Mert Bey'in cevabı (Eren aktarımı 2026-08-03;
yazışma bu repo'nun izlediği Gmail dışında). "Detaylı çalışman için çok
teşekkür ederiz." **Mailin 3 ekran görüntüsü eki 2026-08-03'te alındı →
`Veriler/hoca_ekleri_2026-08-03/`: (a) müşteri mail-notu örneği (kupon
oryantasyon talebi), (b) Plan1 manuel yerleşim üstten, (c) Plan1 manuel
yerleşim Magics 3D (Information panelinde 110,41 görünüyor).**

**🏫 FSM DAVETİ (yeni, mailin ana isteği):**
> "Müsait olduğun bir vakitte FSM'ye gelmen mümkün olur mu? Şu ana kadar
> yaşanmadı ama bazen bazı soruların tam cevabını aktaramamış olmanın
> endişesini yaşıyorum."
- Sonuç: yüz yüze görüşme talebi; kapalı-boşluk/toz konusunu yerinde
  göstermek istiyor. Ziyaret planı EREN'DE.

**C1 — Kapalı boşluk / toz tahliyesi (bizim S2):**
> "FSM'ye gelmenizi bu yüzden tavsiye ederim. **Parçalar arasında zincir
> olmadığı sürece bu durumun sorun olacağını düşünmemekteyim.** Bazen
> tozlar belli bir bölgede çok sıkışabiliyor. Ancak **ufak müdahalelerle
> bu kısımlar açılabiliyor.**"
- Sonuç: kapalı kavite YASAK DEĞİL, eşik YOK; "zincir" (interlok) zaten
  ayrılabilirlik kısıtımız. → `cavity.py` denetimi TELEMETRİ-ONLY kalır,
  legal karara bağlanmaz (DENETIM #21 kapanış kararı). Detay FSM'de.

**C2 — Yoğunluk / termal sınır (bizim S3):**
> "Çok kritik bir nokta bence. Çok yoğun bir üretim olması durumunda
> vermiş olduğumuz boşluklar aslında bizi kurtarmış oluyor. Onun
> haricinde cihaz arayüzünden tozun dozajını artırıp eksik toz serilmesine
> engel olmaktayız. **Yazılımsal olarak şu an için bir eklemeye gerek
> yoktur.**"
- Sonuç: bölgesel-yoğunluk/doluluk kuralı EKLENMEYECEK; mevcut 2mm
  boşluk kuralı yeterli sayılıyor; toz dozajı cihaz tarafında çözülüyor.

**C3 — Parçaya özel gereksinimlerin geliş biçimi (bizim S4; not→kısıt hattı):**
> "Bu biraz farklı şekilde olmaktadır. Bazen müşteri parçanın yönünü
> **teknik resimde (farklı bir .pdf dosyası içinde)** belirtmekle birlikte
> bazen de **mailde** yazmaktadır. En farklı durum ise **parça üzerinden**
> bu bilginin alınmasıdır. Örneğin **288101642-a2 parçasının üzerinde XY
> olarak bir label** bulunmaktadır. Bu parçanın **XY yönünde üretilmesi**
> gerekliliğini ortaya koymaktadır. Maille gelen talebe ait bir ekran
> görüntüsü ekte paylaşılmıştır."
- Sonuç: kısıt kaynağı 3 KANAL — (1) mail metni [mevcut not→kısıt hattı
  doğru hedef], (2) teknik resim PDF'i [yeni kaynak: PDF'ten yön kısıtı
  çıkarımı — backlog], (3) parça STL'i üzerinde kabartma label ("XY" =
  XY düzleminde/yatay üretim = duruş kısıtı) [en zor kanal; uzak backlog].
  a2'nin "XY" label'ı S2 (07-22) "yatay imal" cevabıyla TUTARLI.
- **GERÇEK ÖRNEK NOT ALINDI (ek a; kısıt korpusu için altın):** test kuponu
  siparişi — "Her bir test tipi için 3 farklı oryantasyonda kupon: çekme /
  basma / yorulma testleri için **15 yatay + 15 dikey + 15 transverse (45°)**
  = 45'er, toplam 135; **yatay ve 45° kuponların recoater ve gaz akış yönüne
  DİK durması önemli**; mümkünse tek seferde üretim." → mevcut kısıt
  enum'unun ÖTESİNDE 4 yeni kısıt türü: (1) aynı tipin kopyalarını
  oryantasyon gruplarına BÖLME (15/15/15), (2) 45° ara açı, (3) makine
  eksenine göre hizalama (recoater/gaz-akış yönü — plaka ekseni semantiği
  motora hiç girmedi), (4) tek-plaka tercihi. Korpus + prompt v2 backlog'u.

**C4 — Plan1 110,41'in sırrı (bizim S6):**
> "**Büyük taban parçası yatay olarak yerleştirilmektedir.** Yerleşime ait
> ekran görüntüleri ekte paylaşılmıştır. Aslında bu **tamamen insan
> yerleşimidir.** Bizim de hedefimiz min yüksekliği tutturmaktır. Çok
> fazla kural olmamakla birlikte genel olarak **büyük parçaların ilk
> yerleştirilmesi ve sonrasında diğer parçaların bunun etrafında
> toplanması**dır. Ancak %100 geçerli bir kural değildir."
- Sonuç: 110,41 Magics-otomatik değil İNSAN yerleşimi; sezgisel kural
  "büyük önce, küçükler etrafına".
- **ÇELİŞKİ ÇÖZÜLDÜ (2026-08-03, ekran görüntüleri geldi —
  `Veriler/hoca_ekleri_2026-08-03/`):** Magics 3D görüntüsünde Information
  paneli **110,41 mm / 330,2×328,1 / 112 parça** — referansın birincil
  kanıtı elimizde. Baseplate gerçekten DÜZ (yatay) AMA parçaların
  **ÜSTÜNDE kanopi** gibi; dik duran parçalar ve no-go kolonu çerçevenin
  **DELİKLERİNDEN** geçiyor. Bizim K-56 kapısı parçayı dolu bbox saydığı
  için "düz imkânsız" demişti — delikli parçada YANLIŞ-POZİTİF. Yeni aday
  **K-62** (YONTEM §5): gerçek-geometri no-go fizibilitesi + düz-kanopi
  yerleşimi; beklenti plan1 110-130 bandı.

**C5 — Elle yerleşim süresi (bizim S7):**
> "Bu yerleşim firmadan geldiği için açıkçası tam bilmiyorum. Kendilerini
> aradım ama ulaşamadım. Ulaştığımda bu konu ile ilgili net bilgi
> vereceğim. Hatta **onların uyguladıkları parametreleri de almaya
> çalışacağım.** Ancak tecrübelerime dayanarak; bir insanın bu işi **1
> günden fazla sürede** yapacağını düşünüyorum. Bu 1 gün sonucunda ise
> sizin ulaştığınız yüksekliklerden **oldukça fazla bir yükseklikte**
> yerleşim yapılacağını tahmin ediyorum."
- Sonuç: plan7 595 referansı firma işi; kesin süre + firma parametreleri
  hocadan GELECEK. Değer önerisi güçlendi: insan >1 gün + daha yüksek
  sonuç vs. motor ~103dk + 488,4 (−%17,9).

**C6 — Sipariş dosyalarının geliş kanalı (bizim S5; mail-ingest tasarımı):**
> "Ağırlıklı olarak; **ZIP içinde (teknik resim, excelde adet bilgisi ve
> parça verileri)** veya **maile ek olarak teknik resim ve parça verileri,
> mail içeriğinde adet bilgileri** — 2 farklı şekilde. Daha nadir olarak;
> **Drive linki veya WeTransfer** ile. Müşteri öncelikle maili göndermekte
> (adet bilgili, malzeme vs.) sonra WeTransfer bilgilerini iletmektedir."
- Sonuç: mevcut mail-ingest yatırımı (ZIP çıkarıcı + kardeş-xlsx adet
  tamamlama + gövdeden adet) TAM İSABET; Drive share-link ingest de var.
  Eksik: **WeTransfer link indirme otomasyonu** (nadir kanal — backlog) +
  "önce mail, sonra link" iki-mail eşleştirme senaryosu (pending_orders
  `share_link_dosya_bekleniyor` durumu bu deseni zaten karşılıyor).

**CEVAPSIZ KALAN:** bizim S1 (eski setlerin — özellikle Deneme5 209 —
manuel boşluk değeri) bu mailde de yanıtsız; açık-sorular listesinde kalır.

**Doğrudan işler:** (1) FSM ziyaret planı [EREN]; (2) ~~ekleri kaydet~~ ✅
2026-08-03 `Veriler/hoca_ekleri_2026-08-03/`; (3) ~~plan1 analizi~~ ✅ →
**K-62 adayı YONTEM §5'te** (gerçek-geometri no-go kapısı + düz-kanopi);
(4) DENETIM #21 kapanışı: cavity telemetri-only KALICI kararı; (5) not→kısıt
korpusuna kupon-oryantasyon örneği + PDF-teknik-resim kanalı + 4 yeni kısıt
türü backlog kaydı; (6) WeTransfer indirme backlog kaydı.

## 2026-08-04 — a2-kilitli paket mailine cevap (kısa teşekkür)

**Bağlam:** Eren'in a2-kilitli çözüm maili (`HOCA_MAIL_2026-08-04_GOVDE.txt`;
Drive `plan7_a2_kilitli` klasörü: 6 değişen STL + söküm planı + yeni
özellikli rehber) GÖNDERİLDİ; Mert Bey aynı gün cevapladı:

> "Çok teşekkür ederim, elinize sağlık. Şu an için yeni bir talebim
> bulunmamaktadır. Planlar tarafıma geçtikçe size iletiyor olacağım.
> Bazı konuları FSM'de daha iyi netleştirebileceğimizi düşünüyorum.
> En kısa sürede haberleşmek üzere."

**Sonuçlar:**
- **Mail taahhüdü (a2-kilitli çözüm + güncel STL) RESMEN KAPANDI** —
  paket teslim alındı, itiraz/soru yok.
- Yeni talep ŞU AN yok; **yeni planlar geldikçe iletilecek** (veri akışı
  sürecek — her yeni plan İLK İŞ held-out sınavı, A3).
- **FSM ziyareti teyit edildi** ("bazı konuları FSM'de netleştiririz") —
  tarih henüz yok; açık teknik sorular (S1 eski-boşluk, no-go temas
  toleransı, recoater ekseni, örnek iş emirleri) ziyaret gündemine.

## 2026-08-17 — Yüz yüze görüşme: PİLOT ONAYI + BAYKAR İLGİSİ + iş modeli istişaresi

**Bağlam:** Eren hocayla yüz yüze görüştü (demo günü). Sözlü aktarım;
birebir alıntı değil, Eren'in aktarımıyla kayıt.

**G1 — Pilot/referans site ONAYI:**
- Hoca kendi laboratuvarının pilot + referans olarak kullanılmasını
  KABUL ETTİ. Doğrudan talebi: **"artık bunu kur, biz kullanalım."**
- Sonuç: lab kurulumu resmi iş oldu; kurulum sihirbazı gündeme girdi.

**G2 — BAYKAR görüşmesi:**
- Hoca Baykar yöneticileriyle görüşmüş; fikri — özellikle UYGULAMA
  fikrini — çok beğenmişler ("bayılmışlar"). **Talep var.**
- Hoca zaten Baykar'a drone parçaları basıyor; lab referansı Baykar
  için doğrudan köprü.

**G3 — Gerçek veri gönderimi:**
- Hocanın mühendislerinden biri MAIL ile veri gönderdi. Test tamamen
  uygulama üzerinden yapılacak: mailden çekecek, notları/kısıtları
  işleyecek, sonuç karşılaştırılacak. (A3: yeni gerçek veri = held-out;
  ilk iş held-out sınavı.)

**G4 — İş modeli istişaresi (hoca fikirleri):**
1. **Abonelik/SaaS:** "Gelsinler, bizim server'da çalışsın."
2. **Donanım-dahil premium:** "Bazı şirketlere donanımı da biz
   karşılarız, daha pahalıya satarız."
3. **Alt model (Lite):** mail otomasyonu olmayan, manuel veri yüklemeli
   ucuz kademe.

**Doğrudan işler:** tümü `BUSINESS_PLAN_VE_YAPILACAKLAR.md`'de (yeni
business defteri, 2026-08-17 açıldı): P1 mail-veri uçtan uca app testi
(not→kısıt hattı patlayamaz-kuralı + §2 doğrulama listesi) · P2 lab
kurulumu + sihirbaz (öncesinde P4 kod koruma ŞART) · P3 lab donanım
envanteri (fotoğraflar Eren'den gelecek) + LLM/VL model seçimi ·
P5 uzaktan erişim kararı · §3 kademe kataloğu.

## 2026-08-18 — Hoca teknik geri bildirimleri + uygulama özellik istekleri (Eren aktarımı)

**Bağlam:** Eren'in sözlü aktarımı (görüşme devamı); birebir alıntı değil.

**T1 — Açılı gelen parçalar eksene oturtulmalı:**
- "Bazı parçalar açılı geliyor; onu doğru eksene oturtarak yapmak daha
  iyi kazanç sağlayabilir." → Müşteri STL'i eksene hizasız (tilt'li)
  modellenmiş gelebilir; nesting öncesi OTOMATİK eksen-hizalama
  (PCA/OBB tabanlı kanonik duruş) ön-adımı kazanç adayı.
- NOT: "duruş kilidi" kısıtıyla ETKİLEŞİR — kilitli parçada eksen
  düzeltmesi yapılamaz/müşteriye sorulur; kilitsizde serbest.
- Kayıt: YONTEM §5 aday (K-63 eksen-kanonikleştirme).

**T2 — Gereksiz simetrik dönüşler (zaman kaybı):**
- "Bazı parçalar gereksiz döndürülüyor olabilir; 180° mesela — parça
  aynı yerde kalır, kazanç sağlamaz, zamandan kayıp olur."
- → Parça simetri tespiti (C2/C4/silindirik) ile poz kümesinden
  simetri-eş pozları BUDAMA: sonuç birebir, arama süresi kısalır.
- Kayıt: YONTEM §5 aday (K-64 simetri-poz-budaması; SAF hız işi,
  sonuç-nötr olduğu bit-özdeşlik testiyle kanıtlanmalı).

**T3 — Plan7 boşluk doldurma:**
- "Plan7 başarılı ama çok boşluk var; doldurulursa çok daha iyi olabilir.
  Plan7 (firma işi) 1 günde yapılmış — biz ciddi hız kazancı sağlıyoruz."
- → Mevcut kanopi-altı GLOBAL yeniden-istif hedefiyle (v27 alan-bütçesi:
  verim 0,70→0,80 yolu) BİREBİR örtüşüyor; hoca bağımsız aynı yönü işaret
  etti. Değer önerisi teyidi: insan >1 gün vs. motor ~103dk.

**İ1 — Koşu ilerleme göstergesi (uygulama isteği):**
- "Koşulurken 'bitmesine şu kadar kaldı / %X tamamlandı' yazsın."
- Lab pilotu için operatör-görünür ilerleme çubuğu; mevcut aşama
  callback'leri (on_stage) üzerinden yüzde tahmini.

**İ2 — Koşu hatası bildirimi (uygulama isteği):**
- "Hata olduysa 'koşulamadı' bildirimi gelsin ki boşuna beklemesinler."
- Koşu hata durumunun UI baloncuğu/banner + (ileride) mail bildirimi.
- İkisi de `BUSINESS_PLAN_VE_YAPILACAKLAR.md` P-listesine eklendi
  (pilot kurulumu öncesi öncelikli).

## 2026-08-18 (2) — "Parçalar asla iç içe geçmemeli" beyanı (Eren aktarımı) — ÇELİŞKİ KAYDI

**Bağlam:** Eren aktarımı (sözlü; birebir alıntı değil): hoca "parçalar
asla iç içe geçmemeli; 2mm boşluk dahi olsa öbür türlü çıkarılamaz" dedi.

**ÇELİŞKİ — önceki kayıtlı hoca cevaplarıyla:**
- 2026-07-06 (4 cevap): "iç-içe İZİNLİ + ayrılabilirlik = asıl kısıt".
- 2026-07-14 (K-51b/K-52 kabulü): "az sayıda zor-söküm ihmal edilebilir"
  → A2 rot-söküm katmanının (SÖKÜM-PLANLI LEGAL) dayanağı.
- 2026-08-03: kapalı-kavite serbest (cavity telemetri-only kalıcı).

**Eren'in yorumu (2026-08-18):** "iç içe geçip ÇIKARILABİLİYORSA sıkıntı
olmaz; söküm (çıkarılabilirlik) asıl değerli olan." — Bu yorum 2026-07-06
kayıtlı cevapla AYNI çizgide.

**Motor durumu:** mevcut sözleşme (ANAYASA A2) zaten bu ayrımı yapıyor:
çıkarılamaz iç-içe HİÇBİR ZAMAN legal sayılmaz (INVALID); çıkarılabilir
iç-içe legal + söküm planı (sokum_sirasi/rehberli söküm HTML + rot
sertifikaları) üretilir. Davranış DEĞİŞTİRİLMEDİ.

**Statü:** SÖZLEŞME SORUSU — hocanın yeni beyanı sertleşme mi (hiç iç-içe
istemiyor) yoksa "çıkarılamaz olmasın" vurgusu mu, teyit gerekiyor.
Teyide kadar mevcut A2 semantiği (söküm-kanıtlı iç-içe serbest) geçerli.
Teyit araçları: rehberli söküm HTML demo'su + söküm planı örneği
(hocanın endişesi pratik çıkarma — plan tam bunu adresliyor).

## 2026-08-20 — Mühendis cevabı (FARKLI mühendis) + fabbproject ÖZ-ÖLÇÜMÜ: S2 ÇÖZÜLDÜ (referans ÇOK-PLAKA)

**Mühendis cevabı (Eren aktarımı; 2026-08-18 6-sorulu maile):** "Mailine
henüz bakabildim. Oldukça uzun yazmışsın. Her sorunun tam olarak net bir
cevabı maalesef yok. Bir gün Aluteam'e geldiğinde bu maildeki konuları
detaylı konuşalım." — Bu CEVAP YOK demek; kanal yüz-yüze Aluteam
ziyaretine kaydı. DERS: mühendise mail KISA ve tek-soruluk yazılacak
(uzun mail cevapsız kalıyor).

**ÖZ-ÖLÇÜM (aynı gün — beklemek yerine referans DOSYASI ölçüldü):**
`Veriler/fsm610_2026-08-17/000_17-08-2026.fabbproject` ikili taraması
(kapalı format; isim-etiketi analizi):
- Birleşik referans objesi **"PLAN8(2mm) 315x323x284mm"** — adında hem
  2mm boşluk beyanı hem taban (315x323) hem yükseklik (284) var.
- Obje **shell_001..shell_126** (+_c1 varyantlarıyla ~130) kabuğa ayrık —
  2mm boşluklu birleşik nesnede kabuk = parça ⇒ **PLAN8 ~126-130 PARÇA
  içeriyor, 610 DEĞİL.**
- Adı "PLAN**8**" ⇒ iş EN AZ 8 plana bölünmüş; dosyada başka plan yok
  (yalnız 8. gönderilmiş).

**SONUÇ — S2 KAPANDI:** Referansın 284mm'si 610 parçanın tek-plaka
yüksekliği DEĞİL; ~126 parçalık 8. planın yüksekliği. 516 (bizim,
610-parça-tek-plaka) vs 284 kıyası ELMA-ARMUTMUŞ; "motor %45 geride"
anlatısı tamamen düştü (K-66-a/b hacim analiziyle birlikte: bizim 516
bbox-optimuma ~%4). **Referans pratiği = ÇOK-PLAKA ⇒ U1 (parti yükseklik
bölme) ürün-gerçeği olarak ÖNCELİK YÜKSELDİ.**

**Aluteam ziyareti için kalan KISA soru listesi:** (1) 610 parça kaç
plana bölündü + plan-başına yükseklikler? (2) Çubuklar (399,6mm) hangi
planda, hangi duruşta? (3) İç-içe/söküm teyidi (rehberli söküm HTML
gösterilerek). Ziyaret lab KURULUMUYLA birleştirilir (P2).

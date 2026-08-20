# RUNBOOK — Çalışma Disiplini, Prosedürler ve Süreç Dersleri

> Kuruluş: 2026-08-20 (Eren talebi: "çalışma yöntemimizin hepsi tek
> dosyada, oldukça detaylı, hiçbir adım kaçırılmadan — istikrarımızı bu
> belirleyecek"). Bu dosya HER OTURUMDA geçerlidir (proje CLAUDE.md'den
> bağlanır) ve üç katmanı birleştirir:
>
> - **İLKELER** → `00_ANAYASA.md` (A1-A11) — burada KOPYALANMAZ, işaret
>   edilir (tek-kaynak; kopya = sürüklenme riski).
> - **PROSEDÜRLER** (bu dosya §P) — durum bazlı adım listeleri.
> - **SÜREÇ DERSLERİ** (bu dosya §D) — tarihli, kanıtlı çalışma hataları
>   ve doğruları; her yeni ders buraya İŞLENİR.
>
## §0 — DOSYA HARİTASI + ÇATIŞMA KURALI (karışıklığa karşı tek sayfa)

**Bu runbook TEK GİRİŞ KAPISIDIR.** Her dosya farklı TÜR bir kaydın tek
sahibidir; bir bilgi TEK dosyada yaşar, diğerleri ona link verir (kopya
yasak — kopya sürüklenir). Hangi soru → hangi dosya:

| Soru | Tek kaynak |
|---|---|
| Neye uymak ZORUNDAYIM? (değişmez ilkeler) | `00_ANAYASA.md` |
| Şu durumda NASIL çalışırım? (prosedür + süreç dersleri) | **BU DOSYA** |
| Hangi veri ne rolde / kim held-out? | `01_VERI.md` |
| "Kazanç" ne zaman ilan edilir? (eşikler/kapılar) | `02_EVAL_KAPISI.md` |
| Ne denendi, ne çıktı? (kronolojik kanıt günlüğü) | `MOTOR/YONTEM_HARITASI` §3 |
| Elimizde hangi mekanizmalar var, ne durumda? (envanter) | `MOTOR/MEKANIZMA_KATALOGU.md` |
| ML işleri hangi sırada? (dönemsel İŞ planı) | `ML_YENIDEN_YAPILANMA_PLANI` |
| Hoca/mühendis ne dedi? (beyan arşivi) | `HOCA_CEVAPLARI.md` |
| İş/teslimat/pilot? | `BUSINESS_PLAN_VE_YAPILACAKLAR.md` |

**Çatışma kuralı:** ANAYASA her şeyi ezer → sözleşme kayıtları (A2/hoca
teyitli) → bu RUNBOOK → dönemsel planlar. Çatışma görülürse SESSİZCE
çözülmez: kayıt düşülür + Eren'e taşınır ("X ile Y çelişiyor, hangisi?").

**Şişme freni:** yeni üst-düzey doküman açmak Eren onayı ister; varsayılan
davranış mevcut dokuza eklemektir. Dönemsel planlar işi bitince arşivlenir
(çekirdek dokuz kalır). RESUME dosyaları geçici el-değiştirme notudur,
kaynak değildir.

---

## §P — PROSEDÜRLER (durum bazlı, adım adım)

### P-1 · YENİ GERÇEK VERİ GELDİĞİNDE
1. **Otomatik held-out doğar** (B1) — geliştirme döngüsüne SOKULMAZ (A3).
2. İlk iş **held-out sınavı**: motor mevcut haliyle koşulur; bakış tarihi
   `01_VERI.md` registry'sine loglanır (her bakış sayılır).
3. **Karne**: ilk-koşu açığı (varsa referansa karşı) kaydedilir — trend
   metriği (01_VERI §2.2); "satışa hazır mıyız" göstergesi budur.
4. **Açık-ayrıştırma raporu** (zorunlu): kaybın kaç mm'si hangi katmandan
   — karar mı, çözücü mü, sözleşme/kıyas-şartı mı, uygulama hatası mı?
   (Şablon: RAPOR_FSM610 §1.1 tablosu.)
5. Referans sonucu/dosyası varsa: **önce DOSYAYI ÖLÇ** (P-8.1) — kıyas
   şartları (tek/çok-plaka, duruşlar, boşluk) doğrulanmadan hiçbir sayı
   hedef alınmaz (A10; D-5 dersi).
6. `MEKANIZMA_KATALOGU` güncellenir (yeni gözlem/açık varsa girdi).
7. Yeni sınıf keşfi → **kalıcı sentetik jeneratör ailesi** eklenir
   (ML planı §2.3 kuralı).

### P-2 · HELD-OUT → DEV TERFİSİ ("test'ten train'e çevirme")
1. Terfi ancak AÇIK kararla (Eren) — sessiz terfi yok; gerekçe yazılır.
2. Ön-koşul (B1): aynı aileden held-out stoku yenilenebilir olmalı
   (yeni sipariş akışı held-out stokunu besliyor mu?).
3. Registry'de rol değişir + tarih + karar referansı (`01_VERI.md`).
4. Terfi eden set eğitim tablosuna GİRER ama **aile-dengeli ağırlıkla**
   (tek set dağılımı domine edemez — ML planı §4.4).
5. O setin eski held-out bakışları eğitim-öncesi rapora yazılır
   (kaç kez bakıldı — bilgi sızıntısı şerhi).

### P-3 · YENİ MEKANİZMA KEŞFİ (insan-referansından veya teşhisten)
1. GÖZLEM: kanıtla `MEKANIZMA_KATALOGU`'na girdi (kaynak + tarih).
2. **Geometrik tetik** yazılır — kodda veri adı YASAK (A11.1).
3. Ucuz kâğıt-hüküm (A4): analitik alt-sınır/kapasite hesabı — beklenen
   kazanç bandı KOŞMADAN kestirilir (K-66-a deseni, 3sn'lik hesap).
4. PROTOTİP: `scripts/` deney harness'ı (üretim default'una DOKUNMAZ);
   parametreler geometriden türetilir, sabit sayı gömülmez (§6.6).
5. Tek-set ön-ölçüm = ŞERHLİ; **aynı oturumda** dağılımsal adım planlanır
   (k59 deseni: tetik-doğruluğu + A/B kazanç + yanlış-pozitif).
6. KAPI: 4-set dev + tetiksiz setlerde SIFIR-DOKUNUŞ kanıtı (A11.3).
7. Kapı PASS → üretim kablosu Eren onayıyla; katalog durumu ilerletilir;
   mekanizma **M4 portföyüne KOL olarak eklenir** (ML akışı, katalog §C).

### P-4 · HATA / KRİZ ANINDA (INVALID sonuç, çöken koşu, yanlış rapor)
1. Aynı komut/prompt ile kör tekrar YASAK — önce teşhis (log + .err +
   canlı proses üçlüsü; [[feedback-store-python-proses-adi]] dersi).
2. Kök-sebep bulunana kadar düzeltme commit'lenmez; bulununca **fix +
   regresyon testi birlikte** commit'lenir.
3. Yanlış RAPOR verildiyse: düzeltme aynı kanaldan açıkça duyurulur
   (sessiz düzeltme yok) + YONTEM kaydına "DÜZELTME" bloğu.
4. Süreç hatasıysa (teknik değil): §D'ye tarihli ders yazılır.
5. Kriz kapanınca: `MEKANIZMA_KATALOGU` §B (açıklar) güncellenir.

### P-5 · KOŞU BAŞLATMA DİSİPLİNİ
1. **ETA'sız koşu başlatılmaz**: koşu-başına örnek süre × adet hesabı
   rapora yazılır.
2. **Ağır işler KESİN SIRALI** (suite / ölçüm / NFV): üst üste bindirme
   yok; "sonuç bozulmuyor" gerekçesi GEÇERSİZ (süre de korunan varlık).
3. RAM kontrolü: <4GB boşken NFV-ağır başlatılmaz (K-57a); ölçüm
   koşuları münhasır.
4. Koşular `D:\ie488`'den `python -m scripts.detach_run <modul>`;
   C'ye büyük dosya yazılmaz; kanıt JSON+log D + OneDrive ÇİFT kopya.
5. Her uzun koşuya İZLEYİCİ kurulur — filtre yalnız başarıyı değil TÜM
   ölüm biçimlerini kapsar (çökme/takılma/MemoryError/proses-ölümü).
6. Pencereye sığmayan iş: kapsam küçültülür (append-only ilk-dalga
   deseni: az seed şimdi, kalanı sonraki pencere) — geç saatte
   tam-kapsam başlatılmaz.
7. Üretim log/print SAF ASCII (cp1254); .bat CRLF.

### P-6 · RAPOR YAZIMI (her sonuç raporu)
1. **A11 statüsü görünür**: şerhli mi, hangi kanıt adımları bekliyor.
2. **"Ölçmeden bıraktıklarım" satırı zorunlu** (boşsa "yok" yazılır) —
   516/353-kilit tipi sessiz atlama yasak.
3. Sayılar legal-yükseklik semantiğiyle (A2); hangi kriterle legal
   olunduğu belirtilir (5-yön / söküm-planlı).
4. Dış iletişim metrikleri üretim semantiğiyle (rot_cert vs n_locked
   dersi — [[feedback-dis-iletisim-metrik-semantigi]]).
5. Sonuçlar ONAYSIZ işlenir (YONTEM + katalog + memory); onay yalnız
   KARAR işlerinde (commit/push, üretim değişikliği, baseline, hoca
   içeriği).

### P-7 · EĞİTİM / RETRAIN DALGASI
1. Ön-koşul: **eğitim-öncesi açık-ayrıştırma raporu** (hangi mm hangi
   katmandan — "veriden ders çıkarma" prosedürü; fsm610 şablonu).
2. Etiket üretimi: M4 portföy koşuları (karşı-olgusal; tüm aktif kollar).
3. `mod_yarismasi`: aile-kırılımlı LOO-regret; KURAL her zaman kıyas
   çizgisi olarak yarışır; overfit bayrağı (cv_gap) kontrol.
4. Kapı: kendi sınıfında kuralı yen + diğer ailelerde bozulma yok +
   motor sıfır-dokunuş (ML planı §4 Aşama-1 kapısı).
5. Promote YALNIZ insan onayı + atomik + arşiv versiyonu (A6/Y-1/Y-4).
6. Dağıtım: kalibre güven eşiği + destek zarfı + kural-fallback (§3.5);
   zarf-dışı = çekimser = NFV-max konservatif yol (KARAR-6).
7. Kör-test (plan7 vb.) eğitime ASLA girmez; sınav sonucu karneye.

### P-8 · DIŞ İLETİŞİM (hoca / mühendis / müşteri)
1. **Maile yazmadan önce**: "bu soru ELDEKİ dosyadan/veriden ölçülebilir
   mi?" — ölçülebilenler maile GİRMEZ (PLAN8 dersi: S2'yi dosya çözdü).
2. Mühendise mail: KISA, tek-konu, madde başına 1-2 satır, evet/hayır
   veya tek-sayı ile cevaplanabilir. Uzun teknik içerik: 3-5 satır özet
   + ek dosya.
3. Detay isteyen konular yüz-yüze ajandaya; ziyaretler kurulum/teslimat
   işleriyle birleştirilir (Aluteam deseni).
4. Hocaya giden HER içerik Eren onayından geçer; her cevap/beyan
   `HOCA_CEVAPLARI.md`'ye tarihli işlenir (çelişkiler ÇELİŞKİ kaydıyla).

### P-9 · COMMIT / PUSH DİSİPLİNİ
1. Commit'ler konu-bazlı parçalı; mesajda kanıt (test sayısı, ölçüm).
2. Kablo değişikliğinde TAM SUITE (A9) yeşili commit zincirine eşlik
   eder; anchor değişikliği gerekçeli (A8).
3. Push ve üretim-default değişikliği Eren onayıyla.
4. Veri (Veriler/, 100MB+ dosyalar) ve koşu logları repoya GİRMEZ.

### P-10 · OTURUM RİTMİ
1. Oturum başı: ANAYASA + bu RUNBOOK bilinçli uygulanır (CLAUDE.md);
   motor işi öncesi YONTEM §2+§5.
2. **Şerh-yaşlanma taraması**: 7 günü aşan ŞERHLİ/BEKLİYOR maddeler
   KIRMIZI listelenir → ya o oturum kapatılır ya açıkça ertelenir.
3. "En büyük bilinmeyen" işaretlenen HER madde için AYNI GÜN bir A4
   ucuz-teşhis adımı koşulur veya koşulamama gerekçesi tarihle yazılır.
4. Plana en sert itirazı Eren'den ÖNCE biz üretiriz ("en zayıf varsayım
   + bugün nasıl test ederiz" — plan dokümanlarına bölüm olarak).
5. Oturum sonu: RESUME/memory devam noktası güncel; koşan işlerin
   izleyicileri kurulu.

---

## §D — SÜREÇ DERSLERİ (tarihli; her yeni ders buraya eklenir)

| Tarih | Ders | Kanıt/olay | Bağlı prosedür |
|---|---|---|---|
| 2026-07-06 | Ölçülmemiş beyan yasak (halüsinasyon yasağı Y-10) | tarihi-sayı karışıklığı | P-6 |
| 2026-07-13 | Bekleme-kapılı script, kapı-sonrası duman testi olmadan zincire konmaz; detach .err monitörlenir | 9-saat kaybı | P-5 |
| 2026-07-18 | Canlılık üçlüsü: isim-filtresiz proses listesi + log zamanı + .err (kill -0 / "python.exe" filtresi yalancı) | çift-kopya tuzağı | P-4 |
| 2026-07-19 | Tek-veri geliştirme yasağı ANAYASA'ya (A11); her oturum bilerek | K-56 süreci | P-3 |
| 2026-08-18 | Ürün metriği ile iç metrik karıştırılmaz (rot_cert vs n_locked) | hocaya "15 döndürmeli" hatası | P-6, P-8 |
| 2026-08-20 | **Tembellik/plan-aşıklığı yasağı — 4 kural**: bilinmeyen-bekletme yasağı; şerh 7-gün limiti; "ölçmeden bıraktıklarım" satırı; en sert itirazı önce biz | %45-açığı 2 gün bekledi (3sn'lik hesaptı); 353-kilit sessiz geçildi; A9 16 gün sürüklendi | P-10, P-6 |
| 2026-08-20 | **Koşu sıralama + ETA kuralı**: ağır işler kesin sıralı; ETA'sız başlatma yok; sığmıyorsa kapsam küçült | M4 suite'le çakıştı, gece sabaha taştı | P-5 |
| 2026-08-20 | **Referans DOSYASI önce ölçülür**; kıyas-şartı doğrulanmadan sayı hedef alınmaz | "%45 geride" yanılgısı; PLAN8 öz-ölçümü S2'yi çözdü | P-1.5, P-8.1 |
| 2026-08-20 | Dış mail KISA + tek-konu; uzun mail cevapsız kalır | mühendis "Aluteam'e gel" | P-8 |
| 2026-08-20 | K-38 kuantizasyon dersi HER elle-yerleşimde geçerli: adımlar pitch-katına, toleranslar mühendislik-yuvarlamalı (mikron tozu ceil'i şişirir) | kafes v1 INVALID 1,046; toz bug'ı | P-3.4 |
| 2026-08-20 | Alt-sınır iddiası SINIFINI belirtir: bbox-hücre LB gerçek-geometriye bağlayıcı değil | 496-LB'yi 458,4 deldi | P-6 |
| 2026-08-20 | Analitik kâğıt-hüküm koşudan önce: 3 saniyelik hesap 55 dakikalık koşuyu yönlendirir | K-66-a/hacim analizi | P-3.3 |

> Yeni ders ekleme kuralı: olay + kanıt + hangi prosedürü değiştirdiği.
> Ders eklemek yetmez — ilgili P-maddesi de güncellenir (ders prosedüre
> gömülmemişse KAYBOLUR; bu tablo prosedürün gerekçe-arşividir).

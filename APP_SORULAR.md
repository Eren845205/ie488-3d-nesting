# APP_SORULAR.md — Konteyner Yerleştirme Uygulaması İçin Netleştirilecek Sorular

> Genel plan (2026-06-11): Kullanıcı, konteynere sığdırmak istediği tüm parçaların verisini
> uygulamaya girer; app parçaları sıralar ve konteynerlere en optimize şekilde yerleştirir.
> Algoritma detayları hocadan alınacak bilgiler ışığında kesinleşecek.
> Bu dosya, o görüşmede ve tasarım aşamasında cevaplanması gereken soruların listesidir.
> Her sorunun altında "neden önemli" notu var — cevap mimariyi doğrudan değiştiriyor.

---

## A. Hocaya Sorulacaklar (algoritma ve problem tanımı)

### A1. Parça verisi ne formatta gelecek?
- Gerçek 3D geometri mi (STL/STEP mesh), yoksa sadece **en × boy × yükseklik + adet** mi?
- **Neden önemli:** Kutu boyutuysa voxel'a gerek yok — klasik 3D bin packing (çok daha hızlı,
  saniyeler). Gerçek geometriyse mevcut voxel motoru (`src/nesting3d/`) kullanılır ama
  numune fazında gördük: SA 1000 iterasyon ≈ 519 s. App'te bekleme süresi kabul edilebilir mi?

### A2. Amaç fonksiyonu ne?
- En az **konteyner sayısı** mı?
- Tek konteynerde **maksimum doluluk** mu?
- Belirli parçaların **öncelikli** sığdırılması mı (önce gönderilmesi gerekenler)?
- Birden fazlası geçerliyse öncelik sırası ne?
- **Neden önemli:** Mevcut motorun amacı "yüksekliği minimize et" (open-dimension).
  Konteyner sabit boyutluysa amaç tamamen değişir; SA'nın skor fonksiyonu buna göre yazılır.

### A3. Konteyner(ler) nasıl tanımlı?
- Tek tip ve sabit boyut mu (ör. standart 20ft/40ft), yoksa kullanıcı farklı tipler arasından
  seçecek mi?
- Konteyner sayısı sınırlı mı, gerektiği kadar açılabilir mi?
- **Neden önemli:** Çok tip varsa "hangi parça hangi konteynere" ataması ayrı bir karar
  katmanı (bin selection) gerektirir.

### A4. Fiziksel kısıtlar var mı?
- **Ağırlık limiti** (konteyner başına toplam kg)?
- **İstifleme kuralları** — kırılgan/üstüne yük konamaz parça? Maksimum istif yüksekliği?
- **Yön kısıtı** — "bu yüzü hep aşağı bakacak" (this-side-up) parçalar?
- **Ağırlık dağılımı / denge** — ağır parçalar alta veya tabana yayılma şartı?
- **Neden önemli:** Bunlar yerleştirme geçerliliğini (feasibility) tanımlar; sonradan eklemek
  motorun yeniden yazılması demek. Baştan bilinmeli.

### A5. Rotasyon serbestisi ne kadar?
- Parçalar serbestçe döndürülebilir mi, yoksa sadece eksen-hizalı 90° dönüşler mi?
- (Mevcut motor 4 eksen-hizalı oryantasyon kullanıyor — yeterli mi?)

### A6. Hangi algoritma ailesi bekleniyor / isteniyor?
- Hocanın aklındaki yöntem ne: constructive heuristic (DBLF benzeri), metaheuristic (SA/GA),
  exact model (MILP), yoksa karışım mı?
- Ders/proje kapsamında belirli bir literatür referansı izlenecek mi?
- **Neden önemli:** "Hocadan algoritma bilgisi alınacak" — bu sorunun cevabı projenin
  çekirdeğini belirliyor. Mevcut DBLF + SA iskeleti hangi yöntemle değiştirilecek/genişletilecek?

### A7. Problem tek seferlik mi, sürekli mi?
- Kullanıcı bir kerede tüm parça listesini verip sonucu mu alıyor (offline/statik),
  yoksa zamanla parça eklenip plan güncelleniyor mu (online/dinamik)?

### A8. Fiyat önerisi nasıl hesaplanacak? *(2026-06-11 hoca görüşmesi — pipeline'a eklendi)*
- Formülün girdileri ne: hacim mi, ağırlık mı, konteyner sayısı/doluluk mu, mesafe/rota mı,
  parça değeri mi? Sabit tarife tablosu mu var, müşteriye göre değişiyor mu?
- **Neden önemli:** Hoca pipeline'dan fiyat önerisi de istiyor. Kodlaması formül belli
  olduktan sonra basit; bilgi tamamen hocadan gelmek zorunda — en kritik bağımlılık.

### A9. Mail ingest: veriler hangi formatta/kanaldan gelecek? *(2026-06-11)*
- "Mail geldi, parça verileri geldi" — ekte Excel/CSV mi, STL/STEP mi, mail gövdesinde
  serbest metin mi? Tek gönderen mi (sabit format), çok müşteri mi (karışık format)?
- **Neden önemli:** Sabit şablonlu ekse parser basit; serbest metinse LLM-destekli çıkarım
  katmanı gerekir. Tam otomasyonun en kirli işi burası.

### A10. Önceliklendirme kuralları ne? *(2026-06-11)*
- "Hangisi öncelikli paketlenecek"i ne belirliyor: termin tarihi, müşteri önceliği,
  sipariş sırası, parça değeri, hacim verimi?
- **Neden önemli:** B5 ile bağlantılı ama iş kuralı düzeyi: yerleştirme sırasından önce
  "bu turda hangi parçalar konteynere hiç girecek" seçimini de etkiler (knapsack katmanı).

### A11. Geçmiş nesting verileri ne formatta? *(2026-06-12 görüşme #2 — hoca önerdi)*
- Hoca geçmişte yapılan nesting'lerin sisteme öğretilebileceğini söyledi. Bu veriler
  hangi formatta duruyor: yerleşim planı (Excel/çizim), fotoğraf, CAD dosyası, sadece
  hafıza/tecrübe mi? Kaç örnek var? Parça listesi + nihai yerleşim eşleşmesi çıkarılabilir mi?
- **Neden önemli:** Format her şeyi belirler — yapılandırılmış plan varsa doğrudan benchmark
  + öğrenme verisi olur; sadece fotoğraf/tecrübe ise önce sayısallaştırma işi gerekir.
  Bu veri aynı zamanda R7 (benchmark yok) riskinin en değerli panzehiri: gerçek instance'lar.

### A12. "Diğer algoritmalar" hangileri? *(2026-06-12 görüşme #2)*
- Hoca SA'nın tek başına yeterli olmadığını, başka algoritmaların da kullanılması
  gerektiğini söyledi. Aklındaki spesifik aileler ne: GA, tabu search, constructive
  heuristic varyantları, MILP, literatürden belirli bir makale/yöntem mi?
- **Neden önemli:** A6'nın somutlaşmış hâli — portföye hangi algoritmaların gireceği
  demo-1'in iş listesini doğrudan belirler.

### A13. Veri güvenliği: müşteri verisi bulut API'sine çıkabilir mi? *(2026-06-12)*
- Parça verileri/mailler üçüncü taraf yapay zeka API'lerine (Anthropic/OpenAI bulutu)
  gönderilebilir mi, yoksa her şey şirket içinde (on-prem) mi kalmalı? Müşterilerin
  (savunma sanayi: ASELSAN yan kuruluşu, Baykar tedarikçisi) bu konuda yazılı politikası var mı?
- **Neden önemli:** Cevap LLM katmanının mimarisini belirler: bulut serbest ise API
  (ucuz, güçlü); yasaksa lokal açık-ağırlıklı model (Qwen/Llama, on-prem GPU) — eğitim
  değil inference; katman ince/değiştirilebilir tasarlanırsa geçiş ucuz. Beklenti:
  savunma sanayi müşterisi bulut'a izin VERMEZ — on-prem varsayılan plan olmalı.

### A14. Süper bilgisayar: erişim detayları + ürün aşamasında kullanım *(2026-06-12 — hoca önerdi)*
- Hangi sistem (üniversite HPC mi, kurum kümesi mi)? Donanım profili: CPU çekirdek sayısı,
  GPU var mı? İş gönderme şekli (SLURM kuyruk mu, doğrudan erişim mi)? Kim, ne kadar süreyle
  kullanabilir?
- **Kritik ayrım:** süper bilgisayar **tasarım/benchmark/offline koşular** için mi, yoksa
  satılan üründe **müşteri işlerinin runtime'ı** olarak da mı kullanılabilir? Müşteri verisi
  bu makineye gönderilebilir mi (A13 ile bağlantılı — veri güvenliği)?
- **Neden önemli:** Cevap mimariyi ikiye ayırır: (a) HPC sadece geliştirmede → ürün müşteri
  donanımında makul sürede çalışacak şekilde bütçelenir, HPC ile ince-rotasyon/benchmark
  sweep'leri yapılır; (b) HPC runtime'da da var → "gece gönder, sabah optimal plan al"
  batch-servis modeli mümkün olur ve 0.5° hassasiyet üretimde vaat edilebilir.

### A15. Çizelgeleme katmanı: parti karışımı + kapasite verileri *(2026-06-13 — hoca işleyiş tarifi)*
- Hocanın tarif ettiği çok-müşterili termin-bazlı otomasyon (Ford 5 gün / Baykar 30 gün →
  sistem önceliği kendisi seçer) için iki kritik bilgi:
  (a) **Farklı müşterilerin parçaları aynı partide/konteynerde karışabilir mi?** (Savunma
  sanayinde gizlilik/izlenebilirlik gereği muhtemelen hayır — cevap batch oluşturma
  mantığını kökten değiştirir.) *Güncelleme 2026-06-13: hoca tarifine göre karışım fiilen
  YAŞANIYOR ve sahiplik konteyner içi barkodlarla (bugün insan gözüyle, fotoğraftan)
  çözülüyor — yine de hangi müşteri sınıfları için karışım İZNİ olduğu yazılı teyit
  edilmeli. Görsel barkod-kimlik modülü fikri: APP_YOL_HARITASI §6.5.*
  (b) **Kapasite verileri:** kaç makine/konteyner, parti (build) süresi nasıl hesaplanır,
  vardiya düzeni? Termin taahhüdünün ("5 günde hazır") fizibilite kontrolü buna bağlı.
- **Neden önemli:** A10'un (önceliklendirme) somutlaşmış hâli — çizelgeleme katmanı
  nesting'den önce çalışan ayrı bir karar zekâsı (literatür: nesting and scheduling);
  yanlış varsayımla tasarlanırsa sonradan düzeltmesi pahalı.

---

## B. Uygulama Tasarımı İçin Cevaplanacaklar (hoca + kendi kararımız)

### B1. Platform ne olacak?
- Masaüstü (Python + basit GUI), web uygulaması, yoksa şimdilik CLI + rapor mu?
- Kim kullanacak: sadece biz/hoca mı, yoksa gerçek son kullanıcı mı?
- **Neden önemli:** 3B önizleme ihtiyacı varsa web (three.js) ile masaüstü (matplotlib/trimesh
  viewer) arasında ciddi efor farkı var.

### B2. Veri girişi nasıl olacak?
- Excel/CSV yükleme mi (parça adı, boyutlar, adet, ağırlık kolonları)?
- Form üzerinden tek tek giriş mi?
- STL dosyası yükleme mi (geometri gerekiyorsa)?
- **Neden önemli:** "Kullanıcı bütün parçaların verisini verecek" — pratikte bu neredeyse
  her zaman bir Excel listesidir; şablon baştan tanımlanmalı.

### B3. Çıktı ne olmalı?
- Konteyner başına yerleşim planı: hangi parça, hangi konteyner, hangi konum/oryantasyon?
- 3B görsel önizleme mi, yükleme sırası listesi mi (forkliftçinin izleyeceği adım adım sıra)?
- Rapor formatı: PDF / Excel / ekranda tablo?
- **Neden önemli:** Yerleştirme matematiksel olarak optimal olsa bile yükleme sırası
  uygulanabilir değilse (önce arkaya konacak parça sonda çıkıyorsa) plan kâğıt üstünde kalır.

### B4. Performans beklentisi ne?
- Tipik problem boyutu: kaç parça tipi, toplam kaç adet, kaç konteyner?
- Kullanıcı sonucu kaç saniye/dakika beklemeye razı?
- **Neden önemli:** Numune fazı verisi: 48 parça voxel + SA = ~8.5 dk. App'te bu kabul
  edilemezse ya kutu-tabanlı modele geçilir ya SA hızlandırılır (A1 ile doğrudan bağlantılı).

### B5. Sıralama ("adetine göre") tam olarak ne demek?
- Kullanıcının söylediği "adetine göre sıralayacak" — adet çokluğuna göre mi, hacme göre mi,
  teslim önceliğine göre mi? (Mevcut motor hacim-azalan sıralıyor.)
- **Neden önemli:** Sıralama kriteri constructive heuristic'in kalitesini doğrudan belirler.

---

## C. Cevaplandıkça Doldurulacak

| Soru | Cevap | Tarih | Kaynak (hoca/karar) |
|---|---|---|---|
| A1 | | | |
| A2 | | | |
| A3 | | | |
| A4 | | | |
| A5 | | | |
| A6 | KISMİ: sadece SA değil, birden çok algoritma kullanılacak ("algoritmaları yazılıma öğreteceğiz"); hangi aileler olduğu yazılı cevapla netleşecek. Ek: geçmiş nesting'lerden öğrenme (data-driven) istendi. | 2026-06-12 | hoca (sözlü, görüşme #2) |
| A7 | | | |
| A8 | KISMİ: şirket kendi fiyat stratejisini EXCEL olarak verecek; sistem bunu kural setine çevirip fiyatlayacak; manuel müdahale şart (kural + teklif düzeyi). Excel'in iç yapısı (girdiler, tablo mu formül mü) örnek dosya gelince netleşecek. Tasarım: APP_YOL_HARITASI §6.2 | 2026-06-12 | hoca (sözlü, görüşme #2) |
| A9 | | | |
| A10 | KISMİ: önceliklendirme TERMİN-bazlı (hoca işleyiş tarifi 2026-06-13: Ford 5 gün / Baykar 30 gün → sistem öncelik sırasını kendisi belirler, partileri kurar, nesting+fiyatlamayı otomatik yürütür). Tam kural seti (termin + müşteri önceliği + iş büyüklüğü ağırlıkları) ve A15 cevapları bekleniyor. Tasarım: APP_YOL_HARITASI §6.4 | 2026-06-13 | hoca (sözlü) |
| A11 | | | |
| A12 | KISMİ: hoca GA'nın (genetic algorithm) bu tip veri setlerinde daha iyi olabileceğini söyledi — GA portföyün öncelikli üyesi; tam liste yazılı cevapla netleşecek | 2026-06-12 | hoca (sözlü) |
| A13 | | | |
| A14 | | | |
| B1 | KARAR: **lokal-barındırılan web uygulaması** — web teknolojili arayüz (tarayıcı + three.js 3D önizleme), müşterinin kendi sunucusunda çalışır (on-prem, internet gerekmez → A13 uyumlu); çok kullanıcı + tek noktadan güncelleme + SaaS geçişinde sıfır yeniden yazım. Saf masaüstü reddedildi (tek kullanıcı, zayıf 3D, SaaS'a taşınamaz). Demo: localhost'ta koşar, tarayıcıdan gösterilir | 2026-06-13 | kullanıcı + Claude (mutabık) |
| B2 | | | |
| B3 | | | |
| B4 | | | |
| B5 | | | |

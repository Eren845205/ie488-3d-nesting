# Hoca Görüşmesi — Gündem (Zoom, 19 Haziran 2026)

> Amaç: bundan sonraki yol haritasını netleştirmek **+** uygulamayı tam ürün
> haline getirmek için hocadan alınacak veri/materyalleri belirlemek.
> Bu doküman iki bölüm: **(1) Sorular** · **(2) Hocadan istenecekler**.

---

## 0. Şu an neredeyiz — kısa durum (referans)

Algoritmanın etrafına çalışan bir uygulama oturdu. Hâlihazırda **çalışan** parçalar:

- **Çoklu algoritma portföyü:** DBLF (taban) + SA + GA + Tabu + MultiStart-SA + ALNS — ortak arayüz, adil kıyas, "hepsini koş en iyiyi seç".
- **Algoritma-seçim modeli:** instance özelliğinden kazanan çözücüyü tahmin (yorumlanabilir, 1-NN + karar ağacı) + kolay-instance ön-filtresi + monoton garanti.
- **Öğrenme döngüsü:** geçmiş işlerden öğrenme **manuel + öneri** politikasıyla (otomatik retrain yok — sessiz bozulma riskine karşı).
- **Çok-şirketli önceliklendirme + çizelgeleme:** termin/öncelik/iş büyüklüğüne göre sıralama + parti planı + termin/kapasite uyarıları.
- **Uçtan uca otomasyon:** e-posta → parça dosyası (STL / Excel / CSV) okuma → 3D nesting → otomatik fiyat → müşteri mail taslağı (operatör onayıyla).
- **Fiyatlandırma motoru:** deterministik kural seti + manuel müdahale (iskelet hazır, gerçek kurallar bekliyor).

> Demo seviyesinde uçtan uca çalışıyor; üretim sertleştirmesi (çok-kullanıcı,
> güvenlik, lisans) teslim öncesine planlı.

**Bu yüzden aşağıdaki sorular "sıfırdan" değil — mevcut sistemin yönünü onaylamak
ve eksik gerçek verileri tamamlamak için.**

---

## 1. Hocaya Sorulacak Sorular (yol haritası)

### A. Algoritma yönü
1. **Portföy yönü doğru mu?** Şu an 6 algoritmalı portföy + seçim modeli var.
   Aklınızda eklenmesini istediğiniz **spesifik bir yöntem / literatür makalesi** var mı?
2. **MILP / kesin çözüm** küçük problemler için isteniyor mu, yoksa metasezgisel
   portföy yeterli mi? (Şu an kasıtlı olarak yok.)
3. **Geçmiş işlerden öğrenmenin** sizce doğru biçimi ne: sadece "en iyi algoritmayı
   seçme" mi, yoksa yerleşim kararlarını da taklit etmesi mi? (Öğrenmeyi şu an
   **manuel + öneri** tuttuk — sistemin kendini sessizce bozmaması için. Bu yaklaşım
   sizce uygun mu?)

### B. Problem tanımı & kısıtlar
4. **Amaç fonksiyonu:** şu an "yüksekliği/parti yüksekliğini minimize et". Sizin
   gerçek hedefiniz bu mu, yoksa **konteyner/parti sayısı minimizasyonu** mu,
   **maksimum doluluk** mu? (Cevap skor fonksiyonunu belirliyor.)
5. **Konteyner/parti tanımı:** sabit boyutlu bir hacim mi (ör. makine tablası
   335×335×600), yoksa açık-boyut mu? Birden fazla tip var mı?
6. **Fiziksel kısıtlar:** ağırlık limiti, istif kuralları (üstüne yük konamaz),
   "bu yüz aşağı" (this-side-up), denge — bunlardan hangileri geçerli? (Feasibility
   katmanını belirler; sonradan eklemek pahalı.)

### C. Otomasyon & işleyiş
7. **Önceliklendirme kuralları:** şu an termin + öncelik sınıfı + iş büyüklüğü
   ağırlıklı. Ağırlıkları/kuralı netleştirir misiniz? (Örn. müşteri önceliği termini
   ezer mi?)
8. **Parti karışımı:** farklı müşterilerin parçaları **aynı partide karışabilir mi**?
   (Savunma sanayi gizliliği açısından kritik — batch mantığını kökten değiştirir.
   Hangi müşteri sınıfları için izinli, yazılı teyit gerekir.)

### D. Altyapı & ticari
9. **Veri güvenliği:** müşteri verisi/mailler bulut yapay zeka API'sine çıkabilir mi,
   yoksa her şey **on-prem** mi kalmalı? (Şu an lokal model — Ollama — varsayıldı.)
10. **Süper bilgisayar:** sadece geliştirme/benchmark için mi, yoksa satılan üründe
    **müşteri işlerinin runtime'ı** olarak da kullanılabilir mi? (İkinci durumda
    "gece gönder, sabah optimal plan al" modeli + yüksek rotasyon hassasiyeti mümkün.)
11. **IP / ortaklık çerçevesi:** ürün on-prem teslim edilecek (kod koruma gerekiyor).
    Yapı, roller ve IP mülkiyeti hangi yönde netleşecek? (Teslim öncesi sözleşme.)

---

## 2. Hocadan İstenecekler (uygulamayı tamamlamak için gereken veri/materyaller)

> Bunlar sorudan çok **somut teslimat** — geldiğinde doğrudan kod/benchmark'a girer.
> Öncelik: 🔴 yüksek (en kritik blokör) · 🟡 orta · ⚪ sırası gelince.

- [ ] 🔴 **Fiyatlandırma Excel'i (örnek dosya)**
  — *Ne için:* fiyat motoru iskeleti hazır ama gerçek kurallar yok; örnek Excel'i
  kural setine çevireceğiz.
  — *İdeal format:* şirketin kullandığı fiyat tablosu/formülü — girdiler (hacim,
  ağırlık, konteyner sayısı, mesafe, parça değeri?) hangileri belli olsun.

- [ ] 🔴 **Geçmiş nesting / build verileri**
  — *Ne için:* sistemi gerçek veriyle eğitmek + benchmark (en değerli overfit
  panzehiri). Şu an elimizde tek gerçek numune var; çoklu gerçek veri = tam
  genelleme kanıtı.
  — *İdeal format:* parça listesi **+** nihai yerleşim eşleşmesi (Excel/plan/CAD).
  Kaç örnek var? Fotoğraf/tecrübe ise önce sayısallaştırma gerekir — onu da konuşalım.

- [ ] 🔴 **Gerçek parça örnekleri (geometri)**
  — *Ne için:* motoru gerçek geometride sınamak.
  — *İdeal format:* STL/STEP dosyaları **veya** en×boy×yükseklik+adet listesi.

- [ ] 🟡 **Hedef makine / kapasite parametreleri**
  — *Ne için:* parti planı + termin fizibilitesi gerçek değerlerle çalışsın.
  — *İçerik:* tabla/konteyner boyutu, ağırlık limiti, makine sayısı, vardiya düzeni,
  bir partinin (build) süresi nasıl hesaplanıyor.

- [ ] 🟡 **Fiziksel kısıt listesi**
  — *Ne için:* yerleşim geçerliliği (feasibility) katmanı.
  — *İçerik:* ağırlık, istifleme, this-side-up, denge kuralları.

- [ ] 🟡 **Örnek sipariş/e-posta formatları**
  — *Ne için:* parser şu an demo formatlarını işliyor; gerçek müşteri formatlarına
  göre sağlamlaştıralım.
  — *İçerik:* tipik bir-iki gerçek sipariş maili/eki (anonimleştirilmiş olabilir).

- [ ] ⚪ **Veri güvenliği politikası (yazılı)**
  — *Ne için:* LLM/bulut mimari kararı. Savunma sanayi müşterilerinin bulut izni
  var mı? (Beklenti: yok → on-prem varsayılan.)

- [ ] ⚪ **Süper bilgisayar erişim detayları**
  — *Ne için:* ince-rotasyon/benchmark sweep + olası batch-servis modeli.
  — *İçerik:* hangi sistem, CPU/GPU profili, iş gönderme (SLURM?), kim ne kadar.

- [ ] ⚪ **IP / ortaklık çerçevesi (yön)**
  — *Ne için:* teslim öncesi kod koruma + sözleşme. Demo aşamasında gerekmez,
  gerçek teslimde şart.

---

### En kritik iki blokör (görüşmede bunları garantiye al)
1. 🔴 **Fiyatlandırma Excel'i** — fiyat motorunu gerçeğe bağlar.
2. 🔴 **Geçmiş nesting verileri** — algoritmayı gerçek veriyle eğitir + genelleme kanıtı.

> Bu ikisi gelmeden uygulama "demo" seviyesinde kalır; geldiğinde "gerçek ürün"e döner.

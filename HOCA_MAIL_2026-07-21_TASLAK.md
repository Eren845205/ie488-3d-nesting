# Mail Taslağı — 2026-07-21 (GÖNDERİM EREN ONAYINDA)

> Alıcı: Mert Bey (mcoskun@fsm.edu.tr) · Konu: RE: Plan1 ve Plan 3 Nesting —
> Plan7 sonuçları ve birkaç soru
>
> İç not (maile girmez): Cevaplanmış sorular (plaka, 2mm boşluk, serbest
> rotasyon, iç-içe izni, söküm toleransı, no-go ufak giriş) TEKRAR SORULMUYOR.
> Sorular yalnız aktif geliştirmenin ihtiyaç duyduğu 5 başlık.
> Özne kararı (Eren, 2026-07-22): mail BEN öznesiyle yazılır; yalnız
> hocayla ortak eylemler (konuştuğumuz kurallar, birlikte kararlaştırma)
> biz kalır.

---

Merhaba Mert Bey,

Plan7 verisini ilettiğiniz için çok teşekkür ederim. Sonuçları ve birkaç
kısa sorumu paylaşmak istedim.

## Çalışma yöntemim

Algoritmayı bugüne kadar gönderdiğiniz **Plan1, Plan2, Plan3, Deneme4 ve
Deneme5** verileri üzerinde geliştirdim. Güvenilir bir değerlendirme için
**Deneme6 ve Plan7'yi geliştirmede hiç kullanmadım**; bu iki seti, algoritma
onları daha önce hiç görmemişken, tek seferde ve hiçbir ayar yapmadan
"kör test" olarak çözdürdüm. Yani aşağıdaki sonuçlar, sistemin yeni bir
siparişi kutudan çıktığı haliyle nasıl çözeceğinin ölçümüdür.

## Kör test sonuçları

| Veri | Referans yükseklik | Benim sonucum | Fark |
|---|---|---|---|
| Plan7 (345 parça) | 595 mm | **488,4 mm** | **−%17,9** |
| Deneme6 (15 parça) | 86,32 mm | **68,5 mm** | **−%20,6** |

Her iki sonuç da daha önce konuştuğumuz kurallara uygundur: tüm parçalar
yerleşti, parça arası boşluk en az 2 mm ve tüm parçalar sökülebilir
durumda (Plan7'de 15 parça için sökümde hafif döndürme gerekiyor; kalanı
doğrudan çıkıyor). Plan7 çözümünde yasak bölge kolonunu da (önceki
planlardaki gibi) aktif tuttum. Deneme6 çözümü 29 saniyede, Plan7 çözümü
yaklaşık 1,5 saatte tamamlandı.

## Söküm planı özelliği

Bu arada sisteme yeni bir özellik ekledim: yerleşimi üretirken artık
**adım adım söküm planı** da çıkarıyorum. Plan, parçaların hangi sırayla
söküleceğini ve her parçanın nasıl hareket ettirileceğini (doğrudan yukarı
mı çekileceği, önce yana mı kaydırılacağı, hafif döndürme mi gerektiği)
tek tek listeliyor. Böylece "iç içe yerleşim serbest ama ayrılabilirlik
asıl kısıt" kuralını yalnız kontrol etmekle kalmıyorum; operatöre sökümü
nasıl yapacağını gösteren somut bir talimat da veriyorum. Yukarıdaki
Plan7 ve Deneme6 çözümlerinin söküm planları da bu şekilde üretildi.

Ayrıca sistem artık her parçanın **hangi siparişe ait olduğunu** da takip
ediyor: yerleşim çıktısında ve söküm planında parça adının yanında sipariş
bilgisi görünüyor. Böylece aynı plakada birden fazla siparişin parçaları
birlikte basıldığında, söküm sırasında hangi parçanın hangi siparişe
gideceği doğrudan listeden okunabiliyor.

Dilerseniz her iki yerleşimin STL dosyalarını ve söküm planı görsellerini
de iletebilirim.

## Sorularım

Bundan sonraki geliştirmeyi doğru yönlendirmek için beş noktada görüşünüze
ihtiyacım var:

1. **Plan7 referansının koşulları:** 595 mm'lik yerleşim Magics ile mi
   manuel mi hazırlandı? O yerleşimde parça arası boşluk değeri neydi ve
   yasak bölge kolonu dikkate alındı mı? (Kıyası birebir aynı koşullarda
   yapabilmek için soruyorum — önceki referanslar için de aynı bilgi
   [kullanılan boşluk değeri] elimde yok, paylaşabilirseniz tabloyu
   adil şekilde kesinleştireceğim.)

2. **"Konumu değişmeyecek" notu:** Adet listesinde 288101642-a2 için
   "konumu değişmeyecek" yazıyor. Tam olarak neyin sabit kalması
   gerekiyor — parçanın STL dosyasındaki plaka üzerindeki yeri mi, yoksa
   duruş açısı/yönelimi mi? Bu parçadan 6 adet var; altısının da aynı
   kurala mı tabi olduğunu ve birbirlerine göre nasıl konumlanmaları
   gerektiğini öğrenebilir miyim? (Sisteme "sabit konumlu parça"
   özelliğini ekliyorum; kuralı doğru kurgulamak istiyorum.)

3. **Parça bazlı yön kısıtları:** Daha önce bazı parçaların yalnız dikey
   veya yatay üretilebildiğini belirtmiştiniz. Plan7 parçalarından bu
   şekilde yön kısıtı olan var mı? 488,4 mm'lik çözümümde serbest
   döndürme kullanıldı; kısıtlı parça varsa bildirmenizi rica ederim,
   çözümü o kısıtlarla tekrar üretirim. (İleride her sipariş için bu
   bilgiyi adet listesiyle birlikte alabileceğim basit bir işareti de
   birlikte kararlaştırabiliriz — örn. parça adının yanına "dik"
   yazılması yeterli.)

4. **Yeni veri:** Test havuzumu büyütmek istiyorum. Uygun gördüğünüzde
   yeni siparişleri — mümkünse Magics veya manuel referans yükseklikleriyle
   birlikte — paylaşmaya devam ederseniz çok sevinirim. Elimdeki
   siparişler ağırlıkla orta boy karışık parçalardan oluşuyor; algoritmayı
   gerçekten genelleştirebilmek için özellikle şu karakterlerde örnekler
   benim için çok değerli olur:
   - **İnce cidarlı / kabuk parçalar** (sac benzeri, çan/kapak formları),
   - **Boru ve içi boş silindirik parçalar** (iç içe yerleşim potansiyeli
     yüksek olanlar),
   - **Uzun-ince çubuk/profil parçalar** (plaka boyuna yakın uzunlukta),
   - **Az sayıda çok büyük parça** içeren siparişler (plakayı 1-2 parçanın
     domine ettiği durum),
   - **Tek parçanın çok yüksek adetle tekrarlandığı** siparişler
     (yüzlerce adet aynı parça).
   Bu verilerin benim için değeri yalnız test etmekten ibaret değil.
   Sistemde makine öğrenmesi tabanlı bir **strateji seçim modeli** var:
   siparişin parça karakterine bakıp o sipariş için en uygun yerleştirme
   stratejisini seçiyor ve gerçek koşu sonuçlarıyla eğitiliyor. Ayrıca
   gönderdiğiniz her gerçek veri ailesini örnek alarak benzer karakterde
   **çok sayıda sentetik sipariş üretiyorum**; bir geliştirmenin tek bir
   siparişe özgü kalmayıp o ailenin tamamına genellendiğini bu sentetik
   havuz üzerinde doğruluyorum. Bu yüzden farklı karakterde tek bir
   gerçek sipariş bile — sentetik türevleriyle çoğaltıldığı için — o
   ailenin tümü adına kazanım sağlıyor ve algoritmanın zayıf noktalarını
   kapatmamı doğrudan hızlandırıyor.

5. **Gönderim biçimi:** Bundan sonraki siparişler/parçalar genellikle
   Google Drive linkiyle mi gelecek, yoksa doğrudan e-posta eki (ZIP)
   olarak mı? Sipariş alma tarafını otomatikleştiriyorum; hangi biçim
   sizin için pratikse sistemi ona göre ayarlayacağım.

İyi çalışmalar, saygılarımla,

Eren

---

> İç not (maile girmez): Şerh durumu — 595 ve 86,32 referanslarının
> koşulları bilinmediğinden iki kıyas da şerhli; soru 1 cevabı gelince
> şerh kalkar/kesinleşir. Pin kısıtı 488,4'te uygulanmadı (soru 2 cevabı +
> K-56g kablosu bekliyor); oryantasyon kısıtı bilinmiyor (soru 3).
> d4 220,7 güncellemesi bu maile bilinçli KONMADI (ayrı konu, hoca son
> bildiği 229,3'ü kabul etti; güncelleme bir sonraki kapsamlı raporda).

# Mail Taslağı — 2026-07-25 (rev. 2026-07-26; GÖNDERİM EREN ONAYINDA)

> Alıcı: Mert Bey (mcoskun@fsm.edu.tr) · Konu: RE: Plan1 ve Plan 3 Nesting —
> Yerleşim STL'leri ve söküm planları
>
> İç not (maile girmez): Bu mail 2026-07-22 cevabının borçlarını kapatır:
> (1) Plan7 + Deneme6 STL/söküm paketi teslimi ("cihazın programında kontrol
> etmek verimli olur"), (2) a2 duruş-kilidi teyidi + kısıtlı çözüm, (3) ortak
> Drive klasörü cevabı. Paket toplam **1,1 GB** (deneme6 ASCII 179MB + plan7
> tip-başına binary 872MB + rehberli söküm HTML'leri 17+36MB) → mail eki
> İMKÂNSIZ, Drive zorunlu.
>
> **KARAR NOKTALARI — HEPSİ KAPANDI (Eren, 2026-07-26):**
> - **K1 — a2-kısıtlı çözüm:** MAİL ŞİMDİ GİTSİN; kısıtlı çözüm sakin-makine
>   seansında koşulup aynı klasöre eklenecek ("önümüzdeki günlerde" sözü
>   metinde duruyor — bu bir TAAHHÜT, seans planlanmalı).
> - **K2 — ortak Drive klasörü:** KABUL (tek-kanal otomasyon avantajı).
> - **K3 — d4 220,7 güncellemesi:** MAİLE GİRMEDİ; bir sonraki kapsamlı
>   raporda sunulacak.
> - **K4 — kapalı-kavite sorusu:** metinde VAR (soru 2).
> - **K5 — rehberli söküm HTML:** İKİ SÜRÜM DE PAKETTE (deneme6 17,1MB +
>   plan7 36,2MB, 2026-07-27 üretildi). Plan7 rehberi tarayıcıda açılıp
>   doğrulandı (345 adım, teslim planıyla birebir sıra/kapsam, konsol temiz).
>   Söz verilen iş yapıldı — taahhüt listesinden DÜŞTÜ.
>
> **⚠️ DÜZELTME (2026-07-26):** Bu taslağın ilk hâli ve 2026-07-21'de
> GÖNDERİLEN mail, Plan7 için "15 parça hafif döndürme gerektiriyor" diyordu.
> Teslim edilen söküm planı belgesi ise 344 doğrudan / **1 döndürmeli**
> (174100684-a, Z 1°) diyor. Kaynak: `kilit_5yon=15` (kaba 5-yön ön-denetimi)
> ama `rot_cert=1`, `rot_kilit=0` — 15'in 14'ü ayrıntılı denetimde doğrudan
> çıkıyor. Hoca dosyayı açınca çelişkiyi göreceği için metne açık düzeltme
> cümlesi kondu.

---

Merhaba Mert Bey,

Geçen haftaki ayrıntılı cevaplarınız için çok teşekkür ederim; özellikle
"konumu değişmeyecek" ifadesinin duruş açısı anlamına geldiğini netleştirmeniz
sistemi doğru kurgulamam için çok değerli oldu.

## Yerleşim STL'leri ve söküm planları

İstediğiniz dosyaları hazırladım. Toplam boyut 1 GB'ın üzerinde olduğu için
e-posta ekine sığmıyor; önerdiğiniz **ortak Drive klasörü** fikrini bu
vesileyle memnuniyetle kabul ediyorum — bir klasör açıp sizinle paylaşıyorum,
bundan sonraki tüm dosya alışverişimizi (sizden gelen planlar, benden giden
yerleşimler) oradan yürütebiliriz.

Klasörde şunlar var:

- **Deneme6 (68,5 mm yerleşim):** Tek STL dosyası. Daha önce konuştuğumuz
  gibi her parça dosyanın içinde kendi adıyla ayrı bir katı (solid) olarak
  yazılı — Magics'te açtığınızda parça adlarını ve adetlerini doğrudan
  görebilirsiniz.
- **Plan7 (488,4 mm yerleşim):** Parça tipi başına ayrı STL, 10 dosya
  (toplam 872 MB). Hepsini birlikte içe aktardığınızda 345 parçalık tam
  yerleşimi verir. Burada Deneme6'dan farklı olarak ikili (binary) format
  kullandım: yerleşimde 17,4 milyon üçgen var, metin formatında dosya
  yaklaşık 4,9 GB tutuyordu. İkili formatta parça adı yazılabilecek tek bir
  başlık alanı bulunduğu için de tip başına böldüm; her dosyanın başlığında
  parça adı ve adedi yazılı, ayrıca dosya adlarında da görünüyor.
- **Her iki yerleşim için adım adım söküm planı** (okunabilir metin olarak):
  parçaların hangi sırayla çıkarılacağı ve her parçanın nasıl hareket
  ettirileceği (doğrudan yukarı / önce yana kaydırma / hafif döndürme)
  tek tek listeli. Plan7'de 345 parçanın 344'ü doğrudan çekilerek çıkıyor;
  yalnızca bir parça (174100684-a) çıkarken 1 derecelik hafif bir döndürme
  istiyor. Deneme6'da parçaların tamamı doğrudan çıkıyor.

  Bir düzeltme: geçen mailimde Plan7 için bu sayıyı 15 olarak yazmıştım.
  O 15, kaba ön denetimde "sıkışık" görünen parça sayısıydı; ayrıntılı
  söküm denetimini tamamlayınca bunların 14'ünün de doğrudan çıktığı,
  yalnız birinin döndürme istediği ortaya çıktı. Klasördeki plan bu son
  hâli gösteriyor.
- **Her iki yerleşim için etkileşimli söküm rehberi**
  (`deneme6_68p5_rehberli_sokum.html` ve `plan7_488p4_rehberli_sokum.html`):
  tarayıcıda çift tıklayarak açabileceğiniz tek bir dosya — kurulum ya da
  internet bağlantısı gerektirmiyor. Yerleşimi üç boyutlu gösteriyor;
  adımlarda ilerledikçe sırası gelen parçayı vurgulayıp hangi yöne
  çekileceğini yazıyor. Sahadaki operatör için düşündüğüm biçim bu — sizin
  için de yararlı olur mu, merak ediyorum. (Görüntüde parçalar, dosya
  tarayıcıda akıcı açılsın diye kabalaştırılmıştır; ölçüye esas geometri
  STL dosyalarındadır.)
- Yerleşim koordinat listeleri (JSON) — programatik kontrol isterseniz.

## a2 parçası (duruş kilidi)

288101642-a2'nin yatay imal edilmesi gerektiğini not ettim; sisteme
parça-bazlı duruş kilidi özelliğini ekledim (parçanın geldiği duruş açısı
korunuyor, plaka üzerindeki yeri ve yüksekliği serbest kalıyor).

Şunu açıkça belirtmek isterim: klasördeki 488,4 mm'lik yerleşim, bu kural
bana ulaşmadan önce çözüldüğü için a2 parçalarını serbest duruşta
yerleştiriyor — altı kopyadan beşi sizin belirttiğiniz duruşta değil.
Dosyaları incelerken bunu göz önünde bulundurmanızı rica ederim. Plan7'yi
duruş kilidiyle yeniden çözüp sonucu ve güncel STL'leri önümüzdeki günlerde
aynı klasöre ekleyeceğim; asıl kıyaslanması gereken yerleşim o olacak.

## İki kısa sorum

1. **Eski referansların boşluk değeri:** Plan7 için 2 mm üzerinde
   anlaşmıştık. Elinizdeki eski referans yerleşimlerin (özellikle Deneme5'in
   209 mm'si) hangi parça-arası boşlukla hazırlandığını öğrenme şansımız
   var mı? Karşılaştırma tablomu birebir aynı koşullara oturtmak için hâlâ
   bu tek bilgi eksik.

2. **Kapalı boşluk / toz tahliyesi:** İç içe yerleşimde, çok nadiren de olsa
   parçalar arasında tozun hiçbir açıklıktan tahliye edilemeyeceği tamamen
   kapalı bir boşluk oluşabilir. Sisteme bunu tespit eden bir denetim
   ekledim; sormak istediğim: üretimde böyle bir durum kabul edilebilir mi,
   yoksa tümüyle mi kaçınmalıyım? Belirli bir hacim ya da minimum açıklık
   eşiği var mıdır?

Dosyalara göz atma fırsatı bulduğunuzda geri bildiriminizi çok merak
ediyorum — özellikle söküm planının sahada işinize yarayıp yaramayacağı
benim için önemli bir tasarım sorusu.

İyi çalışmalar, saygılarımla,

Eren

---

> İç not (maile girmez): **Gönderilecek klasör (2026-07-27 taşındı) =
> `C:\Users\erenk\OneDrive\Masaüstü\Veriler\hoca_paketi_2026-07\`** — artık
> repo içinde DEĞİL, ham veri setlerinin yanındaki ortak `Veriler\` klasöründe
> (21 dosya, 1,04 GB). D:\ie488\results\hoca_paketi_2026-07\ eski kopya:
> STL/plan aynı, rehberli-söküm HTML'leri orada YOK. İçerik dosya üzerinde
> DOĞRULANDI:
>   - `deneme6_68p5_yerlesim.stl` 179,2 MB — ASCII multi-solid, **15 solid**,
>     her solid adı parça kimliğini taşıyor (Magics'te ayrı parça olarak açılır).
>   - `plan7_488p4_stl\` **10 binary STL, 872 MB**, toplam 17,44M üçgen;
>     her dosyanın 80-byte header'ında parça adı + adet (`174100684-a_x22`).
>   - `*_sokum_plani.md` + `.json` (plan7: 344 düz / 1 döndürmeli — Z 1°,
>     çıkış yönü +X; deneme6: 15/15 düz) · `*_placements.json`.
>   - `deneme6_68p5_rehberli_sokum.html` 17,1 MB + `plan7_488p4_rehberli_sokum.html`
>     36,2 MB (çevrimdışı, tek dosya, three.js gömülü) + `*_adimlar.json`.
>     Plan7 rehberi tarayıcıda doğrulandı: 345 adım, teslim planıyla birebir
>     sıra ve kapsam, 1 döndürmeli parça 331. sırada, konsol temiz.
> **Toplam paket 1,1 GB.**
> Drive'a yükleme + klasör paylaşımı EREN tarafından yapılacak (Claude'un
> Drive yazma erişimi kullanılmayacak — hoca içeriği). **Sıra: önce ortak
> klasörü aç + yükle, sonra maili gönder** (metin "bir klasör açıp sizinle
> paylaşıyorum" diyor).
> Şerh/taahhüt durumu: 488,4 kısıtsız koşudur; **kalan tek taahhüt = a2
> duruş-kilitli çözüm** (sakin-makine seansı, RAM ≥4 GB, ~1,5-2 saat +
> paket üretimi). Ölçüldü (2026-07-27): mevcut çözümde a2'nin 6 kopyasından
> 5'i duruş kısıtına aykırı (oi 8/8/12/12/15; izinli küme {0,1,4,5}) —
> yeniden çözüm gerçek bir borç, metinde açıkça yazıldı.
> Rehber üretiminde çıkan iki kod hatası düzeltildi (bkz. DURUM.md):
> kabalaştırma yolu + görsel denetimin parça elemesi.
> Soru 1 cevabı gelirse eski-set kıyas şerhleri (A10) tamamen kapanır.

# Literatur Notu — IE 488 Donem Projesi

> Kapsam: 3 makale — M1 (Tang 2025), M2 (Calabrese 2022), M3 (Araujo 2019). Blok 5'te tamamlandi.

---

## M1 — Tang vd. 2025

**Tam referans:**
Tang, A., Fu, G., Zhang, T., Song, P., Xiao, X., Peng, Q., Mo, T., Zhang, A., & Zhang, Z.
(2025). Nesting Problems in Additive Manufacturing: Classification and Review.
*Journal of Computing and Information Science in Engineering*, ASME.
doi:10.1115/1.4070330

---

### Ozet

Tang vd. (2025), eklemeli imalat (AM) alanindaki nesting problemlerini kapsamli bicimde ele alan bir derleme ve siniflandirma calismasi sunmaktadir. Yazarlar 1997-2024 araliginda yayimlanmis 75 makaleyi tarayarak, her biri farkli bir problemi temsil eden 8 sinif koduna gore kategorize etmistir.

#### 3 Boyutlu Siniflandirma Cercevesi

Makale, nesting problemlerini uc temel boyut uzerinden siniflandirir:

1. **Image Mapping (Parca Temsili)** — Parcayi matematiksel olarak nasil temsil ederiz?
2. **Nesting Stratejisi** — Yerlestirme sureci nasil yurutulur?
3. **Optimizasyon Algoritmasi** — Hangi hesaplamali yontem kullanilir?

Her boyuttaki ikiser secenek sekiz kod sinifi olusturur:

| Kod | Aciklama |
|---|---|
| E\\P\\S | Extended image mapping / Pure placement / Single algorithm |
| E\\P\\M | Extended image mapping / Pure placement / Multiple algorithms |
| E\\I\\S | Extended image mapping / Integrated nesting / Single algorithm |
| E\\I\\M | Extended image mapping / Integrated nesting / Multiple algorithms |
| N\\P\\S | Non-extended image mapping / Pure placement / Single algorithm |
| N\\P\\M | Non-extended image mapping / Pure placement / Multiple algorithms |
| N\\I\\S | Non-extended image mapping / Integrated nesting / Single algorithm |
| N\\I\\M | Non-extended image mapping / Integrated nesting / Multiple algorithms |

#### Image Mapping (Boyut 1)

**E-IM (Extended Image Mapping):** Parcayi kaplayan duzenli bir geometrik sekil (ornegin dikdortgen veya kup) kullanir. Temsil edilen alan, parcain gercek alanından buyuktur. AABB (Axis-Aligned Bounding Box), 2D ve 3D nestingde en yaygin E-IM bicimidir. Makale AABB'yi "en eski ve en basit yontem" olarak tanitir: yalnizca genislik, yukseklik ve derinlik bilgisi saklanir, eksen hizalamasiyla hesaplama maliyeti minimaldır. Duzensiz geometriler icin bos alan kaybi fazla olsa da uygulamasi kolayligi nedeniyle bascalangic arastirmalarda tercih edilmektedir.

**N-IM (Non-Extended Image Mapping):** Gercek parca geometrisine yakin temsil yontemleri icermektedir: 2D'de poligon ve raster, 3D'de polyhedron, voxel ve kurecik agaclari (sphere trees). Bu yontemler daha yuksek geometrik dogruluk saglar; ancak cakisma hesaplamalarinin maliyeti E-IM'e kiyasla belirgin sekilde artar.

#### Nesting Stratejisi (Boyut 2)

**P-N (Pure Placement Nesting):** Parca yonelimi onceden sabit kabul edilir; algoritma yalnizca konumlandirma problemini cozer. Uygulamasi basit, literaturde en kalabalik sinif.

**I-N (Integrated Nesting):** Parca yonelimi ve konumlandirma birlikte optimize edilir. Daha iyi doluluk orani saglar; hesaplama karmasikligi artmaktadir.

#### Optimizasyon Algoritmasi (Boyut 3)

**S-OA (Single Optimization Algorithm):** Tek bir yontem — metasezgisel (GA, SA), sezgisel kurallar, makine ogrenmesi veya matematiksel programlama.

**M-OA (Multiple Optimization Algorithms):** Birden fazla yontemi birlestiren hibrit yaklasimlar; karmasik dinamik problemlerde daha etkili.

#### NfAM ve NSfAM Ayirimi

Makale iki ust-kategori de tanimlar:

- **NfAM (Nesting for AM):** Yalnizca yerlesim optimizasyonu; tek veya cok platform uzerinde parcalarin konumlandirilmasi.
- **NSfAM (Nesting and Scheduling for AM):** Yerlesim ile birlikte makine atamasi, gorev onceliklendirme ve zaman penceresi kisitlarini da kapsar.

Bu prototip NfAM kapsamindadir: tek bir build platform, birden cok parca, scheduling yok.

---

### Prototipe Yansimasi

Bu prototip, Tang vd.'nin siniflandirma cercevesinde **E\\P\\S kutusuna** konumlanmaktadir:

- **E-IM:** Parca temsili AABB'dir — her parca `(width_mm, height_mm)` ikilisiyle saklanir. Makale bu yontemi "en erken, en yaygin" olarak tanimlamaktadir; 48 saatlik prototip icin savunulabilir ve implementasyonu en kisa sectim budur.
- **P (Pure Placement):** Build oryantasyonu onceden sabit ({0 derece, 90 derece} arasinda enumeration). Yonelim ve konumlandirma birlikte optimize edilmez; sadelik nedeniyle P-N secildi.
- **S (Single Algorithm):** Tek bir constructive heuristic — Bottom-Left (BL). Ikinci heuristic (BFD) zaman kalirsa Blok 4'te eklenecek; o durumda da S sinifinda kalir (iki ayri kosu, hibrit degil).

E\\P\\S kutusu literaturde en kalabalik sinif oldugu icin bu konumlanma hocaya soylu bir baslangic noktasi olarak sunulabilir: "en temel, en belgelenmus, en kolay iterasyona acik" konumdur.

---

## M2 — Calabrese vd. 2022

**Tam referans:**
Calabrese, M., Primo, T., Del Prete, A., & Filitti, G.
(2022). Nesting algorithm for optimization part placement in additive manufacturing.
*The International Journal of Advanced Manufacturing Technology*, 119, 4613–4634.
doi:10.1007/s00170-021-08130-y

---

### Ozet

Calabrese vd. (2022), additive manufacturing icin bir on-hesaplama (previsional) model gelistirmeyi amaclamaktadir; bu modelin cekirdeginde bir nesting algoritmasi yer almaktadir. Algoritmanin temel gorevi, verilen bir yazici tablasi uzerinde kac adet ayni parcayi basmak mumkun oldugunu hizla tahmin etmek ve bu sayiyi (m) maliyet, uretim suresi ve teknoloji uyumlulugu gibi dokuz Anahtar Performans Gostergesi (KPI) hesabina girdirmektir. Yazar grubu dikdortgen ve dairesel tablalar icin iki ayri alt-algoritma tanimlamistir; her iki durumda da parca geometrisi sinirlayi kutu (bounding box) boyutlariyla temsil edilmekte, tablaya kenarlardan birakilan bosluk (gapB), parcalar arasi yatay ve dikey mesafeler (gapX, gapY) ise parametrik girisler olarak kullanicidan alinmaktadir. Dikdortgen tabla durumunda algoritma, iki oryantasyon senaryosunu (xc ekseni boyunca, yc ekseni boyunca) ayri ayri hesaplayarak hangisi daha fazla parca sigdiriyorsa onu secmektedir; yani rotation karari ikili karsilastirma ile belirlenmektedir. Kritik bir sinirlik olarak, bu algoritma yalnizca ayni olcudeki parcalara uygulanmak uzere tasarlanmistir ve iteratif optimizasyon icermez — kapatilmis-form (closed-form) geometrik formuller araciligiyla tek adimda bir parca sayisi tahmini uretir. Algoritma once TCL dilinde Altair HyperMesh ortaminda gelistirilmis, ardindan AMSA bulut platformuna entegrasyon icin Java'ya aktarilmistir.

---

### Prototipe Yansimasi

Bu makale ile prototip arasindaki ortusme noktalari ve ayrisma noktalari dogrudan not edilmesi gereken bir farkliligi da barindirir.

**Ortusen noktalar:** Parca temsili olarak bounding box kullanimi her iki calismada da ortaktir; makale bounding box'i "bilesenin plan boyutlarini tanimlayan temel veri" olarak konumlandirmaktadir, bu da prototipin E-IM (AABB) kararini destekler. Tablo kenari icin parametrik bosluk (gapB), prototipteki 1 mm kenar payi ile dogrudan eslesmektedir. Iki oryantasyon senaryosunu karsilastirarak en iyisini secme yaklasimi, prototipin {0 derece, 90 derece} enumeration kararinin geometrik gerekcelesiyle uyusur.

**Ayrisan nokta — PLAN.md beklentisi gerceklesmedi:** PLAN.md §3'te M2 icin "constructive yerlestime adimi + objective fonksiyonu + rotation enumeration + siralam kriteri (alan azalan / en uzun kenar azalan)" icerigi bekleniyordu. Ancak bu makale yalnizca ayni boyutlu parcalar icin tasarlanmis, siralam icermeyen, iteratif olmayan bir geometrik kestirim aracini tanimlamaktadir. Siralam karari (buyukten kucuge alan sirasi) icin M2 dogrudan referans gosterilemez; bu karar Bottom-Left ve Best-Fit Decreasing literaturunun genel uygulamasina dayali pratik bir secimdir.

---

## M3 — Araujo vd. 2019

**Tam referans:**
Araujo, L.J.P., Ozcan, E., Atkin, J.A.D., & Baumers, M.
(2019). Analysis of irregular three-dimensional packing problems in additive manufacturing: a new taxonomy and dataset.
*International Journal of Production Research*, 57(18), 5920–5934.
doi:10.1080/00207543.2018.1534016

---

### Ozet

Araujo vd. (2019), AM alanindaki uc boyutlu duzensiz istif (3DIP) problemleri icin mevcut kesme-ve-yerlestime taksonomilerini — Dyckhoff (1990) ve Wascher vd. (2007) — genisletip AM'e ozel bir dortlu-tuple notasyonu (D|C|B|A) onerir. Birinci eleman D, problemin boyutluluğunu ifade eder (2+1, 3 gibi); ikinci eleman C, optimizasyon olcutunu tanimlar (Cikti Maksimizasyonu Ou, Tek-giris Minimizasyonu Si, Paralel Maliyet Cp, Paralel Sure Tp); ucuncu eleman B, tablasanin tipini gosterir (sabit tek tabla Of, degisken yukseklikli Oo, cok ayni I, cok heterojen H); dorduncu eleman A ise parcalarin talep degiskenligi ile geometrik karmasikligini ikili duzey (dusuk/yuksek) olarak kodlar (ll, lh, hl, hh). Makale ayrica mevcut veri setlerinin gercek AM senaryolarini yeterince kapsamamadigini gostermekte ve bu eksikligi gidermek uzere 435 model ile 2.343 ornek iceren A2018 veri setini yayimlamaktadir. Deneysel bolumde Deepest Bottom-Left with Fill (DBLF) ve duvar-insaasi tabanli (WBA) iki sezgisel yontem karsilastirilmis; parcalarin yuzey karmasikliginin DBLF calisma suresini guclu bicimde etkiledigi gosterilmistir.

---

### Prototipe Yansimasi

Bu makalenin taksonomi cercevesi, prototipin literaturdeki konumunu hassas bir sekilde tanimlamaya dogrudan olanak tanir. Prototip, Araujo vd.'nin notasyonunda **2+1|Ou|Of|ll** olarak siniflandirilabilir: boyut 2+1 (parcalarin dikey izdusumu XY platformunda cozulur — FDM ve resin vat teknolojilerine ozgu), Ou (tek tablaya sigdirilamayan parcalar icin cikti maksimizasyonu), Of (sabit boyutlu tek tabla), ll (dusuk talep degiskenligi + dusuk geometrik karmasiklik, cunku test parcalari rastgele dikdortgenlerdir). Tablo 2'de Araujo vd. ll sinifi icin "Deepest Bottom-Left gibi yerlestirme sezgisellerinin iteratif uygulamasi" yapilmasini onermektedir; bu, prototipin Bottom-Left heuristic secimini dogrudan destekleyen literatur kanitini saglar. Makalede ayrica FFD (First Fit Decreasing) ile DBLF kombinasyonunun kullanildigi belirtilmektedir; bu kombinasyon prototipin BFD adayiyla kavramssal olarak ayni ailededir. Gelecek hafta 3D'ye gecis planlanirsa A2018 veri seti gercekci test parcalari olarak kullanilabilir; ancak bu adim kapsamdisi olarak etiketlenmis durumdadir.

# ARAŞTIRMA — Nesting Literatür Sentezi (Magics açığını kapatma)

> Deep-research çıktısı, 2026-06-21. 22 peer-reviewed kaynak, 106 iddia,
> 25 çekişmeli doğrulama (24 onaylı / 1 çürütüldü). Branch: `app-demo-build`.
> Amaç: bizim 3B nesting motorunun Magics'e göre kalite (621 vs 492 = 1.26×,
> doluluk %8) ve hız (Plan2 ~78dk) açığını akademik literatürle kapatmak.
> İlgili: PLAN_KIYAS_IYILESTIRME.md, project-kiyas-iyilestirme memory.

---

## TL;DR (yönetici özeti)

İki açığımızın da literatürde **net, peer-reviewed çözüm yolu** var:

- **KALİTE açığının kök çözümü:** ayrık poz enumerasyonunu (28 sabit poz, n_orientations=4)
  bırakıp konum + yönelimi **sürekli karar değişkeni** olarak modellemek →
  **doğrusal-olmayan optimizasyon (NLP)**. Stoyan/Romanova/Bennell grubunun
  **quasi-phi-function** tekniği (concave polihedra, sürekli rotasyon, asgari
  mesafe) literatürde **%16–28 iyileşme** raporluyor — tam bizim 1.26×'i kapatacak
  büyüklük.
- **En düşük-efor / en yüksek-değer giriş:** **COMPOLY** tarzı *compaction* —
  mevcut heightmap çözümümüzü **fizibıl başlangıç noktası** alıp üstüne sürekli-
  rotasyon NLP sıkıştırma katmanı ekler. Motoru atmadan iyileştirme.
- **DOLULUK (%8) kök çözümü:** heightmap "üstten düşürme"yi **gerçek 3B çakışma**
  ile değiştirmek → çıkıntı-altı / oyuk-içi (cavity-aware / part-in-part) yerleşim
  (Ikonen GA, NFP+guided local search). En yüksek efor, mimari değişim.
- **HIZ açığı (270M voxel):** **per-part (heterojen) çözünürlük** (ince 1mm parça
  tüm grid'i 0.5mm'ye zorlamasın) + **octree** / önceden-hesaplı **Nofit-Voxel (NFV)**
  ile O(1)'e yakın çakışma testi + **COMPOLY** ile O(n²)→O(n) ölçek indirgemesi.

**Kritik içgörü:** rotasyon TEK kol değil. Kalite = rotasyon **+** gerçek-3B
çakışma (cavity-aware) **birlikte**. NFV hız katmanı sabit yönelimlidir → kalite
(rotasyon) katmanıyla beraber kullanılmalı.

---

## ALAN 1 — Sürekli rotasyon / NFP-3D / phi-functions

**(a) En güçlü yöntem:** Stoyan/Romanova/Pankratov/Bennell grubunun **phi-function**
ve radical-free **quasi-phi-function** tekniği.

**(b) Nasıl çalışır:** Parçalar polihedra ile yaklaşıklanır; çakışmama + kapsama
(containment) + asgari-mesafe kısıtları phi/quasi-phi ile **analitik (kapalı-form)
eşitsizlikler** olarak yazılır. Konum VE yönelim (rotasyon açıları) **sürekli**
karar değişkenidir; problem bir **NLP**'ye indirgenip yerel optimizasyonla (IPOPT)
çözülür — milyonlarca ayrık poz enumere edilmez. Quasi-phi, yardımcı (ayırıcı
düzlem) değişkenleri ekleyerek formülleri basitleştirir → off-the-shelf NLP çözücü.

**(c) Kazanç:** Literatür örneklerinde kapsayıcı hedefinde önceki yöntemlere göre
**%16.35–27.88 iyileşme** (N=20/40 concave polihedra).

**(d) Entegrasyon:** Mevcut voxel-heightmap çözümünü **fizibıl başlangıç** alıp
üstüne sürekli-rotasyon NLP compaction (quasi-phi + IPOPT) ekle.

**(e) Değer/efor:** YÜKSEK kalite-kazancı, ORTA-YÜKSEK efor. Ölçeklenme (226 parça)
için kademeli/compaction şart.

**Kaynaklar:** Romanova, Bennell, Stoyan, Pankratov (2018) **EJOR** 268(1):37-53
(White Rose eprint); JORS 67(5):786-800 (2016); J. Global Optimization (2015/16).

---

## ALAN 2 — AM build-volume / build-plate packing (tam bizim problem)

**(a) En güçlü/standart:** (i) AM'ye özel **asgari-YÜKSEKLİK** sürekli-rotasyon
phi-function NLP (Litvinchev/Pankratov/Romanova 2019, IFAC); (ii) yaygın pratik:
**Deepest-Bottom-Left-Fill (DBLF)** + **Genetik Algoritma (GA)**.

**(b) Nasıl çalışır:** phi-NLP parçaları min-yükseklikli kutuya sürekli rotasyon+
ötelemeyle yerleştirir (build-height = katman/çalıştırma sayısı). DBLF+GA voxel
temsille parçaları derin-sol-alt köşeye düşürüp sıra/yönelimi GA ile arar.

**(c) Durum:** phi-NLP AM'yi açıkça motivasyon sayar, build-height minimize eder.
**DBLF deneysel olarak SINIRLI:** non-convex parçalarda optimal paketleme bulamaz,
"daha esnek/akıllı yerleştirme stratejileri" gerekir (bizim drop motorumuzun
tanısını doğrudan teyit eder).

**(d) Entegrasyon:** Hedefimiz (min build-height) phi-NLP min-height formülasyonuyla
**birebir** örtüşür.

**(e) Değer/efor:** phi-NLP min-height = YÜKSEK değer (doğrudan hedef), ORTA-YÜKSEK
efor; DBLF+GA = mevcut yapıya yakın, düşük efor, düşük kalite tavanı.

**Kaynaklar:** Litvinchev/Pankratov/Romanova, **IFAC-PapersOnLine** 52-13 (2019);
Araujo et al. **IJPR** 58(22):6917-6933 (2020), Nottingham OR grubu.

---

## ALAN 3 — Coarse-to-fine / sürekli rotasyon optimizasyonu (0.5–1°)

**(a) En güçlü:** Yönelimi ayrık poz değil **sürekli karar değişkeni** olarak
optimize etmek (hibrit sürekli+kombinatoryal; phi-NLP veya CGF hibrit).

**(b) Nasıl çalışır:** Ma/Chen/Hu/Wang (CGF 2018, HKU) hibrit yöntem konum+yönelimi
**sürekli optimizasyonla** iyileştirir, ardından kombinatoryal adımla (swap/replace/
insert) boşlukları azaltır. Sürekli optimizasyon herhangi bir 0.5–1° ızgarayı
**matematiksel olarak kapsar** (alt-derece hassasiyet otomatik gelir).

**(c) Kazanç:** En genel 3B düzensiz paketlemeyi (keyfi kapsayıcı + keyfi parça +
serbest rotasyon) çözer. Danışmanın "neredeyse sürekli rotasyon" gereğini karşılar.

**(d) Entegrasyon:** Kaba 90° + birkaç eğik pozu, **kazanan kaba açının etrafında
sürekli yerel optimizasyon** (gradient/yerel arama) ile değiştir — coarse-to-fine.

**(e) Değer/efor:** YÜKSEK değer (rotasyon kök sebep), ORTA efor (yerel-optimizasyon
katmanı; tüm motoru değiştirmeden).

**Kaynaklar:** Ma, Chen, Hu, Wang, **Computer Graphics Forum** 37(5):49-59 (2018),
"Packing Irregular Objects in 3D Space via Hybrid Optimization" (Eurographics SGP);
EJOR 2018.

---

## ALAN 4 — Sparse voxel / octree çakışma + per-part çözünürlük + NFV (HIZ)

**(a) En güçlü:** (i) **Nofit-Voxel (NFV)** = 2B nofit-polygon'un 3B uzantısı,
voxel-tabanlı çakışma primitifi; (ii) **octree** hiyerarşik uzay bölme.

**(b) Nasıl çalışır:** NFV_{p,q}, q'nun referans noktası bu küme içindeyse p ile q
**kesin çakışır** — çakışma testi tek nokta-içinde-mi sorgusuna iner (önceden
hesaplanır). Octree (Cagan SA) 3B uzayı hiyerarşik bölerek çok hızlı overlap testi
sağlar; sadece gereken derinliğe iner.

**(c) Kazanç:** Octree "very fast detection of overlaps". NFV INFORMS Operations
Research'te yayımlı. **UYARI:** NFV yönelimi SABİT — rotasyon optimize etmez → Alan
3 ile birlikte kullanılmalı (NFV hız, NLP/sürekli-rotasyon kalite).

**(d) Entegrasyon:** Uniform 0.5mm global pitch yerine **per-part çözünürlük** (ince
parça tüm grid'i zorlamasın); çakışmayı octree/NFV ile yap. 270M voxel / dakikalar
darboğazını doğrudan hedefler.

**(e) Değer/efor:** HIZ için YÜKSEK değer / ORTA efor (rotasyonu çözmez).

**Kaynaklar:** Lamas-Fernandez, Bennell, Martinez-Sykora, **Operations Research**
(INFORMS, 2022); Cagan et al. CAD 30(10):781-790 (1998); Araujo et al. SFF 2015.

---

## ALAN 5 — Cavity-aware / part-in-part 3B nesting (DOLULUK kök çözümü)

**(a) En güçlü:** (i) **Ikonen GA** — non-convex parçaları oyuk/delik (cavities &
holes) ile paketler; (ii) **NFP + guided local search (GLS)**.

**(b) Nasıl çalışır:** Ikonen GA gerçek CAD dosyaları üzerinde computational-geometry
kesişim testleriyle parçaları "ağırlıksız ortamda yüzer gibi" herhangi konum/yönelimde
yerleştirir — **heightmap drop DEĞİL, gerçek 3B çakışma** — ve bir parçanın oyuğuna
başka parça oturtabilir. NFP+GLS non-convex polygon + **iç delikleri** işler.

**(c) Kazanç:** **%8 doluluk darboğazının kök çözümü** — Magics'in "gerçek 3B
kilitleme" davranışının akademik karşılığı.

**(d) Entegrasyon:** Heightmap drop yerine analitik/geometrik çakışma testi (phi
veya CAD-mesh kesişim) + parça iç-boşluklarını (cavity) açıkça temsil + part-in-part
yerleştirme arama.

**(e) Değer/efor:** Kalite için ÇOK YÜKSEK değer, YÜKSEK efor (drop paradigmasından
gerçek-3B-çakışmaya **mimari değişim**).

**Kaynaklar:** Ikonen et al. ICGA 1997; Araujo et al. SFF 2015 (NFP+GLS).

---

## ÇERÇEVE — AM nesting taksonomisi (problemi konumlandırma)

Oh, Witherell, Lu, Sprock (2020), "Nesting and Scheduling Problems for Additive
Manufacturing: A Taxonomy and Review", **Additive Manufacturing** Vol 36 (NIST,
Elsevier). AM nesting/çizelgeleme literatürünü Part/Build/AM-Machine üç boyutu
üzerine taksonomiyle (6 sınıf + 8 kriter, 53 makale) organize eder. **"Nesting for
AM (NfAM)"** sınıfı = tam bizim çoklu-parça tek-build-plate problemimiz.

---

## BONUS — Magics akademik karşılığı + bilinen gap teyidi

Magics SmartNesting/Sinter'in iç algoritması **ticari/yayımlanmamış** (medium güven
çıkarım). Ancak yayımlanmış büyük AM yöntemleri de kaba ayrık rotasyon kullanmış
(Gogate & Pande, IJPR 2008: yalnız 45° artışla 8 yönelim + voxel bottom-left) — yani
bizim kaba-rotasyon sınırlamamız **bilinen/paylaşılan bir açık**. En iyi yöntemler
(phi-NLP, CGF hibrit) bunu sürekli rotasyonla aşar. Magics'in bizden üstün olduğu
iki davranış (sürekli rotasyon + gerçek 3B kilitleme) bu sentezde kapsanan
tekniklerin akademik karşılığıdır.

---

## ÖNCELİKLENDİRİLMİŞ EYLEM LİSTESİ

### KALİTE (yükseklik 621 → hedef ~492 veya altı)

- **[K1] EN YÜKSEK değer/efor — Sürekli-rotasyon NLP COMPACTION post-process.**
  Mevcut heightmap çözümünü fizibıl başlangıç al, üstüne quasi-phi + IPOPT ile
  COMPOLY tarzı O(n) alt-problem sıkıştırması ekle. Literatürde %16–28 iyileşme,
  motoru atmadan. *Çözücü/model entegrasyonu gerek.*
- **[K2] Coarse-to-fine rotasyon.** Kaba açı tara → kazanan etrafında sürekli yerel
  optimizasyon (CGF hibrit mantığı). Alt-derece hassasiyet enumerasyon olmadan.
  *Mevcut motora katman; en hızlı kısmi kazanç.*
- **[K3] Heightmap drop → gerçek-3B çakışma + cavity-aware/part-in-part** (Ikonen
  GA / NFP+GLS). %8 doluluğun kök çözümü. *En yüksek efor, mimari değişim.*

### HIZ (78 dk azalt)

- **[H1] EN YÜKSEK değer/efor — Per-part (heterojen) çözünürlük.** İnce 1mm parça
  tüm grid'i 0.5mm'ye zorlamasın; parça-bazlı pitch.
- **[H2] Octree** hiyerarşik çakışma (Cagan SA) veya önceden-hesaplı **Nofit-Voxel
  (NFV)** ile O(1)'e yakın overlap testi.
- **[H3] COMPOLY ölçek indirgemesi** (O(n²)→O(n)) — NLP'yi 226 parçada uygulanabilir
  kılar.

---

## CAVEATS (dikkat — uygulamadan önce oku)

1. **Lokal optimum, global değil.** phi-NLP ve CGF hibrit NP-zor problemi YEREL
   çözer; %16–28 belirli literatür örneklerinden, 226-parça setimizde aynen
   tekrarlanmayabilir.
2. **Ölçek.** Sürekli-rotasyon NLP örnekleri N=15-40; 226 parça için
   COMPOLY/kademeli compaction **şart**, yoksa çözülemez.
3. **Hacim vs yükseklik.** EJOR 2018 min-HACİM minimize eder; bizim min-build-HEIGHT
   için 2019 IFAC min-height formülasyonu daha doğrudan — **hedef fonksiyon
   adaptasyonu gerek**.
4. **Rotasyon-hız gerilimi (önemli).** Araujo/Panesar IJPR 2020: daha basit
   (enveloping shape) primitif temsil, "makul sürede iyi-yeterli paketlemede
   algoritma seçiminden daha ağır basar". Pratik sonuç: rotasyonu **tek başına
   değil**, gerçek-3B-çakışma + cavity-aware ile **birlikte** ele al. (Not: "ince
   rotasyon sadece küçük kazanç sağlar" iddiası bizim doğrulamada **0-3 çürütüldü**;
   ama envelope-primitif bulgusu geçerli.)
5. **NFV sabit yönelim.** Yalnız hız katmanı; rotasyon (kalite) katmanıyla birlikte.
6. **Kaynak erişimi.** Bazı yayıncı sayfaları paywall (403); abstract'lar yazar
   preprint / NIST PDF / White Rose eprint ile verbatim doğrulandı.
7. **Magics.** İç algoritma ticari; "akademik karşılık" çıkarımsal (medium güven).

---

## AÇIK SORULAR (planı netleştirmek için)

1. Sürekli-rotasyon phi-NLP, 226-parça/16-tip ölçeğimizde (compaction ile bile)
   kabul edilebilir sürede çözülüyor mu — yoksa parça gruplama + kademeli yerleştirme
   gerekli mi? (literatür N=15-40 gösteriyor)
2. min-height (IFAC 2019) formülasyonuna uyarlarken kararlılık/yakınsama nasıl
   etkileniyor — phi-NLP min-height'te benchmark var mı?
3. Cavity-aware part-in-part, %8→hedef doluluğa ne kadar pay sağlar; gerçek-3B
   çakışmaya geçiş, rotasyon iyileştirmesinden bağımsız yüksekliği tek başına ne
   kadar düşürür?
4. Per-part çözünürlük + octree/NFV ile uniform 0.5mm'den beklenen hız kazancı
   nicel olarak ne (270M voxel → ?); sürekli-rotasyon NLP'nin ek maliyetini
   karşılar mı?

---

## ANAHTAR KAYNAKLAR (peer-reviewed, "primary")

- **EJOR** 268(1):37-53 (2018) Romanova/Bennell/Stoyan/Pankratov — quasi-phi concave
  polihedra + COMPOLY. (White Rose eprint açık erişim)
- **Operations Research** INFORMS (2022) Lamas-Fernandez/Bennell/Martinez-Sykora —
  Nofit-Voxel (NFV).
- **IJPR** 58(22) (2020) Araujo et al. — DBLF+GA limitleri, AM nesting.
- **Computer Graphics Forum** 37(5) (2018) Ma/Chen/Hu/Wang — hibrit sürekli rotasyon.
- **IFAC-PapersOnLine** 52-13 (2019) Litvinchev/Pankratov/Romanova — AM min-height
  phi-NLP.
- **Additive Manufacturing** Vol 36 (2020) Oh/Witherell/Lu/Sprock (NIST) — taksonomi.
- Cagan et al. **CAD** 30(10) (1998) — octree SA. Ikonen et al. ICGA 1997 — cavity GA.
- HAPE3D (constructive 3D irregular packing) — ek referans.

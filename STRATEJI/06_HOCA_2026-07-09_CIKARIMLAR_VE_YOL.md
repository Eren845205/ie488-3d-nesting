# 06 — Hoca Cevapları (2026-07-09) → Çıkarımlar ve Algoritma Yolu

> **Amaç:** 2026-07-09 mail cevapları + Plan1 baseplate fotoğrafı + aynı gün
> ölçümlerinden çıkan TÜM çıkarımların ve bundan sonraki algoritma geliştirme
> sırasının KALICI kaydı (Eren talebi: "hepsi yazılı kalsın").
> Ham cevap metni: `HOCA_CEVAPLARI.md` (2026-07-09 girişi).
> Her madde ANAYASA'ya tabidir (özellikle A1 kapı, A4 ölç-önce, A5 dağılım).

---

## 1. Kanıt → Çıkarım tablosu

| # | Kanıt (hoca/foto/ölçüm) | Çıkarım | Motor sonucu |
|---|---|---|---|
| K1 | "Operatör kenara çekip veya döndürerek çıkarıyor; b+c uygun" | +Z-tek kilit metriği gerçekten SERTTİ; kendi kendimizi cezalandırıyorduk | A2 güncellendi: kilit = **5-yön sıralı söküm** (`check_separability_5dir`); (c) döndürme modellenene dek konservatif taban |
| K2 | "Veriler MANUEL hazırlandı, Magics değil; saatler sürüyor" | Rakip yazılım değil, deneyimli insan. Referanslar optimal değil, geçilebilir. Süre beklentisi saatler → bizim 13-45 dk zaten insan-üstü | Ürün konumlandırması değişti: "Magics'i yakala" değil "**insan kalitesini dakikalarda geç**". Süre bütçesi baskısı kalktı; kalite moduna daha cömert bütçe meşru |
| K3 | Yasak bölge x 152,5–185,5 / y 0,2–45 (biz 185,1–215,2 kullanmışız) | Tüm 2026-07-08 mutlak sayılar yanlış koordinatlaydı | 14 scriptte düzeltildi; yeni-kural yeniden ölçüm turu açıldı. İlk sonuçlar: yeni konum hafif dostane (NFV 626→618) |
| K4 | "Yasak bölgeye çok hafif girişler sorun yaratmıyor" (2 kez) + fotoğraf | No-go YUMUŞAK kısıt; Magics/manuel bunu sömürüyor | **Soft no-go** özelliği meşru (bkz. R4). Hard mühür güvenli taban olarak kalır |
| K5 | "2 mm daha güvenli; tüm boşluklar" | 1mm ölçümlerimiz iyimserdi | A2: clearance eşiği 2mm. Ölçüm: 2mm'nin bedeli heightmap'te BÜYÜK (+50mm, p3 685→735), NFV'de KÜÇÜK (~0; 626→618 hatta iyileşti) → **NFV'ye pivot kanıtı** |
| K6 | Fotoğraf: baseplate DÜZ + ~30-45° z-dönüşlü; parçalar çerçevenin PENCERELERİNE yuvalanmış; koniler hep DİK | 110.41'in anatomisi: host parça düz+çapraz, gerisi deliklerde aynı z-bandında | Plan1 reçetesi: düz + **Rz taraması** + delik doldurma (tilt 135 = B planı). NFV'nin kavite stratejisi insan çözümüyle birebir örtüşüyor (strateji doğrulaması) |
| K7 | "Bazı parçalar yalnız dikey/yatay üretilir (silindir yatayda eliptik)" | Poz serbestisi sınırsız değil — ÜRETİM kuralı | **Parça-bazlı oryantasyon kısıtı** ürün gereksinimi (altyapı: `voxelize allowed_orientations` mevcut; eksik: kural/etiket katmanı + UI) |
| K8 | "5'er mm kenar boşluğu durumlarımız olabiliyor" (koşullu) | Kenar payı her zaman değil, geometriye bağlı | Politika: default tam plaka + **operatör seçeneği "kenar payı 5mm"** (veri-odaklı plaka politikasıyla uyumlu; sabit gömme YOK) |
| K9 | Deneme6 geldi (ref 86,32mm, manuel) | Taze kör-test verisi | **HELD-OUT doğar** (A3: tuning'e girmez; her bakış registry'ye). Dosya bekleniyor |
| K10 | Alternatif dizilim teyidi | Seed-rotasyonu/alternatif-üret tasarımı doğru | Mevcut plan geçerli (eval determinizmi + loglu seed) |
| K11 | Ölçüm: d4 söküm 413/588 kilitli vs p3 NFV 14-20/109 | Kenetlenme SET'e bağlı: derin kenet (çan-içi-çan) vs yüzeysel yuvalanma | Family routing'e yeni sinyal adayı: geometriden **kenet-riski tahmini** (bkz. R9) |
| K12 | Ölçüm: plan2 NFV bellek duvarı (FFT 1.76GB @0.5) | NFV ince-pitch'te bu makinede tıkanıyor (H-11) | Çözüm adayları: parça-bazlı çözünürlük (R8) / süper-bilgisayar / RAM. Plan2 şimdilik heightmap'te |

---

## 2. Fotoğraf derin analizi (Plan 1Base plate.jpg)

- Yerleşim tek "katman" mantığında: en büyük parça (baseplate çerçevesi) DÜZ
  yatırılmış, yüksekliği belirleyen şey çerçeve değil en uzun dik parça.
- Çerçeve ~30-45° z-dönüşüyle çapraz: (a) 335 köşegenini kullanıyor,
  (b) yasak kolonla teması azaltıyor (K4 ile birlikte: kalan hafif giriş
  tolere ediliyor).
- Pencere-doldurma: koniler/taper'lar üst bantta DİK; piramitler alt
  hücrelerde; braket/bobinler kollar arasında. İç-içe ama ÇIKARILABİLİR:
  hepsi açık-üstlü hücrelerde (+Z serbest) — usta işi nesting sökülebilirliği
  doğal koruyor → kilit-KAÇINAN skorlamanın (R2) insan-kanıtı.
- Koniler hiç yatay değil → K7 oryantasyon kısıtının görsel teyidi.

## 3. Aynı günün ölçüm kanıtları (bağlam)

- plan3 @yeni kurallar: zincir n24 ~7xx · sıkıştırma şampiyonu **735 (s42)** ·
  **NFV 618.1** (5-yön kilit 20; +Z 64) → NFV avantajı 2mm dünyasında ~120mm.
- K-29 kilit-tahliye probu koşuda (evict + kurallı yeniden yerleştirme +
  doğrulama döngüsü) — hedef: ilk **A2-legal NFV** sonucu (~620-660 bandı).
- plan1 tilt 135.0 legal (eski koordinat; yeni reçete R3 ile ~110-120 hedefi).

---

## 4. ALGORİTMA GELİŞTİRME YOLU (sıralı; her madde ölç-önce kapılı)

> Sıralama mantığı: önce kanıtlanmış en büyük ödül (NFV legalleştirme),
> sonra onu genelleştiren/güçlendiren özellikler, sonra ürünleşme kuralları.

**R1 — Kilit-tahliye üretime (K-29).** Probu GO verirse `solve_nfv`'ye
post-pass olarak bağla (evict→yeniden yerleştir→5-yön doğrula). Çıktı:
NFV sonuçları A2-legal. Kapı: p3'te legal < 735 + d5/p1'de zararsızlık.
*Durum: prob koşuyor.*

**R2 — Kilit-KAÇINAN NFV skorlaması.** Tahliye tedavi; bu, koruyucu hekimlik:
BLB konum skoruna "çıkış-farkındalık" kırılımı (aday poz yerleştirildiğinde
parçanın ≥1 düz çıkış yönü açık kalıyor mu — ucuz sweep testi; eşitlikte
açık-çıkışlı poz kazanır). Foto-kanıtlı (usta yerleşimi hep açık-üstlü).
Beklenti: tahliye ihtiyacı ve yükseklik bedeli düşer. Efor: orta.

**R3 — Host-parçaya sürekli Rz aday pozları (NFV + heightmap).** Fotoğraf
dersi: çapraz duran çerçeve eksen-hizalı menüde YOK. En büyük/host parçaya
Rz taraması (5..85°, tilt prototipinin z-ekseni hâli; eşik dersi: "çözümün
kullandığı pozun z'si"). Plan1 hedefi: 135 → **~110-120** (düz+çapraz+delik
doldurma). Sonra genelleme: height-driver her parçaya. Efor: düşük (prototip
altyapısı hazır: plan1_aci_kurtarma + hedefli_tilt).

**R4 — Soft no-go (yumuşak kenar).** K4 kanıtlı: maskeye parametrik tolerans
şeridi (örn. kenardan ≤T mm giriş = izinli; T operatör ayarı, default 0 =
bugünkü hard mühür). Hem Bin3D hem OccupancyBin3D aynı maske üretiminden
beslendiği için TEK üretim noktası var (`no_go_mask_from_bounds`). Plan1'de
düz pozun önü açılır (R3 ile birleşik ödül). Şerh: hocaya "T kaç mm?" sorusu
sorulmadan default 0 kalır — tahminle kural gevşetilmez.

**R5 — Parça-bazlı oryantasyon kısıtı (ürün gereksinimi, K7).** Katmanlar:
(a) kural motoru: geometri sınıflandırma (silindirik→dikey-zorunlu gibi)
YALNIZ ÖNERİ üretir; (b) operatör onayı/etiketi kalıcı kayıt (sessiz-öğrenme
yasağıyla uyumlu); (c) `allowed_orientations` kablosu üretim zinciri + NFV
menülerine; (d) UI rozeti. Alternatif-dizilim üretiminde de kısıt korunur.

**R6 — 2mm politikasının üretim kablosu.** Ölçüm scriptleri 2.0'a geçti;
sırada `WEB_MIN_CLEARANCE_MM 1.0→2.0` (webapp/gözcü yolu) + anchor stratejisi
(A8: eski anchor'lar 1mm dünyası — gate-PASS'li yeni koşularla güncellenir,
elle düzeltilmez). Tam suite şart (A9 bayat-mock).

**R7 — Kenar payı operatör seçeneği (K8).** Plaka politikası (veri-odaklı,
sabit gömme yasak) korunarak: "kenar payı" alanı (default 0, öneri 5mm
koşullu). Ölçüm etkisi küçük; ürünleşme maddesi.

**R8 — Parça-bazlı (karışık) çözünürlük — plan2 NFV kapısı (K12 + §4.6).**
İnce parçaya ince, kabaya kaba pitch → FFT grid küçülür → plan2 NFV bu
makinede mümkün olabilir; heightmap'te de hız kaldıracı. Efor: yüksek
(voxel uzayları karışınca çakışma testi tasarımı). Ölç-önce: önce "plan2'de
0.5 isteyen parça sayısı + 1.0'da kayıp" ucuz analizi.

**R9 — Kenet-riski sinyali (K11) → family routing.** Geometriden (konkavlık,
kutuluk, iç hacim erişimi) "bu set NFV'de kenetlenir mi?" tahmini;
`predict_nfv_benefit`/seçim modeline özellik olarak. d4 (derin kenet) vs p3
(yüzeysel) ayrımını otomatikleştirir. Öğrenme MANUEL+öneri ilkesiyle.

**R10 — Rotasyon-söküm (c) modellemesi — ANCAK GEREKİRSE.** 5-yön konservatif
taban yeterli olduğu sürece motion-planning sınıfı bu işe girilmez. Tetik:
kalan kilitler tahliye+kaçınma sonrası hâlâ tabloyu belirliyorsa.

**R11 — Deneme6 kör-test protokolü (K9).** Dosya gelince: held-out kaydı
(01_VERI registry) → dokunmadan, yalnız final koşusu `--heldout-final`
bayrağıyla; ref 86,32 manuel. Yeni siparişlerde aynı protokol standart.

**R12 — Süre/kalite yeniden dengeleme (K2).** "Saatler normal" bilgisiyle:
kalite modu bütçeleri gözden geçirilebilir (örn. sıkıştırma seed sayısı,
NFV quality=max defaultları). Gözcü hızlı yolu dakikalarda kalır; operatör
"derin arama" düğmesi saatlik bütçeyle meşru.

---

## 5. Şerhler / riskler

- **A10 kıyas şerhi:** manuel referansların (593 vb.) hangi boşluk/kenar
  kurallarıyla hazırlandığı bilinmiyor; foto tam plaka kullanımı + hafif
  no-go girişi gösteriyor. Kıyas tabloları "manuel referans, koşulları
  yaklaşık" şerhiyle sunulur.
- **Overfit koruması:** buradaki HER madde dev-dağılım (A5) + gerektiğinde
  held-out finali (A3) kapısından geçer; Deneme6 ve gelecek siparişler bu
  kapının yakıtı. n24 held-out finali hâlâ borç (boxy, yeni kurallarla).
- **Metrik evrimi kayıt disiplini:** hangi sonucun hangi kural setiyle
  (koordinat + clearance + kilit tanımı) ölçüldüğü etiketlenmeden tablo
  satırı yazılmaz — bugünden itibaren "eski kural" sayıları yalnız tarihsel.

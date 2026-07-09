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
- Plan1 baseplate'i Magics plakaya açıyla mı basıyor? (110.41'in anatomisi)
- Magics yerleşim STL'leri / ekran görüntüleri paylaşılabilir mi? (dizilim istihbaratı)

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

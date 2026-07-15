# YAPILACAKLAR — Öncelikli İş Listesi

> Kalıcı liste (repo = tek doğruluk kaynağı). Her madde bitince tarih+commit ile
> işaretlenir, silinmez. Kaynak: hoca geri bildirimleri 2026-07-06 akşam
> [[project-hoca-feedback-2026-07-06-aksam]] + oturum bulguları (EVAL-1, K-24).

## 🧰 OPERATÖR SÖKÜM KONSOLU — Faz 2 (2026-07-15, Eren fikri; K-52 rot-kabul üstüne)

Gerekçe: hoca ekibi bugün parça→sipariş eşlemesini ve çıkarma yöntemini plaka
başında GÖZLE, tek tek yapıyor (Eren'e bizzat söyledi). 588 parçalık plakada bu
yavaş + hata açık (yanlış siparişe yanlış parça). Faz 1 verisi hazır: söküm
talimatları (eksen/açı/yön/lift) uçtan uca taşınıyor (`sokum_plani`,
gecmis_detay "Sokum Plani" bölümü). Magics'te karşılığı YOK — ürün farklılaştırıcısı.

- **Önkoşul (ilk iş):** placements `part_id` → `order_id` izinin uçtan uca
  taşındığını doğrula/kablola (sipariş-bazlı kayıtlar parti↔sipariş bağını
  tutuyor; parça-düzeyi eşleme detay JSON'a inmeli — placements _AGIR'da
  düşürüldüğü için eşleme persist ÖNCESİ yapılmalı, dz/sokum_plani deseni gibi).
- **F2-a Siparişe-göre-renk (viewer):** GLB düğümlerine order_id metadata +
  viewer'da "renk: parça tipi / sipariş" anahtarı.
- **F2-b Tıkla-tanı:** parçaya tıkla → yan panel kimlik kartı: parça adı +
  sipariş/müşteri + varsa söküm talimatı.
- **F2-c Rehberli söküm sırası:** `removable_order` (rot denetimi zaten
  üretiyor) adım-adım moda bağlanır: sıradaki parça vurgulanır + talimat +
  "kutusu: Sipariş X". Operatör identify ETMEZ, takip eder.
- **F2-d Sipariş özet kartı:** sipariş başına parça sayısı / kaçı söküm-planlı
  (toplama-paketleme kontrol listesi).
- **F2-e sonuc.html paritesi:** "Sokum Plani" bölümü anlık sonuç ekranına da.
- İlgili hoca isteği (2026-07-06): STL içine adet/parça adı (ASCII multi-solid)
  — aynı tema, birlikte planlanabilir.

## 🎯 KALİTE YOL HARİTASI (2026-07-07 — kullanıcı kararı: "rotasyona suç atmadan önce eksen-hizalı tavanı ölç")

Kanıt tabanı: d4 çekirdek Magics-parite (250.5 vs 250.24) → istif kalitesi sınıfında
tavana yakınız; NFV/kavite yönü 5 ölçümle KAPALI (K-21/22b/23/24/F2-v2); açı z-only
−%3.6 ölçüldü. Güncel tablo (335+nogo): d4 +%15.3 · p3 +%19.1 · d5 +%58 · p1 ölçülüyor.

- **Kademe 0 — dürüst tablo (KOŞUYOR, bu gece):** p1 üretim sayısı + AX24 kuyruğu
  (d5/p1/p2/p3 n24 + p2 ilk baseline; her sette height-driver dökümü + placements
  pickle) + ayrılabilirlik probu (K-21 554 kilit × 5-yön söküm).
- **Kademe 1 — teşhis (1-2 gün):** d5 height-driver analizi (neyi 329'a itiyor) ·
  no-go bedel anatomisi (d5 +59 vs d4 +11.5 neden?) · **hocadan Magics yerleşim
  STL'leri** (p1 110.41 anatomisi — en ucuz istihbarat) · ayrılabilirlik probu
  sonucuna göre hocaya kriter sorusu ("düz çekme mi, döndürerek çıkarma kabul mü?").
- **Kademe 2 — hedefli motor işleri (hafta içi, her biri ölç-önce kapılı):**
  **⭐ 1 numara (2026-07-08 gece teşhisi): plan1 baseplate HEDEFLİ-TİLT** — n24
  height-driver: kulenin tepesi BASEPLATE (260; sonraki parça 147!). DÜZ yatırma
  İMKÂNSIZ: no-go kolonu tam-yükseklik ve 330.2mm ayak izi 335 plakada her düz
  pozisyonda kolonla kesişir (±4.8mm pay) → Magics'in eğik basması ZORUNLULUK.
  İş: baseplate'e sürekli açı taraması (x/y tilt; açı-kurtarma prototipi altyapı)
  → minimum z-uzantılı, no-go'dan kaçan eğik poz + altına/üstüne istif. Rotasyon
  programının (Kademe 3) İLK dilimi fiilen bu — plan1 için öne çekildi. **⭐ n24'ü default'a kablola:** heightmap yolunda
  n24 neredeyse bedava çıktı (d5: 6.4dk, p1: 14.6dk ≈ n8 süreleri) ve d5 −%15 /
  p1 −%14 kazandırdı — cross-dataset teyidi sabah tamamlanınca kablola.
  no-go-farkındalı yerleşim (hedef: d5 no-go bedelini d4 bandına indirmek) ·
  pitch-fallback fit-guard üretime (§4.6; DERS: set-geneli inceltme 112 parçada
  saatler yaktı → parça-bazlı çözünürlük/oryantasyon-eleme tasarla) · n24 kazanırsa
  kalite moduna kablola · ayrılabilirlik kriteri gevşerse NFV kalite modunu yeni
  kriterle YENİDEN değerlendir (plan ailesinde aynı plakada ~100mm ölçülü potansiyel).
- **Kademe 3 — A1 serbest rotasyon (1-3 hafta, kademeli):** (a) hedefli tilt:
  height-driver parçalara x/y+z açı taraması (fine_angle genelleştirme) →
  (b) sürekli-açı poz adayları coarse'ta üret, fine'da rafine →
  (c) süper-bilgisayar geniş tarama (0.5-1°). Ön-şart: n24+fine_angle
  None.exterior bug fix (§4.5). Gerekçe artık resmî: hoca rotasyon serbest dedi.
- **Kademe 4 — kalite güvence:** 335+nogo şampiyonları eval_gate baseline'ı yap
  (regresyon kapısı) · yeni sipariş = held-out doğar · alternatif-dizilim (seed
  rotasyonu) determinizmi bozmadan.
- **Karar kuralı:** her kademe ölçümle açılır/kapanır; <%1 kazanç = yön kapanır
  ve YONTEM_HARITASI'na işlenir (§0 güncelleme kuralı).

## 🔴 ACİL (bu hafta)

### 1. Plan1+Plan3 düzeltilmiş STL gönderimi
- [ ] Gece taraması bitti → kazanan legal STL + sayı kanıtı (yükseklik / ≥1mm / 0 kilit)
- [ ] Mailde dürüst not: "önceki yerleşimde parça-arası boşluk şartı sağlanmıyordu"
- [ ] App restart (working-tree'deki NFV-clearance fix'i canlıya alsın)
- Durum: tarama gece koşuyor (scripts/plan13_tarama.py)

### 2. STL-İÇİ ADET OKUMA (giriş katmanı — hoca: "müşteri adedi maile değil STL'ye yazıyor")
Gözcü akışı bugün adetleri MAIL GÖVDESİNDEN parse ediyor ("Ad - Sayı" formatı).
Hoca: bazı müşteriler adedi mailde HİÇ yazmıyor; STL'nin içine/adına yazıyor.
- [ ] Kaynak sıralaması tasarla: (1) mail gövdesi (mevcut, EN GÜVENİLİR — override eder),
      (2) dosya adı deseni (`-25pcs`, `x12`, `_5adet`...), (3) ASCII STL solid adları,
      (4) STL içi çoklu-kopya geometri sayımı (aynı mesh N kez gömülü → adet N).
- [ ] **UYARI — kanıtlı tuzak:** Deneme4 `"-25pcs"` dosya adı YANLIŞTI (gerçek 26,
      mail+checksum doğruladı). STL/ad-kaynaklı adet ASLA sessiz kabul edilmez:
      mail gövdesiyle çelişkide mail kazanır; mail yoksa operatör onayına düşür
      (parser'ın mevcut onay akışına bağla). Sessiz varsayım YOK.
- [ ] Testler: her kaynak + çelişki senaryoları + idempotency (aynı mail re-process).
- [ ] Telemetri: adet hangi kaynaktan geldi (`qty_source`) logla.
- [ ] Hocadan ÖRNEK dosya iste: "adedin STL içinde yazılı olduğu gerçek bir
      müşteri STL'si" → parser gerçek konvansiyona karşı yazılır + test fikstürü.
- **GERÇEK ÖRNEK GELDİ (hoca eki, 2026-07-07):** `YP2425-Arm-2mm-2Adet.STL` —
  binary; dosya adı `-2Adet` AMA binary header solid-adı `-4Adet` (ÇELİŞKİLİ!).
  → Spec kesinleşti: desen `-NAdet` (case-insensitive, `pcs` varyantıyla);
  kaynaklar: dosya-adı + binary-header-solid-adı + ASCII-solid-adları;
  çelişki = operatör onayı; mail gövdesi hepsini ezer. Test fikstürü: bu dosya.
- **Fizibilite KANITLANDI (2026-07-06 gece probe):** Deneme4 STL'leri binary/
  tek-gövde, adet dosya ADINDA (→ desen parse); gömülü-N-kopya `trimesh.split`
  ile sayılabiliyor (ölçüldü); ASCII solid adı + binary header okunabilir.
  Tahmini efor: ~1 gün (parser + loader + onay kablosu + testler).

### 3. ALTERNATİF DİZİLİM ÜRETİMİ (hoca: "her seferinde farklı dizmeli")
Motor hazır (seed-güdümlü); ürün davranışı eksik.
- [ ] UI: "Alternatif dizilim üret" butonu → yeni rastgele seed ile re-solve.
- [ ] Her sonuçta kullanılan seed KAYITLI (tekrarlanabilirlik korunur —
      determinizm ilkesiyle çelişmez; eval/kapı sabit seed=42'de kalır).
- [ ] Opsiyonel: "en iyi N alternatif" modu (N seed koş, hepsini listele,
      operatör seçer) — tarama altyapısı (plan13_tarama deseni) yeniden kullanılır.

### 4. STL-İÇİ ADET/AD YAZMA (çıkış katmanı — hoca: "STL içine yazabiliyor")
- [ ] Export'a adlandırılmış-solid **ASCII STL** modu: her parça `solid <ad>`
      bloğu (veya tip başına `<ad>_1..N`); Magics/işleyen yazılım parça sayabilir.
- [ ] Alternatif değerlendir: 3MF (modern, isim+metadata doğal) — hocaya sor.
- [ ] Boyut dikkat: ASCII STL ~5× büyük — büyük koşularda ZIP'le.

### 4.5 PLAN3 AÇIĞI (hoca referansı GELDİ: **593mm**, Eren 2026-07-07 gece)
- Durum: legal en iyi 718 (+%21); eski şüpheli NFV 755.5 bile 593'ü geçememişti
  → Magics avantajı kavite DEĞİL, muhtemelen SERBEST ROTASYON (çubuklar çapraz).
- [x] `fine_angle` probu ÖLÇÜLDÜ (2026-07-07, eski plaka 328.74 no-go'suz):
      w90_b70 seed13=693.0 / seed7=701.0 / **step5=692.0** legal (3 bağımsız koşu
      birebir; ref 718 → açı −26mm ≈ −%3.6; `scripts/plan3_acili_prob.log`).
      Kayda değer ama Magics açığını kapatmıyor.
- [ ] **BUG (küçük, robustluk):** `n_orientations=24 + fine_angle` kombinasyonu
      `'NoneType' object has no attribute 'exterior'` ile çözümü ÖLDÜRÜYOR
      (2026-07-07 w90_n24_b70). 153c961 dejenere-açı fix'i eğik pozlu (8-11)
      yolu kapsamıyor — aynı açı-atla/fallback deseni oraya da uygulanmalı + test.
- [ ] Prob sonucuna göre: fine_angle üretim tarifesi (kapıdan) / A1. (F2-v2
      KESİN NO-GO 2026-07-07 — YONTEM_HARITASI §3.1; sky-corridor bedeli +201mm.)
- [x] Hocaya soruldu, cevap GELDİ 2026-07-07: TÜM setler 335×335+NOGO; plan3
      Magics=593. Yeni koşul sonucu: 335+nogo legal=**747.0** (sıkıştırma koşuda).

### 4.6 PLAN1 üretim-zinciri PITCH-FALLBACK ("yerleşEMİYOR" artefaktı — ölçüldü 2026-07-07)
- Bulgu: üretim zinciri (suggest_pitch kaba pitch + margin) plan1 baseplate'i
  (330.2mm) 335 plakaya YERLEŞTİREMİYORDU; pitch 1.0 + margin 1'de eksen-hizalı
  SIĞDI → **303.0 legal** (112/112, clear 1.118, 0 kilit; `plan1_nogo335_aci_303.0mm.stl`).
  **Açı-kurtarma GEREKMEDİ** (kurtarilan=0) → "sığmıyor" pitch/margin kuantizasyon
  artefaktıydı, geometrik imkânsızlık değil.
- [ ] Üretim fix: solve_coarse_to_fine fit-guard — önerilen pitch'te hiçbir pozu
      plakaya sığmayan parça varsa pitch'i otomatik incelt (fallback) + telemetri; testle.
      **ÖLÇÜLMÜŞ SÜRE UYARISI (2026-07-08 gece):** naif fit-guard (set-geneli 1.0'a
      inceltme) + TAM PORTFÖY = 8+ saat bitmedi (bütçe=6 ön-izleme bile 5+ saat) →
      öldürüldü. Fit-guard'lı sette menü dblf_only'ye düşürülmeli VEYA parça-bazlı
      çözünürlük (yalnız sığmayan parçayı ince gridde çöz) tasarlanmalı.
- [ ] Açı-kurtarma prototipi HAZIR (`scripts/plan1_aci_kurtarma.py`) — pitch-fallback'in
      yetmediği gerçek vaka çıkarsa opt-in ikinci hat; şimdilik üretime ALINMAZ (ölç-önce).
- [ ] Magics 110.41 vs bizim 303.0 (+%174): plan1 açığı AYRI iş — aday kaldıraçlar
      A1 serbest rotasyon + istif kalitesi teşhisi (height-driver analizi).

## 🟠 KISA VADE (1-2 hafta)

### 5. Üretimde NFV sonuçlarına A2 kapısı
- [ ] `demo_pipeline`'a kilit+clearance post-nest kontrolü: NFV sonucu kilit>0
      veya boşluk<1mm ise sonuç "ÜRETİLEMEZ — işaretli" (HIGH-2 deseninin kilit eşi).
      Müşteriye kapısız STL gitmesin (bugünkü Plan1+3 kazası bir daha yaşanmasın).

### 6. NFV'yi legalleştirme (plan kazançlarını geri getirme — %20'nin gerçek yolu)
- [ ] Kilit ANATOMİSİ teşhisi: plan1'de kalan 52 kilit gerçek kenet mi, F2
      +Z-çekme konservatifliği mi (hoca döndürerek ayırmaya izin veriyor).
- [ ] Over-provision yarılama: dilation NFV'de çift sayıyor (2.54mm ölçüldü,
      ~1.3 hedef) → dürüst NFV yüksekliği düşer.
- [ ] F2-v2: yerleştirme anında sökülebilirlik kısıtı (asıl iş).
- [ ] Sonra plan2'de dürüst NFV ölçümü → kapıdan geçerse challenger.

### 6.5 TARİHÎ SAYI TEMİZLİĞİ (Eren talebi 2026-07-07: "yanlışın izlerini temizle")
Eski NFV sayıları (plan1 115.5-120.7 / plan2 512-522 / plan3 755-844, "%20-28
iyileşme", "Magics açığı %4.2") dikey-boşluksuz + kilit-ölçümsüz metrikle
alındı → İDDİA OLARAK GEÇERSİZ (EVAL-1). Yapılacak:
- [ ] YONTEM_HARITASI'na tepe-şerhi: K-04/K-05/K-17/K-18 sonuç sayıları
      "pre-clearance NFV — legal yeniden-ölçüm bekliyor" damgalı.
- [ ] Plan1/2/3 NFV'yi clearance'lı fix'le YENİDEN ölç (kilit sayısıyla) →
      dürüst tarih tabanı; kapı tablosuna işle.
- [ ] Hoca-yüzlü geçmiş iddialar (rapor/sunum) tekrar kullanılmadan önce
      yeni sayılarla revize (eski sayı alıntılamak YASAK — A2/A10).

## 🟡 ORTA VADE

### 7. STRATEJI fazları (STRATEJI/02 §5)
- [x] Faz-0 eval_gate CLI (2026-07-06, commit 3986397)
- [x] Faz-1 registry.json + held-out reddi + otomatik bakış-log (2026-07-07)
- [x] Faz-2 telemetri v2: `append_run_v2` + pipeline kablosu, test-korumalı (2026-07-07)
- [x] Faz-3 KOD katmanı: KNNSelector + LogisticSelector + sıcaklık kalibrasyonu +
      loo_regret + gengap model-parametrik + held-out eğitim filtresi + tune_bo.py (2026-07-07)
- [ ] Faz-3 KOŞULAR: baseline kilidi → BO denemeleri → model adayları LOO-regret
      kıyası → kapı + insan kararıyla yürürlük (A1/A6 gereği otomatik DEĞİL)

### 8. Diğer
- [ ] Hoca S1 cevabı gelince Magics clearance-paritesi kıyas güncellemesi
- [ ] Kabuk-ailesi sentetik jeneratörü (01_VERI §6)

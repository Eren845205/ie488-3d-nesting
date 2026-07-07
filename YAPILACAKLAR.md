# YAPILACAKLAR — Öncelikli İş Listesi

> Kalıcı liste (repo = tek doğruluk kaynağı). Her madde bitince tarih+commit ile
> işaretlenir, silinmez. Kaynak: hoca geri bildirimleri 2026-07-06 akşam
> [[project-hoca-feedback-2026-07-06-aksam]] + oturum bulguları (EVAL-1, K-24).

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
- [ ] `fine_angle` probu (z-ekseni açı taraması, motor'da opt-in MEVCUT ama
      planlarda hiç ölçülmedi): 718'i ne kadar indiriyor? (ölç-önce)
- [ ] Prob sonucuna göre: fine_angle üretim tarifesi (kapıdan) / F2-v2 / A1.
- [ ] Hocaya: 593 hangi plakada? (S8 ile birlikte)

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

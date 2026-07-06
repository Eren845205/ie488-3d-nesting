# 05_TRANSFER_PLAYBOOK — Başka İşlere Taşınabilir Meta-Metodoloji

> Eren'in isteği: "buradan öğreneceklerimiz farklı işlerde bile işimize
> yarasın." Bu dosya proje-BAĞIMSIZ dokuz deseni, bu projedeki kanıtıyla ve
> yeni bir işe taşıma reçetesiyle verir. Yeni proje başlarken bu dosya okunur
> ve uygulanacak desenler proje CLAUDE.md/strateji dosyasına seçilerek konur.

---

## D1 — Karar veritabanı ("ne denendi" hafızası)

**İlke:** Denenen HER yaklaşım (başarılı + başarısız) tek dosyada, kanıt
yoluyla (script + log + tarih) kayıtlıdır; işe başlamadan okunur.
**Kanıt:** `MOTOR/YONTEM_HARITASI_DATA_BASE.md` — K-22'nin NO-GO'su K-23'ün
teşhisini, K-23'ünki K-24'ü doğurdu; hiçbir deney iki kez yapılmadı.
**Taşıma:** yeni projede gün 1'de `KARAR_DB.md` aç: §durum-snapshot ·
§denemeler (ne/niçin/sonuç/kanıt) · §açık-yönler · §meta-dersler. Model/oturum
değişse de ilerleme korunur (bu, oturum-bağımsızlığın yarısıdır; diğer yarısı
D5 kapı).

## D2 — Ölç-önce / teşhis-önce

**İlke:** Pahalı deneyden önce "hüküm verecek en ucuz ölçüm ne?" sorusu
zorunlu adımdır. Çoğu fikir dakikalık teşhisle ölür veya yön değiştirir.
**Kanıt:** K-23 (2 saatlik koşu yerine 87sn teşhis); K-24 Adım-1 (post-hoc
imkânsızlığı 6dk'da görüldü, prototipten önce hedef netleşti); H-15 (yanlış
süre atfı sentez-oranı ölçümüyle düzeldi).
**Taşıma:** her deney şablonuna "Adım-0: hükmü değiştirebilecek en ucuz ölçüm"
satırı; teşhis scriptleri `scripts/` + log konvansiyonu.

## D3 — Dürüst metrik (kısıt ihlalini maskeleyen metrik şişer)

**İlke:** Başlık metriği, TÜM sert kısıtları doğrulayıp geçemeyeni INVALID
ilan eder; kısıtsız sayı rapor edilmez.
**Kanıt:** 282mm (0.084mm clearance ihlali) ve 262.5mm (554 kilit) —
ikisi de "rekor" gibi görünüyordu, ikisi de üretilemezdi.
**Taşıma:** metriği tanımlarken "hangi kısıt ihlali bu sayıyı anlamsız kılar?"
listesi çıkar; doğrulayıcıyı metriğin İÇİNE göm (ör. web projesinde "sayfa
hızı" = yalnız DOĞRU render'lanan sayfada; satış botunda "dönüşüm" = yalnız
geçerli/iade-olmayan sipariş).

## D4 — İki-rejim veri ekonomisi

**İlke:** Bol/ucuz veri (sentetik, log, scrape) geliştirmeyi BESLER;
kıt/değerli veri (gerçek müşteri/saha) genellemeyi KANITLAR — ikisi asla aynı
havuza konmaz.
**Kanıt:** 69 sentetik instance eğitiyor; 6 gerçek sipariş doğruluyor;
"hocadan gelen her mail altın → held-out doğar."
**Taşıma:** veri kaynaklarını rejimlere ayır; kıt-rejim verisi için D5'teki
held-out protokolünü uygula.

## D5 — Held-out dokunulmazlığı + eval kapısı (oturum-bağımsız geliştirme)

**İlke:** Kabul kriteri repoda-checkli, deterministik bir değerlendirmedir;
held-out yalnız final'de koşulur ve her bakış loglanır. "Güven bana daha iyi"
kanıt değildir — öneren insan da olsa, AI da olsa.
**Kanıt:** bu klasörün varlık sebebi (clearance dersi).
**Taşıma:** minimum sürüm bir dosyalık: `EVAL.md` (metrik + eşik + komut) +
sabit bir test/benchmark komutu. Büyütmek istersen bu klasörün yapısını kopyala.

## D6 — Dağılım raporlama (en-iyi-durum yasağı)

**İlke:** İyileştirme iddiası tüm test yüzeyindeki dağılımıyla raporlanır;
tek-nokta kazancı kazanç değildir.
**Kanıt:** cross-dataset kapısı; K-05 künyesi ("+%1.1 ilk-12'ydi,
genelleşmedi").
**Taşıma:** rapor şablonuna zorunlu tablo: her senaryo/segment × önce/sonra/Δ;
`min` üzerinden karar (worst-case), `mean` yalnız bilgi.

## D7 — Sessiz-öğrenme yasağı (öneri-insan-kapı üçlüsü)

**İlke:** Kendini güncelleyen her bileşen: sistem ÖNERİR → insan KARAR verir
→ kapı DOĞRULAR → promote atomik, aksi hâlde byte-aynı.
**Kanıt:** `selection/retrain.py` politikası; [[feedback-otomatik-ogrenme]]
(sessiz overfit riski üreticide kalır).
**Taşıma:** her "auto-improve" özelliğinde promote yolunu bu üçlüyle kur;
"scheduler retrain eder" tasarımını reddet.

## D8 — Bayat-mock / bit-özdeşlik disiplini

**İlke:** Refactor "davranış aynı" iddiasıysa bit-özdeşlik testiyle kanıtlanır;
imza değişimlerinde test fake'leri sessiz fallback'e düşebilir → tam suite +
mock imza kilidi.
**Kanıt:** H-15p/H-16 (birebir 282.0 şartı), HIGH-1 `_fake_c2f` tuzağı.
**Taşıma:** golden-output testleri + "mock'lar gerçek imzayı assert eder"
kuralı; kablo değişikliklerinde tam suite şartı.

## D9 — Az-örneklem optimizasyon ekonomisi

**İlke:** Değerlendirme pahalıysa (dakikalar-saatler), yöntem seçimi bütçeden
türer: önce duyarlılık taraması (etkisiz boyutları at), sonra az-örneklemli
optimizasyon (BO/TPE); objective'e worst-case koy ki tek-senaryoya overfit
yapısal cezalansın.
**Kanıt:** `04_MOTOR_TUNING.md` tasarımı; K-21 RAM-taşması dersi (kısıtlar
objective'te olmalı).
**Taşıma:** her "parametre ayarı" işinde aynı üçlü: envanter → duyarlılık →
kısıtlı-worst-case-BO. (Ör. reklam bütçe dağılımı, fiyatlama kuralları, LLM
prompt-config taraması.)

---

## Hızlı başlangıç şablonu (yeni proje, 30 dakika)

1. `KARAR_DB.md` aç (D1) — boş şablonla.
2. Başlık metriğini D3 sorusuyla tanımla; INVALID koşullarını yaz.
3. Veri kaynaklarını D4 rejimlerine ayır; kıt-rejim için held-out listesi (D5).
4. `EVAL.md`: metrik + eşik (D6 tablosu) + tek komut.
5. Öğrenen bileşen varsa D7 üçlüsünü mimariye koy.
6. İlk deneyden önce D2'yi uygula.

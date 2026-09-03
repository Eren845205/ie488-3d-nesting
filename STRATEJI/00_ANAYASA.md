# 00_ANAYASA — Değişmez İlkeler + Alınmış Kararlar

> Bu dosya kısa tutulur ve **her motor/ML oturumu başında okunur.** İlkeler
> ancak Eren'in açık kararıyla değişir; değişiklik tarihli not olarak buraya
> işlenir (sessiz düzenleme yok).

---

## A. Değişmez ilkeler

**A1 — Kapısız kazanç yok.** Hiçbir değişiklik, eval kapısından
(`02_EVAL_KAPISI.md`) geçmeden "iyileştirme" sayılmaz, benchmark anchor'ı
güncelleyemez, üretime bağlanamaz. "Güven bana daha iyi" bir kanıt türü değildir
— hangi model/oturum söylerse söylesin.

**A2 — Dürüst metrik = legal-yükseklik.** Raporlanan yükseklik ancak ÜÇÜ birden
sağlanıyorsa geçerlidir: (i) yerleşen == toplam parça, (ii) min. parça-arası
boşluk ≥ 2mm (`clearance.min_clearance`), (iii) ayrılabilirlik: 0 kilit.
Biri ihlalde sonuç **INVALID**'dir ve sebep raporlanır. Gerekçe: K-19
(0.084mm ihlalli 282), K-21 (554 kilitli 262.5) — kısıt ihlalini maskeleyen
metrik şişer.

> **A2 GÜNCELLEMESİ (2026-07-09, Eren onayı — hoca cevabı sonrası):**
> (ii) boşluk eşiği 1mm → **2mm** (hoca: "2mm daha güvenli, tüm boşluklar").
> (iii) kilit tanımı: +Z-tek düz çekme → **5-yön sıralı söküm** (±X, ±Y, +Z;
> her turda herhangi bir yönden engelsiz parça çıkar). Gerekçe: hocanın gerçek
> kabul kriteri (b)+(c) — "operatör kenara çekip veya döndürerek çıkarıyor";
> +Z-tek metrik gerçeklikten SERTTİ (kendi kendini cezalandırma). Döndürme (c)
> modellenene dek 5-yön = KONSERVATİF taraf. Raporlar hangi kriterle legal
> olunduğunu belirtmeye devam eder. Eski +Z metriği telemetri olarak kalır.

> **A2 GÜNCELLEMESİ-2 (2026-07-15, Eren kararı — K-51b bulgusu + hoca kabulü
> 2026-07-14):** (iii) kilit tanımına **rot-söküm katmanı** eklendi: 5-yön
> kilit>0 tek başına INVALID sebebi DEĞİLDİR — rot-söküm denetimi
> (`kilit_rot_meshes`, K-52 tabanı @1.0, bütçe 1200s) kilitleri yeniden
> yargılar; rot kilit=0 → **SÖKÜM-PLANLI LEGAL** (raporda `sokum_planli` +
> cert sayısı belirtilir). Gerekçe: hoca 2026-07-14 "az zor-söküm ihmal
> edilebilir" + K-52 (12/12 kilit rot'la açıldı, maliyet 1.4dk/588p) — 5-yön=0
> şartı hoca kriterinden SERTTİ (K-51b'de baseline'ı INVALID'e düşürdü).
> Konservatif taraf korunur: rot denetimi hata/bütçe-aşımı → eski RED; rot
> kabulü yalnız kilit koşulunu aklar (clearance/yerleşim aklanmaz); denetim
> yalnız kilit>0 iken koşar (K-42 maliyet dersi).

**A3 — Held-out dokunulmazdır.** Held-out ilan edilen veri tuning/geliştirme
döngüsüne GİRMEZ; yalnız final doğrulamada koşulur ve her bakış
`01_VERI.md` registry'sine tarihle loglanır. Bir kez tuning'e giren set sonsuza
dek development set'tir (Plan1/2/3 + Deneme4 böyle düştü).

**A4 — Ölç-önce / teşhis-önce.** Pahalı deneyden (saatlik koşu) önce ucuz teşhis
(dakikalık analiz) hüküm verebiliyorsa önce o yapılır. Kanıt: K-23 sıra-deneyi
koşusuz kapandı (2 saatlik deney yerine 87 saniyelik teşhis); H-15 süre atfı
sentez-oranı doğrulamasıyla düzeldi.

**A5 — Dağılım raporlanır, en-iyi-durum değil.** Her iddia TÜM dev-set'lerdeki
sonucuyla raporlanır. Bir sette +%10, iki sette −%5 = net kayıp. Tek-set
kazancı kazanç değildir (künye: K-05 "+%1.1 eğik-pozlu ilk-12'ydi, genelleşmedi").

**A6 — Sessiz öğrenme yasak.** Seçim modeli asla otomatik retrain edilmez
(`selection/retrain.py` politikası). Advisor önerir, insan karar verir, gate
doğrular, promote atomiktir. Aynı ilke gelecekteki her öğrenen bileşene uygulanır.

**A7 — Kayıt zorunlu.** Her deney (GO da NO-GO da) `MOTOR/
YONTEM_HARITASI_DATA_BASE.md` §3'e kanıt yoluyla (script + log) işlenir.
NO-GO kaydı, tekrar denenmesini engellediği için GO kadar değerlidir.

**A8 — Anchor disiplini.** Frozen benchmark anchor'ları (regresyon testlerindeki
sabit sayılar) yalnız gate PASS'li bir koşunun çıktısıyla güncellenir; elle
"düzeltilmez". Anchor değişikliği commit mesajında gerekçelendirilir.

**A9 — Bayat-mock tuzağına karşı tam suite.** İmza değişiklikleri test
fake'lerini sessiz fallback'e düşürebilir (H-16 dersi: `_fake_c2f`). Kablo
değişikliklerinde tam suite koşulur; mock imzaları gerçek imzayla kilitlenir.

**A10 — Kıyas ancak eşit şartlarda.** Rakip (Magics) kıyası aynı plaka, aynı
clearance kuralı, aynı ayrılabilirlik şartıyla yapılır; bilinmeyen şart varsa
sonuç "şerhli" raporlanır (bugün: Magics'in clearance-paritesi S1 cevabı
gelene dek şerhli).

**A11 — Tek-veri geliştirme yasağı / genelleme protokolü (2026-07-19, Eren
talebi: "sadece tek bir veri için geliştirme yapma... bunu eval kısmıyla
bağlayalım artık").** Her yeni mekanizma / parametre / sözleşme değişikliği
şu zinciri ZORUNLU izler; zincir tamamlanmadan hiçbir sonuç "kazanç" ilan
edilmez:

1. **Tetik geometrik/aile-koşulludur, veri-adı DEĞİLDİR.** Kodda set adı
   (plan1, deneme4...) geçen özel durum yasak; tetik ölçülebilir koşuldur
   (örn. "no-go'lu plakaya hiçbir düz pozu sığmayan yükseklik-sürücü parça").
   Tek sette keşfedilen mekanizma, tetiği genelleştirilerek kodlanır.
2. **Tek-set derinleşme deneyi = ŞERHLİ ön-ölçüm.** Statüsü YONTEM kaydında
   açık yazılır; "iyileştirme" ancak 4-set dev kapısı (B2 eşikleri) PASS
   olunca ilan edilir.
3. **Tetiksiz setlerde SIFIR-dokunuş kanıtı** (bit-özdeşlik) kapı koşusunda
   gösterilir — mekanizmanın diğer aileleri etkilemediği ölçülür, varsayılmaz.
4. **Sözleşme değişiklikleri ayrı sınıftır** (clearance / no-go / plaka
   semantiği): hoca teyidi + TÜM baseline yenileme + A8 gerekçeli anchor
   güncellemesi ister; şerh commit mesajına yazılır.
5. **Held-out dokunulmaz** (A3): kör-test/held-out görülmeden mekanizma
   "genel" ilan edilmez; yeni gerçek veri geldiğinde ilk iş held-out sınavı.
6. **Karne zorunlu:** her YONTEM §3 kaydının sonuna A11 karnesi düşülür:
   `Karne: tetik=geometrik/AD-VAR | kapı=PASS/BEKLİYOR | sıfır-dokunuş=
   KANITLI/BEKLİYOR | sözleşme=DEĞİL/HOCA-BEKLİYOR | held-out=BEKLİYOR`.

---

## B. Alınmış kararlar (taslağın §9 açık soruları — 2026-07-06)

> Öneri statüsünde karara bağlandı; Eren aksini söylerse güncellenir.

**B1 — Held-out kümesi:**
- **Development (tuning serbest):** plan1, plan2, plan3, deneme4, sentetik
  jeneratör aileleri. (Gerekçe: dördü de K-12..K-25 geliştirmelerinde
  kullanıldı — held-out İLAN EDİLEMEZLER; dürüstlük bunu gerektirir.)
- **Held-out (dokunulmaz):** numune, boxy, ve **bundan sonra gelen HER yeni
  gerçek sipariş otomatik held-out doğar.** Yeni veri yeterince birikince
  (aile başına ≥2) en eski yeni-veri development'a "terfi ettirilebilir" —
  yalnız açık kararla ve registry kaydıyla.

**B2 — Kapı eşikleri (legal-yükseklik, set başına):**
- Gürültü bandı ±%0.5 (voxel kuantizasyonu; bu bant içi = "değişmedi").
- Herhangi bir dev-set'te >%2 kötüleşme VEYA herhangi bir set INVALID'e
  düşüyor → **FAIL.**
- Hiçbir set >%0.5 kötüleşmiyor VE ≥1 set >%0.5 iyileşiyor → **PASS.**
- Arası (küçük trade-off'lar) → **İNSAN KARARI**; trade-off tablosu yazılır.

**B3 — Aile taksonomisi:** F1 geometrik taksonomi (`instances/family.py`:
thin_shell/tube/thin_plate/long_rod/solid_bulk/mixed_scale/unknown)
**birincildir** — üretim (wall_aware/F5 routing) onu kullanıyor. Telemetrideki
jeneratör adları (`random_boxes`...) aile değil **kaynak etiketi**dir; telemetri
v2'de `source` alanına taşınır, `aile` alanı F1 değeri alır (`01_VERI.md` §4).

**B4 — Yatırım seviyesi:** kademeli. Faz-0 konsolidasyon (tek `eval_gate` CLI,
mevcut parçaları birleştirir) → Faz-1 registry → Faz-2 telemetri v2 → Faz-3
Bayesian tuning. Tam framework big-bang'i YOK (bkz `02_EVAL_KAPISI.md` §5).

**B5 — Clearance önceliği:** KAPANDI — `a274628` ile temel atıldı; eval kapısı
bu temelin üstüne kurulur (min_clearance zaten metrik bileşeni).

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
boşluk ≥ 1mm (`clearance.min_clearance`), (iii) ayrılabilirlik: 0 kilit
(`accessibility.check_result`). Biri ihlalde sonuç **INVALID**'dir ve sebep
raporlanır. Gerekçe: K-19 (0.084mm ihlalli 282), K-21 (554 kilitli 262.5) —
kısıt ihlalini maskeleyen metrik şişer.

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

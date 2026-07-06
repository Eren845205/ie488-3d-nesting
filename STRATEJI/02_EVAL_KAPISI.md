# 02_EVAL_KAPISI — Dürüst Metrik, Kapı Tanımı, Runbook'lar

> Anayasa bağları: A1 (kapısız kazanç yok), A2 (legal-yükseklik), A5 (dağılım
> raporu), B2 (eşikler). Bu dosya kapının NASIL koşulduğunu tanımlar.

---

## 1. Dürüst metrik tanımları

**`legal_height_mm`** (başlık metriği):
```
legal_height(koşu) =
  height_mm   eğer  n_placed == n_total
             VE  min_clearance(placements) >= 1.0mm   (clearance.min_clearance)
             VE  accessibility.check_result.n_locked == 0
  INVALID(sebep)  aksi hâlde
```
- INVALID bir sayı DEĞİLDİR; kıyas tablosunda `INV(sebep)` yazılır ve o koşu
  hiçbir iyileşme iddiasına kanıt olamaz. (K-19: 0.084mm ihlalli 282 böyle
  yakalanırdı; K-21: 554 kilitli 262.5 böyle yakalanırdı.)
- Clearance şartı hocanın kuralına bağlı: taban 1mm; yoğun plakada 2mm önerisi
  operatör knob'u (dayatma değil). Kıyaslar hangi değerle koşulduğunu yazar.

**İkincil metrikler:** doluluk oranı (bilgi amaçlı — [[feedback-doluluk]]
dersi: mutlak doluluk işin doğası gereği düşük, kıyas ancak aynı iş üzerinde),
`duration_s`, `peak_ram_mb` (6GB istemci zarfı), `n_locked`,
`min_clearance_mm` (ham değerler her zaman raporda).

**Seçim-modeli metriği — REGRET (accuracy değil):**
```
regret(instance) = legal_height(seçilen mod) - min üzerinden tüm modlar legal_height
```
Accuracy yanıltır: modlar arası fark bazen 0.5mm bazen 100mm. Başlık:
ortalama + maksimum regret (mm), aile kırılımlı. Accuracy yalnız yardımcı.

## 2. Kapı koşusu tanımı

- **Kapsam:** TÜM dev-set'ler (plan1, plan2, plan3, deneme4 + sentetik
  temsilciler). Held-out YALNIZ final doğrulamada (registry'ye bakış kaydıyla).
- **Sabitler:** seed=42, gerçek plaka değerleri (deneme4: 325×325; plan2:
  328.74×328.19; diğerleri registry'den), clearance=1.0mm, üretim decode yolu
  (değişiklik hangi yoldaysa o yol + değişmeyen yollar bit-özdeşlik kontrolü).
- **Çıktı formatı (dağılım tablosu — A5):**

  | set | aile | önce | sonra | Δ% | verdict |
  |---|---|---|---|---|---|
  her satır legal_height; INVALID ise sebep. Altına: süre/RAM değişimi.

- **Eşikler (B2):** herhangi bir set >%2 kötü veya INVALID'e düşüş → FAIL ·
  hiçbiri >%0.5 kötüleşmeden ≥1 set >%0.5 iyileşme → PASS · arası → insan
  kararı (trade-off tablosu zorunlu).
- **Bit-özdeşlik yükümlülüğü:** dokunulmayan yollarda önce==sonra BİREBİR
  beklenir (H-15p/H-16 deseni); fark varsa değişiklik "izole değil" → önce onu
  açıkla.

## 3. Runbook — yeni algoritma fikri (K-xx / H-xx)

1. **Kayıt:** YONTEM_HARITASI §3'e aday satırı (ne, niçin, beklenen ödül).
2. **Ucuz teşhis (A4):** dakikalık analizle hüküm verilebiliyor mu?
   (K-23 deseni: replay/teşhis scripti `scripts/` altına, log'uyla.)
   Teşhis NO-GO derse → §3'e NO-GO kaydı, DUR. (K-24 Adım-1 deseni: teşhis
   "post-hoc imkânsız, sıra-içi umutlu" gibi YÖN de değiştirebilir.)
3. **Prototip:** üretime dokunmadan `scripts/` içinde; ölçüm =
   `legal_height` (INVALID görünce erken kes).
4. **Kapı koşusu:** §2. PASS → üretime bağlama işi (builder + reviewer +
   tam suite, bayat-mock kontrolü A9) → commit + anchor güncelle (A8).
5. **Kayıt kapanışı:** §3 satırı sonuç + kanıt yoluyla güncellenir.

## 4. Runbook — yeni gerçek veri geldi

1. Gözcü işledi → `01_VERI.md` §3 protokolü: registry'ye **held-out** kaydı.
2. Üretim sonucu (müşteri çıktısı) zaten var; bu bakış SAYILMAZ.
3. Ekibin merakı için held-out karşılaştırma koşusu İSTENİYORSA: tek koşu,
   registry'ye bakış kaydı, sonuç rapora — ve o sonuçtan tuning kararı
   ÇIKARILMAZ (çıkarılacaksa set dev'e transfer edilir ve held-out'luğu düşer).
4. Magics/rakip değeri varsa: clearance + plaka + ayrılabilirlik şartları
   sorulmadan kıyas tablosuna "şerhli" girer (A10).

## 5. Fazlar (B4 kademeli yatırım)

- **Faz-0 — Konsolidasyon (ilk iş):** `scripts/eval_gate.py` tek CLI:
  mevcut parçaları çağırır (`c3_generality` DATASETS + `clearance.
  min_clearance` + `accessibility.check_result`), §2 tablosunu üretir,
  verdict basar. Yeni algoritma YOK — yalnız birleştirme. Kabul: Deneme4
  264.0 + plan setleri mevcut anchor'larla birebir.
- **Faz-1 — Registry:** `01_VERI.md` §2 tablosunun `data/registry.json`
  karşılığı + eval_gate'in held-out'u koşmayı reddetmesi (açık bayrak
  `--heldout-final` olmadan).
- **Faz-2 — Telemetri v2:** `01_VERI.md` §5 alanları tek satırda; gözcü
  koşuları otomatik yazar. (Çoğu alan zaten üretiliyor — kablo işi.)
- **Faz-3 — Tuning/öğrenme:** `04_MOTOR_TUNING.md` + `03_SECIM_MODELI.md`
  yol haritaları bu altyapının ÜSTÜNE.

## 6. Bilinen sınırlar (dürüstlük)

- Kapı deterministik ama TEK seed'li; seed-duyarlılığı şüphesinde 3-seed
  (42/13/7) medyanı istenebilir — maliyet 3×, yalnız kritik kararlarda.
- Sentetik dev-set'ler kutu-ağırlıklı; kabuk ailesi tek gerçek temsilciyle
  (deneme4) sınırlı → kabuk jeneratörü gelene dek kabuk kararları fazladan
  ihtiyat ister (01_VERI §6).
- Süre bandı tahminleri iyimser olabilir (H-16 dersi) — GO/NO-GO süre
  iddiaları uçtan-uca ölçümle doğrulanır, bileşen toplamıyla değil.

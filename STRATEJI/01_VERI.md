# 01_VERI — Veri Yönetimi: Registry, Held-Out Protokolü, Taksonomi, Telemetri v2

> İlkeler: `00_ANAYASA.md` A3 (held-out dokunulmaz), B1 (küme kararı),
> B3 (taksonomi). Bu dosya operasyonel detayı taşır.

---

## 1. İki veri rejimi, zıt ekonomiler (temel model)

| | Sentetik | Gerçek |
|---|---|---|
| Arz | Sınırsız + bedava (jeneratörler) | Kıt + değerli (hoca maili) |
| Görev | Seçim modelini **eğitmek**, dev-döngüde çeşitlilik | Genellemeyi **doğrulamak** |
| Sınır | Jeneratörün üretmediği gerçek-dünya şeklini asla öğretmez | Tuning'e sokulan gerçek veri held-out vasfını **sonsuza dek** kaybeder |
| Mevcut | 69 instance / 6 jeneratör ailesi / 460 telemetri satırı | plan1/2/3, deneme4, numune, boxy (+ gözcü kanalı) |

**Tek dürüst genelleme testi gerçek held-out'tur.** Sentetik→sentetik CV skoru
sentetik→gerçek genellemeyi garanti etmez.

## 2. Instance Registry (tek doğruluk kaynağı)

Kayıt yeri: bu dosyanın §2.1 tablosu (Faz-1'de `data/registry.json`'a taşınıp
buradan işaret edilebilir). Her gerçek instance şu alanlarla kaydedilir:
`id · kaynak (mail/elle) · geliş tarihi · parça/adet özeti · F1 ailesi ·
plaka · rol (dev/held-out) · held-out bakış sayısı + tarihleri · notlar`.

### 2.1 Kayıtlı gerçek instance'lar (2026-07-06 itibarıyla)

| id | F1 aile (baskın) | rol | gerekçe / bakış kaydı |
|---|---|---|---|
| plan1 | mixed (NFV kazandı) | **dev** | K-12+ NFV geliştirmesinde kullanıldı |
| plan2 | mixed | **dev** | tuning'de kullanıldı; Magics açığı %4.2 kapanışı |
| plan3 | mixed (levha ağır) | **dev** | K-18 AX24 geliştirmesinde kullanıldı |
| deneme4 | thin_shell (588; 62 çan + düğmeler + 2 ROBT) | **dev** | K-19..K-25 kabuk-ailesi geliştirmesinin ana aracı |
| numune | (tek parça çeşidi; heightmap) | **held-out** | erken dönem frozen anchor'ı var; tuning döngüsünde değil |
| boxy | solid_bulk (sentetik-gerçek karışım kutu) | **held-out** | c3_generality'de kontrol seti |
| deneme6 | (15 parça × 1 adet; küçük-orta karışık; en büyük 149×149×30) | **held-out (doğuştan)** | 2026-07-09 hoca maili → `VERILER/Deneme6/`; **referans 86,32 mm (MANUEL yerleşim — Magics değil; koşullar yaklaşık, A10 şerhli)**. Envanter bakışı 2026-07-09 (yalnız metadata: gövde/adet sayımı; ÇÖZÜM KOŞULMADI). Adet STL'de gömülü değil → 15×1. Kör-test protokolü: R11 (`06_HOCA_2026-07-09...md`) |
| plan7 | *(F1 sınıflaması koşuda)* | **held-out (doğuştan)** | 2026-07-20 hoca maili (thread "Plan1 ve Plan 3 Nesting", mesaj `19f7fad84ee93dbb`; adet .txt eki + Google Drive `Plan7.zip` 19.5MB); **referans 595 mm üretim yüksekliği (hazırlanış yöntemi + boşluk/kenar koşulu MAİLDE YOK → A10 şerhli)**. **Mail kısıtı: `288101642-a2` "Konumu değişmeyecek" (pin — K-56g üretim kablosu bağlanana dek koşular şerhli).** ZIP Drive'dan indirildi 2026-07-21 → `Veriler/Plan7/` (10 STL, adetlerle birebir). Envanter bakışı 2026-07-21 (yalnız metadata: 10 tip / 345 adet, tümü watertight, ince-plaka ağırlıklı, z-max 231mm; ÇÖZÜM KOŞULMADI; kanıt `results/plan7_envanter.json`). eval_gate kablosu hazır (`--heldout-final --sets plan7`); kör-test sakin-makine bekliyor. |
| *(yeni mail)* | *otomatik F1* | **held-out (doğuştan)** | gözcü kanalı, §3 |

**Kural:** held-out koşusu yapıldığında bu tabloya `bakış: YYYY-MM-DD (sebep)`
eklenir. Bakış sayısı bir setin "tükenmişlik" göstergesidir — çok bakılan
held-out sessizce dev-set'e dönüşür (bilgi sızıntısı); ≥3 bakışta rol
değerlendirmesi yapılır.

## 2.2 Kör-test karnesi — held-out İLK-KOŞU açığı (eklendi 2026-07-21)

> **Amaç (Eren eleştirisi 2026-07-21: "sonsuz kere farklı veride açık
> kapatamayız; overfit diye bağırıyorum, önlem uygulanmıyor"):** Genelleme
> iddiasının TEK dürüst ölçüsü, yeni verinin out-of-the-box (hiç dokunmadan,
> üretim default'uyla) referansa açığıdır. Bu seri ZAMANLA DÜŞMÜYORSA
> mekanizma envanteri yakınsamıyor demektir → ürün stratejisi kapsam-beyanına
> döner (güçlü aileler satılır, zayıfta insan-destekli mod). Her yeni veri
> buraya İLK koşusuyla girer; sonradan kapatılan açık BU TABLOYU DEĞİŞTİRMEZ
> (tarihsel dürüstlük — trend metriği ilk-koşudur).

| Set | İlk-koşu tarihi | Üretim kolu | Max kolu | Referans | İlk-koşu açığı | Şerhler |
|---|---|---|---|---|---|---|
| deneme6 | 2026-07-21 | **68.50 LEGAL** (clear 3.25, kilit 0, NFV-fast, 29s) | **65.50 LEGAL** (kilit 6→rot 0 söküm-planlı, 66s) | 86.32 (manuel, A10ş) | **−%20.6 (MANUEL-ALTI)** | 12 gün koşulmadan bekledi (süreç dersi); max kolu −%24.1; kanıt results/deneme6_heldout_final.json |
| plan7 | 2026-07-21 | **488.40 LEGAL** (clear 2.000, kilit 15→rot 0 söküm-planlı, r11 uygulandı, 103dk) | **488.40 BİREBİR-ÜRETİM** (AX24 kazanç 0; clear bit-özdeş; 81dk taze proses) | 595 (yöntem bilinmiyor, A10ş) | **−%17.9 (MANUEL-ALTI)** | pin kısıtı uygulanmadı; koşu NOGO_STD'li (595'in no-go koşulu bilinmiyor — açık bizim aleyhimize bile olabilir) |

**Kural:** kör-test sonucu görüldükten sonra o set için mekanizma
geliştirilmesi = held-out'u dev'e çevirmek. YAPILMAZ; açık ölçülür, kaydedilir,
geliştirme ancak aile dev'e terfi ederse (B1 ≥2 kuralı) başlar.

## 3. Yeni altın kanal: gözcü / otonom_gecmis (taslakta yoktu)

Sipariş-bazlı kalıcı kayıtlar (commit `94c3aeb`) sayesinde **her gelen mail
otomatik olarak tam bir gerçek instance üretir**: STL'ler + adetler + koşu
sonucu + detay JSON + GLB. Protokol:

1. Gözcü yeni siparişi işler → kayıt `data/otonom_gecmis`'e düşer.
2. İnsan (veya oturum) kaydı §2.1 registry'ye ekler: rol = **held-out**.
3. Koşu sonucu (legal-height + telemetri) zaten üretilmiş olur — bu SAYILMAZ
   bakış olarak (üretim koşusu ≠ geliştirme bakışı); ama sonucu bir iddiayı
   ayarlamak için kullanmak = bakıştır, loglanır.
4. Aile başına ≥2 held-out birikince en eskisi açık kararla dev'e terfi
   edebilir (00_ANAYASA B1).

**Hocaya veri talebi standardı:** aile-dengeli 2-3'er sipariş (özellikle
thin_shell, tube/cavity, mixed_scale); format: STL'ler tek ZIP + adet listesi
mail gövdesinde (mevcut parser formatı). Magics karşılaştırma değeri ve
kullanılan clearance/plaka ayarları İSTENİR (A10 eşit-şart kuralı).

## 4. Aile taksonomisi — birleştirme (00_ANAYASA B3'ün uygulaması)

**Birincil:** F1 geometrik taksonomi (`src/nesting3d/instances/family.py`):
`thin_shell · tube · thin_plate · long_rod · solid_bulk · mixed_scale ·
unknown` (+`classify_confirmed` voxel-doluluk rafinesi). Üretim (wall_aware F5
routing) bunu kullanıyor; held-out dengeleme, gate raporu kırılımı ve seçim
modeli stratifikasyonu da BUNU kullanacak.

**İkincil (kaynak etiketi):** jeneratör adları (`random_boxes`,
`few_large_many_small`, `high_qty_repeat`, `thin_plates`, `long_rods`,
`bischoff_ratcliff`) aile DEĞİL, verinin nereden geldiğidir.

**Geçiş:** telemetri v1 satırlarındaki `aile` alanı jeneratör adı taşıyor;
v2'de `aile` = F1 değeri, `source` = jeneratör/mail kaynağı. Eski satırlar
dönüştürülmez (okurken map'lenir: jeneratör adı → `source`, F1 yeniden
hesaplanır — deterministik, geometriden türer).

## 5. Telemetri v2 şeması (karar-yüzeyi kayması için ön şart)

Mevcut satır (`telemetry.py`): `instance_id · cozucu(dblf/sa3d/ga/tabu) ·
height_mm · feature_vector(20) · feature_names · aile(jeneratör)`. Bu şema
eski portföy dünyasına ait. **v2 ekleri** (additive — v1 alanları donuk kalır,
20-özellik vektörü FROZEN; `EXTENDED_FEATURE_NAMES` 20+3 zaten additive
deseni kurdu):

| Alan | İçerik | Niçin |
|---|---|---|
| `mode` | `heightmap` / `nfv` / `wall_aware` | asıl üretim kararı bu — etiketlenmeli |
| `legal_height_mm` | A2 tanımlı; ihlalde `null` + `invalid_reason` | dürüst metrik |
| `min_clearance_mm` | HIGH-2 gate telemetrisi (zaten üretiliyor) | clearance kanıtı |
| `n_locked` | accessibility kilit sayısı | ayrılabilirlik kanıtı |
| `family_f1`, `family_conf` | F1 sınıflandırma + güven | stratifikasyon |
| `source` | jeneratör adı / `mail` / `elle` | rejim ayrımı (§1) |
| `pitch_coarse`, `pitch_fine`, `n_orientations` | koşu config'i | knob-tuning verisi (04) |
| `duration_s`, `peak_ram_mb` | maliyet | hız/kaynak kapıları |

Kaynaklar hazır: `min_clearance_mm` ve `clearance_capped_margin` telemetrisi
`a274628` ile üretimde; kilit sayısı `accessibility.check_result`'ta; F1
`classify_family`'de. **İş = tek satırda buluşturmak** (Faz-2,
`02_EVAL_KAPISI.md` §5).

## 6. Sentetik genişletme (düşük öncelik, ucuz)

- Hedef: 69 → ~150-180 instance (aile başına 20-30) — aile-CV kararlılığı.
  Darboğaz DEĞİL; boş kalan zamanda yapılır.
- **Domain randomization:** gerçek dev-instance'ları perturbe et (qty ±%30
  jitter, tek-tip ölçek ±%10, karışım oranı değişimi) → "gerçeğe komşu"
  sentetikler. Gerçek held-out'a DOKUNMADAN gerçek-dünya dağılımına yaklaşır.
  Perturbe edilmiş veri her zaman `source=perturb(<orijinal>)` etiketi taşır
  ve asla held-out sayılmaz.
- Jeneratör kapsam boşluğu: mevcut 6 aile kutu-ağırlıklı; thin_shell/tube
  jeneratörü YOK (Deneme4'ün ailesi!). Kabuk jeneratörü (parametrik çan/boru
  STL üretimi) sentetik listenin ilk sırası.

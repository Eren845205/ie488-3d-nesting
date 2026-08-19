# ML YENİDEN-YAPILANMA PLANI — Karar Katmanını Öğrenen Sisteme Dönüştürme

> Tarih: 2026-08-18 · Eren direktifi: "Asıl baz almamız gereken NFV-max /
> heightmap [el kuralları] değil — ML kısmı oldukça eksik; bu haliyle
> eğitirsek overfit riski taşır. ML'yi bu büyük işe uygun şekilde
> yapacağız. Hangi verilerin eğitime gireceğine karar vereceğiz; önce son
> veriyle (fsm610) çalışıp sonra hepsiyle yeniden eğiteceğiz. Büyük
> firmalara/fabrikalara hitap edeceğiz — farklı tipte veriler gelecek."
>
> Temel: `RAPOR_FSM610_SINIF_VE_ML_DENETIMI_2026-08-18.md` (D-1..D-7
> bulguları) + `03_SECIM_MODELI.md` + `EGITIM/` protokolü. Bu plan
> ANAYASA'nın HİÇBİR maddesini gevşetmez; A6/Y-1 (sessiz öğrenme yasak),
> Y-2 (held-out dışlama), Y-3 (stdlib) aynen geçerli.

---

## §0 — İLKE: Yamalı kural değil, öğrenen karar katmanı

fsm610 dersi: K-65 tarzı el-istisnaları tek vakayı kapatır ama her yeni
müşteri sınıfında yeni bir el-kuralı gerekir — fabrika çeşitliliğine
ÖLÇEKLENMEZ. Hedef mimari (03 §2'nin uygulanması):

- **Kural = baseline** (bugünkü yönlendirici aynen kalır, hiçbir şey
  silinmez),
- **Model = challenger** (mod-düzeyi karar öğrenir; yalnız kalibre
  güveni yüksekken kuralı ezer),
- **Destek-dışı = çekimser** (eğitim verisinin kapsamadığı bölgede model
  DE kural DA karar dayatmaz → konservatif politika: NFV/çift-yol),
- **Her karar telemetriye etiketli düşer** → sistem zamanla kendi karar
  karnesini üretir (öğrenme insan-onaylı, ölçüm sürekli).

Overfit savunması tek kalemde değil HAT hâlinde (§5) — çünkü asıl risk
tek model değil, süreç: "son krizin verisine göre eğit" refleksi.

## §1 — VERİ ENVANTERİ VE ROL KARARLARI (eğitime ne girer?)

| Veri | Bugünkü rol | ÖNERİ | Gerekçe |
|---|---|---|---|
| plan1, plan2, plan3, deneme4 | dev | **EĞİTİME GİRER** (etiket üretimi §2 ile) | Zaten dev; karar-katmanı etiketi hiç üretilmedi, üretilecek |
| Sentetik 6 aile (69 inst.) + holey_frames + repeat_rod_mix | eğitim | **EĞİTİME GİRER + BÜYÜR** | Eğitimin gövdesi; §2.3 yeni aileler eklenir |
| **fsm610** | held-out (3 bakış) | **DEV'E TERFİ → Aşama-1 odak seti** ⚠️ KARAR-1 | Eren direktifi "önce son veriyle çalış"; §2.2 kuralı gereği held-out vasfı resmen düşürülür, registry'ye işlenir |
| numune, boxy, deneme6 | held-out | **HELD-OUT KALIR — eğitime GİRMEZ** | Genelleme sınavı stoku (Y-2 yapısal dışlama) |
| **plan7** | held-out | **HELD-OUT KALIR — Aşama-3 SINAV SETİ** | 345 adet, ince-plaka ağırlıklı = fsm610'a KOMŞU sınıf; fsm610-eğitiminin sınıf-genellemesini ölçecek EN DEĞERLİ sınav. Eğitime sokmak bu sınavı yakar — sokulmaz |
| deneme5 | **registry'de KAYITSIZ** ⚠️ KARAR-2 | Rol netleştirilsin (koşu geçmişi var; repeat_rod_mix dersi ondan türedi → muhtemelen fiilen dev) | Kayıtsız veri = denetim açığı; 01_VERI §2.1'e satır |
| Gelecek siparişler + mail ricası 6b | — | **OTOMATİK HELD-OUT** (B1) | Held-out stoku yenileme kanalı |

**Net cevap ("hangi veriler eğitime konacak"):** plan1/2/3 + deneme4 +
tüm sentetik aileler + (terfi onayıyla) fsm610. **Başka hiçbir gerçek set
eğitime girmez** — numune/boxy/deneme6/plan7 sınav stokudur.

## §2 — EĞİTİM VERİSİNİN ÜRETİMİ (etiketler — asıl eksik bu)

Bugün karar-katmanı için eğitim verisi YOK (460 satır eski metaheuristik
portföyüne ait). Model eğitmeden önce etiket üretilecek:

**2.1 Portföy koşuları (karşı-olgusal etiketleme).** Her eğitim
instance'ı × {heightmap, nfv-fast, nfv-max, (uygunsa wall_aware)} koşulur;
her koşu telemetri v2 satırı yazar (mode + legal_height + min_clearance +
n_locked + süre + F1 aile + kaynak). Etiket = `winner_mode` + her modun
regret'i (mm). Sentetiklerde ucuz (sn-dk); dev-setlerde pahalı (K-57a
münhasır-koşu disipliniyle, D:\ie488 gece koşuları).

**2.2 fsm610 etiketi.** 3 bakışın kayıtları zaten 2 kolu veriyor
(heightmap 652,8 İHLALLİ / nfv-max 516,0 TEMİZ, kısıtsız). Kısıtlı+NFV
kolu koşuda/koşulacak. Kısıt-semantiği kolu (S1 cevabı) MAİL SONRASI
eklenir — mod-kararı etiketi mail'den bağımsız, kısıt etiketi bağımlı.

**2.3 Sentetik genişleme (dağılım mühendisliği).**
- fsm610-SINIFI kalıcı jeneratör: yüksek-adet homojen ince-plaka kitle +
  plaka-aşan çubuk karışımı (k65 smoke prototipi `synthetic.py`'ye taşınır,
  n>=20 instance, parametrik: adet 200-800, plaka-oranı, çubuk sayısı).
- 2-faktör kombinasyon aileleri (D-7): ölçek × tip × karışım ızgarası.
- Domain randomization: dev-instance perturbasyonları (01_VERI §6,
  `source=perturb(...)` etiketli).
- Kural: **bundan sonra her held-out sınıf keşfi → kalıcı jeneratör aile
  eklenir** (runbook'a resmî adım — D-6 kapanışı).

## §3 — MODEL MİMARİSİ (evrimsel; sklearn'süz — Y-3)

Sıra önemli; her adım bir öncekinin kapısından geçmeden başlamaz:

1. **gengap model-parametrik refactor** (el kitabı backlog #2 — önkoşul;
   mevcut davranış default'ta bit-özdeş + test).
2. **Özellik ekleri (additive — 20 FROZEN korunur):** `solidity`
   (K-62 bulgusu: ML delikli parçayı GÖREMİYOR), `plaka_asan_ratio`
   (K-65 sinyalinin sürekli hâli), ölçek bandı (`log_n_total`).
   EXTENDED_FEATURE_NAMES desenine eklenir.
3. **Modeller (el kitabı §3.3-3.4 spec'leri hazır):** k-NN (k=3-5,
   mesafe-ağırlıklı; k LOO ile) + regularize multinominal logistic +
   Platt kalibrasyonu. Etiket uzayı = mod-düzeyi (`winner_mode`).
   Metrik = **REGRET (mm)**, aile-kırılımlı; accuracy yalnız yardımcı.
4. **Destek-zarfı (abstention — D-3 kapanışı):** eğitim kümesinin
   özellik-uzayı zarfı (per-özellik P1-P99 kutusu + en-yakın-komşu mesafe
   eşiği) modele gömülür; zarf-dışı sorgu → `abstain` → konservatif
   politika (NFV-kalite; asimetri felsefesi: NFV yanlış-pozitifi yalnız
   hız kaybı). Bu kural, EL KURALINA DA uygulanır: kural kendi kanıt
   zarfının (automode_proof kümesi) dışında da düşük-güven sayılır.
5. **Dağıtım politikası:** model yalnız kalibre güven >= eşik (LOO
   üzerinde seçilir) iken kuralı ezer; altında kural; zarf-dışında
   konservatif. Promote insan-onaylı + atomik (A6/Y-4); her promote
   `selection_archive`'a versiyonlu düşer.

## §4 — EĞİTİM PROTOKOLÜ (Eren'in istediği sıra: önce fsm610, sonra hepsi)

**Aşama-1 — fsm610-odaklı çalışma (terfi onayı sonrası):**
1. fsm610 registry'de dev'e terfi (bakış kısıtı kalkar; held-out listesi
   §1'deki hâliyle yenilenmiş olur).
2. fsm610-sınıfı jeneratör ailesi üretilir (§2.3) + fsm610 + sınıf
   sentetiklerinde portföy etiketleri (§2.1).
3. Sınıf-odaklı model adayı eğitilir. **Kapı:** (a) fsm610-sınıfı
   sentetiklerde regret(model) < regret(kural); (b) DİĞER ailelerde
   regret bozulmaz (aile-kırılımlı LOO); (c) dev-set motor kapısı
   sıfır-dokunuş (model yalnız karar önerir, motor değişmedi).
4. fsm610 tek başına eğitim dağılımını DOMİNE EDEMEZ: aile-dengeli
   ağırlıklama (bir gerçek set, sentetik ailesiyle birlikte tek "aile
   oyu" taşır).

**Aşama-2 — Tam yeniden eğitim:** tüm §1 eğitim kümesi + tüm sentetik
aileler; aile-stratified LOO-CV + gengap temiz + kalibrasyon; kural-vs-
model regret tablosu (03 §5.1'in nihayet koşulması). Promote KARARI
Eren'de.

**Aşama-3 — Genelleme sınavı (dokunulmamış held-out):**
1. **plan7 kör-test** (fsm610-komşu sınıf → sınıf-İÇİ genelleme kanıtı;
   pin kısıtı K-56g hattıyla). İlk-koşu açığı karneye (01_VERI §2.2).
2. Bir SONRAKİ gelen gerçek sipariş (sınıf-DIŞI genelleme).
3. Kazanç ilanı ANCAK bu sınavlardan sonra; öncesi tüm raporlar ŞERHLİ.

**Mail bağı:** Aşama-1/2'nin mod-kararı etiketleri mail'den BAĞIMSIZ
üretilir. Mail cevabı (S1/S2) yalnız (a) fsm610 kısıt-kolunun etiketini,
(b) 284-referans kıyasının kurulumunu, (c) U1 çok-plaka önceliğini bekler.

## §5 — OVERFIT SAVUNMA HATTI (tam liste — "bu haliyle eğitirsek" riskine karşı)

1. Held-out yapısal dışlama: registry `rol` alanı eğitim tablosunu
   FİLTRELER (Y-2; kod-seviyesi, niyet-seviyesi değil).
2. Sessiz öğrenme yasak: retrain yalnız insan komutu + gate + atomik
   promote (A6/Y-1/Y-4).
3. Metrik regret (mm), asla accuracy/ham yükseklik (Y-6).
4. Aile-stratified LOO-CV + gengap overfit bayrağı (cv_gap>0.2 → dur).
5. Aile-dengeli ağırlık: hiçbir sınıf (fsm610 dahil) dağılımı domine etmez.
6. Destek-zarfı çekimserliği: model bilmediği bölgede karar DAYATMAZ.
7. Domain randomization + 2-faktör kombinasyonlar: sentetik çeşitlilik
   gerçek çeşitliliğin provası.
8. Kör-test karnesi trend metriği: ilk-koşu açığı zamanla düşmüyorsa
   yakınsama YOK demektir — ürün kararı kapsam-beyanına döner (01 §2.2).
9. Konservatif asimetri: şüphede NFV (yanlış karar = hız kaybı, kalite
   kaybı değil).
10. Yeni held-out stoku sürekli yenilenir (her sipariş + mail ricası 6b).

## §6 — İŞ KIRILIMI (sıra + bağımlılık)

| # | İş | Bağımlılık | Sınıf |
|---|---|---|---|
| M1 | Telemetri v2 mod-düzeyi etiket kablosu (§2.1 formatı) | — | altyapı |
| M2 | gengap model-parametrik refactor | — | altyapı |
| M3 | fsm610-sınıfı jeneratör + kombinasyon aileleri (§2.3) | — | veri |
| M4 | Portföy koşu scripti (çok-kol + regret tablosu; münhasır-koşu uyumlu) | M1 | veri |
| M5 | Özellik ekleri (solidity, plaka_asan_ratio, log_n_total) | — | model |
| M6 | k-NN + logistic + kalibrasyon (el kitabı spec) | M2 | model |
| M7 | Destek-zarfı / abstention katmanı | M6 | model |
| M8 | Aşama-1 eğitim + kapı raporu | M3+M4+M6 | eğitim |
| M9 | Aşama-2 tam retrain + kural-vs-model regret raporu | M8 | eğitim |
| M10 | Aşama-3 plan7 kör-test + karne | M9 + Eren onayı | sınav |
| — | (paralel, ML-dışı ama bağlı) heightmap clearance teşhisi + kapı 2mm | — | korrektlik |

## §6B — ENVANTER DENETİMİ EKLERİ (2026-08-20, Eren "eksik var mı, geçiştirme" talebi)

Denetim bulgusu: model ÇEŞİDİ yeterli (8 aday + RuleAdapter, koddan sayıldı);
yarım olan 3 şey model değil: (1) öğrenilenin üretimde karar vermemesi,
(2) etiket yokluğu + etiket bütçesinin akılsız harcanması, (3) ölçüm-yerine-
tahmin zorunluluğu. Ek iş maddeleri:

| # | İş | Bağımlılık | Sınıf |
|---|---|---|---|
| M11 | **Polarite tersinmesi**: üretim karar problemi "NFV-max baz; heightmap yalnız yüksek-hassasiyet güvenli-atlama kapısıyla" olarak yeniden kurulur (KARAR-6). Etiket semantiği buna göre: hedef = "atlama güvenli mi?" (ikili, precision-öncelikli) | M4 | mimari |
| M12 | **Mod-düzeyi sonda/racing**: kaba-pitch kısa koşuyla kolları GERÇEKTE ölçüp bütçeyi kazanana ver (successive-halving; zarf-dışı/düşük-güven vakalarda tahmin yerine ölçüm) | — | mimari |
| M13 | **Aktif örnekleme**: sentetik etiket bütçesi komite-uyuşmazlığından (bagging adayları + kural AYRIŞAN bölge) tahsis edilir; ızgara/rastgele koşu yerine az koşudan çok ders | M4+M6 | veri |
| M14 | **Model→üretim kablosu**: challenger politikası (kalibre güven eşiği + destek zarfı + kural fallback + "bilgilendirme" modundan karar moduna geçiş) fiilen bağlanır; promote A6 insan-onaylı | M8 | kablo |
| M15 | **Öğrenme eğrisi + özellik-ablasyon harness**: regret-vs-n_train eğrisi ("veri mi yetmiyor temsil mi") + LOO-güdümlü özellik alt-küme denetimi (26 boyut / küçük n) | M4 | denetim |
| — | **Runbook adımı (kalıcı)**: her eğitim dalgası ÖNCESİ fsm610-raporu tipi açık-ayrıştırma (hangi mm hangi katmandan) yazılır; "veriden ders çıkarma" niyetten prosedüre iner | — | süreç |

Çift-yol netleştirmesi (Eren 2026-08-20): belirsiz/zarf-dışı vakada düşüş
yönü DAİMA nfv-max (müşteriye giden sonuç); heightmap yalnız YANINDA,
karşı-olgusal ETİKET için koşulur — kullanılmak için değil. "Heightmap'e
düşme" diye bir yol YOKTUR.

## §6C — ÇÖZÜCÜ-İÇİ ÖĞRENME PROGRAMI (2026-08-20, Eren: "algoritmaları
yarıştırsın diye değil — algoritmanın kendisi gelişsin")

Konum tespiti: mod-seçimi ML'i GÜVENLİK/VERİM katmanıdır; ilerlemenin
motoru değildir ve öyle satılmaz. Algoritmanın kendisini öğrenen yapan
program aşağıdadır — öğrenme ARAMANIN İÇİNE girer:

| # | İş | Bağımlılık | Sınıf |
|---|---|---|---|
| M16 | **Öğrenilen yerleştirme değer-fonksiyonu**: decode aday-poz skoru (temas/yerel-doluluk/kavite/erişim-bloke/boşluğa-girme özellikleri) küçük lineer/ağaç modelle; sinyal = arama geri-oynatımından final-yükseklik kredisi. Pilot saha: K-66-d dekodunun iç-kararları | K-66-d | çözücü-içi |
| M17 | **Öğrenilen sıralama politikası**: "hangi parça önce" — sabit sıra yerine durum-koşullu skor | M16 | çözücü-içi |
| M18 | **Öğrenilen parametre politikası**: instance→(SA bütçesi, relokasyon tetiği, pitch) sürekli haritası | M4 | çözücü-içi |

**Overfit konumu (kritik):** bu programın eğitim verisi MÜŞTERİ VERİSİ
DEĞİL, aramanın kendi ürettiği deneyimdir (sentetik ailelerde koşu başına
binlerce ölçülmüş yerleştirme kararı — kendi-verisini-üreten öğrenme).
Gerçek setler yalnız SINAV (A3/Y-2 aynen). "Az gerçek veri" kısıtı bu
katmanı bağlamaz.

**Risk beyanı:** araştırma-sınıfı iş; kazanç garanti değil (kredi-atama
zor); default'a dokunmadan, dev-set kapısız BAĞLANMAZ (A1/A6). DRL/GNN
uçları YONTEM §5 A3'te park — M16-M18 bunların stdlib'le denetlenebilir
öncülüdür. Öncelik: K-66-d (satış-kritik açık, elle mekanizma) ÖNCE;
M16 pilotu paralel/peşinden.

## §7 — KARAR LİSTESİ (Eren)

- **KARAR-1:** fsm610 dev'e terfi (held-out vasfı resmen düşer; Aşama-1
  başlar). ÖNERİ: EVET.
- **KARAR-2:** deneme5 registry rolü (öneri: dev olarak kaydet — dersleri
  zaten koda girdi).
- **KARAR-3:** Eval kapısı clearance eşiği 1mm→2mm + baseline yenileme
  (D-4 drift'i; ANAYASA A2 zaten 2mm diyor). ÖNERİ: EVET.
- **KARAR-4:** M1-M7 altyapı/model işlerine başlama onayı (koşular
  D:\ie488, münhasır-koşu disipliniyle; üretim default'una dokunulmaz).
- **KARAR-5:** Mail gönderimi (`HOCA_MAIL_2026-08-18_GOVDE.txt` v2).
  [GÖNDERİLDİ 2026-08-18 09:33]
- **KARAR-6 (2026-08-20, Eren sözlü yönergesi "nfv max üzerine gitmeliyiz"):**
  üretim polaritesi tersinir — default kalite-önce NFV-max; heightmap yalnız
  güvenli-atlama kapısıyla (M11). Üretim default değişikliği olduğundan
  bağlanmadan önce 4-set kapı koşusu + süre/RAM etki ölçümü raporlanır
  (A1; sözleşme değişikliği DEĞİL — clearance/no-go semantiği aynı).

## A11/A6 statüsü
Bu bir plan dokümanıdır; koşu/eğitim YAPILMADI, held-out'a bakılmadı,
hiçbir model promote edilmedi. Tüm eğitim adımları §5 hattı + EGITIM
protokolü (4-A/4-C senaryoları) altında, insan-onaylı yürüyecek.

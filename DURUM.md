# DURUM — 2026-07-25 (danışman listesi uygulama raporu)

> Kapsam: Eren onayı "1 için koşuyu şimdilik boşver, diğerlerini yap".
> Ağır koşular (4-set kapılar, plan7 kısıtlı çözüm, p3 makas teşhisi replay'i)
> bilinçli ERTELENDİ; bu rapor kod/kayıt işlerinin kapanışıdır.

## Kapanan işler

| İş | Durum | Kanıt |
|---|---|---|
| **P1 — K-56g düz-pinleme üretim kablosu** | KOD+TDD TAMAM (koşu/kapı bekliyor) | `resolve_no_go_soft` (plate_config) + `duz_pin_onerisi` (targeted_tilt, geometrik tetik — A11) + demo_pipeline c2f dalı + eval_gate `_run_champion` paritesi; **sözleşme-kapılı**: `plate.local.json`'a `no_go_soft` eklenmedikçe ölü kod (bit-özdeşlik yapısal). 12 yeni test (`tests/test_k56g_duz_pin.py`). YONTEM §3 kaydı A11 karneli. |
| **P2 — p3 üretim→şampiyon makası** | TEŞHİS PLANI HAZIR (koşu bekliyor) | Doğrulandı: R11-v4 ZATEN üretimde (`uretim_r11`), K-58 p3-kolu nötr → makas (601.92 vs 577.62) solve-başlangıç yerleşimi farkı. Teşhis adayı YONTEM §2C'de. |
| **P3 — kapalı-kavite denetimi (Faz-1, telemetri-only)** | TAMAM | `src/nesting3d/cavity.py` (dış-hacimden 6-komşuluk flood-fill); `nesting["kapali_kavite"]` + `runs_v2` additive alan; hiçbir karara BAĞLANMADI (hoca cevabı bekleniyor — soru HOCA_CEVAPLARI açık-sorularda). 160³ grid ~0.28s. 8+4 test. |
| **P4 — Dalga-2 mail-format hataları (6/6)** | TAMAM | HTML-only gövde, cp437→cp857 zip adları, çoklu-ZIP (çakışma→needs_review), kardeş .xlsx/.csv adet tamamlama, `;`-CSV sniffer, RFC2047 ek adları. `tests/test_mail_ingest_wave2.py` + eklemeler; 134 doğrudan + 109 komşu test yeşil. |
| **P5 — küçükler (3/3)** | TAMAM | H7: deterministik injection ön-taraması sipariş-parse hattında (ortak kalıp `note_detector`'dan, LLM'e hiç gitmeden karantina) · clearance resolver (`resolve_clearance`: config→env→2.0; **config alanı eklenmedi** — sözleşme onayına saklı) · OtonomJobStore restart dürüstlüğü (marker + "kesildi" kaydı). 109 hedefli test. |
| Kayıt senkronu (bilgi-kaybı düzeltmesi) | TAMAM | registry.json (d5 214.64; d6/p7 kör-test bakışları geri-dolduruldu; p7 pin→duruş kilidi) · YONTEM §2C şampiyon tablosu · HOCA_CEVAPLARI açık-soru güncellemesi · memory. |

**Birleşik doğrulama:** dört iş kolunun birleşmiş hali üzerinde 215 + 23 + 45 =
**283 hedefli test yeşil** (mail/config/kavite süpürmesi + demo_pipeline
kablo regresyonları + K-56 zinciri). ⚠️ **A9 tam suite HENÜZ koşulmadı** —
commit öncesi şart (~1.5 saat, sakin makine).

## Kapı durumları

| Kapı | Durum |
|---|---|
| K-56g 4-set kapısı (+ no_go_soft sözleşme + baseline yenileme) | **BEKLİYOR** (sakin-makine; Eren onayı) |
| K-58 kalan kollar (p3/p1) + commit | **BEKLİYOR** |
| p3 makas teşhisi (şampiyon-reçete replay kıyası) | **BEKLİYOR** |
| plan7 a2-duruş-kilitli çözüm (`plan7_kisitli_cozum.py` hazır) | **BEKLİYOR** (held-out bakışı loglanarak) |
| Kör-test karnesi | deneme6 −%20.6 · plan7 −%17.9 (2/2 referans-altı, 2026-07-21) |

## Güncel karne (referans-manuel karşı; detay PROJECT_OVERVIEW.md §2.6)

4 ÖNDE: p3 577.62ş (−%2.6) · d4 220.69 (−%11.8) · d6 68.50 (−%20.6 kör) ·
p7 488.40 (−%17.9 kör) — 3 GERİDE: p1 202.18/140.21ş · p2 529.04 (+%7.4) ·
d5 214.64 (+%2.7). Dış iletişimde genel "%10-20 daha iyi" KULLANILMAZ.

## Eren onayı bekleyenler

1. Commit paketi (bugünkü tüm working tree; öncesinde A9 tam suite).
2. Sakin-makine koşu seansı: K-56g kapısı + K-58 kalan + p3 teşhis + plan7 kısıtlı.
3. `no_go_soft` alanının plate.local.json'a eklenmesi (sözleşme, kapıyla birlikte).
4. ~~Hocaya STL+söküm paketi gönderimi~~ → **GÖNDERİLDİ + CEVAP GELDİ
   (2026-08-03).** Cevabın tam kaydı `HOCA_CEVAPLARI.md` 2026-08-03 bölümünde:
   FSM daveti · kapalı-kavite serbest (cavity telemetri-only KALICI) ·
   yoğunluk kısıtı gereksiz · kısıt 3 kanal (mail/PDF/parça-üstü XY label) ·
   Plan1 110,41 = insan yerleşimi, DÜZ-KANOPİ (çelişki ÇÖZÜLDÜ → K-62;
   aşağıda 2026-08-03 bölümü) · elle yerleşim >1 gün tahmini · sipariş
   kanalı ağırlıkla ZIP-ek. **3 ekran görüntüsü alındı →
   `Veriler/hoca_ekleri_2026-08-03/`.**
5. `kisit_modu` kapalı→gölge geçişi (eval v1.3 %85 FAIL — kapalı doğru; korpus genişletme backlog'da).
6. D:\ie488 senkronu (robocopy; koşu seansından önce zorunlu).

## Hoca paketi — 2026-07-26 durumu

**Mail:** `HOCA_MAIL_2026-07-25_TASLAK.md` (rev. 07-26) gönderime hazır; iç
işaretler gövdeden temizlendi. Kararlar: K1 mail-şimdi/çözüm-sonra · K2 ortak
Drive KABUL · K3 d4 220,7 maile girmedi · K4 kapalı-kavite sorusu var ·
K5 deneme6 rehberli söküm HTML pakete girdi.

**Paket** — 2026-07-27'de Eren isteğiyle repo dışına, ham veri setlerinin
yanına taşındı: **`Masaüstü\Veriler\hoca_paketi_2026-07\`** (21 dosya,
1,04 GB). `rehberli_sokum_uret.py` iki konumu da arıyor (repo içi → repo
yanı), yol kırılmadı. İçerik dosya üzerinde doğrulandı:
deneme6 ASCII multi-solid 179,2 MB (15 solid, adlar parça kimliği) · plan7
10 binary STL 872 MB (header'da ad+adet, 17,44M üçgen) · söküm planları
.md/.json · placements.json · **rehberli söküm HTML'leri** (deneme6 17,1 MB +
plan7 36,2 MB, 2026-07-27 üretildi) + `*_adimlar.json`.

**Gönderilecek metin:** `HOCA_MAIL_2026-07-26_GOVDE.txt` (düz metin, markdown
işaretsiz — Gmail'e doğrudan yapıştırılabilir).

**Düzeltilen hata:** taslak (ve 07-21'de GÖNDERİLEN mail) Plan7 için "15 parça
döndürme gerektiriyor" diyordu; doğrusu **344 düz / 1 döndürmeli** (Z 1°).
Kaynak: `kilit_5yon=15` kaba 5-yön ön-denetimi, `rot_cert=1` gerçek sertifika
sayısı. **Ders: dış iletişimde döndürme sayısı `rot_cert`/`n_dondurmeli`den
okunur, `n_locked`ten DEĞİL.** Maile açık düzeltme cümlesi kondu.

**Mailde verilen TEK TAAHHÜT:** plan7 a2-duruş-kilitli çözüm + güncel STL'ler
(sakin-makine seansı, RAM ≥4 GB, ~1,5-2 saat + paket üretimi). Gerekçesi
2026-07-27'de ÖLÇÜLDÜ: mevcut 488,4 çözümünde a2'nin 6 kopyasından **5'i**
duruş kısıtına aykırı (oi 8/8/12/12/15; izinli küme `{0,1,4,5}` =
`durus_koru`). Maile açık şeffaflık cümlesi kondu.

## Rehberli söküm — 2026-07-27 üretimi + 2 kod düzeltmesi

Plan7 rehberi üretilirken `scripts/rehberli_sokum_uret.py` içinde iki hata
çıktı ve düzeltildi (ikisi de YALNIZ görselleştirme hattı — motor, STL ve
söküm planı etkilenmedi):

1. **Kabalaştırma ölü yoldaydı.** voxel+marching-cubes `skimage` istiyor,
   kurulu değil → her parça "kabalaştırma olmadı" ile tam çözünürlükte
   kalıyordu (17,4M üçgen → bellek patlaması). Düzeltme: `_kaba_mesh()` önce
   quadric decimation (`fast_simplification`, kurulu) dener, voxel yolu yedek.
   Ölçüm: 116.990 → 10.062 üçgen, konum kayması 0,255 mm.
2. **Görsel denetim parça eliyordu.** Kabalaştırılmış mesh'lerle koşan 5-yön
   denetimi 95 sahte kilit üretip rehberi 250 adımda kesiyordu (teslim planı
   345 diyor). Düzeltme: **paket sırası esas**, görsel koşu yalnız yön ipucu;
   `len(adimlar) != len(placements)` artık sert hata.
   Ek: tip çözümlemesi `288101640-a1_1` gibi alt çizgili adlarda kırılıyordu →
   dosya adı desenine değil, placements'taki gerçek adlara eşleşiyor (10/10).

**Doğrulama:** plan7 rehberi tarayıcıda açıldı — 345 adım, teslim planıyla
birebir sıra ve kapsam, 1 döndürmeli parça 331. sırada (Z 1°, +X), konsol
temiz. Şablonda `clearance` rozeti ham float basıyordu → "parca arasi bosluk:
2.00 mm" olarak düzeltildi, iki rehber de `--repack` ile yenilendi.

**Kalan şerh:** görsel denetimde yön bulunamayan parçalar rehberde varsayılan
"+Z" (yukarı) gösteriyor. Teslim edilen söküm planı da düz parçalar için yön
belirtmiyor ("±X, ±Y veya +Z"), dolayısıyla çelişki yok — ama rehberdeki yön
oku bu parçalarda kesin değil, ipucu.

## ⚠️ Rehber PERFORMANS oturumu — YARIM KALDI (2026-07-27 gece)

Eren: plan7 rehberi "çok kasıyor" (RTX3060'lı makinede!). Yapılan iyileştirme
zinciri (şablonda): şeffaflık→opak renk-karışımı · istek-bazlı render ·
pixelRatio 1.0 · antialias kapalı · `powerPreference: high-performance`
(tarayıcı iGPU seçiyor şüphesi — EN GÜÇLÜ ADAY) · backdrop-filter blur
kaldırıldı · `#tani` hash'iyle açılan tanı rozeti (GPU adı + render-FPS +
üçgen/çizim). Üretim tarafında: skimage kuruldu; `_kaba_mesh` hibrit
(decimation + voxel, küçüğü kazanır; delikli parçada decimation ~%8 tabana
dayanıyor — ölçüldü); plan7 GLB 1,72M → **1,01M üçgen** (FACE_BUTCE 400K'ya
inemedi, geometrik taban).

**~~AÇIK SORUN~~ → ÇÖZÜLDÜ (2026-08-03, koşusuz teşhis — A4):** "Invalid or
unexpected token" HAYALETMİŞ — gecenin üç test kaydı (01:50/52/55,
`.playwright-mcp/page-*.yml`) birebir aynı hata ekranını gösteriyor ve o
ekranda ESKİ şablon etiketi var ("clearance: -"); 01:53'te basılan gerçek
dosya ise yeni etiketi ("parca arasi bosluk") taşıyor. Yani gece testleri
hep BAYAT bir kopyaya koştu (tarayıcı önbelleği veya farklı dizinden servis),
01:53 dosyası hiç denenmedi. Node-parse-temiz çelişkisinin açıklaması da bu.
2026-08-03 doğrulaması (Playwright Chromium, localhost servis): **plan7
31,9MB YENİ ŞABLON ÇALIŞIYOR** — 345 adım, render + turuncu vurgu + yön oku,
rozetler doğru (488.4mm / 345 / 2.00mm / 1 döndürmeli), adım ilerletme OK,
konsol temiz; deneme6 01:52 baskısı da temiz (15 adım). **Bisect'e gerek yok.**

**🎯 "ÇOK KASIYOR" KÖK NEDENİ DOĞRULANDI:** `#tani` rozeti GPU'yu
**"ANGLE (Intel UHD Graphics, D3D11)"** raporladı — tarayıcı iGPU'da render
ediyor, RTX 3060 kullanılmıyor; `powerPreference: high-performance` isteği
OS atamasını ezemiyor (gecenin "en güçlü aday" şüphesi kanıtlandı; şerh:
headless Chromium'da ölçüldü, Eren'in Chrome'unda `#tani` ile teyit edilmeli).
**Çare kod değil kullanıcı ayarı:** Windows Ayarlar → Sistem → Ekran →
Grafik → Chrome'u ekle → "Yüksek performans" (RTX 3060) seç → tarayıcıyı
yeniden başlat. Üçgen azaltma (1,85M→1,01M) zaten üretimde.

**SONUÇ:** performans-iyileştirilmiş plan7 rehberi (results/rehberli_sokum/,
01:53) ÇALIŞIR durumda → istenirse `hoca_paketi_beklemede`deki eski sürümün
yerine pakete geri girebilir; mail metni şu an yalnız deneme6'yı sayıyor —
geri alma kararı Eren'de.

**GÜVENLİ DURUM:** `Masaüstü\Veriler\hoca_paketi_2026-07\` içindeki HTML'ler
(deneme6 17,1MB + plan7 36,2MB, 27.07 00:06) tarayıcıda DOĞRULANMIŞ ÇALIŞAN
sürümler (ilk düzeltme seti; 1,85M üçgen, GPU ipucu yok) — paket bu hâliyle
GÖNDERİLEBİLİR. Eren'in B planı: olmazsa yarın yalnız deneme6 rehberiyle
gönderilir, plan7 rehberi sonra eklenir (mail metnindeki rehber paragrafı o
durumda güncellenmelidir — şu an İKİ dosyayı da sayıyor).

**→ 2026-07-27 gece: B PLANI UYGULANDI.** Eren kararıyla plan7 rehberi bu
gönderimden çıkarıldı ("çok kasıyor"); `plan7_488p4_rehberli_sokum.html` +
`plan7_488p4_adimlar.json` → `Veriler\hoca_paketi_beklemede\` taşındı.
Plan7 METİN söküm planı (.md/.json, 344 düz / 1 döndürmeli — dosyadan
doğrulandı) pakette KALDI. Mail gövdesi güncellendi: (1) rehber paragrafı
yalnız deneme6'yı sayıyor, plan7 rehberi a2-kilitli güncel çözümle birlikte
vaat ediliyor (rehber eski yerleşime iki kez yapılmasın); (2) kapanışa
Eren'in istediği geri bildirim bölümü eklendi (söküm planı nasıl olmuş /
sahada hız-verim kazandırır mı + uygulamada ekle/ekleme yön isteği).
`MAIL_METNI.txt` senkronlandı. plan7 STL doğrulama: 10 dosya, 832 MiB =
872 MB ondalık (maildeki sayı doğru). Tüm sayılar paket dosyalarından
teyitli: d6 15/15 düz (3,25mm boşluk) · p7 344/1 (174100684-a, Z 1°, +X;
2,00mm boşluk).

**Soru seti genişletildi** (Eren kararı, aynı gece revize): önce "ayrı
maile" denmişti, sonra **4 soru da bugünkü maile eklendi** — "Sorularım"
bölümü artık 7 soru: (1) eski referans boşluğu (2) kapalı kavite
(3) termal/yoğunluk sınırı (4) kısıt/not iletim süreci + örnek sipariş
notları isteği [kisit korpusu beslemesi] (5) sipariş dosyaları ek mi /
link mi geliyor [mail-ingest kanal tasarımı; link ise indirme otomasyonu
gerekecek] (6) plan1 110,41 sırrı (7) manuel yerleşim süresi. "Kısmen cevaplasanız da değerli" yumuşatma
cümlesi kondu. `HOCA_MAIL_SONRAKI_SORULAR_TASLAK.md` arşive çekildi (iç
notlar: cevap-sonrası aksiyonlar orada). Yeni veri talebi bilerek yok
(yakın zamanda istendi).

## 2026-08-03 — Hoca cevabı sonrası güncelleme (yeni veriler ışığında)

**Hoca cevabı + 3 ekran görüntüsü işlendi** (tam kayıt `HOCA_CEVAPLARI.md`
2026-08-03; ekler `Veriler/hoca_ekleri_2026-08-03/`). Sonuçları:

| Konu | Karar/Sonuç |
|---|---|
| FSM daveti | Ziyaret planı EREN'DE; gündem taslağı hazırlanabilir |
| Kapalı kavite | Serbest (eşik yok) → cavity TELEMETRİ-ONLY KALICI; DENETIM #21 KAPANDI |
| Yoğunluk/termal kısıtı | "Yazılımsal gerek yok" → iş listesinden DÜŞTÜ |
| Plan1 110,41 | İNSAN yerleşimi; DÜZ-KANOPİ + delikten-geçirme mekanizması (görüntü-kanıtlı) |
| Kısıt kanalları | mail / PDF teknik resim / parça-üstü label (3 kanal) |
| Sipariş kanalı | Ağırlıkla ZIP-ek (mevcut ingest isabetli); WeTransfer backlog |
| Elle yerleşim süresi | Tahmin >1 gün (firma teyidi + parametreler gelecek) |

**K-62 ÖN-TEŞHİS ✅ GO (koşusuz, ~dakikalar; §3 kaydı + kanıt D+repo):**
baseplate_v2 footprint doluluk %26; **düz poz gerçek geometride MÜMKÜN**
(rot0/rot180, en iyi marj 0,5mm, ofset (0, 32.8) — K-56c y-üst-33 ile
örtüşüyor). Bbox kapısı `_tilt_zorunlu_parca` YANLIŞ-POZİTİF kanıtlı.
Kanopi aritmetiği: 110,41 − 40,64 (düz kalınlık) ≈ 69,8mm kanopi-altı istif.
ŞERH: tek-set teşhis; mekanizma kodlanırsa k59-deseni dağılımsal doğrulama
zorunlu (A11). Sözleşme sorusu: no-go-temas toleransı (0,5mm marj).

**Güncel öncelik önerisi (Eren onayına):**
1. **FSM ziyareti** — hoca daveti; açık sorular (S1 eski-boşluk, no-go temas
   toleransı, örnek iş emirleri) yüz yüze kapanabilir.
2. **Sakin-makine seansı** (değişmedi): D senkron → A9 tam suite → commit →
   K-56g kapısı + K-58 kalan + p3 teşhis + **plan7 a2-kilitli (mail taahhüdü)**.
3. **K-62 kodlama** (yeni; beklenti ÇOK YÜKSEK plan1 110-130): (a) gerçek-
   geometri kapı düzeltmesi, (b) düz-kanopi mekanizması, (c) no-go-temas
   sözleşme kararı. K-56g kablosuyla birleşir.
4. **Kısıt korpus v2** → **İLK ADIM YAPILDI 2026-08-03:** gerçek kupon notu
   korpusa eklendi (`g05` tam not + `g06` kısa varyant; beklenen
   `belirsiz_kabul` — şema taşıyamıyor, yüksek-güvenli kısıt = İHLAL).
   Korpus 26→28; Kapı-0 doğrulandı (injection=false, 3 aday yakalanıyor);
   deterministik testler 15/15. Sonraki canlı eval 28 üzerinden ölçer
   (v1.3 %85 kıyasında payda farkı belirtilir). 4 yeni kısıt TÜRÜ (grup-bölme,
   45°, makine-ekseni, tek-plaka) şema/prompt-v2 işi olarak backlog'da;
   kisit_modu KAPALI kalır.
5. Backlog: WeTransfer link-indirme · PDF teknik-resim kısıt çıkarımı ·
   parça-üstü label (uzak).

## 2026-08-03 AKŞAM — kök-sebep analizi + kısıt-v2 planı + mail uygulamaları

**ANA TESLİMAT: `PLAN_KOK_SEBEP_VE_KISIT_V2.md`** (4 paralel kod envanteri
üzerine; Eren onayında). Özet:
- **Plan1 kök sebebi (KS-1..5):** çarpışma matematiği (FFT+drop_map) gerçek
  geometriyi doğru görüyor; üstündeki HER karar katmanı (bbox fizibilite
  kapıları · dilation-şişmiş büyük-önce sıralama + NFV sabit-sıra · kanopi
  altının mühürlenmesi · _drop_fallback/EP bbox yolları · TÜMÜ-bbox ML
  özellikleri) parçayı dolu kutu sayıyor. İnsan hamlesi (küçükler önce,
  delikli çerçeve EN SONA kanopi) bu yüzden arama uzayında yok.
- **Geniş çözüm (K-62 şemsiyesi):** Ç1 gerçek-geometri kapı → Ç2 düz-kanopi
  iki-aşamalı dekod (heightmap kolu; drop_map kanopi mekaniğini ZATEN
  destekliyor — ölçüldü) → Ç5 holey_frames dağılımsal + 4-set kapı → Ç3 ML
  (FEATURE_NAMES'e solidity/true_fill; `heightmap+kanopi` yeni ARM,
  regret-LOO kapısı, A6 manuel retrain) → Ç4 yardımcı yollar.
- **Kısıt-v2:** C1 grup-bölme KISA YOLU bulundu (sanal-ad ön-bölme — motor
  değişikliği GEREKMEZ) · C2 45° orta efor (extra_rot EKLER ama ZORLAMAZ —
  matris-ezici kanal gerek) · C3 recoater-ekseni (poz havuzu azimut-ayrımlı,
  ham malzeme VAR; hocadan "hangi eksen" bilgisi ŞART) · C4 tek-plaka
  (sipariş zaten bölünmüyor; sipariş-seviyesi kısıt kanalı + rapor bayrağı).
- **Yeni bug bulundu:** `/plaka-ayar` POST config'i sıfırdan yazıyor →
  `no_go_soft`/`min_clearance_mm` kaydetmede silinir (merge fix onayda).

**MAİL HATTI — UYGULANDI (testli, 135/135 komşu süpürme yeşil):**
(1) kayıp-veri FIX: share-link alanları poller+webapp'ten store'a akıyor;
(2) Kapı-0 sözlük genişlemesi (ureti·oncelik·acil·basil·tek sefer/parti/
plaka·ayni plaka·birlikte·bolun·recoater·gaz akis·transvers) + kupon gerçek
satırı testte; (3) RawMail in_reply_to/references (iki-mail ön koşulu;
otomatik birleştirme bilerek YOK); (4) allowlist +sharepoint/box/mega.
kisit_modu=kapali → davranış garantisi değişmedi.

## 2026-08-03 GECE — K-62 Ç1 çekirdeği KOD+TDD TAMAM (Eren "başla" onayı)

- `src/nesting3d/kanopi.py`: `duz_rot_matrisleri` + `duz_poz_nogo_fizibilite`
  (gerçek-footprint no-go taraması; üretim voxelizer'ı üstünden, margin=0;
  marj parametresi sözleşmeye açık; None→None bit-özdeşlik). Üretim yolu
  ÇAĞIRMIYOR — kablolama ayrı adım (kapılı).
- `tests/test_k62_kanopi.py` 9/9: delikli/dolu ayrımı + marj + **Bin3D
  mekanizma pinleri** (kule delikten geçer · no-go mührü deliği itmez ·
  son-gelen çerçeve kanopi olur — üç temel taş motorda zaten var, sabitlendi).
- Gerçek-veri çapraz doğrulama: çekirdek ön-teşhisle birebir (0.2606 /
  rot180 / dy 32.5 / 10 uygun).
- SIRADAKİ (Ç2): kanopi dekod ölçüm scripti — plan1'de "kanopi-parça sona +
  düz-kilit + no-go-mühür" koluyla A/B (sakin-makine); sonra Ç5 holey_frames
  dağılımsal + kablolama + 4-set kapı.

## 2026-08-03 GECE-2 — K-62 Ç2 ölçüm scripti HAZIR (duman PASS)

- `scripts/k62_kanopi_plan1.py`: NAİF kanopi iki-aşama ölçümü — aşama-1
  kanopi-hariç şampiyon çözüm (`_run_champion`, extra_rot={}) → aşama-2
  Bin3D replay + düz-4-azimut drop (no-go mühürlü, z_gap=2mm) + merged-mesh
  clearance + **delik-farkındalık telemetrisi** (dolu-kolon-altı vs
  delik-kolon-altı yükseklik dağılımı — "farkındalı aşama-1" kazancının
  ön-ölçümü). Kanopi adayı GEOMETRİK tetikle (alan-oran≥0.35 + doluluk<0.6 +
  no-go-fizibil; veri-adı YOK — A11).
- Duman testi (ucuz yarı): tetik baseplate_v2'yi kendisi seçti; üretim
  pitch 1.016'da soft-no-go ile 115 uygun ofset.
- **No-go dikdörtgeni düzeltmesi:** ön-teşhis HOCA_CEVAPLARI tablosundaki
  (185.1-215.2)'yi kullanmıştı; üretim sözleşmesi `eval_gate.NOGO_STD` =
  (152.5-185.5). Üretim değerleriyle hüküm GÜÇLENDİ: std 30 · soft 510
  uygun ofset (0.5mm). Script üretim sabitlerini kullanıyor.
- Dürüst beklenti: NAİF kolun ~140-145 çıkması muhtemel (K-56f pin'e benzer;
  aşama-1 delik-farkındasız). Ölçümün asıl değeri telemetri: kuleler delik
  bölgesine toplanırsa kanopinin kaç mm'ye ineceğini sayısallaştırır →
  farkındalı-aşama-1 tasarımının verisi.
- KOŞU KUYRUĞU (sakin-makine, sırayla): D senkron → A9 tam suite → commit →
  plan7 a2-kilitli (mail taahhüdü) → K-56g 4-set kapısı → K-58 kalan →
  p3 teşhis → **k62_kanopi_plan1**.

## 2026-08-04 GECE VARDİYASI — A9 yeşil + commit + K-62 Ç2 ÖLÇÜLDÜ (136,50!)

- **A9 tam suite: 3109 passed** (4:05h, düşük-RAM makine); 2 fail = bayat-mock
  (K-56g `orientation_overrides` imzası; test_sure_kirilim +
  test_reporting_wave_f0 fake'leri) → düzeltildi, izole 25/25.
- **Commit `aeb86a1`** (86 dosya): K-61/K-56g/kavite/mail/K-62/kayıtlar.
  Veriler/ dışarıda; PUSH YOK.
- **K-62 Ç2 plan1 ölçümü (şerhli GO):** naif kanopi 148,50 (clear 2,000) →
  telemetri (dolu-altı ort 70,2 ≈ ideal 69,4; p95 105) → **suçlu-taşıma
  iterasyonu 136,50 mm (clear 2,018) — pin 140,21 GEÇİLDİ; plan1 yeni
  en-iyi (şerhli)**. Zincir: 202,18 → 148,5 → 136,5; manuel 110,41'e kalan
  makas 26,1. Kanıt results/k62_kanopi_plan1* (D+C; naif arşiv _v3naif).
  Şerhler + koşu-mühendisliği dersleri (OOM/FATAL-kalkanı/NFV-seyrek)
  YONTEM §3 K-62 kaydında. Sonraki aday: delik-farkındalı aşama-1
  yumuşak-tavan + kule-drop azimut araması.

## 2026-08-04 ÖĞLE — PLAN7 a2-KİLİTLİ ÇÖZÜM TAMAM (MAİL TAAHHÜDÜ KAPANDI)

**SONUÇ: legal 488,40 mm — KISIT MALİYETİ +0,00 mm** (kısıtsız 488,40 ile
birebir; a2'nin 6 kopyası artık `durus_koru` [0,1,4,5] pozlarında).
clear 2,000 · kilit 15→rot 0 (söküm-planlı legal) · r11 uygulandı ·
**süre 49 dk** (K-60 sayesinde; ilk koşu 103 dk idi) · ref-595'e −%17,92.
K-56g/K-61 kısıt kablosunun İLK GERÇEK-VERİ koşusu — kablo çalıştı.
**Paket üretildi:** `D:\ie488\results\hoca_paketi_2026-07\` altında
plan7_a2_kilitli_{placements.json, sokum_plani.md/json, stl/} (10 binary
STL, 872 MB, 345 parça, 1 döndürmeli). Held-out bakışı registry'ye
loglandı (A3). Kanıt: results/plan7_kisitli_cozum.{json,log} (D+C).
Hocaya gidecek içerik HAZIR — gönderim Eren'de (dış-iletişim sınırı).

## 2026-08-04 — k62 V5 deneyi: NO-GO (v4 136,50 geçerli kalır)

V5 (kule-drop 4-azimut + boy-sıralı + çok-tur): tavan AYNI 136,50 →
azimut/sıra kaldıraç DEĞİL; üstelik v5 kompozisyonunda clearance 0,214
(İHLAL) → V5 NO-GO. **Geçerli plan1 şerhli en-iyi: v4 136,50 (clear
2,018).** Ders: 136,5 tavanını kanopi-üstü kule yapıyor; kalan kaldıraç
delik-farkındalı AŞAMA-1 (kuleleri baştan delik bölgesine çözen derin iş —
sabah planına). Script t0-gölgeleme json bug'ı düzeltildi (rerun gereksiz,
v4 kanıtı geçerli).

## 2026-08-04 AKŞAM — k62 v6: NO-GO (öğretici) — v4 136,50 plan1 en-iyisi kalır

**v6 (çözüm-güdümlü kule-pinleme, iki-fazlı):** faz-A suçlu sayımı MÜKEMMEL
çalıştı (28: bobbin ailesi 26 + 811793-1×2; hepsi deliğe pinlendi). Ama
faz-B'de pin uyumu için rota heightmap'e zorulunca (K-56 guard: pin NFV'de
yok) taban istifi çöktü: aşama-1 105,50 (NFV) → **124,97 (heightmap,
pitch 1.016)**. Naif 167,64 · iterasyon 180,85 (clear 0,768 İHLAL; suçlu
58'e patladı — delik kapasitesi doldu) · v5 209 (ihlal). **KÖK NEDEN:
pin kazancı < NFV taban kalitesi kaybı.** Plan1'de 136,5→110 yolu artık
net tek adrese çıkıyor: **NFV dalına pin/bölge-farkındalık desteği**
(üretim-motor işi, kapılı; K-62 Ç2-derin olarak plana yazıldı).
Kalıcı kazanım: coarse_to_fine ÇOKLU-KOPYA pin desteği (testli, 8/8;
tekil davranış bit-özdeş) — gelecekteki her pin işinin altyapısı.
Kanıt: results/k62_kanopi_plan1_v6b.log (+_v6a FATAL arşivi D'de).

## 2026-08-04 GECE — k62 v7: NO-GO — plan1 günü v4=136,50 ile kapandı

**v7 (suçlu tiplere yatay poz-kilidi, NFV-içi):** kilit uygulandı (4 tip,
16 yatay poz) ama öngörülen risk gerçekleşti: yatık bobbinler taban alanını
yiyince NFV tabanı 105,5→119,0'a çıktı; yatıklar üst üste bindi (dolu-altı
max 118,5; suçlu 37'ye çıktı). Naif 157,0 · iterasyon 170,5 → v4'ün
gerisinde. **DERS: alan sınırı — 111 parça 69mm bütçeye tamamen yatırılarak
SIĞMIYOR; kuleler kaçınılmaz, çözüm onları DELİK İÇİNDEN yükseltmekte
(insan çözümü böyle: kanopi ~70 + delikten 110'a kadar kuleler).** Sıradaki
tek adres: v8 = NFV'ye pin/bölge-farkındalık (kapılı motor işi, ayrı seans;
plan Ç2-derin'de). Kanıt: results/k62_kanopi_plan1_v7.log.
Gün özeti: v4 GO (136,50) · v5/v6/v7 NO-GO (üçü de kayıtlı, A7).

## 2026-08-04 KAPANIŞ — yarın hazırlığı + sistem geri-açma

- **Sistem geri açıldı:** OneDrive senkron ✅ · Windows Search ✅ · Ollama ✅.
- **K-56g kapı runner'ı HAZIR:** `scripts/k56g_kapi.py` — soft no-go'yu
  ENV ile ilan eder (üretim config'e DOKUNMAZ); beklenti p1 iyileşme +
  p2/p3/d4 birebir. Koşum (sakin makine): D'den
  `python -m scripts.detach_run k56g_kapi`. PASS sonrası plate.local.json
  ilanı + baseline = ayrı Eren onayı.
- **v8 iş planı yazıldı** (PLAN_KOK_SEBEP_VE_KISIT_V2.md Ç2-derin):
  NFV'ye pinned_placements — occupancy ön-yükleme + taşınmaz kümesi +
  guard güncellemesi + bit-özdeşlik kapısı + k62-V8 ölçümü (beklenti
  111-125). ~1 gün kod+test.
- YARIN SEANSI ÖNERİSİ (Eren onayıyla): (1) k56g_kapi koşusu → PASS ise
  sözleşme/baseline kararları, (2) v8 kodlama+ölçüm, (3) K-58 kalan +
  p3 makas teşhisi (fırsat kalırsa).

## 2026-08-04 GECE-2 — HOCA CEVABI: PAKET TESLİM ALINDI, TAAHHÜT KAPANDI

Mert Bey aynı gün cevapladı ("Çok teşekkür ederim, elinize sağlık"):
yeni talep ŞU AN yok · yeni planlar geldikçe iletilecek · **FSM ziyareti
teyit** ("bazı konuları FSM'de netleştiririz"). → a2-kilitli çözüm + STL
+ rehber taahhüdü RESMEN KAPANDI (kayıt HOCA_CEVAPLARI 2026-08-04).
Bekleyen dış-halka işleri: FSM tarihi (Eren) + yeni plan geldiğinde
İLK İŞ held-out sınavı (A3).

## 2026-08-04 GECE-3 — kapı-1 NOOP = v8 motor değişikliklerinin 4-set kanıtı

k56g_kapi ilk koşusu env-ilan hatası yüzünden pin dalını hiç açmadı (teşhis:
eval_gate sözleşmesi MODÜL-ATTR ister, env okumaz; script düzeltildi) — ama
bu sayede koşu, bugünkü motor değişikliklerinin (çoklu-kopya pin `c7a6af5`
+ NFV-pin `62624bf`) **4-set SIFIR-DOKUNUŞ kanıtına dönüştü: VERDICT NOOP,
exit=0, 68 dk** (p1 202,18 · p2 529,04 · p3/d4 birebir). A11 karnesindeki
"sıfır-dokunuş=BEKLİYOR" kalemi v8 için KANITLI'ya çekildi. Sıra: k62-V8
ölçümü → düzeltilmiş kapı-2 (gerçek K-56g sınavı).

## 2026-08-04 GECE-4 — k62 v8-MVP: NO-GO (teşhisli) + kapı-1 NOOP kanıtı

**v8-MVP (NFV-içi kule-pin):** mekanizma çalıştı (pinler NFV'de, rota
zorlamasız) ama naif 158,5 @ clearance 1,16 İHLAL / iterasyon 213 @ 0,33.
İKİ TEŞHİS: (1) NFV pitch=2,0'da pin mührü RAW footprint — kuantizasyon
2mm boşluk garantisini kırıyor → mühre +1 voxel dilation gerek;
(2) yalnız faz-A'nın 4 tipi pinlendi → başka tipler kuleleşti (47 yeni
suçlu) → pin seti iteratif büyümeli. İkisi de SABAH işi (v8b). Motor pin
desteğinin kendisi SAĞLAM (16 test + kapı-1 NOOP).
**Kapı-1 NOOP = sıfır-dokunuş kanıtı** (68dk, exit=0, 4 set birebir):
çoklu-pin `c7a6af5` + NFV-pin `62624bf` üretim yollarını değiştirmiyor.
Sıra: kapı-2 (gerçek K-56g sınavı, modül-attr düzeltmeli).

## 2026-08-05 GECE — K-56g KAPI-2 TAMAM: SÖZLEŞME-ETKİSİ TABLOSU (İNSAN-KARARI)

Düzeltilmiş kapı (soft sözleşme modül-attr ilanlı; pin tetiklendi
"baseplate_v2 giriş 1,504mm"), 96 dk, exit=1 VERDICT=İNSAN-KARARI:

| Set | Baseline | Kapı-2 | Fark |
|---|---|---|---|
| plan1 | 202,18 | **140,21** (kilit 0) | **−62,0** (pin+soft) |
| plan2 | 529,04 | 521,18 (söküm-planlı) | −7,86 |
| plan3 | 601,92 | 607,50 (söküm-planlı) | **+5,58 (bedel)** |
| deneme4 | 220,69ş | **215,87** (söküm-planlı) | **−4,82 (yeni en-iyi!)** |

Net −69,1; 3 set iyileşme / 1 set bedel (A5 dağılım). d4 215,87 eski
ŞAMPİYONU da geçti. Kanıt: results/k56g_kapi_kosu2.log + eval_gate_last.
SABAH EREN KARARI (sözleşme sınıfı, A11-m4): kabul → plate.local.json
no_go_soft + eval_gate NOGO_STD 33 + 4-set baseline yenileme (+ önce
/plaka-ayar merge bug fix'i); red → p3 gerekçesiyle mevcut kalır.

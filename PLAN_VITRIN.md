# PLAN_VITRIN.md — Demo Vitrin Katmanı: "Algoritma App'i"nden "Otonom Agent Sistemi"ne

> Tarih: 2026-06-14. Kaynaklar: `APP_YOL_HARITASI.md` (§6.1 LLM ilkesi, §6.4 agent
> zinciri, §6.6 rol haritası, **§7 time-to-quote satış çerçevesi**), `PLAN_LLM.md`
> (L0-L5 rol tasarımı + gateway), `PLAN_SERVIS.md` (S0-S2 çalışma-zamanı / insan-onay
> kapısı deseni), `PLAN_DEMO1.md` (Faz 7/8 fiyat+çizelge motorları), mevcut kod
> `src/webapp/app.py` (Flask + LLM zarif düşüş), `scripts/demo_pipeline.py` (uçtan
> uca zincir), `configs/llm.local.json` (Ollama, qwen2.5:3b / llama3.2:3b).
>
> **Kapsam ÇİZGİSİ — bu plan SUNUM/VİTRİN katmanıdır, mantık değil:**
> - LLM rol mantığı (parser/asistan/rapor/açıklayıcı şema + few-shot + topraklama)
>   → `PLAN_LLM.md` L0-L5. Burada TEKRARLANMAZ; bu plan rolleri **görünür kılar**.
> - Çalışma-zamanı (kuyruk, kalıcılık, gerçek IMAP, idempotency, dead-letter)
>   → `PLAN_SERVIS.md` S0-S2. Burası **demo anlatısıdır** — gerçek 7/24 servis
>   DEĞİL; V3 "sahte mail" simülasyonu insan-onay kapısını GÖSTERİR, PLAN_SERVIS
>   onu canlı PRODUCTION'a taşır.
> - Motor (nesting/fiyat/çizelge) → `PLAN_DEMO1.md` + `MOTOR/`. Burası onların
>   çıktısını **agent vitrinine** dizer.
>
> **Tek cümlelik fark:** PLAN_DEMO1 = "motor doğru mu"; PLAN_LLM = "LLM rolleri
> doğru mu"; PLAN_SERVIS = "7/24 canlı mı"; **PLAN_VITRIN = "hocanın vizyonu
> SATIŞ MASASINDA görünüyor mu".** Çelişki/sınır bayrakları §8'de.

---

## Hedef (Goal)

Mevcut "yükle → algoritma koşar → sonuç tablosu" demo'sunu, hocanın vizyonunu —
**teklif sürecini günlerden dakikalara indiren otonom agent sistemi (time-to-quote,
§7)** — satış masasında GÖSTEREN bir vitrine dönüştürmek: webapp'i "agent kontrol
merkezi"ne çevir (5 isimli agent canlı aşama animasyonu + 3D yerleşim önizleme),
LLM rollerini (parser/rapor/asistan/açıklayıcı) Ollama canlıyken GÖRÜNÜR kıl, ve
"sahte mail gelir → agent'lar uçtan uca koşar → insan onaylar → yanıt hazır"
otonom anlatısını canlı oynat — kod yazmadan önceki bu plan, hangi vitrin
parçasının hangi sırayla kurulacağını ve hangi mevcut planın mantığına bağlanacağını
tanımlar.

## Neden (Why)

- **§7 ana satış argümanı vitrinde GÖRÜNMÜYOR.** Bugün demo "optimizasyon
  yazılımı" gibi duruyor (yükle→koş→tablo); satacağımız şey "teklif süresini
  günlerden dakikalara indiren sistem". Time-to-quote (§7 resmî ürün metriği)
  ekranda bir sayı olarak yanıp sönmüyor — en güçlü kozumuz görünmez.
- **Hocanın "bu yazılımı yapan kimse yok" (uçtan-uca akış) iddiası KANITLANMALI.**
  Magics tek modül; bizim ayrışmamız agent zinciri (sipariş→çizelge→nesting→fiyat
  →teklif). Bu zincir bugün `scripts/demo_pipeline.py` içinde GERÇEK koşuyor ama
  kullanıcı onu monolitik "pipeline" olarak görüyor — agent'lara ayrışmış,
  isimli, canlı durumlu görünmüyor. Vaporware değil (PLAN_DEMO1 + §6.4 zinciri
  gerçek) ama vaporware GİBİ sunuluyor.
- **LLM rolleri kurulu ama yarısı gizli.** `report` + `assistant` rolleri kodda
  canlı (`src/llm/roles/`), Ollama açıkken çalışıyor; ama `parser` (mail→sipariş)
  ve `açıklayıcı` (neden bu algoritma/fiyat) henüz YOK — oysa otonom anlatının
  açılış halkası (mail oku) ve "neden buna güveneyim" cevabı bunlar. Demo'nun
  "agent okur" vaadini parser olmadan veremeyiz.
- **Görsel güven açığı.** Savunma sanayi alıcısı + 20k$ Magics çapası karşısında
  "ders projesi" görünümlü bir Flask sayfası satış riskini artırır; profesyonel
  agent-kontrol-merkezi görünümü + 3D önizleme algılanan olgunluğu yükseltir
  (§7 "ilk müşteride çapanın üstüne çıkma" konumunu destekler).

---

## 0. Vitrin değişmezleri (her fazda geçerli — anayasa)

1. **Animasyon GERÇEĞİ yansıtır, sahnelemez.** Her "agent aşaması" görseli
   `run_pipeline()` / LLM rolünün GERÇEK çıktısına bağlıdır; sahte ilerleme
   çubuğu / önceden-kaydedilmiş sonuç YASAK. Bir aşama "yeşil" oluyorsa o adım
   gerçekten koştu (vaporware yasağı — §6.4 "gerçek zincir" ilkesi vitrine taşınır).
2. **MATEMATİK LLM'den çıkmaz (§6.1 korunur).** Vitrin sayıları (yükseklik,
   doluluk, fiyat, time-to-quote) yalnız deterministik motordan; LLM yalnız
   dil/açıklama katmanı. 3D önizleme yerleşimi `SolveResult` placement'larından
   render edilir — LLM hiçbir koordinat üretmez.
3. **Zarif düşüş korunur ve GENİŞLER.** Bugünkü "Ollama kapalıysa LLM bölümünü
   gizle" deseni (`_load_llm_components` → None) bozulmaz. V1 (UI/animasyon) ve
   3D önizleme LLM'siz de TAM çalışır; V2/V3 LLM gerektirir → Ollama yoksa o
   bölümler "LLM kapalı — agent dil katmanı devre dışı" rozetiyle zarifçe gizlenir
   (demo çökmez; algoritma+animasyon yine akar).
4. **İnsan-onay kapısı KUTSAL (§6.4 madde 4 / PLAN_SERVIS §0.6).** V3 otonom
   anlatısında mail ASLA otomatik gönderilmez; "yanıt hazır → İNSAN ONAYLAR"
   kapısı görselin doruğudur, atlanmaz. Bu kapı satış mesajının parçası
   ("sistem önerir, siz onaylarsınız — kontrol sizde").
5. **Mantık tekrarı YASAK.** Vitrin katmanı rol şeması / motor parametresi /
   kuyruk mantığı TANIMLAMAZ; var olanı çağırır + gösterir. Yeni rol gerekirse
   (parser, açıklayıcı) tasarımı PLAN_LLM'e yazılır, burada yalnız "görünür
   kılma" işi kalır (§8 bayrakları).
6. **Demo deterministik kalır.** `run_pipeline()` sabit seed/ref_date ile aynı
   sonucu üretir; vitrin bu determinizmi bozmaz (animasyon zamanlaması rastgele
   olabilir ama VERİ aynı). LLM rolleri doğası gereği non-deterministik (PLAN_LLM
   değişmez #7) — vitrin bunu dürüstçe gösterir (LLM çıktısı "taslak/öneri"
   etiketli; motor çıktısı "kesin" etiketli).
7. **Tek webapp (B1 kararı).** Yeni uygulama açılmaz; `src/webapp/` GENİŞLETİLİR.
   Mevcut rotalar (`/`, `/run`, `/sonuc`, `/ozet`, `/sor`, `/siparisler*`)
   korunur; vitrin yeni rota + zenginleştirilmiş şablonlarla eklenir.

---

## 1. Mevcut durum envanteri (vitrinin başlangıç noktası)

| Bileşen | Durum | Vitrin için anlamı |
|---|---|---|
| `scripts/demo_pipeline.py` `run_pipeline()` | GERÇEK: sipariş→rank→batch→feasibility→tuner-nesting→pricing→rapor; deterministik | Agent zincirinin 5 aşaması ZATEN burada; ayrıştırılıp isimlendirilecek |
| `src/webapp/app.py` `/run` (senkron) | Pipeline'ı senkron koşar → `/sonuc` redirect | V1'de "agent aşamaları" canlandırması bu koşunun ADIMLARINI yayımlamalı |
| LLM `report` rolü | KURULU, canlı (`roles/report.py`) — yönetici özeti / teklif taslağı | V2 "rapor/teklif" agent'ı = bu rol; görünür kılınacak |
| LLM `assistant` rolü | KURULU, canlı (`roles/assistant.py`) — topraklı chat | V2 "asistan" agent'ı = bu rol; chat kutusu var, vitrinleştirilecek |
| LLM `parser` rolü | **YOK** (prompt şablonu `prompts/parser/` var ama `roles/parser.py` YOK) | V2/V3 "Oku" agent'ı için ZORUNLU — PLAN_LLM L2'den implementasyon gerekir (§8 bayrak) |
| LLM `açıklayıcı` rolü | **YOK** (ne prompt ne kod) | V2 "neden bu algoritma/fiyat" için yeni rol — PLAN_LLM'e eklenmeli (§8 bayrak) |
| Ollama gateway | HAZIR: `configs/llm.local.json` → localhost:11434, openai_compat; FakeProvider test yolu | V2/V3 canlı LLM'i bu konfigle koşar; provider takas tek satır |
| 3D yerleşim önizleme | **YOK** (sonuç sadece tablo/metrik) | V1 three.js önizleme — roadmap'te vardı, ilk kez vitrine girer |
| Agent aşama animasyonu / kontrol merkezi UI | **YOK** | V1 ana işi |
| Time-to-quote göstergesi | **YOK** (`elapsed_sec` var ama "X dakikada üretildi" satış mesajı yok) | §7 metriği — V1'de baş köşeye |
| İnsan-onay kapısı ekranı | **YOK** (demo'da onay kavramı yok) | V3 doruğu; PLAN_SERVIS S1.3 onay ekranının demo-anlatı versiyonu |

**Çıkarım:** zincir + 2 LLM rolü + gateway + zarif düşüş HAZIR. Vitrin 3 şeyi
ekler — (a) bu hazır parçaları AGENT olarak GÖRÜNÜR kılan UI, (b) eksik 2 rolü
(parser, açıklayıcı) görünür kılmak için PLAN_LLM'den implementasyon talebi,
(c) otonom anlatı (sahte mail → onay kapısı).

---

## Faz V1 — Agent Kontrol Merkezi UI (LLM'siz tam çalışır)

> Amaç: webapp'i "yükle→koş→tablo"dan, **5 isimli agent'ın canlı durumla çalıştığı
> kontrol merkezine** çevir. Bu faz LLM GEREKTİRMEZ — Ollama kapalıyken de tam
> çalışır (değişmez #3). Bağımlılık: yalnız mevcut `run_pipeline()`.

**5 agent aşaması (sabit isim + sıra — §6.4 zincirinin satış-dili karşılığı):**

| # | Agent (vitrin adı) | Arkasındaki gerçek iş | Durum kaynağı |
|---|---|---|---|
| 1 | **Oku** (Sipariş Agent'ı) | havuz/sipariş okuma + doğrulama (`load_orders`/`Order.validate`) | order sayısı, hatalı satır |
| 2 | **Önceliklendir** (Çizelge Agent'ı) | `rank_orders` + `build_batches` + `check_feasibility` | sıra, parti sayısı, termin uyarısı |
| 3 | **Yerleştir** (Nesting Agent'ı) | `tuner.tune` portföy + Instance-Tuner + selection | yükseklik, doluluk, kazanan konfig |
| 4 | **Fiyatla** (Fiyat Agent'ı) | `PricingEngine.calculate` deterministik döküm | toplam fiyat, satır döküm |
| 5 | **Yanıt** (Rapor Agent'ı) | rapor/teklif (V1'de statik özet; V2'de LLM rapor rolü devralır) | taslak hazır rozeti |

| # | İş | Çıktı | Kabul kriteri | Efor |
|---|---|---|---|---|
| V1.1 | **Aşama yayını:** `run_pipeline()` her ana adım sonrası ilerleme olayı yayımlayabilsin (callback/generator — minimal diff, motor saflığı korunur: pipeline UI import ETMEZ, opsiyonel `on_stage` callback alır) | `scripts/demo_pipeline.py` (opsiyonel callback parametresi), `src/webapp/` koşu sarmalı | Callback'siz çağrı bire bir eski davranış; callback'li çağrıda 5 aşama olayı sırayla gelir; deterministik | S |
| V1.2 | **Canlı durum aktarımı (SSE/poll):** koşu arka planda; tarayıcı her agent'ın `bekliyor→koşuyor→bitti` durumunu + mini-log satırını canlı görür | yeni `/calistir-canli` rotası + SSE/poll uç; `src/webapp/app.py` genişletme | İlk istek <200ms döner; aşamalar tek tek "yeşillenir"; LLM kapalıyken de çalışır | M |
| V1.3 | **Agent kontrol merkezi şablonu:** 5 agent kartı (isim + ikon + canlı durum + son log) yatay zincir; tamamlanınca alttaki sonuç paneline akış | yeni `templates/kontrol.html` (veya `index.html` zenginleştirme), `static/style.css` | 5 kart görünür; durum renkleri canlı; mobil-uyumsuzluk demo-blocker değil (masaüstü sunum) | M |
| V1.4 | **3D yerleşim önizleme (three.js):** kazanan `SolveResult` placement'ları (konteyner + voxel/kutu kutuları) tarayıcıda döndürülebilir 3B sahne; her parti için | `templates/sonuc.html` 3D panel + `static/nesting3d_view.js`; pipeline sonucu placement'ları JSON-serileştirir | Numune/rich senaryoda konteyner + yerleşmiş kutular doğru oranda görünür; LLM'den BAĞIMSIZ; sayılar motordan (değişmez #2) | M |
| V1.5 | **Time-to-quote vitrini (§7 metriği):** sonuç başında büyük göstergede "Bu teklif **X saniyede** üretildi — mevcut sürecinizde kaç gün?" + alt-metin (parça sayısı, parti, fiyat) | `templates/sonuc.html` / `kontrol.html` üst banner | `elapsed_sec`'ten türetilir; satış cümlesi ekranda; her koşuda canlı güncellenir | S |
| V1.6 | **frontend-design geçişi:** profesyonel görünüm — tutarlı renk paleti, tipografi, agent ikonografisi, "kontrol merkezi" hissi (savunma-sanayi olgunluk algısı, §7) | `static/style.css` revizyon + şablon iskeleti | Hocaya gösterilebilir: "ders projesi" değil "ürün" hissi; mevcut işlev bozulmaz | M |

**Faz V1 toplam efor: M (3-5 gün).** LLM'siz tam çalışır. Bağımlılık: yok (mevcut
`run_pipeline()` yeter). **Tek başına demo-1 değeri yüksek** — agent anlatısı +
3D + time-to-quote zaten satış sıçraması.

---

## Faz V2 — LLM Rolleri GÖRÜNÜR (Ollama canlı)

> Amaç: 4 LLM rolünü vitrine bağla — agent'ların "dil katmanı" canlı görünsün.
> Ollama açıkken çalışır; kapalıyken V1 + zarif düşüş (değişmez #3). Her rol
> gateway'e prompt+şema olarak takılır (`PLAN_LLM` mekanizması — burada YENİDEN
> TASARLANMAZ, GÖRÜNÜR KILINIR). **Mantık bağımlılığı §8'de bayraklı.**

**Rol → agent → vitrin eşlemesi:**

| Rol | Agent aşaması | Vitrin yüzeyi | Kod durumu |
|---|---|---|---|
| **parser** (mail→sipariş) | Oku | yapay mail kutusu → "okundu" yapılandırılmış sipariş kartı + güven/eksik-alan rozetleri | **YOK** — PLAN_LLM L2 implementasyonu gerekir (§8.A) |
| **rapor/teklif** (rapor rolü) | Yanıt | müşteri yanıt maili TASLAĞI (kaynak rozetli, "taslak — gönderilmedi" etiketi) | KURULU (`roles/report.py`) — vitrinleştirilecek |
| **asistan** (chat, topraklı) | (yan panel) | "sisteme sor" kutusu: kaynaklı cevap + topraklama/sayı bayrağı görünür | KURULU (`roles/assistant.py`) — vitrinleştirilecek |
| **açıklayıcı** (neden bu algo/fiyat) | Yerleştir + Fiyatla | "Neden bu algoritma?" / "Fiyat nereden çıktı?" sade-dil açıklama balonu | **YOK** — yeni rol, PLAN_LLM'e eklenmeli (§8.B) |

| # | İş | Çıktı | Kabul kriteri | Efor |
|---|---|---|---|---|
| V2.1 | **Rapor agent'ı vitrini:** mevcut `/ozet` çıktısını "Yanıt agent'ı taslağı" olarak göster — kaynak rozetleri (`kullanilan_kaynaklar`), "taslak/gönderilmedi" etiketi, topraklama-uyarısı görünür | `templates/sonuc.html` rapor paneli; mevcut `/ozet` rotası (var) zenginleştirilir | Ollama açık: taslak görünür + kaynak rozetli; topraklama bloğunda kırmızı uyarı; Ollama kapalı: panel zarif gizli | S |
| V2.2 | **Asistan agent'ı vitrini:** mevcut `/sor` chat'ini "Asistan agent'ı" panelinde göster — kaynaklı cevap, `ret` durumunda "bilgi yok" rozeti, `sayi_bayragi` görünür uyarı | `templates/sonuc.html` chat paneli; mevcut `/sor` rotası (var) | Bağlam-içi soru → kaynaklı cevap; bağlam-dışı → ret rozeti; sayı bayrağı görünür; Ollama kapalı: gizli | S |
| V2.3 | **Açıklayıcı agent'ı vitrini:** "Neden bu algoritma?" + "Fiyat nereden çıktı?" düğmeleri → açıklayıcı rol sade-dil balonu (girdi: tuner kazanan + selection.explain + fiyat breakdown = GROUNDED; LLM yalnız düzyazılaştırır, sayı üretmez §6.1) | yeni `/acikla` rotası + panel; **açıklayıcı rol gövdesi PLAN_LLM'den (§8.B)** | Açıklama yalnız grounded girdiden; sayı-topraklama bayrağı aktif; Ollama kapalı: düğme gizli (V1 statik açıklama fallback) | S-M |
| V2.4 | **Parser agent'ı vitrini (Oku):** yapay mail metni kutusu → parser rolü → yapılandırılmış sipariş kartı (müşteri/termin/parçalar + güven + eksik-alan + injection-şüphesi rozetleri) → "havuza ekle" düğmesi (mevcut `add_order`'a bağlanır) | yeni `/oku` rotası + panel; **parser rol gövdesi PLAN_LLM L2'den (§8.A)** | Yapay mail → doğru sipariş kartı; eksik alan görünür; injection kanaryası rozetlenir; Ollama kapalı: panel gizli + manuel form (var) fallback | M |
| V2.5 | **"LLM kapalı" durum rozeti:** her LLM panelinde Ollama durumu görünür ("dil katmanı canlı: qwen2.5:3b" / "LLM kapalı — agent çekirdeği yine çalışır") | tüm LLM şablon panelleri | Provider canlılık kontrolü; durum dürüst gösterilir (değişmez #6 — LLM "öneri", motor "kesin" ayrımı) | S |

**Faz V2 toplam efor: M (3-5 gün, parser/açıklayıcı mantığı PLAN_LLM'de
yapıldıysa).** Bağımlılık: V1 + Ollama canlı + **PLAN_LLM L2 (parser) + yeni
açıklayıcı rol (§8)**. V2.1/V2.2 hemen yapılabilir (roller kurulu); V2.3/V2.4
mantık bağımlılığı bekler.

---

## Faz V3 — Otonom Anlatı: "Çalışırken İzle"

> Amaç: hocanın hikâyesini CANLI oynat — **sahte mail gelir → agent'lar uçtan
> uca koşar → insan-onay kapısı → yanıt hazır.** Bu demo SİMÜLASYONUDUR
> (gerçek IMAP/kuyruk/7-24 servis PLAN_SERVIS S1 işidir — §8.D bayrak); demo
> "tek tıkla otonom akışı izle" gösterir, time-to-quote'u uçtan uca ölçer.

**Otonom akış (tek tıkla canlı oynatım):**
```
[Yapay mail düşer]  → Oku (parser)      → yapılandırılmış sipariş
                    → Önceliklendir     → sıra + parti + termin uyarısı
                    → Yerleştir         → 3D yerleşim + doluluk
                    → Fiyatla           → fiyat dökümü
                    → Yanıt (rapor)     → teklif maili TASLAĞI
                    → [İNSAN ONAY KAPISI: Onayla / Düzelt / Reddet]  ← DORUK
                    → "Yanıt hazır" (gönderilmedi — onay bekliyor)
        ⏱ time-to-quote: tüm zincir X saniyede tamamlandı (§7)
```

| # | İş | Çıktı | Kabul kriteri | Efor |
|---|---|---|---|---|
| V3.1 | **Sahte gelen-kutusu:** 2-3 hazır yapay sipariş maili (Türkçe, gerçekçi; biri "dağınık/eksik alanlı", biri temiz) → "yeni mail geldi" tetikleyici | `templates/otonom.html` gelen-kutusu; fixture mailler `data/demo_mails/` | Mail seç → akış başlar; fixture deterministik; mailler §5.2 (PLAN_LLM) anonim/sentetik | S |
| V3.2 | **Uçtan uca otonom oynatım:** mail seçimi → parser → zincir (V1 aşama animasyonu yeniden kullanılır) → rapor taslağı; her aşama canlı yeşillenir, mini-log akar | `/otonom` rotası; V1.2 SSE altyapısı + V2 rolleri yeniden kullanılır | Tek tıkla mail→taslak uçtan uca; her aşama gerçek çıktıyla (değişmez #1); Ollama kapalı: parser/rapor aşamaları "LLM gerekli" rozetiyle atlanır, motor aşamaları yine koşar | M |
| V3.3 | **İnsan-onay kapısı ekranı (DORUK):** taslak + 3D yerleşim özeti + fiyat dökümü yan yana → "Onayla / Düzelt / Reddet"; onay→"yanıt hazır (gönderilmedi)" durumu; **otomatik gönderim YOK** (değişmez #4) | `templates/onay.html`; PLAN_SERVIS S1.3 onay ekranının demo-anlatı versiyonu | Onaysız "gönderildi" durumu ASLA; reddet→akış durur; düzelt→taslak editlenebilir; satış mesajı "kontrol sizde" görünür | M |
| V3.4 | **Uçtan uca time-to-quote ölçümü (§7 doruğu):** mail-düşüşünden taslak-hazıra toplam süre büyük göstergede; "mevcut sürecinizde günler — burada X saniye" kıyas cümlesi | `otonom.html` üst banner | Süre canlı ölçülür (LLM dahil); §7 satış cümlesi ekranda; deterministik motor + non-det LLM süresi dürüst gösterilir | S |
| V3.5 | **Anlatı modu / sunum kılavuzu:** demo sırasında hocanın anlatacağı 5-6 cümlelik akış (hangi ekranda ne denir) — vitrin değil ama vitrinle teslim | `hocaya_sunum/` altına vitrin sunum notu (markdown — Write ile) | Sunum akışı yazılı; §7 mesajı her ekrana bağlı | S |

**Faz V3 toplam efor: M (3-4 gün).** Bağımlılık: V1 (aşama altyapısı) + V2
(parser + rapor rolleri) + **insan-onay kapısı deseni PLAN_SERVIS S1.3'ten**.
**Otonom anlatının ÖN ŞARTI parser (§8.A)** — parsersiz "mail oku" aşaması
simüle edilir (fixture → hazır sipariş), gerçek LLM-parse gösterilemez (bayrak).

---

## 2. Satış çerçevesi bağlantısı (§7 → demo mesajı)

Her faz §7 time-to-quote argümanına bağlanır — vitrin "optimizasyon yazılımı"
değil "teklif süresini günlerden dakikalara indiren sistem" anlatır:

| §7 satış unsuru | Vitrinde nerede görünür |
|---|---|
| **time-to-quote (resmî ürün metriği)** | V1.5 üst banner (her koşu) + V3.4 uçtan uca (mail→taslak) büyük gösterge |
| **"bu yazılımı yapan kimse yok" (uçtan-uca akış)** | V1 5-agent zinciri + V3 otonom oynatım — Magics'in yapamadığı zincir görünür |
| **manuel hata sınıfını yapısal kapatma** | V2 kaynak rozetleri + topraklama bayrakları + V3 onay kapısı (deterministik döküm + iz) |
| **"sistem önerir, siz onaylarsınız" (kontrol alıcıda)** | V3.3 insan-onay kapısı (doruk) — savunma alıcısına güven mesajı |
| **çapanın üstüne çıkma / olgunluk algısı** | V1.6 profesyonel görünüm + 3D önizleme — "ders projesi değil ürün" |
| **on-prem / veri dışarı çıkmaz (A13)** | V2.5 "dil katmanı lokal: qwen2.5:3b" rozeti — bulut yok, Ollama canlı |

---

## 3. Bağımlılık sırası (özet)

```
V1 (agent kontrol merkezi UI + 3D + time-to-quote)   [LLM'siz tam çalışır]
 │   bağımlılık: mevcut run_pipeline() — yok
 ├─ V2 (LLM rolleri görünür)                          [Ollama + PLAN_LLM]
 │    ├─ V2.1 rapor vitrini    [rol KURULU — hemen]
 │    ├─ V2.2 asistan vitrini  [rol KURULU — hemen]
 │    ├─ V2.3 açıklayıcı       [BEKLER: yeni rol — PLAN_LLM §8.B]
 │    └─ V2.4 parser vitrini   [BEKLER: PLAN_LLM L2 — §8.A]
 └─ V3 (otonom anlatı + onay kapısı)                  [V1+V2 + PLAN_SERVIS S1.3 deseni]
      └─ V3 doruğu (onay kapısı) parsersiz simüle edilebilir; gerçek mail-parse V2.4 bekler
```

**Minimum anlamlı demo dilimi (hocaya ilk gösterim):** **V1 tamı + V2.1 + V2.2**
— agent kontrol merkezi + 3D + time-to-quote + (Ollama açıksa) rapor taslağı +
topraklı asistan. Parser/açıklayıcı/otonom-anlatı ikinci dilim. Toplam V1+V2+V3
≈ **L alt bandı** (~9-14 iş günü; V2.3/V2.4/V3 parser+açıklayıcı mantığı
PLAN_LLM'de hazırsa, yoksa o mantık eforu PLAN_LLM'e ait).

---

## 4. Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Animasyon "sahte" görünür / vaporware algısı (en büyük satış riski) | Değişmez #1: her aşama gerçek çıktıya bağlı; "bu sonuç gerçekten koştu" — istenirse ham rapor (`results/demo_pipeline_report.md`) yan yana gösterilir |
| LLM (3B model) yavaş/bozuk JSON → otonom akış demoda takılır/çirkin | Zarif düşüş (değişmez #3): LLM aşaması fallback'e düşer, motor aşamaları akar; demo asla çökmez; ayrıca demo öncesi Ollama ısıtma + fixture mail provası |
| Ollama demo anında kapalı/erişilemez | V1 + 3D + time-to-quote LLM'siz tam çalışır (değişmez #3); LLM bölümleri "kapalı" rozetiyle zarifçe gizlenir — demo yine satış yapar |
| 3D önizleme (three.js) tarayıcı/performans sorunu | Placement sayısı demo senaryolarında düşük (~20 parça); WebGL fallback = 2D üstten görünüm; 3D opsiyonel zenginlik, blocker değil |
| Parser rolü YOK → "mail oku" agent'ı gösterilemez | V3 parsersiz fixture-simülasyonla başlar (mail→hazır sipariş); gerçek parse V2.4/§8.A gelince açılır — bayrak, sessiz atlama yok |
| Açıklayıcı rolü YOK → "neden bu algoritma" balonu boş | V1 statik açıklama (selection.explain + tuner kazanan zaten metin üretiyor) fallback; LLM açıklayıcı gelince düzyazılaşır (§8.B) |
| LLM sayı uydurur (müşteriye yanlış fiyat/yükseklik) | §6.1 + değişmez #2: LLM sayı üretmez; rapor/açıklayıcı grounded girdiden; sayı-topraklama bayrağı (PLAN_LLM L0.8) vitrine taşınır (V2.1/V2.3) |
| Onay kapısı demo'da atlanır → "otomatik gönderim" yanlış mesajı | Değişmez #4: V3.3 kapısı zorunlu; "gönderildi" durumu yalnız onay sonrası; satış mesajı kontrol alıcıda |
| Vitrin mantığı motor/rol koduna sızar (motor saflığı bozulur) | Değişmez #5 + V1.1: pipeline opsiyonel callback alır, UI import ETMEZ; rol mantığı PLAN_LLM'de kalır |
| PLAN_LLM/PLAN_SERVIS ile çelişki (sessiz ezme) | §8 bayrakları: parser+açıklayıcı mantığı PLAN_LLM'e yazılır; onay kapısı deseni PLAN_SERVIS S1.3'ten türetilir; bu plan yalnız vitrin |
| Demo senaryosu satış toplantısına uymaz (alıcıya özgü değil) | Senaryo fixture'ları (Ford/ASELSAN/Baykar) hâlihazırda alıcı-bağlantılı; gerçek alıcı parçalarıyla değiştirme = sadece `data/` fixture (kod değil) |

---

## 5. Mevcut desenle / diğer planlarla çelişki + karar bayrakları

- **§5.A — `/run` senkron KORUNUR, V1 yeni rota EKLER (çelişki yok):** PLAN_SERVIS
  §11.B `/run`'ı Faz 2'de enqueue'a çeviriyor; bu VİTRİN planı `/run`'ı BOZMAZ —
  V1.2 yeni `/calistir-canli` (SSE) ROTASI ekler. Demo senkron `/run` yine çalışır
  (tek-seferlik mod); canlı-animasyon ayrı yol. PLAN_SERVIS'in asenkron servisi
  bu vitrinin üstüne gelir, çakışmaz.

- **§5.B — V3 otonom anlatı ≠ PLAN_SERVIS canlı servis (sınır bayrağı):** V3
  "sahte mail → akış" DEMO SİMÜLASYONUDUR (tek tıkla oynatım, fixture mail).
  Gerçek IMAP poll + kuyruk + kalıcılık + idempotency + 7/24 = PLAN_SERVIS S1.
  V3 onun VİTRİNİDİR, implementasyonu DEĞİL. İkisi karıştırılırsa "demo = ürün"
  yanılgısı doğar — bu satır o sınırdır.

- **§5.C — parser + açıklayıcı rolleri PLAN_LLM'e AİT (mantık bayrağı):** bu plan
  bu iki rolün ŞEMASINI/few-shot'ını/topraklamasını TANIMLAMAZ. parser = PLAN_LLM
  L2 (zaten tasarlı, kod YOK); açıklayıcı = PLAN_LLM'e EKLENMESİ gereken 6. rol
  (mevcut 5 rolde yok — §8.B). Vitrin yalnız "görünür kılma". Sessiz override
  değil; §8'de açık talep.

- **§5.D — onay kapısı deseni PLAN_SERVIS S1.3'ten türetilir:** V3.3 ekranı yeni
  tasarım değil; PLAN_SERVIS S1.3 (taslak+özet+fiyat yan yana, onayla/reddet/
  düzelt) onay ekranının demo-anlatı izdüşümü. Durum makinesi (AWAITING_APPROVAL)
  PLAN_SERVIS'te; vitrinde yalnız ekran + "onaysız gönderim yok" mesajı.

- **§5.E — kapsam çakışması yok (motor/rol/runtime tekrarlanmadı):** nesting/
  fiyat/çizelge içeriği PLAN_DEMO1'de; LLM rol mantığı PLAN_LLM'de; runtime
  PLAN_SERVIS'te. Bu plan yalnız SUNUM yüzeyi. Tekrar = §0 değişmez #5 ihlali.

---

## 6. Açık sorular (netleşmesi gereken — karar bekler)

1. **Açıklayıcı 6. rol mü, rapor rolünün varyantı mı?** "Neden bu algoritma/fiyat"
   ayrı rol (PLAN_LLM yeni faz) mı, yoksa rapor rolüne `rapor_tipi: aciklama`
   varyantı mı? Varyant daha ucuz (gateway hazır); karar PLAN_LLM sahibinde (§8.B).
2. **3D önizleme kapsamı:** tam voxel render mi (ağır, gerçekçi) yoksa kutu-bounding
   render mi (hafif, hızlı)? Demo senaryosu kutu-tabanlı → bounding-box yeter;
   STL/voxel gerçekçiliği gerekir mi (hoca beklentisi)?
3. **SSE mi poll mı (V1.2)?** Flask dev-server'da SSE kırılgan olabilir; basit poll
   (her 500ms durum sor) demo için yeterli ve sağlam — hangisi? (Demo tek-kullanıcı,
   poll muhtemelen yeter; PLAN_SERVIS'te gunicorn'da SSE ayrı karar.)
4. **Otonom anlatıda LLM mi fixture mi (demo güvenliği)?** Demo anında 3B model
   yavaş/bozuksa risk; "canlı LLM" mi yoksa "önceden-üretilmiş LLM çıktısı +
   canlı motor" hibrit mi? Değişmez #1 canlı ister; ama demo-blocker riskine
   karşı "canlı dene, fallback fixture" politikası netleşmeli.
5. **Hangi alıcıya özel senaryo?** Demo fixture'ları genel (Ford/ASELSAN/Baykar);
   gerçek satış toplantısında alıcının kendi parçaları gösterilmeli mi (A11 geçmiş
   nesting verisi gelince)?

---

## 7. BLOKLU — dış girdiye / diğer plana bağlı

Bu plan V1 tamı + V2.1/V2.2 ile BAŞLAR (mevcut kod yeter). Aşağıdakiler ilgili
parçayı bloke eder, vitrinin tamamını DEĞİL.

| Bekleyen | Bloke ETTİĞİ | Bloke ETMEDİĞİ |
|---|---|---|
| **PLAN_LLM L2 parser implementasyonu (§8.A)** | V2.4 (parser vitrini) + V3 gerçek "mail oku" agent'ı | V1 tamı; V2.1/V2.2; V3 fixture-simülasyon (mail→hazır sipariş) |
| **Açıklayıcı rol kararı + implementasyonu (§8.B — PLAN_LLM)** | V2.3 (açıklayıcı balonu LLM versiyonu) | V1; V2.1/V2.2/V2.4; V2.3 statik-açıklama fallback (selection.explain mevcut) |
| **Ollama canlı + model kalitesi (qwen2.5:3b / llama3.2:3b)** | V2/V3 canlı LLM gösterimi | V1 tamı (LLM'siz); zarif düşüş her yerde |
| **A9 — gerçek mail formatları** | V3 sahte maillerin GERÇEKÇİLİĞİ (gerçek tona uyum) + parser kalite güveni | V3 sentetik fixture maillerle başlar (PLAN_LLM §5.2 deseni) |
| **PLAN_SERVIS S1.3 onay ekranı deseni** | V3.3 ekranının mantık tutarlılığı (durum makinesi referansı) | V3.3 demo-anlatı versiyonu (durum simülasyonu — gerçek jobs tablosu gerekmez) |
| **A11 — alıcıya özel parça verisi** | Alıcı-özel demo senaryosu | Genel Ford/ASELSAN/Baykar fixture'larıyla tam demo |

### §8 — PLAN_LLM'e açık talepler (vitrin tetikledi)

- **§8.A — parser rolü implementasyonu:** PLAN_LLM L2 tasarlı ama `src/llm/roles/
  parser.py` YOK (yalnız `prompts/parser/` şablon var). V2.4 + V3 "Oku" agent'ı
  için gövde gerekir. Talep: L2'yi koda dök (vitrin değil, PLAN_LLM işi).
- **§8.B — açıklayıcı (6.) rol:** mevcut 5 rolde (parser/tuner/hipotez/asistan/
  rapor) "neden bu algoritma/fiyat sade dilde" AYRI rol yok. Karar: ayrı rol mü
  (yeni faz) yoksa rapor rolü varyantı mı (§6 açık soru 1). Talep: PLAN_LLM'de
  netleştir — vitrin yalnız tüketir.

# PLAN_SERVIS.md — Çalışma-Zamanı & Dağıtım Katmanı: Sürekli Çalışan Servis Mimarisi

> Tarih: 2026-06-14. Kaynaklar: `APP_YOL_HARITASI.md` (§6.4 agent zinciri /
> sipariş havuzu, §6.1 on-prem LLM ilkesi, §6.6 rol haritası), `APP_SORULAR.md`
> (A9 mail/ek formatı, A13 on-prem/veri güvenliği, A14 HPC, A15 kapasite,
> B1 lokal-barındırılan web kararı), `PLAN_DEMO1.md` (Faz 7/8 mekanizma-önce
> deseni), `PLAN_LLM.md` (§5 güvenlik, insan-onay/§6.4 ilkesi), mevcut kod
> `src/webapp/` (Flask + `orders_store` atomik JSON havuzu).
>
> **Kapsam ÇİZGİSİ:** bu plan akışın MANTIĞINI tekrarlamaz — parser/asistan
> rolleri `PLAN_LLM.md`'de, çizelgeleme/fiyat/nesting motorları `PLAN_DEMO1.md`
> Faz 6/7/8'de + `MOTOR/`'da tasarlandı. Burası YALNIZCA o mantığı 7/24 canlı
> tutan **çalışma-zamanı sarmalayıcısı**: süreç modeli, kuyruk, zamanlayıcı,
> kalıcılık, dağıtım, canlı-kalma. Çelişki bayrakları §11'de.
>
> **Faz konumu:** bu PLAN_DEMO1 Demo-1'i (Faz 1) GEREKTİRMEZ — webapp tek-seferlik
> "yükle→koş→gör" zaten yapıyor (`src/webapp/app.py` `/run` senkron). Bu plan
> **Faz 2 (tam otomasyon)** işidir. Bugün yalnız "tasarıma-açık tutma" kararları
> (§9) alınır; servis kurulumu sonra.

---

## Hedef (Goal)

Hocanın "mail gelir → parçalar çekilir → çizelgele → nest → fiyatla → yanıtla"
zincirini (§6.4), on-prem / hava-boşluklu çalışabilen, yeniden başlatmada iş
kaybetmeyen, aynı maili iki kez işlemeyen, dakikalar süren nesting'i web
isteğini bloklamadan koşan **sürekli çalışan bir self-hosted servise**
dönüştürmek — ilk müşteride doğru kurulursa SaaS çok-kiracılığına sıfır
yeniden-yazımla geçecek şekilde.

## Neden (Why)

- §6.4 zinciri bugün yalnız **mantık** olarak var (`src/scheduling/`,
  `src/pricing/`, `src/nesting3d/`, `src/llm/`); onları tetikleyen **süreç
  modeli HİÇ planlanmadı**. Mevcut `/run` rotası senkron — dakikalar süren
  nesting bir web worker'ını bloklar, eşzamanlı kullanıcıda çöker.
- A13 (savunma sanayi, veri buluta çıkamaz) → bulut tabanlı zamanlayıcı/kuyruk
  servisleri (trigger.dev, AWS SQS, Cloud Tasks) **mimari olarak yasak**.
  Self-hosted, hava-boşluklu kurulabilir bir yığın zorunlu — bu kısıt teknoloji
  seçimlerinin TAMAMINI şekillendirir.
- "İlk müşteri tek-kurulum" ile "SaaS çok-kiracı" arasındaki fark mimaride
  baştan ayrılmazsa (konfig=veri değil kod olursa) ikinci müşteride yeniden
  yazım doğar (§6.3 per-tenant ilkesi, B1 "SaaS'a sıfır yeniden yazım" kararı).
- Mail otomasyonu doğası gereği **dayanıklılık** ister: süreç düşse mail
  kaybolmamalı, çift işlenmemeli, hatalı iş sonsuz döngüye girmemeli. Bunlar
  "sonra eklenir" denecek şeyler değil; kuyruk/kalıcılık deseni baştan doğru
  seçilmezse sökülüp değişir.

---

## 0. Tasarım değişmezleri (servis anayasası — her fazda geçerli)

1. **Hava-boşluğu kuralı:** hiçbir çalışma-zamanı bileşeni internet erişimi
   VARSAYAMAZ. Tüm broker/DB/zamanlayıcı/LLM self-hosted; bulut SaaS bağımlılığı
   = RED. Konteyner imajları offline kurulabilir (registry mirror / tarball).
2. **Motor saflığı korunur:** nesting/fiyat/çizelge motorları çalışma-zamanını
   BİLMEZ — saf `solve(...)`/fonksiyon çağrısı kalır (PLAN_DEMO1 değişmez).
   İşçi süreç motoru çağırır; motor kuyruk/DB/Flask import ETMEZ. Bu sınır
   Faz 2'yi ucuzlatan #1 karardır (§9).
3. **Müşteri konfigü VERİDİR, kod değil:** fiyat kuralları, öncelik ağırlıkları,
   kapasite, mail hesabı, LLM rol→sağlayıcı eşlemesi → hepsi `tenant_id`
   anahtarlı konfig kayıtları. Kod tenant adı bilmez (PLAN_LLM değişmez #5'in
   servis izdüşümü).
4. **İdempotency zorunlu:** her dış tetik (mail, dosya, manuel) deterministik
   bir `idempotency_key` taşır; aynı anahtar iki kez işlenmez (§3).
5. **İş kalıcı:** kuyruğa giren iş broker DEĞİL **DB'de** kayıtlıdır (durum
   makinesi). Süreç/makine yeniden başlasa iş kaybolmaz, yarım kalan yeniden
   alınır (§3 — at-least-once + idempotent işçi = effectively-once).
6. **İnsan-onay kapısı varsayılan:** §6.4/PLAN_LLM ilkesi — sistem ÖNERİR,
   insan ONAYLAR; mail OTOMATIK GÖNDERİLMEZ. Çalışma-zamanı bu kapıyı bir
   **durum** olarak modeller (`AWAITING_APPROVAL`), zamanlanmış otomatik
   gönderim YOK (güven oturana dek — §6.4 madde 4).
7. **Sır asla kodda/imajda değil:** mail parolası, API anahtarı, DB parolası →
   ortam değişkeni / dosya-tabanlı secret (Docker secrets / systemd
   `EnvironmentFile`, `chmod 600`). Repoda, imajda, audit logunda ASLA (§6).
8. **Gözlemlenebilir:** her iş durumu + her geçiş izlenebilir; operatör mevcut
   webapp'ten "ne nerede, ne bekliyor, ne battı" görebilir (§5).
9. **TURNKEY (anahtar-teslim) dağıtım — ÜRÜN, danışmanlık DEĞİL (2026-06-14 kullanıcı şartı):**
   altyapı **uygulamanın İÇİNDE PAKETLİ** gelir; müşteri parça seçmez/kurmaz.
   - Tüm yığın (Postgres + Redis + işçi + web + zamanlayıcı) **tek `docker compose`
     dosyasında**; müşteri TEK komutla (`docker compose up`) her şeyi ayağa kaldırır.
     DB/broker seçimi BİZİM (Postgres gömülü) — müşteri "hangi veritabanı" KARARI
     VERMEZ (her müşteri farklı seçerse = bespoke kâbus, ölçeklenmez).
   - Müşteriye özel olan tek şey **değerler**: `.env`/config (mail hesabı, veri
     volume yolu, port, fiyat kuralları) veya kurulum sihirbazı — **kod değil,
     değer doldurur** (değişmez #3'ün dağıtım izdüşümü).
   - Teslimat = **kurulum paketi + dokümantasyon + (gerekirse) setup script**;
     müşteri kendi kurar, **biz YALNIZ yardım/destek veririz — her müşteriyi elle
     inşa ETMEYİZ**. Bu, SaaS'a / çok-müşteriye ölçeklenmenin ön şartı.
   - SaaS fazında (S2) bu otomasyon bir adım ileri: per-tenant provizyon (yeni
     müşteri = config kaydı + volume, elle kurulum değil).

---

## 1. Süreç modeli mimarisi — bileşen haritası

Tek host, çok süreç. Her kutu = ayrı süreç/konteyner; ok = veri akışı.

```
                         ┌──────────────────────────────────────────┐
   (operatör tarayıcı)   │  nginx (reverse proxy, TLS sonlandırma)   │
        │  HTTPS         └──────────────────┬───────────────────────┘
        ▼                                    │ 127.0.0.1
   ┌─────────────────────────────┐          ▼
   │  WEB (gunicorn + Flask)      │   src/webapp/app.py (genişletilmiş)
   │  - havuz CRUD (var)          │   - SADECE hızlı I/O: enqueue + durum oku
   │  - /run → enqueue(job)  ◄────┼── (artık SENKRON koşmaz — kuyruğa atar)
   │  - durum paneli (yeni)       │   - onay kapısı uçları (approve/reject)
   │  - LLM özet/sor (var, hızlı) │
   └──────────┬──────────────────┘
              │ enqueue + job kaydı
              ▼
   ┌────────────────────────┐        ┌──────────────────────────────┐
   │  POSTGRES (kalıcılık)  │◄──────►│  REDIS (broker + sonuç sırtı) │
   │  - jobs (durum mak.)   │        │  - görev kuyruğu              │
   │  - tenants/config      │        │  - hızlı kilit (idempotency)  │
   │  - approvals, audit    │        └──────────────┬───────────────┘
   │  - processed_mail_keys │                       │ dequeue
   └────────────┬───────────┘                       ▼
                │ durum güncelle      ┌──────────────────────────────────┐
                └────────────────────►│  WORKER(lar) (Celery/RQ işçi)    │
                                      │  ringer süreç — uzun iş burada:  │
   ┌──────────────────────────┐      │   parse(mail)  [llm]             │
   │  SCHEDULER (beat/APSched)│──────►│   schedule(havuz) [det. motor]   │
   │  - IMAP poll (her N dk)  │enqueue│   nest(parti)  [DAKİKALAR — voxel]│
   │  - termin/SLA tarama     │       │   price(sonuç) [det. motor]      │
   │  - dead-letter süpürme   │       │   draft_reply(ctx) [llm]         │
   └──────────────────────────┘      └──────────────────────────────────┘
                                          │ her adım sonrası
                                          ▼ job durumu + audit DB'ye
                              (uzun nesting için ayrı "nest" kuyruğu/işçi —
                               kısa LLM/IO işleri hızlı kuyruğu tıkamasın)
```

**Sorumluluk ayrımı:**

| Bileşen | Sorumluluk | Yapmadığı |
|---|---|---|
| **nginx** | TLS, statik dosya, tek giriş, hız sınırlama | iş mantığı yok |
| **WEB (gunicorn+Flask)** | Yalnız hızlı istek: havuz CRUD, iş kuyruğa atma, durum okuma, onay kapısı | uzun nesting'i KOŞMAZ — kuyruğa atar |
| **WORKER** | §6.4 zincirinin her adımı (parse→schedule→nest→price→draft); motoru saf çağırır | HTTP dinlemez |
| **SCHEDULER** | Periyodik tetikler: IMAP poll, SLA tarama, dead-letter süpürme → kuyruğa iş bırakır | işi kendisi koşmaz |
| **REDIS** | Görev brokerı + kısa-ömürlü idempotency kilidi | kalıcı doğruluk kaynağı DEĞİL |
| **POSTGRES** | Tek doğruluk kaynağı: iş durum makinesi, tenant konfig, onaylar, audit, işlenmiş-mail anahtarları | — |

**Neden iki kuyruk (nest ayrı):** nesting dakikalar sürer; parser/draft/IMAP
saniyeler. Tek kuyrukta bir nesting işi 5 LLM işini bekletir. `nest` kuyruğu
ayrı işçi(ler)e, `default` kuyruğu hızlı işlere → SLA korunur.

---

## 2. Teknoloji seçimleri + on-prem gerekçesi

| Katman | Seçim | Alternatif (elenen) | On-prem / savunma gerekçesi |
|---|---|---|---|
| Web sunucu | **gunicorn + nginx** | Flask dev server | dev server tek-thread, prod değil; gunicorn çok-işçi + nginx TLS/hız-sınırı. Her ikisi offline kurulur |
| İş kuyruğu | **Celery** (öneri) | RQ | Celery: ayrı `nest`/`default` kuyruk, zamanlayıcı (beat), yeniden-deneme/backoff, dead-letter olgun — §3 ihtiyaçları yerleşik. RQ daha basit ama beat + çoklu kuyruk + retry politikası elle kurulur. **Karar gerekçesi §11.A** |
| Broker | **Redis** | RabbitMQ | Tek binary, hava-boşluklu kurulumu kolay, Celery+RQ ikisini de besler, kilit/sayaç da verir. RabbitMQ daha güçlü ama bu ölçekte (saatte düzineler) fazla ağır + ek operasyon yükü |
| Veritabanı | **PostgreSQL** | SQLite | İş durum makinesi + eşzamanlı işçi yazımı + tenant ayrımı + audit → çok-yazıcı dayanıklılık gerek. SQLite tek-yazıcı kilidi çoklu işçide darboğaz/kilit-hatası üretir. **Pilot tek-tenant'ta SQLite cazip görünür ama §9'daki "SaaS'a sıfır yeniden-yazım" kararı Postgres'i baştan seçtirir** |
| Konteynerleştirme | **Docker Compose** | bare-metal / k8s | Compose: tek dosyada tüm yığın (web/worker/scheduler/redis/postgres), `restart: always`, müşteri sunucusunda tek `up -d`. k8s bu ölçekte aşırı; bare-metal kurulum tekrarlanamaz. İmajlar offline tarball ile taşınır (hava-boşluğu) |
| Zamanlayıcı | **Celery beat** | cron / systemd timer / APScheduler | Celery seçilince beat doğal gelir (aynı görev tanımları, aynı retry/kalıcılık). cron host'a bağımlı + container'da kırılgan; APScheduler in-process (web süreciyle ölür). **RQ seçilirse → APScheduler ayrı `scheduler` konteynerinde** (§11.A) |
| Mail ingest | **IMAP poll (imaplib/imap-tools)** | webhook / Gmail API | Hava-boşluklu ortamda push/webhook YOK (dışarıdan bağlantı kabul edilemez). Müşteri kendi mail sunucusuna (Exchange/Zimbra on-prem) **giden** IMAP bağlantısı → poll. Gmail API bulut = A13 RED. **Erişim yöntemi A9/A-mail BLOKLU (§10)** |
| Süreç yönetimi | **Docker `restart: always`** (+ opsiyonel systemd üst-kabuk) | nohup / screen | Çökmede otomatik yeniden başlatma; host reboot'ta otomatik ayağa kalkma. systemd yalnız Docker daemon'ı garanti eder (ince üst-katman) |
| LLM sağlayıcı | **(PLAN_LLM)** OpenAICompat → Ollama/vLLM, on-prem GPU | Anthropic bulut | A13: savunma müşterisi → lokal. Çalışma-zamanı açısından LLM de bir işçi-içi çağrı; ayrı süreç değil (Ollama kendi servisi olarak compose'a eklenir). Bkz. PLAN_LLM §6.2 donanım |

**Neden n8n DEĞİL:** n8n self-host edilebilir (A13 uyumlu) ve görsel akış cazip
görünür; AMA (1) ağır Python nesting motoru n8n node'undan değil **işçi
sürecinden** çağrılmalı — n8n'i kuyruk+işçi önüne koymak iki orkestratör
katmanı (n8n + Celery) demek; (2) idempotency/dead-letter/durum-makinesi
mantığımız Postgres'te yaşıyor, n8n kendi kalıcılığını dayatır → çift doğruluk
kaynağı; (3) injection-hassas mail parse + insan-onay kapısı kod düzeyinde
sıkı kontrol ister (PLAN_LLM §5.3), n8n node grafiğinde gevşer. Sonuç:
**kuyruk + işçi deseni (Celery/Redis) Python-ağır + güvenlik-hassas bu iş için
n8n'den doğru.** (n8n'in iyi olduğu yer hafif SaaS-glue entegrasyonu — bizim
yük profili değil.)

---

## 3. Canlı-kalma + güvenilirlik

### 3.1 İş durum makinesi (Postgres `jobs` tablosu — doğruluk kaynağı)

```
RECEIVED → QUEUED → RUNNING → AWAITING_APPROVAL → APPROVED → COMPLETED
                       │                              │
                       ├── FAILED (retry<max) ──┐    └─ REJECTED
                       │                          ▼
                       └── DEAD_LETTER (retry tükendi → operatör)
```

Her geçiş audit'lenir (zaman, eski→yeni durum, işçi-id, hata). **Broker değil
DB tek doğruluk:** Redis'teki görev kaybolsa scheduler `QUEUED`/`RUNNING`'de
takılı (zaman aşımı geçmiş) işleri yeniden kuyruğa alır.

### 3.2 İdempotency (aynı mail iki kez işlenmez)

- Her mail için `idempotency_key = sha256(tenant_id + Message-ID + ek-hash)`.
- `processed_mail_keys` tablosunda UNIQUE kısıt; IMAP poll aynı maili tekrar
  görse (poll çakışması, sunucu read-flag gecikmesi) INSERT çakışır → atlanır.
- İşçi adımları idempotent: aynı `job_id` yeniden çalışırsa (retry/çökme
  sonrası) ara çıktı üzerine yazılır, yan etki tekrarlanmaz. **Mail gönderimi
  asla otomatik olmadığı için (insan-onay) en tehlikeli yan etki zaten kapalı.**

### 3.3 Hata / yeniden-deneme / dead-letter

- **Geçici hata** (LLM sağlayıcı timeout, IMAP bağlantı): üstel geri çekilmeli
  retry (max N, konfigde). PLAN_LLM zaten sağlayıcı-içi retry tanımlar; bu işçi
  düzeyi DIŞ retry.
- **Kalıcı hata** (parse edilemez ek, şema-dışı veri): retry ANLAMSIZ → doğrudan
  `DEAD_LETTER` + operatör paneline düşer (§5). PLAN_LLM `HumanFallback` ile
  uyumlu: parser fallback'i = onay kuyruğuna eksik-satır, sistem hatası =
  dead-letter.
- **Dead-letter kuyruğu:** kalıcı/retry-tükenmiş işler ayrı tabloda; operatör
  inceler, düzeltir, elle yeniden kuyruğa atar. Sessiz yutma YOK.

### 3.4 Kalıcılık (yeniden başlatmada kaybolmaz)

- Postgres + Redis named volume (Docker) → host reboot'ta veri durur.
- `jobs` DB'de olduğundan: işçi çökse `RUNNING` işi zaman aşımıyla yeniden
  alınır; web çökse kuyruk dolu kalır; scheduler çökse poll'u kaçırır ama
  bir sonraki poll'da kaldığı yerden (IMAP UID/tarih imleci DB'de).
- **Açık tasarım kararı:** at-least-once teslim + idempotent işçi =
  effectively-once. Exactly-once kuyruk garantisi (pahalı, kırılgan) gerekmez.

---

## 4. Mail ingest akışı (çalışma-zamanı tarafı — parse mantığı PLAN_LLM'de)

```
SCHEDULER (her N dk IMAP poll)
   → yeni mail UID listesi (DB imlecinden sonrası)
   → her mail için idempotency_key → processed_mail_keys INSERT (çakışırsa atla)
   → RECEIVED job kaydı + ekleri güvenli geçici dizine indir
   → enqueue("parse", job_id)        [default kuyruk, hızlı]
WORKER:
   parse  → schedule → nest → price → draft   (her adım ayrı görev,
            zincir job_id üzerinden; nest "nest" kuyruğuna)
   draft sonrası → AWAITING_APPROVAL (insan-onay kapısı — §6.4)
```

Bu plan **yalnız tetikleme/sıralama/kalıcılık** katmanını tanımlar; her adımın
İÇERİĞİ ilgili planda (parse→PLAN_LLM L2, schedule→PLAN_DEMO1 Faz 8,
nest→Faz 6, price→Faz 7, draft→PLAN_LLM L1). Ek formatı (Excel/STL/serbest
metin) **A9 BLOKLU** — geçici dizin + tip-tespiti sözleşmesi hazır, parse
gövdesi A9'a bağlı.

---

## 5. Gözlemlenebilirlik + operatör paneli

Mevcut `src/webapp/` GENİŞLETİLİR (yeni uygulama değil — B1 lokal web kararı):

| Yetenek | Nereye | Not |
|---|---|---|
| **Loglar** | yapılandırılmış JSON log (her süreç stdout → `docker logs` / dosya) + Postgres `audit` | ham müşteri verisi loga YAZILMAZ (PLAN_LLM §5.2 redaksiyon) |
| **Durum paneli** | yeni `/panel` rotası | iş listesi + durum + hangi adımda + bekleyen onaylar + dead-letter sayısı; canlı (poll/SSE) |
| **Onay kapısı** | yeni `/onay/<job_id>` rotaları | taslak + nesting özeti + fiyat dökümü yan yana; onayla/reddet/düzelt → durum geçişi (§6.4 insan-onaylı dönem) |
| **Sağlık ucu** | `/health` (web), worker/scheduler heartbeat → DB | "süreç canlı mı" + son poll zamanı; A13'te dış izleme yok, panelden bakılır |
| **Dead-letter ekranı** | `/panel` alt-bölüm | başarısız işler + hata + "yeniden dene" düğmesi |

Mevcut `/sonuc`, `/ozet`, `/sor` rotaları KORUNUR — yalnız `/run` davranışı
senkron'dan enqueue'a döner (§11.B çelişki bayrağı).

---

## 6. Güvenlik

- **Sır yönetimi:** mail parolası / LLM anahtarı / DB parolası → Docker secrets
  veya systemd `EnvironmentFile` (`chmod 600`); imaj ve repo TEMİZ. Audit/log
  redaksiyonu PLAN_LLM §5.2.
- **Ağ (on-prem):** tüm iç servisler (redis, postgres, ollama, worker) yalnız
  Docker iç ağında — host'tan dışarı PORT AÇMAZ. Sadece nginx (443) dışarı.
  Hava-boşluklu kurulumda dış bağlantı = yalnız müşterinin mail sunucusuna
  giden IMAP (kontrollü).
- **Yetki katmanları:** operatör paneli kimlik doğrulamalı (en az temel oturum;
  SaaS'ta tenant-bazlı RBAC). Onay kapısı = yetkili kullanıcı; otomatik gönderim
  yok (§0 madde 6). LLM injection savunması PLAN_LLM §5.3 (parser çıktısı yalnız
  şema-JSON, tool yok).
- **Çok-kiracı izolasyonu (SaaS):** her sorgu `tenant_id` filtreli; bir tenant
  diğerinin işini/konfigini GÖREMEZ — Faz B'de zorunlu, Faz A'da tek tenant.

---

## 7. Fazlama — minimum servis (tek müşteri) vs SaaS (çok-kiracı)

> Desen PLAN_DEMO1 Faz 7/8 ile aynı: mekanizmayı baştan doğru kur, kapsamı
> kademeli aç. Her faz çalışan servis bırakır.

### Faz S0 — Çalışma-zamanı iskeleti (mantık değişmeden)

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| S0.1 | Docker Compose yığını: web(gunicorn)+nginx+redis+postgres+worker+scheduler iskeleti; `restart: always`; named volume | `docker-compose.yml`, `Dockerfile`, `nginx.conf` | `docker compose up -d` tüm servisleri ayağa kaldırır; host reboot'ta otomatik döner |
| S0.2 | İş durum makinesi + `jobs`/`audit` Postgres şeması + migrasyon | `migrations/`, `src/runtime/jobs.py` | Durum geçişleri + audit testli; geçersiz geçiş RED |
| S0.3 | Kuyruk entegrasyonu (Celery+Redis): `default`/`nest` kuyrukları, retry+backoff politikası, dead-letter | `src/runtime/queue.py`, `src/runtime/tasks.py` | Sahte uzun görev: enqueue→worker koşar→durum DB'de; işçi öldür→iş kaybolmaz |
| S0.4 | `/run` enqueue'a dönüşür (senkron koşu kaldırılır) + `/panel` durum paneli | `src/webapp/app.py` (genişletme), `templates/panel.html` | Web isteği <200ms döner; iş arka planda koşar, panelde görünür |
| S0.5 | İdempotency altyapısı: `idempotency_key` + `processed_mail_keys` UNIQUE | `src/runtime/idempotency.py` | Aynı anahtar iki kez → bir kez işlenir (testli) |

Efor: **M** (3-4 gün). Bağımlılık: yok (mantık motorları mevcut). A9/A13 bekletmez.

### Faz S1 — Mail ingest + zincir orkestrasyonu (insan-onaylı)

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| S1.1 | IMAP poll scheduler (Celery beat): UID imleci DB'de, ek indirme, RECEIVED job | `src/runtime/mail_ingest.py` | Test IMAP (greenmail/yerel) → yeni mail job'a döner; imleç ilerler; iki poll = bir işlem |
| S1.2 | Zincir görevleri: parse→schedule→nest→price→draft, job_id üzerinden, `nest` ayrı kuyrukta | `src/runtime/tasks.py` | FakeProvider + sahte motor: uçtan uca job COMPLETED'a/AWAITING_APPROVAL'a ulaşır |
| S1.3 | Onay kapısı rotaları + ekranı (taslak+özet+fiyat yan yana, onayla/reddet/düzelt) | `src/webapp/` (onay), `templates/onay.html` | Onaysız mail GÖNDERİLMEZ; reddet→durum REJECTED; düzelt→yeniden kuyruk |
| S1.4 | Dead-letter ekranı + yeniden-dene | `/panel` genişletme | Kalıcı hatalı iş dead-letter'a düşer, operatör yeniden kuyruğa atabilir |

Efor: **M** (3-4 gün). Bağımlılık: S0 + PLAN_LLM L1/L2 + PLAN_DEMO1 Faz 6/7/8.
**A9 ek-parse'ı bloklar (S1.2 parse gövdesi), zincir iskeleti bloklamaz.**

### Faz S2 — Çok-kiracı (SaaS) ek katmanı

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| S2.1 | `tenants` + `tenant_config` tabloları; tüm sorgular tenant-filtreli; tek-tenant kurulum varsayılan tenant olur | `src/runtime/tenancy.py`, migrasyon | Faz A verisi geçişte bozulmaz; tenant-çapraz erişim testle ENGELLENİR |
| S2.2 | Konfig-veri taşıması: fiyat kuralı/öncelik/kapasite/mail-hesabı/LLM-eşlemesi → tenant kaydı (kodda sabit YOK) | konfig şeması + yükleyici | Yeni tenant = yalnız konfig kaydı; kod değişmez |
| S2.3 | Tenant-bazlı RBAC + panel izolasyonu | `src/webapp/` auth | Operatör yalnız kendi tenant'ını görür |
| S2.4 | Kaynak adaleti: tenant-başına kuyruk önceliği/kota (bir tenant nesting'i diğerini aç bırakmaz) | kuyruk routing | Yük testinde adil paylaşım |

Efor: **M-L**. Bağımlılık: S0+S1 oturduktan sonra; ikinci müşteri tetikler.

---

## 8. Bağımlılık sırası (özet)

```
S0 (çalışma-zamanı iskeleti: compose + durum makinesi + kuyruk + idempotency)
  └─ S1 (mail ingest + zincir orkestrasyonu + onay kapısı)
       │  [içerik bağımlılıkları: PLAN_LLM L1/L2, PLAN_DEMO1 Faz 6/7/8]
       └─ S2 (çok-kiracı SaaS katmanı)   [ikinci müşteri tetikler]
```

S0 tamamen bağımsız başlar (mevcut motorlar yeter). S1 içerik için diğer
planlara bağlı ama **iskeleti** (FakeProvider + sahte motor) onlarsız kurulur
ve testlenir. Toplam: **~L alt bandı** (S0+S1 ≈ 1.5-2 hafta; S2 müşteri-tetikli).

---

## 9. "Şimdi tasarıma-açık tut" — bugünkü ucuz kararlar (Faz 2'yi ucuzlatır)

Bugün (Demo-1 / mevcut kod) alınırsa Faz 2'de yeniden-yazım doğurmayacak küçük
kararlar — hiçbiri bugün servis kurmayı gerektirmez:

1. **Motoru saf çağrılabilir tut (zaten böyle):** nesting/fiyat/çizelge
   fonksiyonları Flask/kuyruk/DB import ETMESİN — işçiden çağrılabilsin.
   `scripts/demo_pipeline.run_pipeline()` bugün senkron çağrı; bu saf imza
   korunursa işçi onu olduğu gibi sarar.
2. **Pipeline sonucu serileştirilebilir (JSON-uyumlu) dön:** işçi sonucu DB'ye
   yazacak → `SolveResult`/pipeline çıktısı bugünden `to_dict()`'lenebilir
   olsun (kısmen var — `_build_grounded_context` zaten dict okuyor).
3. **Konfigi VERİ yap (kısmen yapıldı):** `orders_store._DEFAULT_PRICING_RULES`
   / `_DEFAULT_CAPACITY` bugün modül sabiti — bunları **dosya/dict parametresi**
   olarak geçirilebilir tut (kodda gömülü bırakma). Tek-tenant'ta varsayılan,
   SaaS'ta tenant kaydı olur → S2.2 sıfır yeniden-yazım.
4. **`orders.json` atomik yazımı zaten doğru:** `save_orders` tmp+rename
   (Windows `os.replace`) — Postgres'e geçişte aynı "atomik" sözleşme;
   havuz okuyan kod depolama-agnostik kalsın (load/save arkasında).
5. **`is_id` / iş kimliği kavramı bugünden tek alan:** `GroundedContext.is_id`
   var ("demo-pipeline") — Faz 2'de gerçek `job_id` olur; kavramı şimdi tek
   yerden türet, dağıtma.
6. **LLM zarif-düşüş deseni korunur:** `app.py` `_load_llm_components` LLM
   yoksa çökmüyor — servis modunda da "LLM down → iş AWAITING yerine
   dead-letter/insan" aynı dayanıklılık felsefesi.

---

## 10. BLOKLU — hocaya/dış girdiye bağlı bağımlılıklar

| Bekleyen | Soru | Bloke ettiği |
|---|---|---|
| **A9 — mail/ek formatı** | Sabit şablon mu serbest metin mi; Excel/CSV/STL/STEP ek tipleri | S1.2 ek-parse gövdesi (zincir iskeleti BLOKLU değil — geçici-dizin + tip-tespiti sözleşmesi hazır bekler) |
| **Mail erişim yöntemi** (A9 alt) | IMAP mı, müşteri Exchange/Zimbra mı, kimlik bilgisi/port/TLS, hava-boşluklu ortamda giden bağlantıya izin var mı | S1.1 IMAP konfig + bağlantı modeli; webhook olasılığı (yoksa kesin poll) |
| **Dağıtım hedefi** | Müşteri sunucu spec (OS, CPU/RAM, GPU var mı, Docker izni, root erişimi, internet tamamen kapalı mı kısmi mi) | S0.1 compose hedef profili; on-prem GPU (Ollama) yerleşimi; imaj taşıma yöntemi (registry mirror vs tarball) |
| **A15 — kapasite verileri** | Makine/konteyner sayısı, parti süresi, vardiya | scheduler SLA-tarama eşikleri (S1.1 tarama mantığı — içerik PLAN_DEMO1 Faz 8'de, tetik zamanlaması burada) |
| **A13 — veri güvenliği yazılı politika** | Bulut tamamen yasak mı, kısmi mi; log retention/redaksiyon politikası | §6 payload log default + LLM sağlayıcı (PLAN_LLM); mimari iki senaryoda da aynı, yalnız konfig satırı |
| **A14 — HPC runtime'da mı** | HPC sadece geliştirme mi, üretim runtime'ı mı | nest işçisinin yerleşimi: yerel işçi (varsayılan) vs HPC kuyruğuna gönderen işçi (gelecek opsiyon — kuyruk soyutlaması buna açık) |

---

## 11. Mevcut desenle / diğer planlarla çelişki + karar bayrakları

- **§11.A — Celery vs RQ KARARI ucu açık (bayrak):** plan Celery'yi ÖNERİR
  (beat + çoklu kuyruk + retry/dead-letter yerleşik). RQ daha sade ve bağımlılığı
  hafif; küçük ekip + tek-tenant pilotta RQ + APScheduler yeterli olabilir.
  **Karar S0.3'te, gerçek operasyon yüküne göre verilir** — kuyruk soyutlaması
  (`src/runtime/queue.py`) ikisini de arkasına alacak şekilde tasarlanır, tek
  noktadan değiştirilir. Sessiz seçim değil; bu satır o açık karardır.
- **§11.B — `/run` senkron→asenkron (açık sözleşme değişikliği):** mevcut
  `src/webapp/app.py` `/run` rotası `run_pipeline()`'ı SENKRON koşup `/sonuc`'a
  redirect ediyor (Demo-1 için doğru — tek kullanıcı, "koş→gör"). Faz 2'de bu
  enqueue'a döner; `/sonuc` "son tamamlanan iş"i, `/panel` "koşan/bekleyen"i
  gösterir. **Demo-1 davranışı KORUNUR** (tek-seferlik mod compose'suz çalışır);
  servis modu ek katman. Sessiz override değil — bayrak.
- **§11.C — SQLite cazibesi reddedildi (bayrak):** pilot tek-tenant'ta SQLite
  daha basit görünür; AMA çoklu-işçi yazımı + §9.3 "konfig=veri / SaaS sıfır
  yeniden-yazım" kararı Postgres'i baştan seçtirir. Bu bilinçli "şimdi biraz
  fazla, sonra sıfır göç" tercihi — gerekçesi §2 tablo + §9 madde 3.
- **§11.D — kapsam çakışması yok:** zincir adımlarının İÇERİĞİ (parse/schedule/
  nest/price/draft) bu planda TEKRARLANMADI; yalnız tetik/sıra/kalıcılık var.
  İçerik referansları: §6.4 (zincir mantığı), PLAN_LLM L1/L2 (draft/parse),
  PLAN_DEMO1 Faz 6/7/8 (nest/price/schedule). Bu plan onların runtime sarmalı.

---

## 12. Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Süreç çöker, koşan nesting işi kaybolur | İş durumu Redis'te değil Postgres'te (§3.1); `RUNNING` zaman-aşımı → scheduler yeniden kuyruğa alır; idempotent işçi tekrar koşar |
| Aynı mail iki kez işlenir → çift teklif | `idempotency_key` UNIQUE (§3.2); poll çakışması INSERT'te elenir |
| Uzun nesting hızlı LLM/IO işlerini bekletir | Ayrı `nest` kuyruğu + ayrı işçi (§1); SLA korunur |
| Hatalı iş sonsuz retry döngüsü (kaynak yer) | Kalıcı hata = retry yok → dead-letter (§3.3); max-retry + backoff geçici hatada |
| Bulut bağımlılığı sızar (A13 ihlali) | §0 madde 1 hava-boşluğu kuralı; tüm bileşen self-hosted; CI/review'da "dış endpoint" taraması |
| Mail/DB parolası imaja/repoya sızar | §6 secret yönetimi; imaj/audit redaksiyon; review kapısı |
| SQLite ile başlanır, SaaS'ta yeniden yazılır | §11.C: Postgres baştan; konfig=veri (§9.3) |
| Otomatik mail yanlış teklif gönderir | §0 madde 6: otomatik gönderim YOK; AWAITING_APPROVAL kapısı (§5 onay ekranı); güven oturana dek insan |
| n8n iki orkestratör katmanı + güvenlik gevşemesi | §2: kuyruk+işçi deseni seçildi, gerekçeli; n8n elendi |
| Hava-boşluklu ortamda imaj/güncelleme taşınamaz | §10 dağıtım hedefi BLOKLU: registry mirror / tarball stratejisi sunucu spec netleşince |
| Web süreci içi zamanlayıcı (APScheduler) süreçle ölür | Zamanlayıcı AYRI süreç/konteyner (Celery beat veya bağımsız scheduler); web'e gömülmez (§2) |
| Eşzamanlı işçi yazımı DB'de yarış | Postgres satır kilidi + durum-geçiş kısıtı (§3.1); geçersiz geçiş RED |

---

## 13. Açık sorular (netleşmesi gereken — karar bekler)

1. **Mail erişimi push mu poll mu?** Hava-boşluklu ortamda dışarıdan webhook
   muhtemelen imkânsız → IMAP poll varsayıldı. Müşteri mail altyapısı (A9 alt)
   teyit edilmeli; poll aralığı (SLA vs yük) konfig.
2. **HPC runtime'da kullanılacak mı (A14)?** Eğer "gece gönder sabah al" batch-
   servis modeli isteniyorsa nest işçisi HPC kuyruğuna gönderen bir varyant
   ister — kuyruk soyutlaması buna açık tutuldu ama karar gelmedi.
3. **Tek-tenant pilotta operatör kimlik doğrulaması ne kadar sıkı?** Hava-
   boşluklu LAN'da basit oturum mu, kurumsal SSO/LDAP entegrasyonu mu?
4. **Celery mi RQ mi (§11.A)?** Operasyon yükü + ekip aşinalığı netleşince;
   soyutlama arkasında tutuldu.
5. **Dağıtım: tek host mu yeter, yoksa web/worker ayrı makine mi?** Müşteri
   sunucu spec (A-dağıtım BLOKLU) gelince ölçek kararı.

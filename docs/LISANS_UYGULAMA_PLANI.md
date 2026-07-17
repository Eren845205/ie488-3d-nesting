# IP Koruma + Süreli Lisans Sistemi — Uygulama Planı

> **DURUM (Eren kararı 2026-07-17): ERTELENDİ — "ürün tamamlandıktan sonra
> yaparız."** Uygulama zamanı: ürün tamamlanınca ve HER HALÜKÂRDA ilk
> teslimattan ÖNCE (korumasız paket asla dışarı çıkmaz — kurulum sonrasına
> bırakılamaz). Aşağıdaki tasarım + keşif + test planı HAZIR; uygulama ~2-3
> gün (Faz 1 + build hattı). Lisans sistemi kodu ŞİMDİ YAZILMAYACAK.
>
> Tetik: teslim konuşması somutlaştığında bu doküman öne alınır ve Faz 1 +
> build hattı UYGULANIR. Keşif dosya:satır referansları 2026-07-17 anına
> aittir (drift olabilir; uygulamadan önce doğrulanır). Bağlantılı strateji:
> `APP_YOL_HARITASI.md` §7 (fiyat) + §9 (üç katman kararı).

## Context

Eren ürünü ilk müşteriye (hocanın firması) ve sonrasında başkalarına satmaya
hazırlanıyor. Endişe: on-prem teslim edilen yazılımın süresiz kullanılması,
kodun çıkarılması, üçüncü taraflara satılması. `APP_YOL_HARITASI.md` §9'un üç
katmanı (yasal EULA + süreli sunucu lisansı + derlenmiş dağıtım) bugüne dek
yalnız plandı; keşif doğruladı: repoda lisans/parmak-izi/paketleme kodu ve
asimetrik kripto YOK. Bu plan Faz 1'i (lisans çekirdeği + satıcı araçları +
EULA taslağı + testler) kodlar; Faz 2 (Cython build hattı) ilk gerçek teslim
öncesine bırakılır. İlkeler: dev/test dünyası BİT-ÖZDEŞ (2800+ test lisans
yolu çalıştırmaz), lisans OFFLINE doğrulanır, tek-sunucu/site lisansı.

Eren kararları (2026-07-17): süre dolunca default = **salt-okunur mod**;
(plan-dışı ama sıralı iş) K-54 commit+push edilecek ve k51e koşusu başlatılacak.

## Temel tasarım kararları

- **İmza: Ed25519** (`cryptography` — yeni bağımlılık). 32B pubkey build'e
  gömülür; padding/parametre riski yok. İmzalanan şey kanonik JSON
  (`sort_keys, separators=(",",":")`). Lisans dosyası:
  `{"format_version":1, "payload":{...}, "signature":"<b64>"}`.
- **Payload:** `license_id, customer_id, customer_name, machine_hashes{5},
  issued_at, expires_at, warn_days=14, grace_days=14,
  expiry_mode="readonly"|"lock" (DEFAULT readonly — Eren), features[], build_id`.
- **Makine parmak izi (5 bileşen, ham değil SHA-256 hash; eşleşme 3-of-5):**
  MachineGuid (winreg, ana çapa) · C: birim seri (ctypes GetVolumeInformationW)
  · BIOS seri (PowerShell Get-CimInstance, timeout 10s, placeholder filtresi)
  · CPU ProcessorId (aynı yöntem) · birincil MAC (uuid.getnode, sanal-MAC
  filtresi). NIC+disk değişse bile kilitlenmez; klonlamada GUID+BIOS+CPU taşınamaz.
- **Saat-geri-alma:** `data/license_state.json` {last_seen_utc, hmac} +
  ikincil HKCU registry kopyası; `now < last_seen - 24h` → CLOCK_TAMPER.
  Şerh: state silinirse rollback koruması sıfırlanır ama süre UZAMAZ
  (expires_at duvar saati her zaman kontrol).
- **Durum makinesi:** DISABLED → VALID → WARNING(≤14g, sarı bant) →
  GRACE(+14g, kırmızı bant, tam işlev) → EXPIRED(readonly: GET serbest,
  yazma-metotları 403 / lock: her şey /lisans'a) · hata: MISSING, INVALID,
  MACHINE_MISMATCH, CLOCK_TAMPER (lock gibi; /lisans+/health+/giris muaf —
  ilk kurulumda lisans yüklenebilsin diye sunucu MISSING'de de açılır).
- **Enforcement aktivasyonu:** `src/licensing/build_info.py` repo'da
  `LICENSE_REQUIRED=False` (dev varsayılanı, bit-özdeşlik). Müşteri build'i
  bu dosyayı True + pubkey + customer_id + build_id ile yeniden üretir.
  Çift kapı: kapı yalnız `LICENSE_REQUIRED` iken değerlendirilir.

## Yeni dosyalar

`src/licensing/` (7 dosya):
- `build_info.py` — dev varsayılanları (yukarıda).
- `crypto.py` — `canonical_bytes / sign_payload / verify_payload /
  generate_keypair` (cryptography SADECE burada, lazy import — dev'de
  kurulu değilse LICENSE_REQUIRED=False iken hiç import edilmez).
- `machine_id.py` — toplayıcılar ayrı fonksiyonlar (monkeypatch için):
  `collect_components / component_hashes / machine_code / match_score`,
  `MATCH_THRESHOLD=3`; modül-içi cache (PS ~1-2s, before_request'te ASLA).
- `license_file.py` — `LicensePayload` dataclass + jsonschema doğrulama;
  `load_license / save_license` (atomik tmp+replace). Konum
  `configs/license.json`, `LICENSE_PATH` env override.
- `clock_guard.py` — `ClockGuard(state_path, secret, now=time.time)`;
  HMAC anahtarı = sha256(machine_guid_raw + PUBLIC_KEY_B64).
- `guard.py` — `LicenseState` enum + `LicenseStatus` (blocks_request(method)
  matrisi tek yerde) + `LicenseGuard(build_info/license_path/state_path/now
  enjekte edilebilir; status() TTL-cache 600s + threading.Lock;
  evaluate() taze doğrulama; install_license(raw))`.
- `revalidator.py` — MailPoller deseni (`src/runtime/mail_poller.py:346,
  469-497` birebir kalıp): daemon thread, 5dk'da bir evaluate + saat heartbeat.

`vendor/` (müşteri paketine ASLA girmez):
- `keygen.py` — müşteri-başına anahtar; private → `~/.nesting_vendor/keys/`
  (üzerine yazma `--force` ister), pubkey stdout.
- `sign_license.py` — machine-code blob → payload → imza → license.json +
  `~/.nesting_vendor/registry.jsonl` müşteri kaydı.
- `verify_license.py` — satıcı-tarafı offline doğrulama yardımcısı.

`docs/EULA_TASLAK.md` — Türkçe taslak; başına "TASLAK — yürürlük öncesi
avukat incelemesi zorunludur" şerhi. Maddeler: taraflar/tanımlar · lisans
kapsamı (tek sunucu, süreli, devredilemez) · fikri mülkiyet (kod satıcıda) ·
yasaklar (tersine müh., yeniden satış) · süre/yenileme/fesih · teknik koruma
önlemlerini aşma=ihlal · sorumluluk sınırı (tavan=ödenen bedel) · veri
sahipliği (müşteri verisi müşterinin) · gizlilik · TR hukuku.

`templates/lisans.html` — makine kodu göster + lisans dosyası yükleme formu
+ durum kartı.

## Değişecek dosyalar

- `src/webapp/app.py` (5 nokta):
  1. `create_app(..., license_guard_override=None)` (`:422`; llm_provider_override
     deseni). Gövdede guard kur, `app.config["LICENSE_GUARD"/"LICENSE_REQUIRED"]`
     (`REQUIRED = build_info.LICENSE_REQUIRED or override is not None`).
     Startup'ta REQUIRED+not testing ise bir kez evaluate + log.
  2. `_security_guard` (`:556-578`): CSRF-token satırından sonra, TESTING
     erken-dönüşünden ÖNCE lisans bloğu (`LICENSE_REQUIRED` ise): exempt seti
     `{lisans, lisans_yukle, health, static, giris, cikis}` dışında
     `blocks_request` → GET redirect /lisans, yazma 403 JSON. (Dev'de
     REQUIRED=False → blok hiç girmez = bit-özdeş; override'lı testler
     TESTING'de de çalışır.)
  3. Revalidator başlatma: poller gate'inin (`:1190-1192`) yanına aynı kalıp
     (`LICENSE_REQUIRED and not TESTING`).
  4. `/health` (`:1230-1261`): `out["license"]={required,state,customer,
     expires_at,days_left}` (dev'de `{required:False}`) — önce
     `tests/test_webapp_health.py` kontratı okunur, gerekirse güncellenir.
  5. `/lisans` GET + `/lisans/yukle` POST rotaları (`@_limit("10 per minute")`,
     CSRF normal) + `_inject_license` context_processor (banner).
- `src/webapp/templates/base.html` — header sonrası uyarı bandı
  (`{% if license_banner %}`) + `static/style.css` 2 sınıf (sarı/kırmızı).
- `requirements.txt` — `flask` (eksikti!), `cryptography>=42`, `waitress` ekle.
- `.gitignore` — `vendor/*.json`.

## Testler (5 yeni dosya)

- `test_licensing_crypto.py` — imzala/doğrula, 1-bayt oynat→red, yanlış
  pubkey→red, kanonik JSON determinizmi.
- `test_licensing_machine.py` — toplayıcı monkeypatch'leri, placeholder BIOS
  filtresi, machine_code round-trip, 3-of-5 sınırları (3 geç / 2 kal),
  PS timeout→bileşen düşer.
- `test_licensing_guard.py` — `now` enjeksiyonuyla VALID→WARNING→GRACE→EXPIRED;
  readonly vs lock `blocks_request` matrisi; MISSING/INVALID/MACHINE_MISMATCH;
  cache TTL + iki-thread status.
- `test_licensing_clock.py` — ileri akış, 24h+ geri→TAMPER, HMAC bozuk→TAMPER,
  dosya yok→ilk-çalıştırma, atomik yazım.
- `test_webapp_license_gate.py` — (a) REGRESYON KİLİDİ: repo build_info
  `LICENSE_REQUIRED is False` + testing app'te guard.status HİÇ çağrılmıyor
  (MagicMock ile); (b) override'lı: EXPIRED GET→redirect, POST→403;
  GRACE→200+banner; exempt rotalar kilitliyken erişilir; /lisans/yukle
  geçerli/bozuk; /health lisans alanları.

## Faz 2 (BU PLANDA KODLANMAZ — teslim öncesi ayrı iş)

`vendor/build_customer.py`: Cython → .pyd (nesting3d + pricing + licensing;
Nuitka-standalone scipy/trimesh riskleri yüzünden reddedildi), kalan src
bytecode-only, templates/static düz; müşteri watermark (`_wm.py` HMAC);
Python 3.13 embeddable + site-packages gömülü zip; waitress `serve.py` +
`run_server.bat`; requirements-lock; smoke (/health MISSING). MSVC yalnız
build makinesinde. Motor-içi ikincil lisans kontrolü (nfv_solve girişi).

## Doğrulama

1. Yeni lisans testleri: `python -m pytest tests/test_licensing_*.py
   tests/test_webapp_license_gate.py -q` → yeşil.
2. Bit-özdeşlik: `python -m pytest tests/test_webapp*.py -q` (357 webapp
   testi) → mevcut sayılarla birebir yeşil; ardından TAM SUITE (A9).
3. Uçtan uca canlı prova (dev makinede, geçici): `vendor/keygen.py` +
   makine kodu + `sign_license.py` ile 2 dakikalık gerçek lisans üret;
   `license_guard_override` YERİNE gerçek build_info'yu geçici monkeypatch
   eden bir script ile REQUIRED=True app başlat → banner/kilit/yükleme
   akışını tarayıcıda doğrula (ekran görüntüsü), sonra temizle.
4. `cryptography` kurulumsuz dev ortam simülasyonu: REQUIRED=False iken
   app import + testler cryptography'siz de yeşil (lazy import kanıtı).

## Plan-sonrası sıralı işler (plan modundan çıkınca, kodlamadan önce)

1. K-54 commit + push (Eren onayladı): cap + testler + YONTEM/memory kayıtları.
2. k51e tam 4-set baseline koşusu detach başlat (Eren onayladı; ~3h, kodlamayla paralel).
3. Sonra bu planın Faz 1 implementasyonu.
